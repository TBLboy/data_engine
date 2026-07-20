# Current Session

## Last Updated

- 2026-07-20 11:10 CST（T12 运营面与真实标注闭环完成）

## Current Objective

- 已确认业务逻辑的运行环境落地。统一导出、JSONL 和标注运营面已在 PostgreSQL Compose 真实验收；下一步接入标注资格失效/恢复与持久化统计投影。

## Current Status

### 第一阶段实施计划
- [x] Sub Goal Schema、annotation task、草稿、occurrence、revision 模型与 migration
- [x] 标注资格、任务创建、草稿保存和完成校验领域服务
- [x] 基础 API、权限、编辑锁和 revision 接口
- [x] 人工标注首页、任务列表和 Sub Goal 工作台
- [x] 回归测试、后端/前端/migration 检查（临时全新 SQLite migration 通过；默认历史 SQLite 存在既有 migration drift）

### 当前基线
- `data_label` 跟踪 `origin/data_label`。
- annotation V1 已落地；不修改现有 QC 表单、批次裁决或历史 `UNQUALIFIED` 迁移。
- 已有 project-log 文档修改保留；不修改现有 QC 逻辑。
- 当前导出实验代码尚未提交：它错误地把既有导出接口收紧为仅已完成标注，必须在实施统一导出方案前撤销或重构，不能直接提交。

### 已完成

#### 本轮离线审查与修复（2026-07-18）
- 修复 `business_resolver`：确认缺失后的 raw/processed 恢复会重新置回存在；空 List/缺失 Episode 会同步确认选择性 `EpisodeObject` 缺失；未变化 fingerprint 保留 `qc_ready`。
- 修复 `data_assets`：任务级资产重算等待子批次时退出当前循环，避免同一 pending job 无限重试阻塞 coordinator。
- 修复 `scan_queue`/`scan_worker`：取消请求在 shard 完成、失败重试和业务发布前均有二次检查，不会在取消后提交成功结果。
- 修复 `scan_coordinator`：full 调度先于 smart 调度，避免周日同桶 active job 去重导致 weekly full 被吞掉。
- 切断应用内旧 `scanner.run_minio_scan` 定时入口，v3 coordinator 成为唯一调度扫描实现；Compose 中 coordinator/worker 等待 backend healthy，确保 backend 启动迁移先完成。
- 新增资产重算死循环回归测试。

#### 后端核心服务实现（本轮之前）
- 迁移 `20260717_0026`：scan_mode、priority、active_key、shard 计数器、heartbeat、cancel、created_at/updated_at 追加；新增 `scan_shards`、`scan_prefix_states`；`lists/episode_inventory/episode_objects` source_status/missing 证据列；`episode_inventory` raw/processed 独立状态；`Episode.is_active`；batch/task recompute `rerun_requested`
- `scan_v3_types.py` — snapshot/result dataclasses
- `namespace_discovery.py` — 分层 MinIO 前缀发现
- `list_snapshot.py` — 流式枚举、SHA-256 fingerprint、选择性对象索引
- `business_resolver.py` — List/Batch/Inventory/Episode/Object upsert、raw/processed 独立 missing/recovery、不覆盖人工 QC/批次判定
- `scan_queue.py` — 持久 job/shard 队列、`create_or_get_scan_job`、FOR UPDATE SKIP LOCKED claim、lease/heartbeat/retry/cancel
- `scan_coordinator.py` — 每日 smart/每周 full 调度、discovery 展开、lease 回收、aggregate、资产重算
- `scan_worker.py` — `multiprocessing` 可终止子进程执行、publish 前二次校验、suspect_missing 生成确认 shard、repair-manifest-metrics CLI

#### 本轮（API/前端集成，2026-07-18）
- **`scan_queue.py` 修复**：调度 job ID 重复创建 `IntegrityError` 改为按 `job_id` 回退查找后再查 `active_key`
- **`scan_coordinator.py` 修复**：`_update_prefix_state_from_shard` 跳过已聚合的 shard（`last_success_at >= finished_at`），防止每次 coordinator tick 递增 backoff
- **`scan_worker.py` 修复**：空 snapshot + 未知前缀时拒绝(`RuntimeError`)创建空 List/Batch，而非静默通过 `resolve_list_snapshot` 创建
- **`schemas/qc.py` 拓展**：`IngestScanRequest` 新增 `mode`（`smart`/`full`/`incremental`/`manual_prefix`）、`scope` 向后兼容别名、`prefixes`；`IngestJobSchema` 新增 `mode`、`totalShards`、`succeededShards`、`runningShards`、`failedShards`、`skippedShards`、`errorSummary`、`triggerSource`、`cancelRequestedAt`
- **`payloads.py` 重写**：`serialize_ingest_job` 支持 v3 全状态机（queued/discovering/running/cancelling/succeeded/partially_failed/failed/cancelled）加 legacy 兼容；基于分片计算真实进度（discovery 阶段 0-10%，list 阶段 10-100%，manual_prefix 直接 `succeeded/total`）
- **`qc.py` API 路由**：
  - `POST /database/scan` 切为 `create_or_get_scan_job`（mode scope 冲突校验、prefixes 规范化和合法性检查）
  - `GET /database/scan/{job_id}` — 查询单 job 详情
  - `POST /database/scan/{job_id}/cancel` — 请求取消（调用 `request_cancel`）
  - `POST /database/scan/{job_id}/retry` — 重试失败/timeout shard（调用 `retry_failed_shards`，409 冲突处理）
  - 移除遗留 `_expire_stale_scan_jobs` 和旧 `ScanJob` 手工构造
