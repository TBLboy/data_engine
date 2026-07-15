# Problem Brief For AI Assistance

## Audience

This document is intended for another AI model such as GPT to review a proposed technical route for a data-asset architecture upgrade in an internal robot teleoperation data QC platform.

The goal is not to explain the whole project from scratch, but to give enough confirmed context so the next solver can judge whether the proposed route is appropriate for long-term scale.

---

## What I Need Help With

We need to upgrade the platform's `数据总库` page so it can show:

- global data asset summary;
- batch-level data asset profiles;
- correct and explainable duration/frame statistics;
- server-side filtering/pagination;
- a design that still works when data volume becomes much larger in the future.

I already have a tentative long-term technical route, but I want GPT to evaluate whether it is appropriate, whether the schema boundary is correct, and whether there is a better large-scale design under the current constraints.

---

## Current Goal

The immediate product requirement is based on the task brief:

- add top-level cards for total duration and total frame count on the `数据总库` page;
- add a batch-level asset profile section under the Episode list;
- ensure the global summary and batch rows use the same statistics scope;
- keep `qc_status` and `batch_decision` semantically separate;
- avoid N+1 queries;
- choose a route that is acceptable for long-term growth rather than a short-lived patch.

There is also a strong expectation that the data volume will grow significantly, so the architecture decision should not assume the current dataset size will remain small.

---

## Project Background

### Product Positioning

This project is an internal robot teleoperation data QC and training-data asset platform.

Main scope of the platform:

1. Data management:
   scan MinIO object storage, identify lists and episodes, and persist control-plane metadata into PostgreSQL.
2. Data QC:
   combine manual QC and automatic L3 trajectory metrics.
3. Dataset consumption:
   determine which episodes are finally usable for training and export qualified data.

Upstream data collection and raw storage already exist and are not being redesigned here.

### Main Pipeline

```text
TeleDex collection -> MinIO object storage -> platform data management -> QC -> dataset export
```

### Business Phase

Confirmed from project log:

- research and control-plane design are already completed;
- the project is in the implementation/enhancement phase of Robot QC V1 / RDDQF v1.2;
- current work is no longer greenfield architecture discovery, but targeted platform enhancement on an existing codebase.

---

## Environment

- OS: Linux
- Frontend: Vue 3 + TypeScript + Element Plus + Vite + Pinia + Chart.js
- Backend: FastAPI + SQLAlchemy + Alembic
- Database: PostgreSQL
- Object storage: MinIO
- AI helper stack: Ollama / local LLM support exists, but is not central to this requirement

Relevant project path:

- `/home/tbl/Project/data_collect/software`

Relevant requirement document:

- `/home/tbl/下载/Robot_QC_数据总库批次资产画像改造任务说明.md`

---

## Confirmed Architecture Facts

### 1. This project already has a real control-plane layer

This is not a simple app with only `batches` and `episodes`.

The backend already contains a MinIO control-plane model with these tables:

- `lists`
- `episode_inventory`
- `episode_objects`
- `scan_jobs`
- `discovered_prefixes`
- `classification_rules`

These tables describe object-storage discovery, list recognition, episode existence, object roles, and ingest status.

### 2. There is already a separate business batch / episode layer

The main business tables are:

- `batches`
- `episodes`
- `qc_tasks`
- `qc_review_revisions`
- `batch_decision_log`

So the system already has at least three conceptual layers:

1. object-storage control plane;
2. business batch / episode layer;
3. QC / adjudication / dataset-consumption layer.

### 3. Current active business scope is not “all rows in episodes”

The current code already defines an active scope using `Batch` joined with active `ListRecord` rows.

In practice, the platform excludes historical residual batches that do not belong to an active list.

This is important because the new summary cards and batch asset profiles should follow the same scope, not a different ad hoc scope.

### 4. `duration_sec` and `frame_count` already have a persisted source

In the current scan pipeline:

- `manifest.json` is read during scan;
- `manifest.duration` is written into `EpisodeInventory.duration_sec` and `Episode.duration_sec`;
- `manifest.frame_count` is written into `EpisodeInventory.frame_count` and `Episode.frame_count`.

So the current authoritative source for both duration and frame count is the manifest-derived value already persisted to PostgreSQL.

### 5. `frame_count` is manifest-declared frame count, not multi-camera summed frames

This is important because global asset statistics should not accidentally multiply data scale by summing all camera videos together.

### 6. The current `数据总库` page is Episode-centric

