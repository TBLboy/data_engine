# MinIO Data Lake — Control Plane Schema Design

> Based on Node F baseline. Status: draft v0.2, ready to guide implementation before migration.

## 1. Design Principles

- **MinIO is opaque to business logic.** PostgreSQL owns all business queries, state transitions, QC dispatch, and audit.
- **The mapping layer is thin.** New tables bridge "what's in the bucket" to "what's in the QC system", nothing more.
- **Existing `episodes`/`batches`/`ingest_jobs`/`qc_tasks` are kept.** The new tables answer "what exists in MinIO"; the old tables continue to answer "what can be QCed / what was QCed".
- **Prefix is identity, not the object key.** An episode is identified by its prefix (e.g., `yaocao/K1/.../episode_000099/`); individual objects under that prefix are mapped one-to-many.
- **Scanner semantics are monotonic.** V1 assumes "multiple small writes" are common, so object discovery and episode readiness should move forward by UPSERT rather than depend on synchronized one-shot uploads.

## 2. Entity Diagram (Logical)

```
scan_jobs 1──N discovered_prefixes
scan_jobs 1──N lists
lists     1──N episode_inventory
episode_inventory 1──N episode_objects
lists     0..N──1 task_types (via `final_task_type_id`)
```

Existing tables sit downstream:
```
ingest_jobs (source_path → list.list_prefix)
batches     (can be partitioned per list or merged)
episodes    (can reference episode_inventory via external_episode_id)
```

## 3. Table Definitions

### 3.1 `scan_jobs`

Each row = one invocation of the bucket scanner.

| Column | Type | Purpose |
|--------|------|---------|
| `id` | `VARCHAR(64) PK` | e.g. `scan_20260623_001` |
| `bucket` | `VARCHAR(128) NOT NULL` | scanned bucket name |
| `scope` | `VARCHAR(32) NOT NULL DEFAULT 'full'` | `full` (default), can later add `prefix` for targeted scans |
| `status` | `VARCHAR(32) NOT NULL DEFAULT 'running'` | `running` → `scanning` → `classifying` → `episode_inventory` → `done` / `failed` |
| `total_prefixes` | `INTEGER DEFAULT 0` | count of prefixes discovered (all depths) |
| `confirmed_lists` | `INTEGER DEFAULT 0` | prefixes that passed structural check |
| `total_episodes` | `INTEGER DEFAULT 0` | unique episode prefixes found |
| `new_episodes` | `INTEGER DEFAULT 0` | episodes NOT seen in any prior scan |
| `triggered_by` | `VARCHAR(64) NOT NULL` | user account username that initiated the scan |
| `error_detail` | `VARCHAR(500) DEFAULT ''` | last error if failed |
| `started_at` | `DATETIME NOT NULL` | |
| `finished_at` | `DATETIME` | nullable |

Index: `(bucket, started_at)` for listing recent scans per bucket.

### 3.2 `discovered_prefixes`

Raw output of recursive `list_objects_v2(Delimiter='/')` walk. Stored so the scanner can diff across scans without re-scanning.

| Column | Type | Purpose |
|--------|------|---------|
| `id` | `INTEGER PK AUTOINCREMENT` | internal |
| `scan_job_id` | `VARCHAR(64) FK → scan_jobs.id NOT NULL` | which scan discovered this |
| `bucket` | `VARCHAR(128) NOT NULL` | |
| `prefix` | `VARCHAR(1024) NOT NULL` | the prefix as returned by S3 (trailing `/`) |
| `depth` | `INTEGER NOT NULL` | slash-separator count from bucket root |
| `has_raw_child` | `BOOLEAN DEFAULT FALSE` | `raw/` exists as direct child prefix |
| `has_processed_child` | `BOOLEAN DEFAULT FALSE` | `processed/` exists as direct child |
| `has_episode_grandchild` | `BOOLEAN DEFAULT FALSE` | at least one `episode_XXXXXX/` under raw or processed |
| `is_list_candidate` | `BOOLEAN DEFAULT FALSE` | passes structural rule |
| `first_seen_scan_id` | `VARCHAR(64) FK → scan_jobs.id` | when this prefix was first observed |
| `last_seen_scan_id` | `VARCHAR(64) FK → scan_jobs.id NOT NULL` | latest scan that re-confirmed this prefix |

Index: `UNIQUE (bucket, prefix)` — one row per prefix ever discovered. The scanner UPDATEs `last_seen_scan_id` and structural flags on re-scan; it never DELETEs.

### 3.3 `lists`

Confirmed structural match — `bucket + list_prefix` that actually contains `raw/` and/or `processed/` with `episode_XXXXXX/` entries.

| Column | Type | Purpose |
|--------|------|---------|
| `id` | `VARCHAR(64) PK` | e.g. `list_yaocao_K1_double_linkerhand_...` |
| `bucket` | `VARCHAR(128) NOT NULL` | |
| `list_prefix` | `VARCHAR(1024) NOT NULL` | without bucket, without trailing `/` on the list name itself |
| `confirmed_scan_id` | `VARCHAR(64) FK → scan_jobs.id NOT NULL` | the scan that first confirmed this prefix as a list |
| `last_active_scan_id` | `VARCHAR(64) FK → scan_jobs.id NOT NULL` | most recent scan where this list still had structure |
| `has_raw` | `BOOLEAN NOT NULL DEFAULT FALSE` | |
| `has_processed` | `BOOLEAN NOT NULL DEFAULT FALSE` | |
| `total_raw_episodes` | `INTEGER DEFAULT 0` | episode count under this list's `raw/` |
| `total_processed_episodes` | `INTEGER DEFAULT 0` | episode count under `processed/` |
| `candidate_task_type` | `VARCHAR(128) DEFAULT ''` | keyword-inferred from prefix |
| `candidate_source` | `VARCHAR(32) DEFAULT ''` | `prefix_keyword` / `manual` / `metadata` |
| `final_task_type_id` | `VARCHAR(64) FK → task_types.id` | NULL until manually confirmed or rule-matched |
| `is_active` | `BOOLEAN DEFAULT TRUE` | set FALSE if list structure disappears in a scan |
| `created_at` | `DATETIME NOT NULL` | |
| `updated_at` | `DATETIME NOT NULL` | |