- **`scan_scheduler.py` 切除**：移除 `_scan_job` 函数及 cron 注册（`daily_scan`）；保留 data assets recompute 和 reconcile
- **`main.py` 移除旧扫描 scheduler**：`startup` 事件不再启动 `start_scheduler()`（已无 `_scan_job`，日志消息改为 `asset recompute scheduler`）
- **`docker-compose.yml` 新增服务**：
  - `scan-coordinator`：单实例，依赖 db healthy，运行 `python -m app.services.scan_coordinator`
  - `scan-worker`：可扩副本（`--scale scan-worker=2`），依赖 db healthy，运行 `python -m app.services.scan_worker`
  - 环境变量通过 YAML 逐服务设置，含 schedule/poll/lease/heartbeat/timeout/confirmation 全部配置
- **前端 `types/qc.ts`**：`IngestJob.status` 扩展为 v3 全状态联合；新增 `mode`、`totalShards`、`succeededShards`、`runningShards`、`failedShards`、`skippedShards`、`errorSummary`、`triggerSource`、`cancelRequestedAt`
- **前端 `api/client.ts`**：
  - `IngestScanRequest` 新增 `mode`/`prefixes`/`scope`
  - 新增 `fetchScanJob(jobId)`、`cancelScanJob(jobId)`、`retryScanJob(jobId)`
- **前端 `database-view.vue`**：
  - 扫描表单：`mode` 选择器（`smart`/`full`/`manual_prefix`）+ `manual_prefix` 出现时显示 Prefixes textarea（每行一个前缀）
  - 点击 `开始扫描` 后调用 v3 `scanDatabase`，显示"扫描任务已创建"而非"扫描完成"
  - 活跃任务自动轮询 `fetchScanJob`（3s 间隔，递归 setTimeout），终态时停止并刷新页面
  - 挂载时从 `ingestJobs` 中查找活跃任务自动开始轮询
  - 任务表新增 shard 进度列（s/r/f/t）、操作列（活跃可取消、failed/partially_failed 可重试）
  - `onBeforeUnmount` 停止轮询 timer
- **前端 `api/mock.ts`**：`ingestJobs` mock 数据补齐全部新增字段，类型检查通过
- **编译/构建验证**：
  - `py -3.12 -m compileall -q app migrations` 静默通过
  - `vue-tsc --noEmit` + `vite build` 通过

### 遗留约束

- `frontend` Docker 构建走 COPY dist 模式，要求本地 `npm run build` 后 Docker build 才会拿到新代码
- 前端 JS 哈希每次构建变化，用户浏览器需要 Ctrl+Shift+R 硬刷新
- 当前外网环境无 PostgreSQL/MinIO，无法运行 coordinator/worker 或执行 SQLite 之外的 ORM 测试
- PostgreSQL `alembic --sql` 无法离线生成全量脚本：历史迁移 `20260623_0003`/后续条件迁移调用 `inspect(bind)`，Alembic mock connection 不支持 inspection；真实在线 PostgreSQL 迁移仍未验收。
- 默认 `backend/data/robot_qc.db` 的 Alembic version 落后但已有 `batches.list_id`，执行全量升级会在历史 `20260715_0023` 报 duplicate column；本轮使用全新 `/tmp/annotation-v1-final.db` 验证完整 migration chain 至 `20260718_0027`。

## Problems And Resolutions

1. `create_or_get_scan_job` 给定 `job_id` 且历史 job 已终态（`active_key=NULL`）时，`IntegrityError` 回退仅查 `active_key` 导致 `None` 匹配失败后重抛异常
   - 解决：先按 `job_id` 查找已有记录再查 `active_key`
2. `_update_prefix_state_from_shard` 每次 coordinator tick 都对所有 succeeded shard 重算，导致 `consecutive_unchanged` 每次 tick 递增 1
   - 解决：当 `state.last_success_at >= shard.finished_at` 时整个跳过
3. 空 snapshot + 未知 MinIO 前缀会通过 `resolve_list_snapshot` 创建全新的空 List 和空 Batch
   - 解决：抛出 `RuntimeError` 让 shard 失败，不产生业务空记录
4. 前端 `vue-tsc` 需要本地 `node_modules`（`npm ci`），否则 `npx vue-tsc` 会因全局 typescript 版本不匹配报 `ERR_PACKAGE_PATH_NOT_EXPORTED`
   - 解决：运行 `npm ci` 后直接用本地 `vue-tsc` 检查

