# Problem Brief For AI Assistance

## Audience

This document is for another AI model (for example GPT) to evaluate a **task-level data asset profile** design for an internal robot teleoperation QC / training-data platform.

The goal is **not** to implement code yet.  
The goal is to decide:

1. whether a dedicated task-level projection is needed;
2. whether extra tables are required;
3. how to keep the design consistent with the already-accepted Route C' batch-asset architecture;
4. what is the lowest-risk path for future large-scale data growth.

---

## What I Need Help With

We already finished:

- global data-asset summary;
- batch-level data-asset profile;
- Route C' architecture:
  - `batches.list_id`
  - `batch_asset_rollups`
  - `batch_asset_recompute_jobs`
  - independent `/api/data-assets/*`

Now we want to add a **task-level view** inside `数据总库`.

Current product idea:

- `数据总库` currently has two perspectives:
  1. Episode-level browsing
  2. Batch-level asset profile
- We want a third perspective:
  3. **Task-level asset profile**

For each task (`task_types` row), the page should show a clear asset portrait, roughly:

| Metric | Meaning |
|---|---|
| batch_count | how many batches belong to this task |
| episode_count | how many episodes belong to this task |
| available_episode_count | usable / qualified episodes |
| unavailable_episode_count | unusable / unqualified episodes |
| not_reviewed_or_pending_count | not yet QC'd / not yet finally adjudicated |
| pass_rate / qualified_rate | among already QC'd / adjudicated episodes, what fraction is usable |
| total_duration_sec | total seconds |
| total_frame_count | total frames |

Important product intent:

- this is a **task-level asset portrait**, not just another filter on the episode list;
- it must remain consistent with the existing batch/global asset scope;
- it must be designed for **future large scale**, not only current ~5k episodes / ~46 batches.

Please answer:

1. Is it enough to aggregate from `batch_asset_rollups` on read, or should we introduce a task-level projection table?
2. If a new table is needed, what should its boundary be?
3. Should task-level metrics reuse `final_dataset_status`, `manual_qc_status`, or both?
4. How should dirty marking / recompute work for task-level stats?
5. What is the recommended migration order under the existing Route C' design?
6. Which metrics should be stored, which should be computed at read time?
7. What are the main failure modes if data becomes much larger?

---

## Current Goal

Short-term product goal:

- add a task-level card / section in `数据总库`;
- provide one clear row/card per task type;
- show counts, availability, QC progress, duration, and frames;
- keep the same statistical scope as existing data-asset APIs;
- prepare for long-term scale instead of a temporary SQL patch.

This is an architecture decision brief, not an implementation request.

---

## Project Background

### Product Positioning

Internal robot teleoperation data platform.

Main pipeline:

```text
Teleoperation collection
  -> MinIO object storage
  -> platform data management / scan
  -> QC (manual + L3 auto metrics)
  -> dataset consumption / export
```

Upstream collection and raw storage already exist and are **outside** this platform's redesign scope.

Platform responsibilities already implemented:

1. MinIO scan / list recognition / episode inventory
2. Batch / Episode business entities
3. Manual QC workflow
4. Batch adjudication
5. Dataset export
6. Data-asset summary + batch-level asset profile (Route C')

### Current Business Phase

Confirmed:

- research and control-plane design are done;
- Route C' data-asset architecture is implemented and verified;
- current remaining zeros in duration/frame are mostly pure-raw episodes without processed manifest, which is accepted business truth, not a stats-layer bug.

Current approximate live numbers after Route C' + manifest repair:

- total episodes in active scope: about `5216`
- episodes with valid duration/frame: about `4524 ~ 4525`
- pure raw without processed manifest: about `692`
- total duration: about `50034` seconds
- total frames: about `823320`
- active batches involved in asset rebuild: about `46`

This is still small, but the architecture must assume much larger growth.

---

## Environment

- OS: Linux
- Frontend: Vue 3 + TypeScript + Element Plus + Vite + Pinia
- Backend: FastAPI + SQLAlchemy + Alembic
- Database: PostgreSQL
- Object storage: MinIO
- Deploy: Docker Compose
- Project path: `/home/tbl/Project/data_collect/software`

Relevant existing docs:

- `/home/tbl/Project/data_collect/software/docs/data-assets-architecture-brief.md`
- `/home/tbl/下载/Robot_QC_数据总库批次资产画像改造任务说明.md`
- `/home/tbl/下载/Robot_QC_数据资产架构升级分析报告.md`
- `/home/tbl/Project/data_collect/software/.project-log/business-logic/decision-records.md`
- `/home/tbl/Project/data_collect/software/.project-log/business-logic/main.md`

---

## Confirmed Architecture Facts

### 1. The system already has three layers

#### A. Object-storage control plane

- `lists`
- `episode_inventory`
- `episode_objects`
- `scan_jobs`
- `discovered_prefixes`
- `classification_rules`

#### B. Business entities

- `task_types`
- `batches`
- `episodes`

#### C. QC / dataset consumption

- `qc_tasks`
- `qc_review_revisions`
- `batch_decision_log`
- `dataset_export_jobs`

### 2. Route C' is already the frozen long-term batch asset route

Formal objects:

- `batches.list_id`
- `batch_asset_rollups`
- `batch_asset_recompute_jobs`

Formal APIs:

- `GET /api/data-assets/summary`
- `GET /api/data-assets/batches`
- `POST /api/data-assets/rebuild`

Formal statistics scope:

```text
active_list_active_batch_indexed_episodes
```

Meaning:

- active `ListRecord`
- active `Batch`
- business `Episode` under those batches
- inactive / residual historical batches outside active lists are excluded

### 3. Batch-level projection already exists and is the preferred aggregation base

`batch_asset_rollups` currently stores rebuildable metrics such as:

- `episode_count`
- `total_duration_sec`
- `duration_covered_episode_count`
- `duration_missing_episode_count`
- `total_frame_count`
- `frame_covered_episode_count`
- `frame_missing_episode_count`
- `sampled_episode_count`
- `reviewed_count`
- `manual_pass_count`
- `manual_fail_count`
- `qualified_count`
- `unqualified_count`
- `pending_dataset_count`
- `last_episode_updated_at`
- `source_watermark`
- `calculation_version`
- `refreshed_at`

Projection boundary already decided:

Do **not** make projection authoritative for:

- `qc_status`
- `batch_decision`
- `task_type_id`
- `reject_threshold`
- `batch_name`
- `failure_rate`

These remain business facts on `batches` / related dimension tables.

### 4. Task type is human-managed business master data

Confirmed business rule:

- `task_types` are managed by `admin/qc_manager`
- scanner does **not** authoritatively create formal task types
- new / unknown batches go to `task_type:unclassified` / `待分类`
- batch-to-task reassignment is allowed
- deleting a task type recycles batches back to unclassified

This matters because task-level stats must tolerate:

- reassignment of batches across tasks;
- unclassified task existence;
- inactive task types if present.

### 5. Duration / frame authority is already fixed

- `duration_sec` and `frame_count` come from processed manifest during scan
- persisted into both `episode_inventory` and `episodes`
- `frame_count` is episode-level frame count, **not** multi-camera summed frames
- values `> 0` count as covered
- pure raw episodes without processed manifest may legitimately remain 0

### 6. There are already some weak / partial task-level counters, but they are not the right long-term asset profile

Existing incomplete pieces:

#### A. `task_types.total_batches` / `task_types.total_episodes`

- stored on `task_types`
- refreshed opportunistically in some list/update paths
- only coarse counts
- not a full asset profile
- refresh is not a durable projection system like Route C'

#### B. `DatasetSummaryService.task_summary()`

Existing dataset-consumption summary for a task includes:

- `qualifiedEpisodeCount`
- `totalEpisodeCount`
- `batchCount`
- accepted / rejected / pending batch counts
- manual pass / fail counts
- exportable episode count

But:

- it is focused on **dataset consumption**, not full asset portrait;
- it currently loads batches/episodes and aggregates in Python;
- it does not use Route C' rollups;
- it does not expose duration / frame totals as first-class asset metrics;
- it is not designed as the long-term `数据总库` read model.

#### C. `/api/dataset/tasks/*`

This path is for training-data consumption / export workflows.

`数据总库` asset analysis should stay on the data-asset side, not silently overload dataset-consumption APIs.

---

## Product Requirement: Task-Level Asset Profile

### Desired UX placement

Inside `数据总库`, introduce a third perspective:

1. Episode view
2. Batch asset view
3. **Task asset view**

Suggested page behavior:

- top cards may remain global summary;
- a new section lists task cards / task table;
- clicking one task can filter batch list and/or episode list to that task;
- optional task detail drawer later, but first version can be list/cards only.

### Desired per-task fields

Minimum useful portrait:

```text
task_type_id
task_type_name
is_active
batch_count
episode_count

available_episode_count      # currently proposed = QUALIFIED
unavailable_episode_count    # currently proposed = UNQUALIFIED
pending_or_not_reviewed_count

qualified_rate               # among adjudicated / reviewed subset
manual_pass_count
manual_fail_count
reviewed_count

total_duration_sec
duration_covered_episode_count
duration_missing_episode_count

total_frame_count
frame_covered_episode_count
frame_missing_episode_count

freshness / refreshed_at / stale flag
```

### Important semantic ambiguity to resolve

The user said:

> 有多少可用 episode，多少不可用，多少未质检，合格率是多少（所有质检过的数据中可用的比例）

There are at least two possible definitions:

#### Definition Set A — Final dataset consumption semantics

- available = `final_dataset_status == QUALIFIED`
- unavailable = `final_dataset_status == UNQUALIFIED`
- not finished = `final_dataset_status == PENDING`
- qualified_rate = `QUALIFIED / (QUALIFIED + UNQUALIFIED)`

This matches training-data usability after batch adjudication.

#### Definition Set B — Manual QC semantics

- reviewed = `manual_qc_status in (MANUAL_PASS, MANUAL_FAIL)`
- available-ish = `MANUAL_PASS`
- unavailable-ish = `MANUAL_FAIL`
- not reviewed = `NOT_REVIEWED`
- pass_rate = `MANUAL_PASS / (MANUAL_PASS + MANUAL_FAIL)`

This matches human QC progress, not final training usability.

#### Definition Set C — Hybrid display

Show both:

- QC progress: reviewed / pass / fail
- Final usability: qualified / unqualified / pending

I currently lean toward **Definition Set C** for the long-term asset portrait, because the platform already separates:

- manual QC result;
- final dataset status after batch adjudication.

Please explicitly recommend which definition should be primary for the task-level portrait.

---

## Existing Relevant Code Paths

### Models

- `backend/app/models/task_type.py`
- `backend/app/models/batch.py`
- `backend/app/models/episode.py`
- `backend/app/models/control_plane.py` (`BatchAssetRollup`, `BatchAssetRecomputeJob`, `ListRecord`, ...)

### Services

- `backend/app/services/data_assets.py`
  - active scope helpers
  - batch rollup recompute
  - summary from batch rollups
  - batch asset list
- `backend/app/services/dataset_service.py`
  - current task-level dataset summary, Python aggregation
- `backend/app/services/payloads.py`
  - `task_type_active_counts()`
- `backend/app/services/batch_adjudication.py`
  - writes final dataset status

### Frontend

- `frontend/src/pages/database-view.vue`
  - already has episode table + batch asset section + global summary cards

### Business truth docs

- `.project-log/business-logic/decision-records.md`
- `.project-log/business-logic/main.md`
- `.project-log/business-logic/constraints.md`

---

## Confirmed Constraints From Route C'

These should not be casually violated:

1. Do not put long-term aggregation back into `/api/database`.
2. Do not make `batches` an ever-growing analysis dump table.
3. Prefer rebuildable derived projections over request-time full episode scans as the long-term main path.
4. Keep projection fields rebuildable and non-authoritative for business state.
5. Keep one consistent statistics scope across summary / batch / task views.
6. Prefer whole-entity recompute over fragile `+1/-1` counters.
7. Keep dirty/recompute durable in PostgreSQL rather than only in-process memory tasks.
8. Current global summary is derived from batch rollups, not a separate global authority table.

Implication:

Any task-level design should preferably be a natural extension of Route C', not a parallel second stats system with different scope and different refresh semantics.

---

## Candidate Technical Routes

Please compare at least the following routes.

### Route T0 — Read-time aggregate from episodes

```text
task list page
  -> SQL GROUP BY task_type over episodes/batches
```

Pros:

- simplest;
- no new table.

Cons:

- repeats the exact problem Route C' already rejected for batch/global stats;
- summary and task cards can drift if filters/scopes differ;
- will degrade as episode volume grows;
- duplicates work already solved by batch rollups.

Likely only acceptable as temporary baseline / verification SQL, not long-term main path.

### Route T1 — Read-time aggregate from `batch_asset_rollups`

```text
batch_asset_rollups
  join batches
  group by batches.task_type_id
```

Pros:

- reuses Route C' already-built projection;
- no new table initially;
- keeps same duration/frame/QC aggregate base;
- easy consistency with global summary if same active-scope join is used.

Cons:

- every task list request still needs join + group;
- still cheap now, but if task page later needs sort/filter by many derived rates and freshness, repeated aggregation grows;
- task reassignment is easy (batch changes task_type_id), but still no dedicated task freshness entity;
- coarse `task_types.total_*` remains a separate weak cache unless removed/replaced.

This may be a good phase-1 route if task cardinality stays small.

### Route T2 — Add `task_asset_rollups` projection table

```text
task_types
  1 --- 0..1 task_asset_rollups
```

Rebuild from either:

1. sum of `batch_asset_rollups` under the task; or
2. direct episode aggregation under the task.

Pros:

- page reads become O(task count);
- can store task-level freshness / calculation_version / source_watermark;
- natural extension of Route C';
- good for future large batch counts under each task.

Cons:

- another projection to keep consistent;
- needs dirty rules for:
  - batch reassigned to another task;
  - batch rollup refreshed;
  - task deactivated / deleted / recycled;
- risk of dual sources if also keeping `task_types.total_batches/total_episodes`.

### Route T3 — Only expand fields on `task_types`

Store more counters directly on `task_types`.

Pros:

- few joins.

Cons:

- mixes master data and analytics state;
- same anti-pattern already rejected for stuffing stats into `batches`;
- harder to version, rebuild, and reconcile;
- not recommended as long-term authority.

### Route T4 — Event/OLAP path

Kafka / ClickHouse / warehouse-style serving layer.

Almost certainly overkill right now. Please only recommend if there is a strong reason under current scale trajectory.

---

## My Current Working Preference

Not final. Please challenge it.

### Preference

Adopt a **Route C'-compatible staged design**:

#### Phase 1

- Do **not** immediately invent a totally separate stats system.
- Serve task profile by aggregating active-scope `batch_asset_rollups` joined to `batches.task_type_id`.
- Add independent API such as:
  - `GET /api/data-assets/tasks`
  - optional later: `GET /api/data-assets/tasks/{task_type_id}`
- Keep scope identical to batch/global asset scope.
- Use this phase to freeze metric definitions and verify against episode baseline SQL.

#### Phase 2

If/when task list needs:

- stable sort by qualified rate / duration / freshness;
- low-latency dashboard under much larger batch counts;
- independent stale tracking per task;

then introduce:

```text
task_asset_rollups
```

rebuilt primarily by summing child `batch_asset_rollups`, not by rescanning all episodes.

#### Dirty strategy preference

- batch fact changes already enqueue `batch_asset_recompute_jobs`
- after a batch rollup is recomputed, mark parent task dirty
- optionally maintain `task_asset_recompute_jobs`
- or recompute task rollup synchronously from batch rollups because task cardinality is small

#### Do not do

- do not keep inventing ad hoc counters only on `task_types`
- do not make dataset-consumption page the home of raw asset portraits
- do not create a second scope definition for task view

Please judge whether this staged preference is correct, or whether we should jump directly to `task_asset_rollups` now because “data will become large eventually”.

---

## Metric Definition Questions That Must Be Settled

Please recommend exact definitions for:

### 1. available / unavailable / not QC'd

User language is product language. Need formal fields.

Candidates:

- available = `final_dataset_status = QUALIFIED`
- unavailable = `final_dataset_status = UNQUALIFIED`
- not finished = `final_dataset_status = PENDING`

or:

- not QC'd = `manual_qc_status = NOT_REVIEWED`
- available-like = `manual_qc_status = MANUAL_PASS`
- unavailable-like = `manual_qc_status = MANUAL_FAIL`

### 2. qualified rate

User said:

> 所有质检过的数据中可用的比例

Possible formulas:

```text
A. QUALIFIED / (QUALIFIED + UNQUALIFIED)
B. MANUAL_PASS / (MANUAL_PASS + MANUAL_FAIL)
C. QUALIFIED / reviewed_count
D. QUALIFIED / episode_count
```

I currently prefer:

- display both:
  - `manual_pass_rate = manual_pass / (manual_pass + manual_fail)`
  - `final_qualified_rate = qualified / (qualified + unqualified)`
- do **not** use total episode count as denominator for “质检过的可用比例”

### 3. duration / frame totals

Should task totals:

- sum only covered values (`> 0`) like batch rollups already do; and
- also expose covered/missing episode counts?

I believe yes, for consistency with batch/global cards.

### 4. inactive task types

Should inactive task types appear in the task asset view?

Current lean:

- default list only active tasks;
- allow admin filter to include inactive if needed.

### 5. unclassified task

`待分类` must remain visible because many batches may still sit there.

### 6. batch decision counts

Should task portrait also show:

- accepted_batch_count
- rejected_batch_count
- pending_batch_count

These are useful, but they are batch-business states, not pure rollup facts.
They can be joined from `batches` at read time.

---

## Scale Assumptions

Current:

- thousands of episodes
- tens of batches
- small number of task types

Future assumption:

- data volume will grow substantially
- more batches per task
- more QC dimensions later
- more dashboards / filters / sorting on aggregate metrics

Therefore:

- avoid designs that force full episode scans for every task-page load;
- prefer designs that scale with batch/task cardinality first;
- keep rebuildability and reconciliation.

But also:

- do not over-engineer into warehouse/OLAP prematurely.

---

## Consistency Requirements

Task view must satisfy:

1. same active scope as global summary and batch list;
2. duration/frame totals reconcilable against sum of child batches;
3. qualified/unqualified/pending reconcilable against child batches or baseline SQL;
4. after batch reassignment from task A to task B:
   - A decreases
   - B increases
   - global totals remain unchanged
5. after episode QC / adjudication changes:
   - batch rollup updates
   - task portrait updates with bounded delay
6. no silent fallback to fake zeros when APIs fail

---

## Suggested API Shape To Review

Not final. Please improve.

### `GET /api/data-assets/tasks`

Query:

- `keyword`
- `include_inactive`
- `page`
- `page_size`
- `sort_by`
- `sort_order`

Response item sketch:

```json
{
  "taskTypeId": "task_type:tudou",
  "taskTypeName": "土豆",
  "isActive": true,
  "batchCount": 12,
  "episodeCount": 1800,
  "qualifiedCount": 900,
  "unqualifiedCount": 300,
  "pendingDatasetCount": 600,
  "reviewedCount": 700,
  "manualPassCount": 500,
  "manualFailCount": 200,
  "manualPassRate": 0.714,
  "finalQualifiedRate": 0.75,
  "totalDurationSec": 12345.6,
  "durationCoveredEpisodeCount": 1500,
  "durationMissingEpisodeCount": 300,
  "totalFrameCount": 222222,
  "frameCoveredEpisodeCount": 1500,
  "frameMissingEpisodeCount": 300,
  "acceptedBatchCount": 8,
  "rejectedBatchCount": 2,
  "pendingBatchCount": 2,
  "refreshedAt": "2026-07-15T13:20:00",
  "stale": false
}
```

### Optional later

- `GET /api/data-assets/tasks/{task_type_id}`
- task detail drawer with top batches under that task
- click-through into existing batch asset list filtered by `taskTypeId`

Note: batch asset list already supports `taskTypeId` filter in current frontend/backend direction, so task -> batch drilldown is natural.

---

## Whether Extra Tables Are Needed

Please give a direct recommendation on these table decisions:

### Decision A

Is `task_asset_rollups` needed in v1?

### Decision B

If yes, should it be rebuilt from:

1. `batch_asset_rollups` (preferred if possible), or
2. raw `episodes`?

### Decision C

Do we need `task_asset_recompute_jobs`, or can task recompute be piggybacked after batch recompute?

### Decision D

Should `task_types.total_batches` / `total_episodes` be:

1. kept as compatibility cache;
2. deprecated;
3. replaced by task rollup fields?

### Decision E

Should accepted/rejected/pending batch counts be stored in task rollup, or joined live from `batches`?

My current lean:

- store only rebuildable episode-derived aggregates in projection;
- join batch decision counts live from `batches` because task/batch cardinality is small and these are business states.

---

## Dirty / Rebuild Triggers To Consider

Events that should affect task portrait:

Must:

- episode enters / leaves active scope
- episode duration/frame changes
- episode manual QC result changes
- episode final dataset status changes
- batch active flag changes
- batch list relation changes
- batch reassigned to another task
- list active/inactive changes
- manual rebuild

Maybe:

- task rename
- task arm_mode change
- task description change

Probably no recompute needed for pure display metadata changes like description.

Especially important:

**batch reassignment across tasks** must correctly move contribution from old task to new task.

If task rollups exist, this is a two-task dirty event.

---

## Recommended Questions For The Next Solver

Please answer in this structure:

### 1. Conclusion

Is the staged Route T1 -> Route T2 approach correct for long-term scale, or should we go directly to task projection now?

### 2. Metric authority

Exact definitions for:

- available
- unavailable
- not QC'd / pending
- qualified rate
- duration/frame coverage

### 3. Schema decision

- need new tables or not?
- if yes, exact proposed tables/fields
- what must not be stored in projection

### 4. Refresh mechanism

- how dirty marking works
- whether task jobs are needed
- rebuild order relative to batch rollups

### 5. API / frontend placement

- recommended API boundaries
- how task view should interact with existing batch/episode views

### 6. Migration order

Lowest-risk implementation sequence.

### 7. Risks

Main failure modes and how to prevent drift between:

- global summary
- batch profile
- task profile

### 8. What not to do

Explicit anti-patterns under this codebase.

---

## What I Already Know / Already Tried

Confirmed completed work:

1. Route C' implemented and verified.
2. Global summary reads from batch rollups.
3. Batch asset list reads from batch rollups + batch business fields.
4. Manifest duration/frame backfill completed for processed episodes.
5. Remaining zero metrics mostly correspond to pure-raw episodes without processed manifest.

Not yet done:

1. No formal task-level asset portrait in `数据总库`.
2. No `task_asset_rollups`.
3. Existing dataset task summary is consumption-oriented and not the desired long-term asset-read model.
4. Metric definitions for “可用 / 不可用 / 未质检 / 合格率” are not fully frozen for the task asset view.

---

## Constraints

- Must stay compatible with existing Route C' decisions.
- Must not break current episode browsing or batch asset views.
- Must keep Chinese product terminology clear, but backend field names can stay English.
- Prefer rebuildable derived data over hidden counters.
- Prefer PostgreSQL-centered design; no need for Kafka/ClickHouse unless strongly justified.
- Current code already has independent `/api/data-assets/*`; task profile should extend that family if possible.
- Historical residual batches outside active lists must remain excluded.
- `task_type:unclassified` must continue to exist and be countable.
- Do not invent fake coverage for raw-only episodes missing manifest metrics.

---

## Unknowns

- Future exact peak scale is unknown, only directionally “will become large”.
- Whether operators care more about final training usability or manual QC progress on the task portrait is not fully frozen.
- Whether task detail drawer is required in first version is optional.
- Whether inactive tasks must appear by default is not frozen.
- Whether one list may later map to multiple business batches in complex ways is still an open longer-term question, but current design already uses explicit `batches.list_id`.

---

## Please Answer

Please act as a senior backend/data-platform architect and review this requirement under the real current codebase constraints.

Specifically:

1. Recommend the best long-term technical route for task-level asset profiling.
2. Tell me whether extra tables are needed now, later, or not at all.
3. Freeze metric definitions for available / unavailable / not QC'd / qualified rate.
4. Propose schema, refresh, API, and migration sequence that stay consistent with Route C'.
5. Call out any part of my staged preference that is weak or over-engineered.

I want a practical architecture recommendation that is correct for future large data volume, but not a premature warehouse redesign.