Index: `UNIQUE (bucket, list_prefix)`. Index: `(final_task_type_id)`. Index: `(is_active)`.

Design note: Parent/child conflict (where a prefix AND its sub-prefix both satisfy the structural rule) is resolved by the scanner — only the deepest matching prefix becomes a `list`. See §4.1.4.

### 3.4 `episode_inventory`

Every episode prefix discovered across all scans, both raw-side and processed-side.

| Column | Type | Purpose |
|--------|------|---------|
| `id` | `VARCHAR(128) PK` | composite: `{list_id}/episode_XXXXXX` |
| `list_id` | `VARCHAR(64) FK → lists.id NOT NULL` | parent list |
| `episode_name` | `VARCHAR(64) NOT NULL` | canonical `episode_XXXXXX` segment |
| `episode_prefix` | `VARCHAR(1024) NOT NULL` | canonical list-level episode identity, stored as `bucket/list_prefix/episode_xxxxxx` |
| `raw_prefix` | `VARCHAR(1024) DEFAULT ''` | concrete raw-side prefix if present |
| `processed_prefix` | `VARCHAR(1024) DEFAULT ''` | concrete processed-side prefix if present |
| `state` | `VARCHAR(32) NOT NULL DEFAULT 'ingestable'` | `ingestable` → `processable` → `qc_ready` |
| `raw_exists` | `BOOLEAN NOT NULL DEFAULT FALSE` | `raw/episode_XXXXXX/` exists |
| `processed_exists` | `BOOLEAN NOT NULL DEFAULT FALSE` | `processed/episode_XXXXXX/` exists |
| `manifest_hash` | `VARCHAR(64) DEFAULT ''` | SHA-256 of `manifest.json` content |
| `metadata_hash` | `VARCHAR(64) DEFAULT ''` | SHA-256 of `metadata.json` |
| `episode_id_from_manifest` | `VARCHAR(128) DEFAULT ''` | the `episode_id` value read from `manifest.json` |
| `duration_sec` | `FLOAT DEFAULT 0` | from manifest |
| `frame_count` | `INTEGER DEFAULT 0` | from manifest |
| `state_changed_at` | `DATETIME` | when the last state transition occurred |
| `first_seen_scan_id` | `VARCHAR(64) FK → scan_jobs.id NOT NULL` | |
| `last_seen_scan_id` | `VARCHAR(64) FK → scan_jobs.id NOT NULL` | |
| `ingested_episode_id` | `VARCHAR(64)` | FK to `episodes.id` once this inventory entry is promoted into the QC system |

Index: `UNIQUE (list_id, episode_name)`. Index: `(state)` for querying `qc_ready`. Index: `(ingested_episode_id)` for reverse lookup.

### 3.5 `episode_objects`

One-to-many: every S3 object under an episode prefix.

| Column | Type | Purpose |
|--------|------|---------|
| `id` | `INTEGER PK AUTOINCREMENT` | internal |
| `episode_inventory_id` | `VARCHAR(128) FK → episode_inventory.id NOT NULL` | |
| `object_key` | `VARCHAR(1024) NOT NULL` | full S3 key including bucket-relative path |
| `object_scope` | `VARCHAR(16) NOT NULL` | `raw` / `processed` |
| `object_role` | `VARCHAR(64) NOT NULL` | normalized role for readiness, rendering, and audit |
| `size_bytes` | `BIGINT DEFAULT 0` | |
| `content_hash` | `VARCHAR(64) DEFAULT ''` | SHA-256 of object content |
| `last_modified` | `DATETIME` | from S3 `LastModified` |
| `last_seen_scan_id` | `VARCHAR(64) FK → scan_jobs.id NOT NULL` | |

Index: `UNIQUE (episode_inventory_id, object_key)`. Index: `(episode_inventory_id, object_role)` for checklist queries. Index: `(content_hash)` for dedup.

### 3.6 `classification_rules`

How `candidate_task_type` keyword matches a `final_task_type`.

| Column | Type | Purpose |
|--------|------|---------|
| `id` | `INTEGER PK AUTOINCREMENT` | |
| `pattern` | `VARCHAR(256) NOT NULL` | case-insensitive substring match against normalized list_prefix |
| `target_task_type_id` | `VARCHAR(64) FK → task_types.id NOT NULL` | |
| `candidate_label` | `VARCHAR(128) NOT NULL DEFAULT ''` | business-facing candidate label written into `lists.candidate_task_type` |
| `match_scope` | `VARCHAR(32) NOT NULL DEFAULT 'basename'` | `basename` / `full_prefix` |
| `priority` | `INTEGER DEFAULT 0` | higher = tried first |
| `is_authoritative` | `BOOLEAN DEFAULT TRUE` | if TRUE, match can write `final_task_type_id` automatically in V1 |
| `is_active` | `BOOLEAN DEFAULT TRUE` | |
| `created_by` | `VARCHAR(64) NOT NULL` | username |
| `created_at` | `DATETIME NOT NULL` | |

Index: `(is_active, priority DESC)`.

If no rule matches, `lists.final_task_type_id` stays NULL and the list appears in the unclassified group for manual assignment.

## 4. Scanner Specification

### 4.1 Phase A: Recursive Prefix Discovery

#### 4.1.1 Traversal contract

The scanner must treat the bucket as an unbounded prefix tree and never assume lists live at depth 1 or depth 2.

Canonical traversal procedure:

1. Create `scan_jobs` row, set `status='scanning'`.
2. Initialize a FIFO queue with the empty root prefix `''`.
3. Pop one prefix at a time and call `list_objects_v2` with:
   - `Bucket=bucket`
   - `Prefix=<current_prefix>`
   - `Delimiter='/'`
   - `ContinuationToken` loop until `IsTruncated=False`