The existing `/api/database` endpoint and the `database-view.vue` page are primarily centered around Episode browsing and filtering.

They are not designed as a dedicated aggregated data-asset analysis module.

### 7. There is already a separate dataset-consumption page

The project also has `dataset-management.vue`, which already exposes batch decision summaries and dataset export logic.

However, that page is focused on final training-data usability, not raw/overall asset profiling.

---

## Relevant Existing Data Model

Below is a simplified description of the most relevant current tables.

### Control Plane / Asset Facts

#### `lists`

- represents a recognized data list under MinIO;
- tracks bucket, list prefix, active state, task-type linkage and raw/processed episode counts.

#### `episode_inventory`

- represents one discovered episode in object storage;
- tracks raw/processed prefixes;
- stores `duration_sec`, `frame_count`, `state`, and linkage to ingested business episode.

#### `episode_objects`

- stores per-object metadata under an episode inventory record;
- tracks object role such as `manifest`, `metadata`, `telemetry_npz`, `camera_rgb_video`, etc.

### Business Layer

#### `batches`

- business batch entity;
- stores task type, name, imported time, QC sampling/progress fields, batch decision fields and related counts.

Important current fact:

- `batches` currently does not have a direct `list_id` foreign key;
- the relationship between `Batch` and `ListRecord` is currently inferred by id convention.

#### `episodes`

- stores business episode information;
- includes `duration_sec`, `frame_count`, QC status, reviewer, reason, manual QC state and final dataset state.

### QC / Dataset Layer

#### `qc_tasks`

- current active/manual QC task attempts.

#### `batch_decision_log`

- immutable per-adjudication audit record for batch-level pass/reject decisions.

---

## Current Requirement Summary From The Task Brief

The product/task brief asks for a batch asset profile upgrade around these themes:

1. Add global asset statistics to the `数据总库` page.
2. Add batch-level asset profile rows.
3. Expose duration and frame totals with coverage counts.
4. Keep summary scope and batch-row scope consistent.
5. Support service-side filtering and pagination.
6. Avoid mixing:
   - `qc_status` as process/progress state;
   - `batch_decision` as final batch accept/reject result.
7. Think about long-term scale, not only the current small data volume.

The brief also explicitly asks whether a new database table is needed and emphasizes that the design should be considered from a long-term point of view.

---

## Relevant Current Code / Modules

These files are the main places currently related to this problem:

- `backend/app/models/control_plane.py`
  - `ListRecord`, `EpisodeInventory`, `EpisodeObject`
- `backend/app/models/batch.py`
  - current `Batch` schema
- `backend/app/models/episode.py`
  - current `Episode` schema
- `backend/app/services/scanner.py`
  - MinIO scan, manifest parsing, control-plane + business-episode persistence
- `backend/app/services/payloads.py`
  - active batch / active episode query helpers and `/api/database` payload logic
- `backend/app/services/dataset_service.py`
  - dataset summary/export logic
- `backend/app/api/routes/qc.py`
  - current `/api/database` and dataset-management related endpoints
- `frontend/src/pages/database-view.vue`
  - current data catalog page
- `frontend/src/pages/dataset-management.vue`
  - current dataset-consumption page

---

## Observed Design Constraints

Confirmed from project docs and code:

- TeleDex data format must not be changed.
- Frontend must not access MinIO directly.
- PostgreSQL is the business query source.
- Active/inactive semantics in the control plane matter and must be preserved.
- Existing pages and APIs should not be broken unnecessarily.
- The future data scale is expected to grow, so large-scale behavior matters now.

---

## Current Technical Route Options Considered

### Route A: Keep everything as real-time aggregation on `episodes`

Idea:

- keep using current tables only;
- compute global summary and batch asset rows by runtime `GROUP BY` on `episodes` for every request.

Pros:

- simplest first implementation;
- no new table;
- minimal migration work.

Cons:

- likely acceptable only while the dataset is small;
- repeated aggregation cost grows with data size;
- summary cards and batch list become more expensive over time;
- hard to extend cleanly to more asset dimensions later.

### Route B: Put more aggregate columns directly into `batches`

Idea:

- add more asset-stat fields directly on the `batches` table;
- update them during scan/QC/adjudication.

Pros:

- easy page reads;
- low query cost.

Cons:

- `batches` becomes a mixed entity containing both domain state and growing analytics state;
- future additions such as storage bytes, modality coverage, annotation coverage, trend snapshots and export coverage make the table increasingly messy;
- update triggers spread into many business paths.

