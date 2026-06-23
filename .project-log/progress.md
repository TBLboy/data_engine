# Progress Log

## 2026-06-17 14:00 — Project log initialized

- Type: workflow
- Status: validated
- Importance: medium
- Objective: Initialize `.project-log/` structure for TeleDex QC software.
- Work completed: Created `.project-log/` skeleton with minimum required + architecture, hardware, debugging directories.
- Business logic impact: None yet — structure only.
- Problems encountered: None.
- Verification: Directory structure verified.
- Files changed: `.project-log/` (initialized)
- Next steps: Define business logic with user.

## 2026-06-17~06-21 — Business logic design & V1.0 definition

- Type: design
- Status: completed
- Importance: high
- Objective: Define full business logic for robot data QC platform V1.0.
- Work completed:
  - Researched public robot dataset QC strategies (RH20T, LeRobot, RoboMimic, RT-X, RoboCasa, ManiSkill, DROID).
  - Designed data storage architecture: PostgreSQL + local filesystem, Docker Compose orchestration.
  - Designed multi-user access: LAN browser access, admin-created accounts, role-based access (admin/qc_manager/reviewer/viewer).
  - Designed task assignment & audit trail: assign → claim → submit → revision history → audit_event.
  - Designed database tables (field-level): task_types, batches, episodes, qc_tasks, qc_results, qc_review_revisions, review_locks, audit_events, batch_qc_summaries, users.
  - Designed V1.0 API interface spec (REST routes).
  - Defined frontend pages & data flow.
  - Defined V1.0 scope boundary: manual QC only, AutoQC deferred to V2.
  - Wrote all above into `.project-log/business-logic/main.md`, `nodes.md`, `edges.md`, `constraints.md`.
- Problems encountered: None significant.
- Verification: Requirements alignment confirmed with user.
- Files changed: `business-logic/main.md`, `nodes.md`, `edges.md`, `constraints.md`, `requirements.md`
- Next steps: Frontend UI implementation.

## 2026-06-22 — 抽检派发业务逻辑修订

- Type: design
- Status: completed
- Importance: high
- Objective: 将任务派发策略收口为”默认百分比抽检，可选全量派发”，并同步到 V1.0 业务逻辑文档。
- Work completed:
  - 更新 `requirements.md`，明确 V1.0 支持按比例抽检派发或全量派发。
  - 更新 `constraints.md`，固化默认抽检、候选池保留、补派审计、样本口径统计等规则。
  - 更新 `edges.md`，将 ingest→QC 队列链路改为先入候选池，再按派发计划生成任务。
  - 更新 `business-logic/main.md`，同步修正状态流转、标准派发链路、`qc_task`/`batch_qc_summary` 字段、Dashboard/Task Pool/Report 口径、最小交付标准与接口分组。
  - 明确新增接口：`POST /api/qc/batches/{batchId}/dispatch-plan`、`GET /api/qc/batches/{batchId}/dispatch-preview`。
- Problems encountered:
  - 环境无 `apply_patch` 命令，改用内置编辑工具完成文档更新。
- Verification:
  - 已复查核心文档中的派发主链、统计口径和 V1.0 范围表述，已与”默认百分比派发，可选全量派发”保持一致。
- Files changed: `.project-log/requirements.md`, `.project-log/business-logic/constraints.md`, `.project-log/business-logic/edges.md`, `.project-log/business-logic/main.md`
- Next steps: 按新派发模型开始后端 dispatch-plan / dispatch-preview / task assignment 实现，并同步更新前端任务池与 Dashboard 语义。

## 2026-06-22 — 前端抽检派发语义收尾

- Type: implementation
- Status: completed
- Importance: high
- Objective: 将前端页面和数据结构对齐新的抽检派发业务逻辑。
- Work completed:
  - `types/qc.ts`：新增 `DispatchMode`、`DispatchPreview`，扩展 `BatchSummary` 和 `QcTask` 字段（`dispatchMode`、`samplingRatio`、`sampledEpisodeCount`、`completedSampleCount`、`sampleCoverageRate`、`sampleReviewCompletionRate`）。
  - `api/mock.ts`：补齐 `DispatchPreview` mock 数据，`batches`/`qcTasks` 全部按新字段重构。
  - `dashboard.vue`：页面重写为候选总量 / 已抽中样本 / 样本完成率 / 抽检覆盖率口径，批次表格展示派发模式与样本进度。
  - `task-pool.vue`：新增派发计划区（派发模式切换、抽检比例输入、候选池预览卡片），任务队列新增派发模式列，派发规则说明更新。
- Verification: `npm run build` 通过，无新增错误。
- Files changed: `frontend/src/types/qc.ts`, `frontend/src/api/mock.ts`, `frontend/src/pages/dashboard.vue`, `frontend/src/pages/task-pool.vue`
- Next steps: 后端 dispatch-plan / dispatch-preview / task assignment 接口实现。