4. For every returned `CommonPrefixes[].Prefix`, treat it as a newly discovered child prefix.
5. UPSERT that child into `discovered_prefixes`.
6. Push every child prefix back into the queue for deeper traversal.
7. Do not depend on `Contents[]` to discover deeper structure; recursion is driven by `CommonPrefixes`.
8. Continue until the queue is empty.

Implication: `yaocao/<list>/...` and `yaocao/K1/<list>/...` are discovered by the same mechanism, with no branch-specific logic.

#### 4.1.2 Prefix bookkeeping

For each discovered prefix `p`:

- `depth` = slash count of `p` after stripping trailing `/`.
- `first_seen_scan_id` is set only on first insert.
- `last_seen_scan_id` is updated on every scan that rediscovers `p`.
- `has_raw_child` becomes `TRUE` if `p + 'raw/'` exists as a direct child.
- `has_processed_child` becomes `TRUE` if `p + 'processed/'` exists as a direct child.
- `has_episode_grandchild` becomes `TRUE` if either `p + 'raw/'` or `p + 'processed/'` has direct children matching `episode_\d+/`.

#### 4.1.3 Structural list recognition

A prefix qualifies as a list candidate when all of the following hold:

1. It has at least one direct structural child: `has_raw_child=TRUE` or `has_processed_child=TRUE`.
2. Under at least one structural child, there exists at least one direct `episode_XXXXXX/` grandchild.
3. The `episode_XXXXXX/` segment is interpreted as the canonical episode unit; objects deeper than that belong to the episode, not to list detection.

V1 deliberately does **not** require raw and processed to both exist. Therefore:
- raw-only list: valid candidate
- processed-only list: valid candidate
- raw+processed list: valid candidate

A prefix that contains media files directly under itself without `raw/` or `processed/` does **not** qualify as a list in V1.

#### 4.1.4 Parent/child dedup: deepest-match

The scanner must resolve overlapping candidates after the full recursive walk, not during prefix discovery.

Dedup procedure:

1. Collect all prefixes with `is_list_candidate=TRUE` before dedup.
2. Sort candidates by descending depth.
3. Iterate from deepest to shallowest.
4. Keep candidate `C` as a real list unless an even deeper kept candidate already consumes the same structural branch.
5. If parent `P` and child `C` are both candidates:
   - keep `C`
   - drop `P` for the overlapping branch
6. Exception: if `P` also owns direct `raw/` or `processed/` episode children that are **not** nested under `C`, then `P` remains a list for those parent-owned episodes.

This rule prevents one object tree from being registered twice while preserving the user-confirmed case where a parent has its own episodes and also contains child lists.

#### 4.1.5 List materialization

After dedup, every kept candidate is UPSERTed into `lists`:

- `confirmed_scan_id` is set only on first confirmation.
- `last_active_scan_id` is updated on every scan that still confirms the structure.
- `has_raw` / `has_processed` reflect whether the kept list currently has those direct child trees.
- `total_raw_episodes` / `total_processed_episodes` are counts of unique episode names under each side.
- A previously confirmed list not seen in the current scan is not deleted; it becomes stale and may later be marked `is_active=FALSE` by post-scan reconciliation.

### 4.2 Phase B: Classification

#### 4.2.1 Normalization contract

Before any rule matching, the scanner builds a normalized string view of the list:

1. `normalized_full_prefix`: lowercase `list_prefix`
2. `normalized_basename`: last path segment of `list_prefix`, lowercased
3. separators `-`, `_`, `/`, and duplicated spaces are all treated as token boundaries
4. timestamp-like suffixes such as `2026-06-05_10-50-45` are ignored for classification semantics
5. device/location markers such as `k1`, `k2`, `left`, `right`, `double_linkerhand` are retained as metadata context but are not by themselves task labels

This means V1 classification is driven by business-action tokens, not by machine/location/time fragments.

#### 4.2.2 Matching procedure

1. Set `scan_jobs.status='classifying'`.
2. For each active list confirmed in the current scan:
   - build `normalized_full_prefix` and `normalized_basename`
   - load active `classification_rules` ordered by `priority DESC`, then `pattern` length DESC
3. Evaluate each rule against its declared scope:
   - `match_scope='basename'`: match only against `normalized_basename`
   - `match_scope='full_prefix'`: match against the whole normalized prefix
4. First matching rule wins.
5. On match:
   - set `lists.candidate_task_type = classification_rules.candidate_label`
   - set `lists.candidate_source = 'prefix_keyword'`
   - if `is_authoritative=TRUE`, also set `lists.final_task_type_id = target_task_type_id`
   - if `is_authoritative=FALSE`, keep `final_task_type_id=NULL` and require manual confirmation
6. If no rule matches:
   - set `candidate_task_type=''`
   - leave `final_task_type_id=NULL`
   - keep the list available for manual assignment

V1 does not combine multiple matching rules. Precedence is encoded entirely by `priority` and pattern specificity.

#### 4.2.3 Seed rule design principles

The initial seed set must follow these principles:

- **Prefer action/object tokens, not device tokens.** `huanggua`, `tudoutiao`, `fanqie`, `qie`, `dao`, `grasp`, `place` are candidate business cues; `k1`, `double_linkerhand`, and timestamps are not.
- **Prefer basename matching first.** Most semantic signals are expected in the final list folder name; parent prefixes like `K1/` should not affect business classification.
- **Use authoritative auto-match only for high-confidence one-to-one mappings.** If one token clearly maps to one task type in current operations, V1 may auto-fill `final_task_type_id`.
- **Leave ambiguous compound names as non-authoritative or unmatched.** If a basename combines multiple produce names or verbs in a way that may map to different business tasks, the rule should only produce `candidate_task_type` or no match at all.
- **Manual confirmation is part of the normal path, not an exception.** Seed rules are meant to reduce queue size, not eliminate review.

#### 4.2.4 Seed rule categories

The initial seed rules are divided into three categories.

**Category A: high-confidence authoritative rules**

Use when one normalized token or fixed token pair maps stably to one task type already present in `task_types`.