### Route C: Facts tables + explicit batch/list relation + separate aggregate stats table + async per-batch recompute

Idea:

- keep existing control-plane and business tables as the only facts/source of truth;
- add an explicit foreign key from `batches` to `lists`;
- add a separate batch-level aggregate stats table;
- make the UI read summary and batch profiles from that aggregate table;
- recompute stats asynchronously per affected batch whenever scan/QC/adjudication changes relevant facts.

Pros:

- much better long-term boundary;
- page reads become stable and cheap;
- summary and batch rows can share exactly the same scope;
- future extensibility is better;
- keeps business entity and reporting entity separate.

Cons:

- requires new schema and backfill;
- requires dirty-marking and recompute orchestration;
- operational complexity is higher than Route A.

---

## Current Recommended Route

My current recommendation is Route C.

### Why I am leaning toward Route C

1. Large-scale growth is treated as a real future condition, not a vague possibility.
2. The project already has a meaningful control-plane layer, so “asset profiling” is no longer a greenfield reporting problem.
3. Keeping aggregated state separate from business entities will age better than bloating `batches`.
4. Summary cards and batch asset lists are read-heavy views and are natural consumers of a derived aggregate table.
5. A deterministic “recompute one batch from facts” strategy is usually more robust than fragile incremental `+1/-1` counters.

---

## Proposed Long-Term Architecture

### 1. Keep existing tables as facts/source of truth

These should remain the authoritative source:

- `lists`
- `episode_inventory`
- `episode_objects`
- `batches`
- `episodes`
- QC/adjudication tables

### 2. Make batch-to-list relationship explicit

Proposed schema change:

- add `batches.list_id` as a foreign key to `lists.id`

Reason:

- today the relationship is derived from id convention;
- for long-term scale and maintainability, explicit linkage is safer for querying, indexing and data repair.

### 3. Add a separate aggregate table

Proposed new table:

- `batch_asset_stats`

Suggested first columns:

- `batch_id`
- `list_id`
- `task_type_id`
- `episode_count`
- `total_duration_sec`
- `duration_covered_episode_count`
- `duration_missing_episode_count`
- `total_frame_count`
- `frame_covered_episode_count`
- `frame_missing_episode_count`
- `reviewed_count`
- `qualified_count`
- `unqualified_count`
- `failure_rate`
- `reject_threshold`
- `qc_status`
- `batch_decision`
- `last_episode_updated_at`
- `refreshed_at`

Notes:

- The table is intended as an aggregate/reporting surface, not the source of truth.
- `qc_status` and `batch_decision` may be copied into this table for query convenience, but the canonical truth still lives in `batches` and `episodes`.

### 4. Read global summary from batch-level aggregate stats

Instead of immediately creating a separate global table, the first global summary can be computed as:

- `SUM(batch_asset_stats.episode_count)`
- `SUM(batch_asset_stats.total_duration_sec)`
- `SUM(batch_asset_stats.total_frame_count)`
- etc.

This keeps global summary and batch list perfectly aligned in scope.

### 5. Use asynchronous per-batch recomputation

Suggested refresh pattern:

1. facts change;
2. mark affected `batch_id` dirty;
3. background worker recomputes that batch from facts;
4. upsert into `batch_asset_stats`.

Events that should mark a batch dirty:

- MinIO scan that changes list/episode inventory or business episode facts;
- episode QC result submission;
- batch adjudication result change;
- batch task-type reassignment if the aggregate table stores `task_type_id`.

Important design preference:

- prefer deterministic “recompute full stats for one batch from facts”;
- do not rely on many scattered incremental counters unless there is a proven need.

### 6. Keep the API boundary separate from `/api/database`

Suggested endpoints:

- `GET /api/data-assets/summary`
- `GET /api/data-assets/batches`

Reason:

- current `/api/database` is Episode-centric;
- the new feature is aggregate-centric;
- separate endpoints preserve a cleaner boundary and avoid one oversized payload.

### 7. Keep statistics scope explicit

Suggested statistics scope:

- active lists + active batches + indexed business episodes in that active scope.

Suggested authority for asset metrics:

- `duration_sec`: manifest-derived persisted field already in DB;
- `frame_count`: manifest-derived persisted field already in DB.

Suggested missing-value semantics:

- duration missing if `duration_sec <= 0`;
- frame missing if `frame_count <= 0`.

### 8. Represent “batch updated time” carefully

Current fact:

- `batches` does not have an `updated_at` column.

Suggested first implementation for profile display:

- use `MAX(episodes.updated_at)` as the effective latest activity time of the batch;
- persist that value into `batch_asset_stats.last_episode_updated_at`.

This avoids inventing a misleading `batches.updated_at` without first defining its exact business meaning.

---

## Suggested Migration Sequence

One reasonable rollout sequence would be:

1. Add `batches.list_id` and backfill it from current implicit mapping.
2. Add `batch_asset_stats`.
3. Write a one-off full backfill job that computes stats for all existing active batches.
4. Add dirty-marking and per-batch recompute logic for future changes.
5. Add `/api/data-assets/summary` and `/api/data-assets/batches`.
6. Update the `数据总库` page to consume those APIs.
7. Later, if needed, introduce higher-level aggregates such as:
   - `task_type_asset_stats`
   - `global_asset_stats`
   - external OLAP/warehouse sync

---

## Known Risks / Weak Points Already Observed In Current Code

### 1. Potential manifest variable issue in scanner

In the current scan loop, `manifest` is used for state derivation, but it is not clearly initialized for every episode before the optional manifest-read branch.

This may not be the main topic of this request, but it matters because duration/frame statistics rely on the scan pipeline being trustworthy.

### 2. Current codebase already has some query patterns that do not scale well

For example, there are places where per-batch counts are obtained with repeated queries or where service logic is more page-oriented than scale-oriented.

This reinforces the need for a cleaner aggregate boundary rather than continuing to build more features directly on top of runtime aggregation.

### 3. Deletion / inactive semantics remain an open long-term concern

The project log already records an open question about how MinIO deletion or disappearance should affect PostgreSQL facts.

This matters because aggregate refresh must eventually align with the project’s final inactive/soft-delete semantics.

---

## Confirmed Constraints

- Do not change TeleDex upstream data format.
- Do not expose MinIO directly to the frontend.
- PostgreSQL remains the business query entry point.
- Preserve existing active/inactive semantics.
- Avoid breaking current QC and dataset-management workflows.
- The solution should be acceptable for future large-scale data growth.

---

## Assumptions

These are working assumptions, not guaranteed truths:

- Batch-level aggregate refresh can be handled by a background worker or scheduled task without introducing unacceptable operational burden.
- Future data growth is large enough that a pure real-time `GROUP BY episodes` design will age poorly.
- The explicit `batches.list_id` relationship is acceptable from a data migration perspective.

---

## Unknowns

- Whether `batch_asset_stats` is the right long-term aggregate boundary, or whether a more event-driven/reporting-oriented architecture is better even now.
- Whether `batches.list_id` should be made mandatory immediately or phased in gradually.
- Whether global summary should remain derived from `batch_asset_stats` or become a dedicated aggregate later.
- How far the project should go now on async orchestration versus keeping the first phase simpler.
- How deletion / inactive semantics in the control plane should eventually propagate into aggregate tables.

---

## Need Help

Please review the proposed route and tell me whether it is appropriate under this project’s real constraints.

I especially want help answering these questions:

1. Is Route C the right long-term direction for this platform?
2. If not, what architecture would you recommend instead under FastAPI + PostgreSQL + MinIO and the current codebase shape?
3. Should we add `batches.list_id` now, or is the current id-derived relation acceptable for longer?
4. Is `batch_asset_stats` the right boundary for long-term scalability, or would you structure the aggregate layer differently?
5. Should global summary be derived from `batch_asset_stats`, or should a separate global aggregate exist from the beginning?
6. How would you design the dirty-marking and per-batch recompute workflow so it stays robust and simple?
7. Which fields belong in `batch_asset_stats`, and which should remain only in `batches` / `episodes`?
8. What migration sequence would minimize risk while preserving compatibility with the current system?

---

## Expected Output From GPT

An ideal answer would include:

1. a judgment on whether the proposed route is suitable;
2. a clearer target architecture if it should be adjusted;
3. a recommended schema boundary;
4. a recompute / refresh strategy;
5. a migration sequence;
6. key tradeoffs and likely failure modes.

Please answer concretely against the current stack and schema shape.

Avoid generic advice like “use caching”, “consider materialized views”, or “add monitoring” unless the recommendation is tied to this exact codebase boundary and includes when it should be introduced.

If you recommend an alternative architecture, please explain:

- why it is better than the proposed Route C in this codebase;
- what tables and services would change;
- how the migration would work from the current implementation.