## Next Steps

- 生产内网 PostgreSQL/MinIO 验收：
  - 迁移 `20260717_0026` 执行
  - coordinator + worker 容器部署和健康检查
  - `POST /database/scan` smart/full/manual_prefix 三种模式执行验证
  - 取消、重试、轮询联动
   - lease 回收、确认 shard 执行、资产重算触发

## Annotation V1 Implementation (2026-07-18)

- Added ORM and migration `20260718_0027` for Sub Goal schemas/definitions, annotation tasks, mutable drafts, fixed occurrences, immutable revisions, locks and invalidation state.
- Added domain service and API under `/api/annotations` for active-scope `QUALIFIED` eligibility, task ensure, assignment/public claim, locking, CAS draft saves, completion validation and revision creation.
- Added Vue annotation workbench at `/annotations` with task queue, optional episode preview, schema-driven occurrence editor, task outcome, draft save, completion and lock controls.
- Reviewer task visibility includes unassigned public-claim tasks; assignment and claim transition tasks to `assigned`, and lock acquisition transitions them to `in_progress`.
- Verification: backend compile and mapper configuration pass; annotation routes are present; frontend `npm run build` passes; fresh SQLite `alembic upgrade head` passes through `20260718_0027`.

## Annotation V1 Verification And Handoff (2026-07-18)

- Fixed migration `20260715_0023` so databases that already contain `batches.list_id` can continue the Alembic chain without duplicate-column failure; clean installs keep the original schema and foreign key creation path.
- Added `tests/test_annotations.py` covering published-schema replacement, QUALIFIED active-scope enforcement, idempotent task creation, reviewer lock, row-version CAS, completion validation, immutable revision creation and operational statistics.
- Added `GET /api/annotations/statistics` for role-aware annotation progress counts.
- Viewer access is read-only in the annotation workbench; only admin, qc_manager and assigned reviewers can edit.
- Verification results: annotation service tests 4/4, data-assets tests 11/11, AI QC tests 6/6, backend compile and mapper configuration pass, frontend build pass, SQLite migration from the historical drift database reaches `20260718_0027`.

## Next Cycle Decision

- Keep the existing QC and batch adjudication boundaries unchanged. Annotation remains downstream of `QUALIFIED` episodes and is exported as an optional, immutable Episode enhancement rather than a second export gate.
- The dataset page must show `质检合格 / 完成标注` and row-level annotation status. One export must include every active-scope `QUALIFIED` Episode; completed annotations attach revision/Schema/payload, incomplete annotations remain null.
- Implement `DatasetExportJob` + `dataset_export_items` snapshots before serving production training exports. JSONL package is the training format, CSV is audit-only, and `uncertain` is completed but default-excluded from training.
- Real PostgreSQL/MinIO and browser acceptance remain required before calling the platform production-ready; the running Compose stack currently uses the pre-annotation backend image and the local Playwright Chrome binary is unavailable.

## T12 Annotation Operations Acceptance (2026-07-20)

- Fixed task-type eligibility/ensure queries: `active_qualified_episode_query()` already joins `Batch`; filtering now reuses that join and no longer creates PostgreSQL `DuplicateAlias` failures.
- Added PostgreSQL row locks around annotation claim, assignment, public-claim changes and lock acquisition. Reassigning is allowed only for `pending`/`assigned` tasks without an active editor lock; audit includes old/new reviewer and row version.
- Re-editing an already completed task now explicitly transitions it into a new pending revision cycle on lock acquisition and records a dedicated audit event. Completion creates the next immutable revision.
- Added manager operations to `/annotations`: active QUALIFIED eligibility, task backlog/completion/workload, bounded ensure, Schema draft/publish lifecycle, reviewer assignment and public-claim toggles. Reviewer editor flow remains unchanged.
- Real Compose/PostgreSQL acceptance using `task_type:luobo`:
  - eligibility `169`, initial task count `0`; published Schema `sgs_f09b34db55834e9db2233b645378e333`.
  - manager ensure created three initial tasks plus one 515-frame task for complete-path validation.
  - assigned the validation task to `reviewer01`; lock, draft, required occurrences and completion produced revision `1`.
  - JSONL export job `56`: `episodeCount=169`, `annotationCompletedCount=1`, `trainingDefaultIncludedCount=1`, and its `dataset_export_items` row stores the task/revision/schema snapshot.
  - reviewer re-edit produced revision `2`; export job `56` item remains revision `1`, proving historical export immutability.
- Verification: `tests/test_annotations.py` 7/7, `tests/test_data_assets.py` 11/11, backend compileall, `npm run build`, `git diff --check`, Compose backend/frontend healthy, and browser `/annotations` manager panel/API requests all passed.
- Remaining formal gaps: eligibility invalidation is not invoked after QC/scan changes; annotation statistics are not yet persistent rollups; VLM generation queue is intentionally deferred to T13.