Examples of intended shape:
- `huanggua` → 黄瓜相关任务
- `tudoutiao` → 土豆条相关任务
- `dao_huanggua` or `qie_huanggua` → 黄瓜切配类任务

Behavior:
- write `candidate_task_type`
- auto-fill `final_task_type_id`
- list enters classified state without manual intervention

**Category B: suggest-only compound rules**

Use when the prefix clearly contains business material but may still need operator judgment.

Examples of intended shape:
- `qingdaofanqieluobo`
- `fanqie_luobo`
- `mixed_vegetable`

Behavior:
- write `candidate_task_type`
- set `candidate_source='prefix_keyword'`
- keep `final_task_type_id=NULL`
- list remains in manual classification queue

**Category C: no-match fallback**

Use when the prefix only provides device, site, or timestamp information, or contains unknown shorthand.

Behavior:
- `candidate_task_type=''`
- `final_task_type_id=NULL`
- list is shown as unclassified

#### 4.2.5 Initial seed table shape

The business-logic seed document should be expressed as rows with these columns:

| Pattern | Scope | Candidate label | Target task_type | Priority | Authoritative | Intended use |
|---|---|---|---|---:|---|---|
| `huanggua` | `basename` | `huanggua` | `task_type:huanggua` | 100 | yes | 单一食材高置信任务 |
| `tudoutiao` | `basename` | `tudoutiao` | `task_type:tudoutiao` | 100 | yes | 单一食材高置信任务 |
| `fanqie` | `basename` | `fanqie` | `task_type:fanqie` | 80 | no | 仅给候选，避免与复合任务抢判 |
| `luobo` | `basename` | `luobo` | `task_type:luobo` | 80 | no | 仅给候选，避免与复合任务抢判 |
| `qingdaofanqieluobo` | `basename` | `qingdaofanqieluobo` | none | 120 | no | 复合任务，需人工确认 |

The exact `task_type` IDs remain bound to the real `task_types` table at migration time, but the business rule format is fixed now.

#### 4.2.6 Conflict handling

V1 conflict policy:

1. Higher `priority` wins.
2. If priorities tie, longer `pattern` wins.
3. If both still tie, `basename` scope wins over `full_prefix`.
4. If still tied, the lower `classification_rules.id` wins deterministically.

This makes compound exact phrases able to outrank shorter ingredient tokens.

#### 4.2.8 Task catalog and list binding semantics

V1 must distinguish three concepts that are easy to conflate:

1. `task_types` = canonical business task catalog, managed by operators/admins
2. `lists` = scanner-discovered MinIO collection/upload units
3. `qc_tasks` = downstream review work items dispatched from ingested `episodes`

They are related but not interchangeable.

Cardinality rules:

- one `task_type` may be referenced by many `lists`
- one `list` may have zero or one `final_task_type_id`
- one `list` must not be bound to multiple `task_types` in V1
- one `qc_task` is created from downstream episode dispatch, never directly from a MinIO list row

Operational meaning:

- creating a task means creating or enabling a row in `task_types`; it does not create a MinIO list
- scanning MinIO may discover new `lists`; it does not by itself create new canonical task definitions
- assigning a list means setting `lists.final_task_type_id`
- clearing an assignment means setting `lists.final_task_type_id=NULL` while preserving `candidate_task_type` for audit and re-review

#### 4.2.9 Task creation, retirement and manual association rules

V1 task/list operations follow these rules:

1. **Create task type**: allowed. Admin creates a new canonical `task_type` row when business needs a new task label, even if no current list is bound yet.
2. **Manual list association**: allowed. Operator may set `lists.final_task_type_id` explicitly for any classified or unclassified list.
3. **Manual unbind**: allowed. Operator may clear `final_task_type_id` and return the list to the manual classification queue.
4. **List delete**: not allowed as a normal business operation. `lists` are scanner-owned inventory rows and are never manually hard-deleted in V1.
5. **Task type delete**: physical delete is not the default operation. If a task type has ever been referenced by any `lists`, `episodes`, `batches` or QC history, it must be treated as retired/disabled rather than hard-deleted.
6. **Historical stability**: changing or clearing `lists.final_task_type_id` only affects future ingest/dispatch. Already ingested `episodes`, historical `batches`, and existing QC records keep their original task assignment.
7. **Reference safety**: a task type may be physically deleted only when it has never been referenced by any list or downstream business row.

This means the product-level "delete task" action should be implemented as **retire/disable for future use**, not as destructive row removal.

#### 4.2.10 Classification review and checking workflow

V1 must support an explicit review loop for task/list associations:

1. **Check unclassified lists**: query all active lists with `final_task_type_id IS NULL`.
2. **Check suggest-only lists**: query lists where `candidate_task_type != ''` but `final_task_type_id IS NULL`.
3. **Check bound lists by task**: query active lists grouped by `final_task_type_id` to verify that one business task currently covers which MinIO lists.
4. **Check stale bindings**: query inactive lists or lists whose latest scan no longer matches prior object distribution, so operators can verify the old binding is still meaningful.
5. **Check downstream effect**: list detail should show how many `episode_inventory` rows are `qc_ready`, how many have already been ingested, and which downstream batch/task assignments already exist.

The checking surface is not optional in V1 because prefix-based auto-classification is intentionally conservative and requires operator review.

#### 4.2.11 Minimal admin/API contract for task/list operations

Recommended V1 capabilities:

- `GET /api/task-types` — list canonical task catalog, including whether each task is still selectable for future binding
- `POST /api/task-types` — create a new canonical task type
- `PATCH /api/task-types/{task_type_id}` — rename or retire/restore a task type
- `GET /api/minio/lists?finalTaskTypeId=...` — inspect which lists are currently bound to one task type
- `POST /api/minio/lists/{list_id}/classify` — set or clear `final_task_type_id`
- `GET /api/minio/lists/{list_id}` — inspect one list's raw/processed counts, candidate/final classification, state counts and downstream ingest status

`POST /api/minio/lists/{list_id}/classify` should accept both bind and unbind semantics. Recommended request shape:

```json
{
  "finalTaskTypeId": "task_type:huanggua"
}
```

or to clear:

```json
{
  "finalTaskTypeId": null
}
```

Response should return the updated list classification snapshot so frontend does not need to re-derive state locally.

#### 4.2.12 Manual override policy

When an operator manually sets `lists.final_task_type_id`:

- the manual value becomes the business truth for that list
- future rescans must not overwrite that manual `final_task_type_id` unless the operator explicitly clears or changes it
- auto-match may continue refreshing `candidate_task_type` for audit/reference, but not the confirmed final value
- per prior decision Q-DD-003, already ingested episodes keep their historical task assignment

#### 4.2.13 Real `yaocao` basename inventory and first-pass seed review

Observed from the real `yaocao` bucket scan:

- 36 structural list hits were found under the current scanner rule.
- 35 of them are business-like list basenames.
- 1 hit is a technical nested branch: `raw_data/` under `double_linkerhand_task_fengqintudou_2026-06-09_10-49-07/`; V1 keeps it in inventory but it should fall into `no-match`, not into any business seed.
- Prefix noise is consistent: `double_linkerhand`, optional `task`, optional upper-level `K1/`, and timestamp suffixes are structural context only.
- Repetition suffixes such as `2/3/4/5/6` indicate repeated collection batches, not different business tasks.
- `qingdao` appears in both single-material and compound names, so it is treated as process/context wording, not a `task_type` token by itself.

First-pass review table for seed curation:

| Basename sample | Normalized business tokens | Proposed candidate label | Target `task_type` | Authoritative | Reason |
|---|---|---|---|---|---|
| `double_linkerhand_task_qingdaohuanggua_2026-06-10_13-31-16` | `qingdaohuanggua` | `huanggua` | `task_type:huanggua` | yes | Single material signal, repeated across multiple sibling lists (`...huanggua2/3/4`) with no competing material token |
| `double_linkerhand_qingdao_huangguakuai_2026-06-11_13-33-28` | `qingdao huangguakuai` | `huangguakuai` | `task_type:huangguakuai` | yes | Distinct cut-form token `huangguakuai` is stable and more specific than plain `huanggua` |
| `double_linkerhand_task_qingdaotudou_2026-06-08_10-19-00` | `qingdaotudou` | `tudou` | `task_type:tudou` | yes | Single material signal, repeated across `...tudou2/3/4/5`, no competing object token |
| `double_linkerhand_qingdao_tudoutiao_2026-06-12_14-20-31` | `qingdao tudoutiao` | `tudoutiao` | `task_type:tudoutiao` | yes | `tudoutiao` is a stable product-form token and should outrank plain `tudou` |
| `double_linkerhand_task_qingdao_luobo_2026-05-28_10-31-42` | `qingdao luobo` | `luobo` | `task_type:luobo` | yes | Single material signal with repeated sibling list `...luobo2`; no multi-material ambiguity |
| `double_linkerhand_task_qingdaofanqieluobo_2026-06-05_10-50-45` | `qingdaofanqieluobo` | `fanqie_luobo` | none | no | Compound material token, likely mixed workflow; safe to suggest only |
| `double_linkerhand_task_qingdaohuanggualuobo_2026-06-04_11-33-49` | `qingdaohuanggualuobo` | `huanggua_luobo` | none | no | Two materials in one basename; should not auto-write final `task_type` |
| `double_linkerhand_task_chengfanghuanggualuobo_2026-06-02_13-31-56` | `chengfanghuanggualuobo` | `chengfang_huanggua_luobo` | none | no | Compound plus action/process wording; business semantics need operator confirmation |
| `double_linkerhand_task_qingdao_misezhuobu_tudoutiao_2026-06-16_14-50-14` | `qingdao misezhuobu tudoutiao` | `misezhuobu_tudoutiao` | none | no | Contains specialized workflow wording plus product token; keep as suggest-only until business side confirms mapping |
| `double_linkerhand_task_fengqintudou_2026-06-09_10-49-07` | `fengqintudou` | `fengqin_tudou` | none | no | Compound shorthand is not yet self-evident enough for auto-classification |
| `double_linkerhand_task_tiaoliaoping_2026-06-10_09-33-54` | `tiaoliaoping` | `tiaoliaoping` | none | no | Looks business-relevant but lacks corroborating sibling samples and may denote a process step rather than a canonical task type |
| `double_linkerhand_task_quanliucheng1_2026-05-27_14-33-37` | `quanliucheng1` | `` | none | no | Generic workflow/staging wording; leave unclassified |
| `double_linkerhand_task_naguo_2026-05-26_16-36-54` | `naguo` | `` | none | no | Token meaning is unclear from basename alone |
| `double_linkerhand_task_chengfanghuangguang_2026-06-01_11-09-13` | `chengfanghuangguang` | `` | none | no | Appears to be typo or shorthand drift; safer to leave unmatched |
| `raw_data` | `raw data` | `` | none | no | Technical nested branch, not a business list seed source |

First-pass seed conclusion:

- **Authoritative candidates now justified by real samples:** `huanggua`, `huangguakuai`, `tudou`, `tudoutiao`, `luobo`
- **Suggest-only candidates now justified by real samples:** `fanqie_luobo`, `huanggua_luobo`, `chengfang_huanggua_luobo`, `misezhuobu_tudoutiao`, `fengqin_tudou`, `tiaoliaoping`
- **Remain unmatched / no-match:** `quanliucheng1`, `naguo`, `chengfanghuangguang`, `raw_data`

This review table becomes the source for the first migration seed insert. The remaining implementation-stage action is to bind these labels to the real `task_types.id` values at migration time.

### 4.3 Phase C: Episode Inventory Build

1. Set `scan_jobs.status='episode_inventory'`.
2. For each confirmed list, enumerate direct children under `list/raw/` and `list/processed/`.
3. Only direct children matching `episode_\d+/` are episode units.
4. Canonicalize by `episode_name`, then merge raw-side and processed-side evidence into one `episode_inventory` row.
5. UPSERT one row per `(list_id, episode_name)`.
6. Store:
   - `raw_prefix` if raw side exists
   - `processed_prefix` if processed side exists
   - `episode_prefix` as the canonical list-level identity
7. For each episode side, enumerate all objects below the side-specific prefix and UPSERT into `episode_objects`.
8. If `manifest.json` or `metadata.json` exists, parse content to populate hashes and business fields.

### 4.4 Phase D: Completion

On successful completion:

- `scan_jobs.status='done'`
- `scan_jobs.finished_at=now`
- `scan_jobs.total_prefixes = COUNT(discovered_prefixes WHERE last_seen_scan_id=current)`
- `scan_jobs.confirmed_lists = COUNT(lists WHERE last_active_scan_id=current)`
- `scan_jobs.total_episodes = COUNT(episode_inventory WHERE last_seen_scan_id=current)`
- `scan_jobs.new_episodes = COUNT(episode_inventory WHERE first_seen_scan_id=current)`

On any terminal error:

- `scan_jobs.status='failed'`
- `error_detail` stores the failing step and object/prefix context if available
- already-written discovery rows remain committed; the next scan reuses them via UPSERT

### 4.5 Re-scan Idempotency

- **discovered_prefixes**: matched by `UNIQUE(bucket, prefix)`. On re-scan, UPDATE `last_seen_scan_id` and structural flags. Keep old `first_seen_scan_id`.
- **lists**: matched by `UNIQUE(bucket, list_prefix)`. On re-scan, UPDATE `last_active_scan_id`, counts, and side flags. Keep historical `confirmed_scan_id`.
- **episode_inventory**: matched by `UNIQUE(list_id, episode_name)`. On re-scan, UPDATE existence flags, parsed metadata, hashes, state, and `last_seen_scan_id`.
- **episode_objects**: matched by `UNIQUE(episode_inventory_id, object_key)`. On re-scan, UPDATE size/hash/mtime/`last_seen_scan_id`; insert newly appeared objects.

**No DELETEs from inventory tables.** If a list or episode disappears between scans, rows remain for audit and recovery; recency is tracked by `last_seen_scan_id` and activation flags.

## 5. Episode State Transition Rules

### 5.1 Evidence fields

The scanner computes these booleans per episode:

- `raw_exists`: at least one object exists under `raw/episode_xxxxxx/`
- `processed_exists`: at least one object exists under `processed/episode_xxxxxx/`
- `has_manifest`: `processed/episode_xxxxxx/manifest.json` exists
- `has_metadata`: `processed/episode_xxxxxx/metadata.json` exists
- `has_telemetry_npz`: `processed/episode_xxxxxx/telemetry.npz` exists
- `has_rgb_video`: at least one processed RGB video role exists

### 5.2 State definitions

#### `ingestable`

Use when:
- `raw_exists=TRUE`
- `processed_exists=FALSE`

Meaning:
- the episode has arrived in the bucket
- processed artifacts are not yet ready
- it should remain visible in inventory but cannot enter manual QC

#### `processable`

Use when either of these holds:
- `processed_exists=TRUE` but the `qc_ready` minimum checklist is incomplete
- `processed_exists=TRUE` and `raw_exists=FALSE`

Meaning:
- some processed outputs already exist, so downstream conversion likely started
- the episode is not yet safe to present to QC
- this state also captures partial writes during ongoing upload or repair

#### `qc_ready`

Use when all V1 minimum processed-side evidence is present:
- `processed_exists=TRUE`
- `has_manifest=TRUE`
- `has_metadata=TRUE`
- `has_telemetry_npz=TRUE`
- `has_rgb_video=TRUE`

Meaning:
- the episode has the minimum assets needed by manual QC
- it can be promoted into existing `episodes` / `batches`
- V1 does not require raw-side presence once processed-side QC evidence is complete

### 5.3 Transition policy

V1 transitions are monotonic by default:

- `ingestable → processable`: when any processed-side object first appears
- `ingestable → qc_ready`: allowed if a later scan first sees a fully complete processed side
- `processable → qc_ready`: when the minimum checklist becomes complete

V1 does **not** automatically downgrade `qc_ready` back to `processable` or `ingestable` just because a later scan temporarily fails to observe an object. Reasons:
- MinIO listing races and partial visibility should not churn the QC task pool
- the user explicitly expects multiple small writes
- already-ingested QC work must remain stable

If a later scan detects object disappearance or hash inconsistency after `qc_ready`, record it as an audit/integrity event in implementation, but keep the business state stable unless an operator explicitly intervenes.

### 5.4 `state_changed_at`

Update `state_changed_at` only when the stored `state` value actually changes. Re-scans that merely refresh hashes or mtimes do not modify it.

## 6. `object_role` Dictionary and `qc_ready` Checklist

### 6.1 Role normalization principles

- `object_role` is a business-facing normalized label, not the raw filename.
- V1 normalization is path-driven: role is inferred from relative path under the episode prefix.
- Unknown objects are preserved as rows with `object_role='unknown'`; they are never dropped.
- Readiness checks operate on normalized roles, not exact filenames, so future suffix changes are less disruptive.

### 6.2 V1 role catalog

| Relative path pattern | Scope | `object_role` | Used for `qc_ready` |
|---|---|---|---|
| `manifest.json` | processed | `manifest` | required |
| `metadata.json` | processed | `metadata` | required |
| `telemetry.npz` | processed | `telemetry_npz` | required |
| `camera_info.json` | processed | `camera_info` | optional |
| `cameras/*rgb*.mp4` | processed | `camera_rgb_video` | required, at least 1 |
| `cameras/*depth*colormap*.mp4` | processed | `camera_depth_colormap_video` | optional |
| `cameras/*depth*.mp4` | processed | `camera_depth_video` | optional |
| `cameras/*left*.mp4` or `cameras/*right*.mp4` | processed | `camera_aux_video` | optional |
| `*.npy` under processed timestamps/sync-like names | processed | `timestamp_npy` | optional |
| `*.png` under processed depth/frame trees | processed | `depth_png_frame` | optional |
| `recording_info.json` | raw | `recording_info` | not used |
| `device_info.json` | raw | `device_info` | not used |
| `metadata.yaml` | raw | `raw_metadata_yaml` | not used |
| `*.mcap` | raw | `raw_mcap` | not used |
| any other object | raw/processed | `unknown` | not used |

Notes:
- V1 intentionally collapses camera indices into family roles such as `camera_rgb_video` rather than enforcing `cam0/cam1/cam2` completeness.
- This matches the current user-confirmed policy that `qc_ready` is based on a minimum common denominator, not task-specific sensor templates.

### 6.3 Minimum `qc_ready` checklist

An episode is `qc_ready` when the processed side contains:

1. `manifest`
2. `metadata`
3. `telemetry_npz`
4. at least one `camera_rgb_video`

Everything else is recorded for audit and UI rendering, but does not block readiness in V1.

### 6.4 Unknown object handling

If the scanner sees an object that matches no known role:

1. insert/update it in `episode_objects` with `object_role='unknown'`
2. do not block `qc_ready` because of the unknown object alone
3. surface the unknown count in future list/episode detail pages so naming drift can be reviewed

This keeps V1 robust against benign object additions while preserving evidence for later schema refinement.

## 7. Downstream Ingestion: Inventory → `episodes`/`batches`

Once `episode_inventory` has entries in `qc_ready` state, a separate ingest step promotes them:

```
INSERT/UPDATE episodes:
  episode.id = generate from episode_inventory.id or episode_id_from_manifest
  episode.batch_id = (existing batch for this list, or create new batch)
  episode.task_name = final_task_type.name if present, else lists.candidate_task_type
  episode.source_path = episode_inventory.episode_prefix  (MinIO prefix, not local path)
  episode.source_hash = episode_inventory.manifest_hash
  episode.ingest_status = 'indexed'
  episode.duration_sec = from manifest
  episode.frame_count = from manifest

UPDATE episode_inventory.ingested_episode_id = episodes.id
```

The existing `episodes` schema is sufficient for QC flow — the new tables only need to feed `episode_id` and `batch_id` into the existing pipeline. `episodes.source_path` changes from local filesystem path to MinIO prefix, which is a transparent change for the QC UI.

## 8. Manual QC Object Access Protocol (V1)

### 8.1 Decision

V1 adopts a hybrid access protocol:

- preview/playback media objects are exposed to the QC UI as short-lived presigned URLs
- structured objects and sensitive reads stay behind backend APIs
- the frontend still talks only to backend APIs and never derives bucket/key rules by itself

This keeps the browser path simple enough for multi-video playback, while preserving backend control over identity, permission, audit and future protocol changes.

### 8.2 Why pure proxy is rejected for V1

A full backend streaming proxy would centralize control, but it is the wrong default for V1 because:

- manual QC needs concurrent playback of multiple MP4 objects
- FastAPI/Nginx proxying all preview traffic would add unnecessary backend bandwidth and latency pressure
- the current frontend contract is already backend-first, so backend control can be preserved without making backend the data plane for every preview byte

### 8.3 Why pure presigned is also rejected

A presigned-only design would make the frontend too aware of storage semantics and would weaken auditability because:

- `manifest.json`, `metadata.json`, `telemetry.npz` and future export/download objects may contain structured content that should stay under backend parsing and permission checks
- the UI should receive normalized media descriptors, not raw bucket/key conventions
- future bucket migration or object-role renaming should not require frontend changes

### 8.4 Object classes and serving rules

| Object class | Examples | V1 protocol | Notes |
|---|---|---|---|
| Preview media | `camera_rgb_video`, `camera_depth_colormap_video`, optional previewable auxiliary MP4 | backend returns short-lived presigned URL | for browser `<video>` playback |
| Structured QC inputs | `manifest.json`, `metadata.json`, `telemetry.npz`, future parsed timestamps | backend reads/parses directly | not exposed as raw object URL |
| Controlled download/export | raw archive, NPZ export, original object download, future evidence bundle | backend download/proxy endpoint | keeps auth and audit on explicit download actions |
| Unknown/non-preview objects | `unknown`, non-video technical artifacts | no direct UI exposure by default | can be surfaced later through admin/debug APIs |

### 8.5 Backend contract for manual QC

`GET /api/episodes/{episode_id}/qc-context` remains the main entrypoint, but its payload must be extended with normalized media descriptors rather than local placeholder panels.

Recommended V1 payload shape:

```json
{
  "episode": {"id": "..."},
  "metrics": [],
  "timelineSegments": [],
  "revisions": [],
  "reviewLock": {},
  "media": [
    {
      "objectId": "episode_objects.id",
      "role": "camera_rgb_video",
      "label": "Top Camera",
      "variant": "rgb",
      "slot": "top",
      "mimeType": "video/mp4",
      "previewUrl": "https://minio-presigned/...",
      "previewExpiresAt": "2026-06-23T10:00:00Z",
      "refreshable": true,
      "downloadable": false,
      "width": 640,
      "height": 480,
      "frameRate": 30,
      "durationSec": 12.4,
      "sortOrder": 10
    }
  ]
}
```

Rules:

1. Frontend stores and renders only backend-returned media descriptors.
2. Frontend never concatenates bucket, prefix or object key.
3. V1 contract uses `previewUrl` as a concrete playback field, not a generic `url` union field.
4. `previewUrl` is already a backend-issued short-lived presigned URL at `qc-context` load time.
5. `previewExpiresAt` is the canonical expiry signal for frontend refresh decisions; `refreshable` tells frontend whether refresh is allowed for the current user/session.
6. `downloadable=false` is the default for preview descriptors; explicit download capability is exposed separately by backend policy, not assumed from previewability.
7. `slot` + `variant` + `sortOrder` define stable UI ordering so frontend does not infer camera layout from filenames.

### 8.6 Refresh contract

V1 should support a narrow refresh API rather than forcing a full page reload whenever one preview URL expires.

Recommended endpoint:

- `POST /api/episodes/{episode_id}/media/refresh`

Recommended request body:

```json
{
  "objectIds": ["obj_1", "obj_2"]
}
```

Recommended response body:

```json
{
  "media": [
    {
      "objectId": "obj_1",
      "previewUrl": "https://minio-presigned/...",
      "previewExpiresAt": "2026-06-23T10:05:00Z",
      "refreshable": true
    }
  ]
}
```

Rules:

1. Refresh accepts only `objectId` values that are already linked to the episode through `episode_objects`.
2. Refresh returns only updated preview fields; frontend merges them back into existing descriptors by `objectId`.
3. Refresh is only valid for previewable media roles; structured objects are not part of this contract.
4. Refresh must not require frontend to send bucket/key/object-role guesses.
5. If refresh is denied because the user no longer holds the review lock, backend returns a permission error rather than silently extending preview access.

### 8.7 URL TTL and audit rules

- Default preview URL TTL: 5 minutes.
- Backend may issue fresh preview URLs only for an actively held review lock.
- Initial `qc-context` load may include preview URLs for a user who can open the manual QC page, but indefinite refresh is not granted without the active lock.
- Preview URL issuance should be logged as an access event at the API layer; explicit downloads should additionally be logged as download/export events.
- No MinIO credential, bucket policy detail or object key pattern is exposed as frontend configuration.

### 8.8 Authorization boundary

The backend must verify before issuing any media access result:

1. requester is authenticated
2. requester is allowed to view the episode/task
3. episode is in a state eligible for manual QC visibility
4. requested object belongs to the episode through `episode_objects`
5. requested object role is allowed for the requested operation (`preview` vs `download`)

This means object access is resolved by PostgreSQL relationship first, MinIO second.

### 8.9 Interaction with review lock

Review lock is not the same as storage authorization, but it constrains refresh and long-session behavior:

- a user who can open manual QC may receive initial preview URLs for viewing
- a user holding the active review lock may continue refreshing preview URLs during the session
- if the lock is lost, already-issued URLs may expire naturally, but backend must stop issuing fresh preview URLs
- explicit submit/export actions still follow their existing task permission checks

### 8.10 Controlled download contract

Explicit download is a separate backend-controlled operation and must not reuse the preview URL field.

Recommended endpoint:

- `GET /api/episodes/{episode_id}/objects/{object_id}/download`

Rules:

1. Download endpoint resolves `objectId` through PostgreSQL and then streams/proxies the underlying MinIO object as an attachment.
2. Download authorization is stricter than preview by default; previewable media is not automatically downloadable.
3. Structured objects such as `manifest.json`, `metadata.json`, `telemetry.npz` may be downloadable only when the caller has explicit export/debug permission.
4. Download events must be auditable as explicit user actions.
5. Frontend should expose download only through deliberate UI actions, never as implicit player behavior.

### 8.11 API impact additions

Additional V1 endpoints/capabilities:

- `GET /api/episodes/{episode_id}/qc-context` — returns telemetry context plus media descriptors with embedded `previewUrl`
- `POST /api/episodes/{episode_id}/media/refresh` — refreshes expired/soon-expiring preview URLs for specific `objectId` values
- `GET /api/episodes/{episode_id}/objects/{object_id}/download` — controlled backend download for non-preview or explicit export flows

## 9. API Impact

New endpoints:
- `POST /api/minio/scan` — trigger a full bucket scan (returns `scan_job.id`)
- `GET /api/minio/scan/{scan_job_id}` — poll scan progress
- `GET /api/minio/lists` — paginated list view, with filters such as `finalTaskTypeId`, `classificationState`, `active`, `hasRaw`, `hasProcessed`
- `GET /api/minio/lists/{list_id}` — detail with episode counts by state, classification snapshot and downstream ingest status
- `GET /api/minio/episodes?state=qc_ready` — episodes ready for ingest
- `POST /api/minio/lists/{list_id}/classify` — manually set or clear `final_task_type_id`
- `GET /api/minio/classification-rules` / `POST` / `DELETE` — manage auto-classify rules
- `GET /api/task-types` — list canonical task catalog
- `POST /api/task-types` — create canonical task type
- `PATCH /api/task-types/{task_type_id}` — rename / retire / restore canonical task type

Existing `/api/database/scan` endpoint changes semantics from "scan local directory" to "trigger MinIO bucket scan" and creates `scan_jobs` instead of `ingest_jobs` directly.

## 10. Migration Plan

1. **New migration revision**: Add `scan_jobs`, `discovered_prefixes`, `lists`, `episode_inventory`, `episode_objects`, `classification_rules` tables.
2. **Seed initial `classification_rules`** from observed list_prefix patterns (to be defined in the next business-logic step).
3. **Existing tables untouched** — no column drops or renames in this revision.
4. **`episodes.source_path`** semantic change from local path to MinIO prefix is a config/runtime change, not a schema change — the column type stays `VARCHAR(255)`.

## 11. Resolved Design Decisions

- **Q-DD-001 (2026-06-23)**: Can a single `episode_inventory` entry appear under TWO lists? → **V1 否决**。每个 episode 只属于一个 list。
- **Q-DD-002 (2026-06-23)**: Should `qc_ready` object checklist be hardcoded or per task_type? → **V1 硬编码**最小集（`manifest` + `metadata` + `telemetry_npz` + `>=1 camera_rgb_video`）。按 task_type 模板化是 V2。
- **Q-DD-003 (2026-06-23)**: When `final_task_type_id` is changed manually, should ingested episodes re-assign? → **仅新入库生效**。已入库 episode 保持原 task_type。
- **Q-DD-004 (2026-06-23)**: Will deepest-match cause parent-owned episodes to be lost? → **不会**。deepest wins, but parent-owned direct episodes remain a parent list entry.
- **Q-DD-005 (2026-06-23)**: Should manual QC use presigned URLs, backend proxy, or a hybrid protocol for MinIO media access? → **V1 采用混合协议**。预览/播放类 MP4 使用短时 presigned URL；结构化对象读取与显式下载仍走后端控制路径。