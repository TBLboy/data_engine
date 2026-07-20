## 2026-07-20 17:55 CST — T19 night window + export re-verify

- Type: coordinator policy / export acceptance
- Status: **T19 done**; confirmed annotation+export business logic verified on real Compose/PG
- Work:
  - Config: `ANNOTATION_DISCOVERY_ENABLED/TIMEZONE/WINDOW_START/END/DAILY_LIMIT`
  - `is_discovery_window_open`, daily auto-quota on `request_group_id like auto-%`
  - Coordinator still reclaims leases always; discovery gated; manual enqueue unaffected
  - compose + deploy README env docs; default 00:00–06:00 Asia/Shanghai, daily 100
- Tests: `test_annotations` 16/16 (window overnight + daily limit + manual bypass)
- Real evidence:
  - 17:52 CST window_open=False; discover_daytime=0; coordinator log "outside configured window"
  - export `task_type:luobo` JSONL ZIP 169; pending=168 completed=1; job 58 items=169
  - unannotated QUALIFIED still included (no second gate)
- Remaining optional: commit when asked; occurrence quality tuning

## 2026-07-20 17:45 CST — T18c vision + 2-pass JSON acceptance

- Type: backend worker / ollama vision / real acceptance
- Status: **T18c done** — media path + mmproj + draft instruction/occurrences verified on production Compose/PG/Ollama
- Root causes fixed this round:
  1. `scripts/start_ollama.sh` / deploy README still pointed at `models/qwen2.5`; aligned to `Qwen3-VL-32B-Thinking` + dual-FROM mmproj registration (`ensure-model`).
  2. Thinking VLMs dump analysis into `thinking` / prose and exhaust `num_predict` before JSON → empty drafts.
  3. Chat path with `think=false` still often empty content; **`/api/generate` + think=false** returns clean JSON.
- Work:
  - Prompt `subgoal-occurrence-v6` shortened (codes/max only).
  - `call_ollama` prefers JSON-looking content/thinking; optional `think` flag; new `call_ollama_generate`.
  - Worker: pass1 vision chat (`num_predict=8192`, images_b64) → if unusable, pass2 text JSON convert via generate.
  - Publish still blank-only / not `human_modified`.
- Real evidence:
  - task `ann_0f7529ad12b945b49387f3b1571b0f72` job `vlm_7c05f3c09da34793910ff314e5a54c2d` succeeded ~25s.
  - `media_image_count=5`, `media_camera=cam_top.mp4`.
  - draft: `Collect one radish.` / `采集一根萝卜` / `completed_normally` / 2 occurrences.
  - offline `test_annotations` 15/15 OK.
- Remaining: commit T13–T18c when user asks; optional night window; optional occurrence quality tuning.

## 2026-07-20 16:15 CST — T18b MinIO media sampling + Ollama image fallback

- Type: backend worker / media / real acceptance
- Status: media pipeline implemented and verified; vision model mmproj missing so text-only fallback used
- Work:
  - `annotation_frame_sampler.py`: resolve preferred RGB mp4 from inventory, download MinIO, ffmpeg (via `imageio-ffmpeg` static binary) extract JPEGs at sample steps.
  - `annotation-worker` compose env: MinIO credentials; `requirements.txt` + imageio-ffmpeg (apt ffmpeg blocked by offline Debian mirrors).
  - `call_ollama(..., images_b64=...)`; on `image input is not supported / mmproj` auto retry text-only.
  - Cap media frames at 6; record media_* in `annotation_ai_runs.input_summary_json`.
  - Duration probe via ffmpeg stderr when ffprobe absent; optional episode.duration_sec fallback.
- Real evidence:
  - media_image_count=5, camera=cam_top.mp4, sample_steps metadata present.
  - Ollama 500 mmproj → text-only 200 → job `succeeded`.
  - offline tests 15/15.
- Open: deploy vision-capable Ollama model/mmproj (T18c); commit batch when requested.

## 2026-07-20 15:45 CST — T18a occurrence path + publish PG fix

- Type: backend worker / real acceptance
- Status: T18a done (Schema prompt + normalize + blank draft occurrence write); T18b media frames still open
- Work:
  - New `annotation_vlm.py`: `uniform-steps-v1` sample metadata, `subgoal-occurrence-v3` prompt, parse/normalize helpers.
  - Worker publish uses Schema definitions; only blank non-`human_modified` drafts get instruction/outcome/occurrences with `source=vlm_initial`.
  - Fixed PostgreSQL publish crash: `joinedload` + `with_for_update()` on outer joins → lock task row only.
  - `call_ollama(..., format='json')` for structured output; reject meta/placeholder instruction text.
  - Offline: `test_annotations` 14/14 including sample/normalize/nested JSON parse.
- Real Compose/Ollama evidence:
  - `annotation_ai_runs.input_summary_json` includes `frame_count` + `sample_steps` + prompt/sampler versions.
  - Controlled publish: 2 normalized occurrences written; invented codes dropped; `human_modified` blocks overwrite.
- Quality note: without media pixels, live model often returns empty/placeholder JSON; media sampler remains T18b.
- Next: T18b MinIO frame sampling into Ollama; commit batch when user requests.

## 2026-07-20 15:00 CST — T17 frontend VLM generation ops

- Type: frontend ops
- Status: implemented + npm build OK; frontend image rebuild
- Work:
  - types: `AnnotationGenerationJob*` in `qc.ts`
  - client: `fetchAnnotationGenerationJobs` / `enqueueAnnotationGenerationJobs` / `cancel` / `retry`
  - `/annotations` manager panel: queue table, status filter, enqueue limit, cancel/retry actions
- Verification: `npm run build` OK; backend tests still 13/13 + 11/11
- Next: T18 media/occurrence；explicit commit of T13–T17 batch

## 2026-07-20 14:45 CST — T13 real VLM invoke + generation API

- Type: acceptance / bugfix / API
- Status: real Compose/PostgreSQL/Ollama path verified
- Fixes:
  - `discover_eligible_tasks` 原先错误查询 `AnnotationTask` 判断 job 是否存在，导致永不入队；改为按 `annotation_generation_jobs` 幂等创建/跳过。
  - Path2 补齐已有 task 缺 initial job 的补漏；`enqueue_initial_job_for_task` 返回 existing queued/running/succeeded job。
  - Worker：`call_ollama` 返回 `LlmResult`（无 `.parsed`/`.raw_text`）导致发布失败 → 本地 `_parse_vlm_payload` + 安全草稿填充。
  - thinking 模型偶发 content 空：`llm_client` 回退读取 `message.thinking`。
  - 失效时 queued 立即 cancel，running 写 `cancel_requested_at`；publish 前 re-check。
- API：`GET/POST /api/annotations/generation-jobs`、`enqueue`、`cancel`、`retry`。
- 离线：`test_annotations` 13/13（含 claim/complete/idempotent enqueue + invalidate cancel）；`test_data_assets` 11/11。
- 真实验收证据：
  - Ollama `192.168.20.147:11434` / `qwen3-vl-thinking:32b` HTTP 200。
  - jobs：`succeeded>=3`，draft 写入 e.g. `Collect one radish.` / `采集一个萝卜`，`human_modified=false`。
  - `annotation_ai_runs` 有 succeeded/failed 审计行与 duration_ms。
  - statistics `task_type:luobo`：`total=169`（coordinator 全量 ensure）、`eligible=169`、`completed=1`。
  - list API `status=succeeded` 返回 3 条；enqueue 幂等跳过已有 job。
- Remaining: 夜间窗口配置/媒体抽帧/SubGoal occurrence 对齐、前端 VLM 运营面、本批未 commit。

## 2026-07-20 14:20 CST — T13 VLM annotation generation queue

- Type: infrastructure / backend worker
- Status: implemented; Compose deployed; later real VLM invoke acceptance closed in 14:45 entry
- Objective: 持久化 annotation generation 队列、worker、coordinator，与现有资格/统计/导出链路集成。
- Work completed:
  - Migration `20260720_0033`：`annotation_generation_jobs` + `annotation_ai_runs`；claim/retry/cancel/mutating 索引。
  - ORM + models export in `__init__.py`；AnnotationTask.generation_jobs 关系。
  - `annotation_generation_queue.py`：create/claim/heartbeat/complete/fail/cancel/reclaim，GLOBAL_CONCURRENCY_LIMIT=1，mutating job per-task 互斥。
  - `annotation_worker.py`：poll → claim → execute VLM → publish result；eligibility re-check，timeout，heartbeat，cancel 检查。
  - `annotation_coordinator.py`：periodic discovery + lease reclamation。
  - `reconcile_annotation_eligibility()` 失效时同步 cancel pending generation jobs。
  - Compose: `annotation-coordinator` + `annotation-worker` 服务，bridge gateway Ollama 默认。
- Verification: SQLite/PostgreSQL alembic to `0033`；tests + Compose tables。

## 2026-07-20 CST — T14/T15 acceptance closure

- Type: implementation plan
- Status: in progress
- Objective: 在 `data_label` 分支按已确认边界落地数据标注 V1 第一阶段。
- Scope: 仅处理 `final_dataset_status = QUALIFIED` 且位于 `active_list_active_batch_indexed_episodes` 的 Episode；`task_outcome` 在标注阶段填写。
- Explicitly out of scope: 不改现有 QC 表单、批次裁决逻辑、历史 `UNQUALIFIED` 迁移、VLM worker 全流程和自由 Segment 训练标签。
- Plan:
  1. Sub Goal Schema、annotation task、草稿、occurrence、revision 的模型与 migration。
  2. 标注资格、任务创建、草稿保存和完成校验领域服务。
  3. 基础 API、权限、编辑锁和 revision 接口。
  4. 人工标注首页、任务列表和 Sub Goal 工作台。
  5. 回归测试、后端/前端/migration 检查和最终审计。
- Baseline: `data_label` 已跟踪 `origin/data_label`；当前无 annotation 代码或 migration；已有未提交 project-log 文档修改保留。
- Next step: 实现第一阶段数据模型与 migration。

## 2026-07-18 CST — Annotation V1 闭环验证

- Type: verification and handoff
- Status: implemented, tested, ready for next production cycle
- Work completed:
  - `20260715_0023` migration now tolerates historical SQLite databases where `batches.list_id` was created before the migration revision, while preserving clean-install behavior.
  - Added `tests/test_annotations.py`: 4/4 tests pass for schema lifecycle, active-scope qualification, idempotent task creation, lock/CAS, completion and immutable revision, and statistics.
  - Added annotation operational statistics endpoint and corrected viewer workbench behavior to be read-only.
- Verification:
  - `tests/test_annotations.py`: 4/4 passed
  - `tests/test_data_assets.py`: 11/11 passed
  - `tests/test_ai_qc_explain.py`: 6/6 passed, including Ollama-unavailable template fallback
  - backend compile and SQLAlchemy mapper configuration passed
  - frontend `npm run build` passed
  - historical SQLite migration reached `20260718_0027`
- Next step: commit this version, rebuild Compose images, then implement and validate Schema operations, bulk task generation, assignment/workload operations, and the training-export gate.

## 2026-07-20 10:40 CST — T11 Compose/PostgreSQL/真实导出与 Ollama 验收

- Type: verification / production acceptance
- Status: done
- Objective: 把统一导出与 annotation 相关 migration 部署到运行中的 Compose，并完成真实 HTTP + Ollama 验收。
- Work completed:
  - 重建 backend/frontend/scan-coordinator/scan-worker
  - PostgreSQL migration：`20260717_0026 → 20260718_0027 → 20260720_0028`
  - 真实验收：admin 登录；`/api/annotations/statistics`；`/api/dataset/tasks/task_type:luobo/summary`；JSONL 导出 169 条；`dataset_export_items=169`
  - Ollama：本机 `qwen3-vl-thinking:32b` 可用；`/api/ai/explain` source=`llm`，`fallbackUsed=false`
  - 前端产物确认含「质检合格 / 完成标注」「导出 JSONL 包」「是否完成标注」
- Findings:
  - 生产 annotation_tasks 仍为 0；导出增强字段目前全部 `not_created`，符合统一导出语义但运营面未跑通
  - 容器默认 `OLLAMA_BASE_URL=localhost` 不可达，实际 AI 走 GeneralConfig 的 host/port 成功
- Next steps: T12 运营面（Schema 管理、批量 ensure、分配 workload），再核对导出增强字段在真实完成标注后的表现。

## 2026-07-20 11:10 CST — T12 标注运营面与真实 revision/export 闭环

- Type: feature / production acceptance
- Status: done
- Objective: 使生产 QUALIFIED 数据通过 Schema、ensure、派发、reviewer 完成进入统一导出标注增强字段。
- Work completed:
  - 修复 TaskType eligibility/ensure 的重复 `Batch` join，避免 PostgreSQL `DuplicateAlias`；补齐 `Batch` import。
  - assignment/claim/public-claim/lock 状态转换使用 PostgreSQL row lock，减少并发归属覆盖风险。
  - completed task 获取编辑锁时明确进入新 revision 周期，完成后生成下一 immutable revision；历史 export item 不会变更。
  - `/annotations` 增加管理运营区：TaskType pool 指标、bounded ensure、Schema draft/publish、reviewer workload、分配和公共领取。
  - `task_type:luobo` 生产验收：169 eligible；ensure 创建 4 条；`reviewer01` 完成 1 条；JSONL job `56` 有 `annotationCompletedCount=1`、`trainingDefaultIncludedCount=1`，item 固定引用 revision 1 / Schema；重编辑为 revision 2 后 item 仍为 revision 1。
- Verification:
  - `tests/test_annotations.py`: 7/7 passed
  - `tests/test_data_assets.py`: 11/11 passed
  - backend compileall, frontend `npm run build`, `git diff --check` passed
  - Compose backend/frontend healthy，alembic `20260720_0028 (head)`
  - browser manager panel rendered; its dataset/accounts/annotations requests returned HTTP 200 and no console errors
- Next step: T16 eligibility invalidation/recovery hook + persistent annotation rollups, then T13 VLM queue.

## 2026-07-20 13:45 CST — T16a/T16b Compose/PostgreSQL 真实验收

- Type: lifecycle + operational projection / production acceptance
- Status: done (code uncommitted)
- Objective: 完成标注资格状态机与持久化运营投影，并在真实 Compose/PostgreSQL 验证导出/标注链路一致。
- Work completed:
  - T16a: `reconcile_annotation_eligibility()` with explicit `db.flush()` under production `autoflush=False`; batch adjudication and scan-v3 list publish call it in-transaction.
  - Invalidation: `work_status=invalidated`, preserve prior status, clear lock/public claim, keep drafts/revisions/export history.
  - Restoration: no new task; prior `in_progress` becomes `assigned`/`pending` without lock resurrection.
  - T16b: `task_annotation_rollups` + `reviewer_annotation_rollups`; migrations `20260720_0029`–`20260720_0032`.
  - Statistics API preserves historical `total`/`byStatus`/`completed`, and adds `activeTaskCount`/`eligibleEpisodeCount`/`activeCompletedCount` with coverage over active QUALIFIED scope.
  - Frontend operations KPI and invalidated read-only UX; lock refresh 30s.
- Verification:
  - offline: `test_annotations.py` 11/11; `test_data_assets.py` 11/11; SQLite alembic to `20260720_0032`; compileall; `npm run build`; `git diff --check`.
  - Compose rebuild: backend/frontend/coordinator/worker healthy; PostgreSQL head `20260720_0032`.
  - HTTP `task_type:luobo`: statistics `{total:4, activeTaskCount:4, eligibleEpisodeCount:169, completed:1, activeCompletedCount:1, byStatus:{pending:3,completed:1}}`; eligible `{169,4,165}`; SQL fact match.
  - PostgreSQL rollback-only lifecycle: in_progress+lock → invalidated → assigned; eligibility/stats/workload consistent; no production pollution.
- Next step: commit this batch when requested; then T13 VLM queue / T14 Ollama defaults / T15 export history slimming.

## 2026-07-20 11:25 CST — T16a 标注资格失效/恢复接入

- Type: lifecycle consistency / regression fix
- Status: implemented and tested; later accepted under 13:45 entry
- Objective: 让已有 annotation task 在 QC 裁决或 scan-v3 active scope 变化后，严格随 canonical active-scope QUALIFIED 资格失效或恢复，不影响 immutable revision 历史。
- Work completed:
  - Added bounded `reconcile_annotation_eligibility()` for existing tasks, using Episode/List scope plus canonical `active_qualified_episode_query()` rather than duplicating qualification rules.
  - Invalidated tasks retain their previous status, disable public claim, release an active editor lock, increment the CAS version and emit audit evidence. Recovered tasks restore that previous status and clear invalidation metadata; neither path creates a task or alters revisions.
  - Integrated reconciliation into every `batch_adjudication.adjudicate_batch()` outcome after final episode status updates and before its commit.
  - Integrated reconciliation into scan-v3 `_publish_list()` before shard completion/commit, covering List or Episode soft-deactivation and recovery performed by `business_resolver`.
  - Replaced second-granularity batch-decision audit IDs with UUID IDs after a back-to-back adjudication regression test exposed a collision.
- Verification:
  - `tests/test_annotations.py`: 10/10, including empty bounded scope, direct QUALIFIED departure/recovery, and `ACCEPTED -> REJECTED -> ACCEPTED` batch adjudication.
  - `tests/test_data_assets.py`: 11/11.
  - backend `compileall`, frontend `npm run build`, `git diff --check` passed.
- Next step: implement T16b persistent annotation rollup, then deploy/rebuild Compose and verify actual QC and scan scope state changes against PostgreSQL.

## 2026-07-20 10:25 CST — JSONL 数据包导出完成

- Type: feature
- Status: implemented, tested
- Objective: 完成统一导出的 JSONL 训练主产物格式。
- Work completed:
  - `format=jsonl` 生成 zip 包：`manifest.json` + `episodes.jsonl` + `schemas.json`
  - manifest 记录门禁、计数、training default policy、文件 hash
  - 前端增加「导出 JSONL 包」按钮，下载扩展名为 `.zip`
  - 回归测试覆盖包内容与 schema 快照
- Verification: annotation 7/7、compile、frontend build 通过
- Next steps: commit 本批；T11 容器/PostgreSQL 真实验收。

## 2026-07-20 10:15 CST — 统一 QUALIFIED 导出主链路落地

- Type: feature
- Status: implemented, tested, ready to commit
- Objective: 将错误的“必须完成标注才导出”重构为统一质检合格数据导出，并补齐标注增强字段与 export item 快照。
- Work completed:
  - `DatasetExportService` 导出全部 active-scope QUALIFIED Episode；未标注不阻断。
  - 导出行增加 `annotationCompleted` / `annotationStatus` / `trainingDefaultIncluded` / revision / Schema / payload。
  - 新增 migration `20260720_0028`、`DatasetExportItem`；`record_export` 事务内写入 item 快照。
  - 前端卡片改为「质检合格 / 完成标注」；Episode 列表增加是否完成标注与标注状态列。
  - 回归测试覆盖无标注导出、完成标注导出、历史 item 在新 revision 后不变。
- Verification:
  - `tests/test_annotations.py` 6/6
  - `tests/test_data_assets.py` 11/11
  - backend compileall 通过
  - frontend `npm run build` 通过
- Deferred:
  - 独立 JSONL zip（manifest/episodes/schemas）作为 T05 后续
  - Compose/PostgreSQL/MinIO 真实验收作为 T11
- Next steps: 正式 commit 本批，再做 JSONL 数据包与容器验收。

## 2026-07-20 10:02 CST — 代码进度盘点 + task-list 建立

- Type: planning / progress audit
- Status: done for audit; implementation next
- Objective: 对照统一导出业务逻辑盘点代码落地进度，建立可执行 task-list，commit 备份后再改代码。
- Work completed:
  - 审计确认 Annotation V1 主链路已完成；统一导出业务逻辑文档已收口。
  - 确认当前 WIP 导出实现方向错误：强制 completed annotation 才允许导出，与正式规则冲突。
  - 新建 `.project-log/task-list.md`，列出 T00–T12，明确 done / wrong / todo 与验收标准。
- Next steps: T01 commit 备份 → T02 重构统一 QUALIFIED 导出门禁。

## 2026-07-20 CST — 统一质检合格数据导出业务逻辑收口

- Type: business logic decision
- Status: confirmed, implementation pending
- Objective: 消除“普通导出”与“带标注训练集导出”是否应为两个入口的歧义，确定 QC -> 标注 -> 训练数据消费的统一数据集语义。
- Decision: 保留一套统一的质检合格数据导出。范围为 active scope 内全部 `final_dataset_status = QUALIFIED` Episode；标注完成度作为 Episode 增强字段导出，不构成排除未标注 Episode 的第二道门禁。
- Business logic impact:
  - 训练数据集卡片改为“质检合格 / 完成标注”，完成标注须同时满足 `work_status=completed` 与当前 immutable revision 存在。
  - 未完成标注的数据导出基础 QC/资产信息，`annotation_completed=false`，annotation/revision/Schema/payload 为 `null`。
  - 已完成项导出 immutable revision、Schema 和 `task_outcome`；`failed` 默认训练包含，`uncertain` 完成但默认训练排除。
  - `DatasetExportJob` + `dataset_export_items` 保存每条 Episode 的历史快照；导出 worker 不得重读当前草稿。
  - 主训练产物为 JSONL + manifest + Schema 快照，CSV 仅供审计；LeRobot 经转换器产生。
- Problems encountered: 先前实验曾将现有唯一导出接口收紧为已完成标注门禁，会破坏既有普通 QC 合格数据导出语义，因此未提交。
- Resolution: 已确认采用统一导出与可选标注增强模型；实验代码必须重构或撤销后才能继续实现。
- Verification: 已审阅并更新 `annotation-v1-final-decisions.md`、`annotation-v1.md`、`annotation-sub-goals-v1.md`、`main.md`、`constraints.md`、`decision-records.md` 与 `current-session.md`。
- Unverified items: API、数据表 migration、导出 worker、前端列/卡片和真实 PostgreSQL/MinIO 链路尚未实现。
- Next steps: 将未提交的错误门禁实验重构为统一导出；新增 job/item 快照 schema、JSONL manifest 输出、行级标注状态和回归测试。

## 2026-07-18 CST

- Type: feature
- Status: implemented, compiled, frontend built
- Importance: critical
- Reusable: yes
- Objective: 扫描入库 v3 API + 前端集成落地，完�?POST/GET/cancel/retry 端点、前端口模式/进度/操作联动，遗�?3 个后�?bug 修复�?- Work completed:
  - **bugfix: `create_or_get_scan_job` 第二次调度相�?job_id + `active_key=NULL` �?`IntegrityError`** �?改为先按 `job_id` 回退查找，再�?`active_key` 匹配
  - **bugfix: `_update_prefix_state_from_shard` 每次 coordinator tick 递增 backoff** �?跳过 `last_success_at >= finished_at` �?shard
  - **bugfix: �?snapshot + 未知前缀拒绝创建空业务记�?* �?抛出 `RuntimeError` 而非静默通过 `resolve_list_snapshot`
  - **schemas/qc.py 拓展**：`IngestScanRequest` 新增 `mode`（smart/full/incremental/manual_prefix）、`prefixes`；`IngestJobSchema` 新增 `mode`、shard 计数器（total/succeeded/running/failed/skipped）、`errorSummary`、`triggerSource`、`cancelRequestedAt`
  - **payloads.py 重写**：`serialize_ingest_job` 支持 v3 全状态机（queued/discovering/running/cancelling/succeeded/partially_failed/failed/cancelled�? legacy 兼容；基于分片计算进度（discovery 0-10%，list 10-100%�?  - **API路由(qc.py)**：`POST /database/scan` 切为 `create_or_get_scan_job`（mode/scope/prefixes 校验），新增 `GET /database/scan/{id}`、cancel、retry 端点；移除遗�?`_expire_stale_scan_jobs` 和旧 `ScanJob` 手工构�?  - **scan_scheduler.py 切除**：移�?`_scan_job` 函数�?cron registration；保留资产重算与 reconcile
  - **main.py 移除旧扫�?scheduler**：startup 不再启动 `start_scheduler()`（已�?`_scan_job`�?  - **docker-compose.yml 新增服务**：`scan-coordinator`（单实例�?+ `scan-worker`（可扩副本），依�?db healthy
  - **前端类型/api**: `IngestJob` 拓展 v3 状�?字段；新�?`fetchScanJob`/`cancelScanJob`/`retryScanJob`
  - **前端 database-view.vue**: 扫描表单 `mode` 选择器（smart/full/manual_prefix�? 前缀 textarea；扫描调用改为创建任务而非等待完成�?s 自动轮询 fetchScanJob（递归 setTimeout）；shard 进度列；操作列（active 可取消，failed 可重试）；`onBeforeUnmount` 停轮�?  - **前端 mock.ts**: mock 数据补齐全部新增字段
- Business logic impact:
  - v3 扫描正式成为唯一扫描实现，legacy `scanner.py` 已从 scheduler 断开
  - 前端一键扫描改�?创建任务→轮询进�?模式，不再阻塞等�?  - 用户可查�?shard 级进度，主动取消/重试
  - 三种扫描模式（smart/full/manual_prefix）提供不同粒度的用户控制
- Problems encountered:
  - `create_or_get_scan_job` 给定终�?job_id 后按 `active_key IS NULL` 查找失败
  - `_update_prefix_state_from_shard` �?last_success_at 防护，每 tick 递增 backoff
  - �?snapshot + 未知前缀静默创建空业务记�?  - 前端 `vue-tsc` 依赖本地 `node_modules`，全局 typescript 版本不匹�?- Resolution:
  - 三点 backend bug 均已在本次修�?  - 前端运行 `npm ci` 后使用本�?`vue-tsc` 检�?- Verification:
  - `py -3.12 -m compileall -q app migrations` 静默通过
  - `vue-tsc --noEmit` + `vite build` 通过
- Files changed:
  - `backend/app/services/scan_queue.py`
  - `backend/app/services/scan_coordinator.py`
  - `backend/app/services/scan_worker.py`
  - `backend/app/schemas/qc.py`
  - `backend/app/services/payloads.py`
  - `backend/app/api/routes/qc.py`
  - `backend/app/services/scan_scheduler.py`
  - `backend/main.py`
  - `deploy/docker-compose.yml`
  - `frontend/src/types/qc.ts`
  - `frontend/src/api/client.ts`
  - `frontend/src/pages/database-view.vue`
  - `frontend/src/api/mock.ts`
  - `AGENTS.md`
  - `.project-log/current-session.md`
  - `.project-log/progress.md`
- Next steps:
  - 补写 SQLite 离线单元测试（queue state machine、coordinator expansion、worker publish、serializer�?  - 生产内网 PostgreSQL/MinIO 验收：migration 执行、coordinator/worker 容器部署、三种模式扫描验证、取�?重试/轮询联动、lease 回收、确�?shard 执行、资产重算触�?
## 2026-07-17 CST

- Type: architecture decision
- Status: validated and frozen
- Importance: critical
- Reusable: yes
- Objective: 基于真实生产数据和现有代码，把扫描入库优化从 v2 升级为可直接实施、覆盖每日自�?性能扩展/失败恢复/删除同步/一键操作的 v3 正式主干�?
- Work completed:
  - 审计当前 `scanner.py`、控制面模型、线程队列、APScheduler、扫�?API、MinIO client 和扫描外键关系�?
  - 查询生产 PostgreSQL�?8 active List�?,987 Inventory、约 2,909,780 �?`episode_objects`；确�?49 个一�?List�? 个二�?List�?
  - 确认最近两个旧扫描停在 `classifying`，瓶颈不只是 MinIO 网络，还包括全量内存、逐对�?ORM 和部分提交�?
  - 创建 `docs/scan-architecture-final-plan-v3.md`，将 v2 标记为被替代�?
  - 固化每日 smart/每周 full、任意深�?namespace discovery、List shard、独�?coordinator/worker、可终止子进程、Episode 指纹、选择性对象索引、原子发布和二次确认软删�?恢复�?
  - 关闭 Q-20260623-004、Q-20260624-008、Q-20260624-009、Q-20260624-010�?
  - 将五项用户目标写成正式能力合同和验收标准�?
- Business logic impact:
  - v3 替代 v2，成为唯一扫描实现依据�?
  - `scan_jobs` 改为原地演进；废弃重命名旧表并新�?BIGINT 主键的方案�?
  - `episode_objects` 改为选择性关键对象索引；bulk frame 使用 Episode 聚合指纹�?
  - 删除同步采用两次独立成功扫描确认、软失活和自动恢复，失败 shard 不得产生缺失证据�?
- Problems encountered:
  - v2 基于�?10 万对象估算，与当前约 291 万对象索引严重不符�?
  - v2 �?`scan_jobs` 重建方案与现有多张表的字符串扫描 ID 外键冲突�?
  - 当前单调 Episode state 无法表达关键对象删除后的 readiness 降级�?
- Resolution:
  - 以真实库重定方案边界；保留历史扫描主键；增加当前 state + max_observed_state；以选择性索引和 Episode fingerprint 控制数据库规模�?
- Verification:
  - 已通过代码与数据库查询交叉验证现状和外�?路径层级约束�?
  - 已人工检�?v3 五项能力均有执行链、失败边界和验收标准�?
  - 本次只固化业务逻辑，未修改运行代码、未执行 v3 扫描�?
- Files changed:
  - `docs/scan-architecture-final-plan-v3.md`
  - `docs/scan-architecture-final-plan-v2.md`
  - `AGENTS.md`
  - `.project-log/business-logic/main.md`
  - `.project-log/business-logic/decision-records.md`
  - `.project-log/business-logic/constraints.md`
  - `.project-log/business-logic/graph.md`
  - `.project-log/business-logic/nodes.md`
  - `.project-log/business-logic/edges.md`
  - `.project-log/business-logic/open-questions.md`
  - `.project-log/current-session.md`
  - `.project-log/progress.md`
- Next steps:
  - 启动 v3 Step 0，只�?census 和旧扫描性能基线；之后进�?schema migration �?`business_resolver.py` 抽离�?

## 2026-07-15 CST

- Type: decision
- Status: validated
- Importance: high
- Reusable: yes
- Objective: 在不开始新的代码改动的前提下，对照真实模型与现有命名，把“数据总库资产画像升级”的最终业务逻辑、正式对象和统计口径彻底固化�?`.project-log`，作为后续实现的唯一业务依据�?

- Work completed:
  - 审阅“数据总库批次资产画像改造任务说明”、现有代码模型、当前迁移命名，以及 GPT 输出的《Robot_QC_数据资产架构升级分析报告》，确认长期路线采用 Route C'�?
  - 将正式决策写�?`.project-log/business-logic/decision-records.md`，并把过渡期的“命名候选”收口为正式对象：`batches.list_id`、`batch_asset_rollups`、`batch_asset_recompute_jobs`�?
  - 更新 `.project-log/business-logic/main.md`，补充正式数据对象、统一统计作用�?`active_list_active_batch_indexed_episodes`、`frame_count` 定义、投影层边界、独�?`/api/data-assets/*` 路径等关键约束�?
  - 更新 `.project-log/business-logic/graph.md` / `nodes.md` / `edges.md`，把该升级路线在逻辑图谱中收口为固定边界，而不是继续停留在泛化描述�?
  - 更新 `.project-log/business-logic/constraints.md`，把“独立资�?API”“不再以 `/api/database` 做长期聚合主路径”“failure_rate 不在投影层重定义”等稳定约束单独写清�?
  - 更新 `.project-log/current-session.md`，将当前会话状态收束为“仅更新 project-log，不开始新的代码改动”�?

- Business logic impact:
  - 数据总库长期正式方案已经确定，不再继续采用“现�?Episode 明细接口上堆实时聚合”的演进路径�?
  - 后续代码实现必须�?`batches.list_id` + `batch_asset_rollups` + `batch_asset_recompute_jobs` + `active_list_active_batch_indexed_episodes` 为边界，任何新方案若偏离该路线，需要先重新更新 project-log 决策记录�?

- Problems encountered:
  - GPT 报告中的个别字段类型和当前代码不完全一致，例如 `lists.id` 在真实代码中是字符串主键，不是数值主键，因此 project-log 固化时已按真实代码口径修正理解�?
  - 现有日志中“数据画像”仍残留“候选命�?/ 待实�?/ 继续讨论”类表述，若不先收口，后续实现阶段容易出现文档互相矛盾�?

- Resolution:
  - 所有固化内容均以当前仓库真实模型、扫描逻辑和页面结构为准；�?GPT 报告作为参考分析，而不是原样照搬�?
  - 对不属于最终业务逻辑的细节不做过度承诺，只固化正式边界、正式对象、正式口径与正式职责分层�?

- Verification:
  - 已人工核�?`main / decision-records / constraints / graph / nodes / edges / current-session / progress` 之间口径一致�?
  - 本次未开始新的代码改动，仅更新业务逻辑文档�?

- Files changed:
  - `.project-log/business-logic/decision-records.md`
  - `.project-log/business-logic/main.md`
  - `.project-log/business-logic/graph.md`
  - `.project-log/business-logic/nodes.md`
  - `.project-log/business-logic/edges.md`
  - `.project-log/business-logic/constraints.md`
  - `.project-log/current-session.md`
  - `.project-log/progress.md`

- Next steps:
  - 在已固化的业务逻辑基础上，等待用户明确开始编码后，再进入数据总库资产画像升级实施：先冻结统计口径与基�?SQL，再�?`batches.list_id`、`batch_asset_rollups`、`batch_asset_recompute_jobs` 与自动重算链路推进�?

## 2026-07-10 14:35 CST

- Type: bugfix
- Status: resolved, verified
- Importance: critical
- Reusable: yes
- Objective: 修复"申请重新质检" Internal Server Error �?audit_events 表两列宽度溢�?

- Root cause:
  - **`detail` �?*：模型定�?`String(500)`，生�?DB 实际�?`VARCHAR(64)`（历史漂移）。复检 audit detail 字符�?65 字节超限
  - **`id` �?*：模�?+ baseline migration 均定�?`String(64)`，但复检 audit ID 格式 `audit_rereview_req_{episode_id}_{timestamp}` = 67 字符，天然超�?
  - 另：reviewer 历史任务池调用未定义�?`format_time()` 导致 NameError

- Work completed:
  - 新增 `format_time(dt)` helper 函数
  - DB 直接执行 `ALTER TABLE audit_events ALTER COLUMN detail TYPE VARCHAR(500)` �?`ALTER COLUMN id TYPE VARCHAR(128)`
  - 模型 `audit.py` �?`id` 列从 `String(64)` 改为 `String(128)`
  - Dockerfile 改为 `start.sh` 启动脚本，自动在容器启动时执�?`alembic upgrade head`
  - 排查过程确认：其�?audit 事件（claim/submit/dispatch 等）ID 均在 61 字符以内，不受影响。只�?rereview 三种事件 ID 前缀过长

- Problems encountered:
  - Alembic `op.alter_column` / `op.execute` 在容器内未生效（疑似 Docker 层缓存导�?migration 文件未进镜像�?
  - `_audit_detail` 临时截断方案误伤 `_active_lock_owner` 函数体，已通过 git checkout 撤回
  - 初始排查方向错误——一直聚�?`detail` 列，实际第二次报错是 `id` �?

- New deployment risk analysis:
  - `detail` 列：新机部署 **不会** 遇到此问题（baseline migration 已创建为 500，当前环境漂移是孤立问题�?
  - `id` 列：新机部署 **�?* 遇到此问题（baseline migration 20260623_0001 仍为 64）。目前模型已修正�?128，但 baseline migration 未同步更新——新机初始化�?baseline 建表�?`id` 仍为 64，需追加 migration 或提前修�?baseline

- Business logic impact: 无新�?

- Resolution:
  - `docker exec` �?DB 容器直接执行 ALTER TABLE 绕过所有缓存和 Alembic 机制
  - `git commit` 包含 format_time helper、模�?id 列修正、Dockerfile start.sh 改�?

- Verification:
  - DB: `detail` = VARCHAR(500)、`id` = VARCHAR(128)
  - Backend compile OK，容�?healthy
  - 浏览器：复检申请不再�?Internal Server Error

- Files changed:
  - `backend/app/api/routes/qc.py`
  - `backend/app/models/audit.py`
  - `backend/Dockerfile`
  - `backend/start.sh` (new)

- Next steps:
  - 同步修改 baseline migration `20260623_0001` �?`audit_events.id` �?64 �?128，确保新机部署零问题
  - 继续浏览器端到端验收 reviewer 双卡�?+ 申请重检 + admin 审批 + admin 认领 done
## 2026-07-10 17:45 CST

- Type: deployment
- Status: deployed, verified
- Importance: high
- Reusable: no
- Objective: 部署本轮全部变更到生产容器�?
- Work completed:
  - `docker compose up --build -d backend frontend` 重建并启动，backend healthy、frontend running�?
  - `alembic upgrade head` 成功将数据库�?20260708_0018 升级�?20260710_0019（新�?`qc_rereview_requests` 表）�?
  - 修复了两处构建失败：import 缺失 `ReviewerCurrentTasksPayloadSchema` / `ReviewerHistoryTasksPayloadSchema`；删除重复的 rereview 路由代码块�?
- Business logic impact: 无新增，本轮仅部署验证�?
- Problems encountered:
  - 首次 backend 构建启动报错 `NameError: ReviewerCurrentTasksPayloadSchema is not defined` �?import 遗漏�?
  - 再次启动报错 `RereviewRequestItemSchema is not defined` �?文件中有 linter 产生的重复路由块使用了未导入�?schema 和旧 URL�?
- Resolution:
  - 补充 `ReviewerCurrentTasksPayloadSchema`、`ReviewerHistoryTasksPayloadSchema` import�?
  - 删除重复的旧 rereview 路由块（lines 924-1050），保留末尾我手写的版本�?
- Verification:
  - `docker compose ps backend frontend` 确认 backend Up (healthy)、frontend Up�?
  - alembic history 确认 head = 20260710_0019�?
- Files changed: `backend/app/api/routes/qc.py`（import 补全 + 删除重复代码�?
- Next steps: 浏览器端到端验收 reviewer 双卡�?/ 申请重检 / admin 审批 / admin 认领 done�?

## 2026-07-10 17:30 CST

- Type: feature
- Status: implemented, compiled
- Importance: high
- Reusable: yes
- Objective: 兑现 reviewer 当前/历史任务池、admin 接管 done、重新质检申请与审批的完整闭环�?
- Work completed:
  - 后端 claim/submit/release 状态机收口：reviewer 仅可认领 assigned+派发给自�?的任务；admin 可认�?new/assigned/done �?active 任务；admin 认领 done 时执�?reopen（episode 重置�?in_review/pending）�?
  - release 仅允�?in_review 状态；submit 仅允�?active+in_review+本人锁�?
  - 新增 `QcRereviewRequest` 模型 + migration `20260710_0019_qc_rereview_requests.py`�?
  - 新增后端路由：POST `/qc/episodes/{id}/rereview-request`、GET `/admin/rereview-requests`、POST `/admin/rereview-requests/{id}/approve`、POST `/admin/rereview-requests/{id}/reject`�?
  - 新增后端路由：GET `/reviewer/tasks/current`、GET `/reviewer/tasks/history`（分页，history �?hasPendingRequest）�?
  - manual-qc context 新增 viewMode/canClaim/canSubmit/taskStatus 权限标志�?
  - 前端 `task-pool.vue` reviewer 改为双卡片独立分页：我的任务清单 + 历史任务清单�?
  - 前端 `task-pool.vue` 历史�?`申请重新质检` 按钮已启用，支持填写原因提交申请�?
  - 新增 `rereview-approvals.vue`（admin/qc_manager 审批页），支持批�?拒绝并补备注�?
  - 路由 + 侧边栏菜单已接入 `rereview-approvals`�?
  - 前端 `manual-qc.vue` claim/submit 按钮改为受后端权限标志控制；历史查看模式加提�?alert�?
- Business logic impact: 任务状态机与角色权限规则已落地到代码。reviewer 当前池不再含 done，done 只能通过审批流重新分配�?
- Problems encountered:
  - build 首次失败：`rereview-approvals.vue` 引入了未使用�?`computed`�?
- Resolution: 移除 `computed` import 后重 build 通过�?
- Verification:
  - Python `py_compile` 全部通过�?
  - `npm run build` 通过，产�?`rereview-approvals-CwwoPixG.js`、`task-pool-CzSt90lE.js` 等新 chunk�?
- Unverified items:
  - 需要在生产/测试环境执行 `alembic upgrade head`（升级到 20260710_0019）�?
  - 需要浏览器端到端验�?reviewer 双卡�?+ 申请重检 + admin 审批 + admin 认领 done 完整路径�?
- Files changed:
  - `backend/app/api/routes/qc.py`
  - `backend/app/models/qc.py`
  - `backend/app/models/__init__.py`
  - `backend/app/schemas/qc.py`
  - `backend/app/services/payloads.py`
  - `backend/migrations/versions/20260710_0019_qc_rereview_requests.py`
  - `frontend/src/api/client.ts`
  - `frontend/src/components/AppLayout.vue`
  - `frontend/src/pages/manual-qc.vue`
  - `frontend/src/pages/rereview-approvals.vue`
  - `frontend/src/pages/task-pool.vue`
  - `frontend/src/router/index.ts`
  - `.project-log/business-logic/main.md`
  - `.project-log/business-logic/decision-records.md`
  - `.project-log/debugging/known-issues.md`
  - `.project-log/progress.md`
  - `.project-log/current-session.md`
- Next steps: 执行 migration + Docker 部署后做浏览器验收测试�?

## 2026-07-10 15:10 CST

- Type: decision
- Status: validated
- Importance: high
- Reusable: yes
- Objective: 明确 reviewer 当前任务�?/ 历史任务池、admin 接管 assigned/done 任务、claim 权限�?reopen 语义，作为下一阶段代码实现的正式业务规则�?
- Work completed:
  - 审计现有 `QcTask` / `Episode` / claim / release / submit / task-pool 链路，确认当前任务池�?`done` 混入 reviewer 当前列表、reviewer 可认领未派发任务、`done` 缺少清晰阻断�?reopen 规则�?
  - 与用户确认新的目标业务逻辑：reviewer 当前任务池只保留 `assigned/in_review`；历史任务池单独展示已完成历史记录；admin 允许直接接管 `done`，且该动作明确语义为 `reopen + ownership transfer`�?
  - 将新规则细化写入 `.project-log/business-logic/main.md`，补齐角色行为、任务池定义、claim/release/submit 约束、admin reopen done 的状态重置要求、前端页面改造点�?
  - �?`.project-log/business-logic/decision-records.md` 记录正式决策；新�?`.project-log/debugging/known-issues.md` 记录现状漏洞与修复目标，供后续实现时逐条对照�?
- Business logic impact: 主干业务逻辑已更新；后续实现必须遵守“任务池视图靠查询区分、admin 认领 done = 正式 reopen”规则�?
- Problems encountered:
  - 现有代码�?`is_active` 与任务池视图语义容易混淆�?
  - 如果历史任务池只依赖当前 `QcTask.status='done'`，admin 接管 done 后旧 reviewer 历史记录可能消失�?
- Resolution:
  - 明确 `is_active` 只表示当前有效任务尝试，不再承担“当前池/历史池”语义�?
  - �?reviewer 历史任务池定义为“已完成历史记录 / revision 视图”，而不是简单复用当�?active task 查询�?
- Verification:
  - 已通过代码审计确认相关后端/前端入口与状态机现状；本次仅更新业务逻辑文档，未改代码�?
- Unverified items:
  - 业务规则已确认，但尚未真正改动后端接口、前端页面与数据库查询逻辑�?
- Files changed:
  - `.project-log/business-logic/main.md`
  - `.project-log/business-logic/decision-records.md`
  - `.project-log/debugging/known-issues.md`
- Next steps: 按新业务规则实施后端 claim/release/submit 权限收口、reviewer 当前/历史任务池分页接口、manual-qc 权限模式与前端双卡片页面改造�?

## 2026-07-08 19:25 CST

- Type: feature + infrastructure + bugfix
- Status: deployed, verified
- Importance: high
- Reusable: maybe
- Objective: �?AI 质检助手推进�?QC Agent Phase 1，并完善 manual QC 遥操作曲线多信号与缩放交互�?
- Work completed:
  - **QC Agent Phase 1**：落�?episode 级持久化 conversation/message，新�?conversation API、message restore、pageState 上下文�?
  - **SSE 流式输出**：后�?`chat_stream` 通过 SSE 返回 status/text/meta/done；前�?`postChatStream` + `sendStream` �?chunk 渲染�?
  - **模型服务�?*：Ollama 改为 systemd 常驻服务，Qwen3-VL-32B-Thinking Q4_K_M 注册上线，`KEEP_ALIVE` 常驻 GPU，启动后自动预热�?
  - **模型配置�?*：设置页新增 AI 模型名称，后端从 `GeneralConfig.ai_model_name` 读取，不再硬编码�?
  - **可用性增�?*：发送前快速健康检查；模型不可达时立即提示；AI 面板新消息自动滚动�?
  - **遥操作曲线增�?*：manual QC 曲线从位置扩展为位置/速度/力矩多信号行，左右臂/手双面板，统一图例，DOF 元数据由后端返回�?
  - **缩放/平移/游标**：接�?`chartjs-plugin-zoom`，Ctrl+滚轮 x 缩放，xy 平移，所有行缩放联动；中键拖动游�?seek�?
  - **游标边界 bugfix**：修复缩放和平移后蓝色播放游标、黑�?hover 游标穿出�?右边界的问题；鼠标取时和游标显示均按 Chart.js `chartArea.left/right` 裁剪，左右图 visibility 分离，避免一侧旧 left 残留�?
  - **部署文档**：`deploy/README.txt` 补齐 AI 模块、Ollama systemd、模型下�?注册、健康检查、故障排查�?
- Business logic impact: manual QC 现在具备本地 LLM 辅助解释能力和多信号遥操作曲线审查能力；AI 服务仍保持平台与模型服务器解耦�?
- Problems encountered:
  - 7B 小模型对 JSON prompt 响应千篇一律�?
  - Qwen3-VL-32B-Thinking 首次加载�?thinking 输出导致等待时间长�?
  - HuggingFace GGUF 下载后签名验证超时，Ollama 未自动注册模型�?
  - stream 路由曾在模型名配置化编辑中被误删/合并�?
  - Chart.js 缩放后游标位置按 canvas 而不是真实绘图区计算，导致游标消失或穿出坐标系�?
- Resolution:
  - prompt 改为文本摘要 + 对话式指�?+ 历史上下文�?
  - `num_predict` 提升�?1024，保�?thinking 模式；Ollama systemd 常驻和预热降低后续等待�?
  - �?Modelfile 指向已下�?blob 手动注册模型�?
  - 补回独立 `chat/stream` 路由�?
  - 游标计算统一使用 `chartArea`，出绘图区隐藏；左右图状态独立控制�?
- Verification:
  - `npm --prefix frontend run build` 通过�?
  - `docker compose -f deploy/docker-compose.yml up --build -d frontend` 已重建并重启前端容器；backend 被依�?recreate �?healthy�?
  - `docker compose -f deploy/docker-compose.yml ps frontend backend` 确认 frontend Up、backend healthy�?
- Unverified items:
  - 缩放/平移/边界修复已部署，但仍需用户在浏览器中实操确认最终手感�?
- Files changed:
  - `backend/app/ai_qc/llm_client.py`
  - `backend/app/api/routes/qc.py`
  - `backend/app/models/general_config.py`
  - `backend/app/services/l3_v2/telemetry_parser.py`
  - `deploy/README.txt`
  - `deploy/docker-compose.yml`
  - `frontend/package.json`
  - `frontend/package-lock.json`
  - `frontend/src/api/client.ts`
  - `frontend/src/components/ai/AiAssistantPanel.vue`
  - `frontend/src/composables/useAiAssistant.ts`
  - `frontend/src/pages/manual-qc.vue`
  - `frontend/src/pages/settings.vue`
- Next steps: 用户浏览器强刷后复测 AI 对话与曲线缩�?游标边界；若确认稳定，进�?QC Agent 下一阶段工具调用/NPZ 数据查询能力�?

## 2026-07-08 (Ollama systemd 服务�?+ 32B 模型上线 + 健康检�?+ 自动滚动)

- Type: infrastructure + enhancement
- Status: deployed, verified
- Importance: high
- Objective: �?Ollama 从手动后台进程升级为 systemd 生产级服务，Qwen3-VL-32B-Thinking 正式上线

- Work completed:
  - **systemd 服务**（`/etc/systemd/system/ollama.service`）：
    - `OLLAMA_KEEP_ALIVE=8760h` 模型常驻不卸�?
    - `OLLAMA_NUM_PARALLEL=1` 节省显存
    - `OLLAMA_CONTEXT_LENGTH=4096` 适配 24GB 显存
    - `ExecStartPost` 自动预热模型
    - `Restart=on-failure` 崩溃自动重启
    - `WantedBy=default.target` 开机自�?
  - **模型配置�?*�?
    - `GeneralConfig` 新增 `ai_model_name` 字段
    - 设置页新�?模型名称"输入�?
    - 后端三个端点全部�?GeneralConfig 读取模型�?
  - **Qwen3-VL-32B-Thinking 上线**�?
    - �?HuggingFace unsloth GGUF 下载（Q4_K_M, 19GB�?
    - 下载签名验证失败时用 Modelfile 手动注册
    - `num_predict` �?512 提升�?1024（保�?thinking 模式�?
    - 推理延迟 ~12-18s�?2B Q4 + thinking�?
  - **健康检�?*�?
    - 后端 `GET /api/ai-assistant/health`�?s 超时 ping Ollama�?
    - 前端 `sendStream` 发送前先检查，不可达立即提�?
  - **自动滚动**：Panel 组件 `watch(messages)` + `scrollTop = scrollHeight`
  - **部署文档更新**：deploy/README.txt 完整重写 AI 模块（systemd 服务/模型管理/故障排查�?
  - **路由修复**：stream 端点被误删后补回

- Files changed (9):
  - `deploy/README.txt` �?AI 模块完整重写
  - `backend/app/models/general_config.py` �?+ai_model_name
  - `backend/app/api/routes/qc.py` �?模型名动态读�?+ 健康检查端�?+ stream 路由修复
  - `backend/app/ai_qc/llm_client.py` �?num_predict 1024
  - `backend/app/services/l3_v2/telemetry_parser.py` �?+qvel_hand + effort_hand
  - `frontend/src/api/client.ts` �?+checkAiHealth
  - `frontend/src/composables/useAiAssistant.ts` �?+healthOk + setScrollFn + 发前检�?
  - `frontend/src/components/ai/AiAssistantPanel.vue` �?+healthOk prop + scrollToBottom
  - `frontend/src/pages/settings.vue` �?+模型名称输入�?
  - `frontend/src/pages/manual-qc.vue` �?+healthOk + @ready 绑定
  - `deploy/docker-compose.yml` �?TIMEOUT 30�?20

- Infrastructure notes:
  - Ollama 模型目录：`/home/tbl/Project/models/qwen2.5/`（两个模型共用）
  - Qwen3-VL-32B Q4_K_M 显存占用 ~22.4GB/24GB，KV cache ~1.5GB
  - 平台通过 `192.168.20.147:11434` 访问 Ollama
  - systemd 日志：`journalctl -u ollama -f`

## 2026-07-08 (曲线图多信号行：位置+速度+力矩 + 缩放联动 + 中键拖动)

- Type: feature
- Status: deployed, verified
- Importance: medium
- Objective: 遥操作曲线从�?qpos/actions 扩展为多信号行，支持缩放平移

- Work completed:
  - **后端**：`telemetry-curve` 端点新增 `qvelArm/qvelHand/effortArm/effortHand`，返�?DOF 元数据（armLeftDof/armRightDof/handLeftDof/handRightDof），�?metadata.json 读取不硬编码
  - **telemetry_parser**：新�?`qvel_hand` / `effort_hand` 提取
  - **多信号行渲染**�?
    - `signalRows` computed 动态生成行定义
    - 机械�?3 行（位置 280px + 速度 200px + 力矩 200px�?
    - 灵巧�?1-2 行（位置 + 速度仅当数据非全零）
    - 每行左右双面板，独立 y 轴标�?
  - **单图�?*：顶部一份图例，颜色跨行统一，位置行 qpos 实线+actions 虚线
  - **缩放**：`chartjs-plugin-zoom`，Ctrl+滚轮缩放 x 轴，所有行联动同步，xy 方向拖动平移
  - **中键拖动游标**：`event.button === 1` 触发 seek，左键留�?pan
  - **游标修复**：多轮迭代解决联动缩放下游标越界/重复问题
  - **性能**：游标移动时不再触发 chart 重绘（`updateCursorOnly` vs `drawChartOverlay`�?

- Files changed (4):
  - `backend/app/api/routes/qc.py`
  - `backend/app/services/l3_v2/telemetry_parser.py`
  - `frontend/src/pages/manual-qc.vue`
  - `frontend/src/api/client.ts` �?TelemetryCurve 类型扩展

## 2026-07-08 (SSE 流式输出前端落地：postChatStream + sendStream + �?token 渲染)

- Type: feature
- Status: frontend built, Docker deployed, SSE endpoint verified
- Importance: medium
- Objective: 前端接入后端 SSE 流式端点，用户能看到 AI 逐字输出而非 loading 动画干等

- Work completed:
  - **client.ts**: 新增 `postChatStream()` async generator �?fetch ReadableStream + 手动 SSE 解析（event/data 行分割），每�?yield 返回 `{event, data}`
  - **useAiAssistant.ts**: 新增 `sendStream()` �?�?addMessage(user) �?创建�?content 占位 assistant 消息 �?for await SSE chunk 逐次追加 content �?done 时回�?provider/model；新�?`streamPhase` ref 反映 LLM 状�?
  - **AiAssistantPanel.vue**: 新增 `streamPhase` prop + `streamPhaseText` computed（thinking�?正在分析..."，fallback�?模型超时..."�?
  - **manual-qc.vue**: `handleAiSend`/`handleAiOpen` 切到 `sendStream`，模板传�?`:stream-phase`

- Verification:
  - `npm run build` �?
  - `curl` SSE endpoint: 确认�?token 输出�?这条" �?"数据" �?"的质�? �?... �?"done"�?
  - Docker deploy frontend �?

- Files changed (4):
  - `frontend/src/api/client.ts`
  - `frontend/src/composables/useAiAssistant.ts`
  - `frontend/src/components/ai/AiAssistantPanel.vue`
  - `frontend/src/pages/manual-qc.vue`

- Next: 浏览器端验收流式体验；等模型下载完成�?Qwen3-VL-32B-Thinking

## 2026-07-08 (QC Agent Phase 1 落地：持久化聊天 + conversation API + 流式 SSE + pageState)

- Type: feature (major)
- Status: backend + frontend built, Docker deployed, migration 0018 applied, API verified
- Importance: high
- Reusable: yes
- Objective: 按照 `docs/qc-agent设计.md` �?Phase 1 规划，将 AI 助手�?无状态的单次解释请求"升级�?持久化多轮对�?Copilot"
- Design doc: `docs/qc-agent设计.md` �?完整技术评估已产出，结论：能做，分 3 阶段；Phase 1 低风�?1-2 �?
- Model plan: qwen2.5:7b �?Qwen3-VL-32B-Thinking (Q4_K_M, ~19GB, HuggingFace unsloth GGUF), 下载�?

- Work completed:
  - **DB 模型** (`models/ai_assistant.py`):
    - `AiConversation`: id, episode_id, user_id, title, status, created_at, updated_at
    - `AiMessage`: id, conversation_id, episode_id, user_id, role, content, content_json(JSONB), provider, model, latency_ms, created_at
    - Migration `20260708_0018` 已执行到生产�?
  - **持久化层** (`conversation_store.py`):
    - `get_or_create_conversation`: �?episode+user 自动复用活跃对话
    - `add_message` + `get_recent_messages`: 消息 CRUD，自动修剪超 200 条旧消息
    - `list_user_conversations` / `get_conversation_messages`
  - **Chat Service** (`chat_service.py`):
    - `chat()`: conversation �?persist user msg �?build evidence �?LLM �?validator �?persist assistant msg �?response
    - `chat_stream()`: SSE Generator，流式�?token 输出 + 最终持久化
    - 自动 fallback: LLM 不可�?校验失败 �?template
  - **API 端点** (`routes/qc.py`):
    - `POST /api/ai-assistant/conversations` �?创建/恢复对话
    - `GET /api/ai-assistant/conversations/{id}/messages` �?获取消息历史
    - `POST /api/ai-assistant/chat` �?发送消息（非流式）
    - `POST /api/ai-assistant/chat/stream` �?发送消息（SSE 流式�?
  - **Schemas 扩展** (`ai_qc/schemas.py`):
    - PageState: selectedMetricId, currentVideoTimeSec, selectedTimelineSegmentId, visibleChart, openedMetricPanel
    - AiChatRequest/ChatResponse, AiConversationDetail, AiMessageItem
  - **llm_client 增强**: 新增 `call_ollama_stream()` �?httpx.stream + iter_lines �?token yield
  - **prompt_builder 增强**: 新增 `page_state` 参数，注�?质检员当前查看的指标/时间/曲线"
  - **前端 useAiAssistant 重写**:
    - `loadConversation(episodeId)`: 打开面板时从服务端恢复历史对�?
    - `send(prompt, context, pageState)`: 发送消�?+ pageState 上下�?
    - conversationId 持久化，关闭重开自动恢复
  - **前端 API client**: 新增 fetchOrCreateConversation / fetchConversationMessages / postChatMessage
  - **前端 types**: 新增 PageState / AiChatRequest / AiChatResponse / AiConversationDetail / AiMessageItem
  - **manual-qc.vue**: 新增 buildPageState() / selectedMetricId ref；handleAiOpen 改为�?loadConversation 再发首次解释；handleAiSend 传入 pageState

- Key design decisions:
  - **Phase 1 不做工具调用、不做多模�?*：先完成持久化和上下文增强，Phase 2 再加工具�?
  - **conversation �?episode+user 自动复用**：同一 episode 的对话不会散落多�?conversation
  - **�?`/api/ai/explain` 端点保留**：向后兼容，渐进迁移
  - **后端流式 SSE 已就�?*：前端暂用非流式（等 32B 模型上了再切，因为推理时间长更需要流式）
  - **pageState 注入 prompt**：让模型知道用户在看什么，解决"这个""这里"的指代问�?

- Verification:
  - 后端 `python3 -m compileall` �?
  - 前端 `npm run build` �?(392ms)
  - Docker build + deploy �?
  - Migration `20260708_0018` �?
  - API: create conversation �?chat �?close + reopen 恢复 2 条历�?�?

- Files changed (12 files):
  - `backend/app/models/ai_assistant.py` (new)
  - `backend/app/models/__init__.py`
  - `backend/migrations/versions/20260708_0018_ai_assistant.py` (new)
  - `backend/app/ai_qc/schemas.py`
  - `backend/app/ai_qc/conversation_store.py` (new)
  - `backend/app/ai_qc/chat_service.py` (new)
  - `backend/app/ai_qc/llm_client.py`
  - `backend/app/ai_qc/prompt_builder.py`
  - `backend/app/api/routes/qc.py`
  - `frontend/src/types/qc.ts`
  - `frontend/src/api/client.ts`
  - `frontend/src/composables/useAiAssistant.ts`
  - `frontend/src/pages/manual-qc.vue`

- Next steps:
  - Qwen3-VL-32B-Thinking 模型下载完成后切换模型名测试
  - 浏览器端完整验收：打开面板 �?多轮对话 �?关闭 �?重开恢复 �?切换 episode
  - Phase 2 规划：NPZ/曲线工具 + 视频关键�?+ 多模态视觉证�?

## 2026-07-08 (AI 助手对话体验修复：prompt 重写 + 对话历史 + 校验放宽)

- Type: bugfix + enhancement
- Status: backend + frontend rebuilt, Docker deployed, API verified
- Importance: high
- Reusable: yes
- Objective: 修复 AI 质检助手无论用户说什么都回复相同报告的问题，�?qwen2.5:7b 能真正进行对�?
- Root cause: 三个问题叠加导致小模型无法正常对�?
  1. **提示词太死板**：系统指�?把事实解释给质检�? + 完整 JSON 事实数据 �?7B 模型�?JSON 淹没，只会照 JSON 念报�?
  2. **没有对话历史**：每次调用都是全新请求，模型不知道之前聊了什�?
  3. **校验器过于严�?*：强制每次输出都�?封顶/截断"，对话场景下不适用
- Work completed:
  - **prompt_builder.py 完全重写**�?
    - JSON 格式替换为自然语言文本摘要（~150 字），对 7B 模型更友�?
    - 系统指令改为对话式："问什么答什么，不要复述完整报告"
    - 打招呼→友好回应不提数据；问概念→解释概�?结合当前数据举例；问具体指标→只回答相关部分
    - 新增 `history` 参数支持多轮对话
  - **schemas.py**：`AiExplainRequest` 新增 `history: list[dict[str, str]]` 字段
  - **service.py**：传�?`history` �?prompt builder、`is_conversation` �?validator
  - **validator.py 放宽**�?
    - 移除 `{` `<` 误判模式
    - 对话模式下不强制要求�?封顶/截断"
    - MAX_CHARS 300�?00
  - **useAiAssistant.ts**：`send()` 自动提取最�?3 轮对话作�?history 发�?
- Key insight: 小模型（7B）和大模型的 prompt 设计理念完全不同�?
  - 大模型能从大�?JSON 中提取关键信息并灵活回答
  - 小模型会�?JSON 结构淹没，需要自然语言摘要 + 灵活的系统指�?
  - 系统指令不能太死板，否则小模型只会执�?主任�?而忽略用户实际输�?
- Verification:
  - "哈喽" �?"你好！当�?Q_motion 被封顶是因为 DI-02..."（友好开�?+ 简要）
  - "数据完整性是什么意思，为啥会影响分�? �?解释概念 + 当前 DI-02 情况
  - "MQ-01 轨迹平滑度是干嘛�? �?只解�?MQ-01，不提其他指�?
  - 带历史追�?�?DI-02 具体是什么意�? �?基于前文继续回答
- Files changed:
  - `backend/app/ai_qc/prompt_builder.py` �?完全重写
  - `backend/app/ai_qc/schemas.py` �?+history 字段
  - `backend/app/ai_qc/service.py` �?传�?history + is_conversation
  - `backend/app/ai_qc/validator.py` �?放宽校验规则
  - `frontend/src/composables/useAiAssistant.ts` �?发送对话历�?
- Commit: pending

## 2026-07-08 (manual QC 遥操作曲线图左侧坐标轴对齐修�?

- Type: frontend bugfix + deployment
- Status: frontend rebuilt, Docker deployed, user verified effective
- Importance: medium
- Reusable: yes
- Objective: 修复 manual QC 页面中机械臂双面板曲线图左侧坐标轴未对齐的问题，确保上下两张图的绘图区左边界一�?
- Root cause:
  - 问题并不�?x 轴时间范围，而在 y 轴自动布局
  - 机械臂图�?y 轴刻度文本更长（�?`0.0020 / -0.0010`），Chart.js 会自动分配更宽的左侧轴区�?
  - 结果是上下两张机械臂图虽�?`x.min/x.max` 一致，但绘图区 `chartArea.left` 不一致，视觉上表现为左侧不对�?
  - 灵巧手图之所以正常，是因为其 y 轴刻度文本更短，自动布局碰巧一�?
- Work completed:
  - **时间轴范围对�?*：两张图统一显式设置 `x.min = 0`、`x.max = maxTime`
  - **双图光标解�?*：左右图分别计算 playback / hover cursor 像素位置，不再错误复用左图坐�?
  - **拖拽体验优化**：scrub 改为 16ms 节流的同�?`video.currentTime` 更新，快速拖动时不再明显掉帧
  - **最终对齐修�?*：为 Chart.js y 轴增�?`afterFit()`，固定机械臂图的 y 轴宽度，消除因刻度文本长度差异带来的左边距漂�?
  - **部署补齐**：确认前端容器最初未包含最�?bundle 后，重新 build frontend 并重�?`robot-qc-frontend` 容器
- Files changed:
  - `frontend/src/pages/manual-qc.vue` �?统一 x 轴范围、分离双�?cursor、固定机械臂 y 轴宽度、优�?scrub 逻辑
- Verification:
  - `npm --prefix frontend run build` �?
  - `docker compose -f deploy/docker-compose.yml build frontend && up -d frontend` �?
  - 用户刷新页面后确认修复生�?�?
- Next steps:
  - 当前问题已收口，无额外跟进项

## 2026-07-08 (lerobot-doctor 全部 11 条对标审查完�?

- Type: review + benchmark
- Status: 审查完成，对标改造全部落�?
- Importance: high
- Reusable: yes
- Objective: �?lerobot-doctor 为参照基准，逐条审查 Robot QC L3 引擎覆盖度，补齐数据质量缺口
- Summary: 11 条中 5 条已对标改造�? 条不适用�? 条已有覆�?

| # | lerobot check | Robot QC | 结论 |
|---|---------------|----------|------|
| 1 | metadata | manifest 格式不同 | �?不适用 |
| 2 | temporal | DI-01 重写（声明FPS+抖动+丢帧+FPS一致性） | �?改造完�?|
| 3 | actions | MQ-01/02/03 + DX-02 NaN/Inf | �?已对�?|
| 4 | videos | 后端不解码视频，浏览器播�?| �?已有覆盖 |
| 5 | statistics | DI-03 维度健康 + DX-02 扩展 | �?改造完�?|
| 6 | episodes | DI-04 Episode 完整�?| �?改造完�?|
| 7 | consistency | npz 固定 schema | �?不适用 |
| 8 | training | LeRobot 训练框架概念 | �?不适用 |
| 9 | anomalies | DI-03 + arm_mode 过滤 | �?已有覆盖 |
| 10 | portability | MinIO 对象存储 | �?不适用 |
| 11 | per_episode | manual QC �?episode 页面 | �?已有覆盖 |

- Next steps:
  - 部署验证 + 参数调优
  - 考虑 batch 级跨 episode 统计（分布漂移、长度方差等�?

## 2026-07-07 (DI-03 维度健康 + DX-02 扩展：zero-variance / MAD outliers / effort+qvel NaN/Inf)

- Type: enhancement
- Status: backend compile passed, Docker deployed, healthy
- Importance: high
- Reusable: yes
- Objective: 对标 lerobot-doctor statistics 检查项（NaN/Inf in observations、zero-variance、extreme outliers），补齐 Robot QC 逐维度统计异常检�?
- Decisions confirmed:
  - **NaN/Inf**：扩展现�?DX-02，补 effort + qvel 数组扫描（原来只扫了 actions + qpos�?
  - **Zero-variance**：逐维度查 std==0，直接定位故障传感器或填充假数据维度
  - **Extreme outliers**：用 MAD（中位数绝对偏差）替�?mean/std 计算 robust z-score，避免异常值自污染
  - **指标归属**：Zero-variance + outliers 合并�?DI-03 Dimension Health，归�?data_integrity 维度
  - **DI-03 不参�?Q_motion**：weight=0，作为独立诊断展�?
- Work completed:
  - **feature_extractor.py**�?
    - NaN/Inf 扫描扩展�?actions / qpos / effort / qvel 四数组全覆盖
    - 新增 `_compute_dim_health()`：遍�?arm_qpos / arm_actions / arm_effort / arm_qvel / hand_qpos / hand_actions 每个维度，算 std（零方差检测）+ MAD robust_z（异常值检测），单臂模式自动跳过手部维�?
  - **metric_engine.py**�?
    - DX-02 `_data_validity()` 纳总加�?effort/qvel NaN/Inf，描述同步更�?
    - 新增 `_dimension_health()` �?DI-03：汇总零方差维度 + 异常值超标维度，按问题维度占比衰减评分，零方�?bad，仅异常�?warn
  - **l3_v2_config.py**：新�?`di03_outlier_z`（默�?10）、`di03_outlier_ratio_warn`（默�?0.01�?
- Key design decisions:
  - **为什么用 MAD 而非 mean/std**：单�?episode 内如果异常帧占比高，mean/std 会被污染导致 z-score 失效；MAD 基于中位数，不受异常值影�?
  - **robust_z 阈�?10**：乘�?0.6745 后与传统 z-score 尺度对齐�?0 是保守阈值，减少误报
  - **outlier_ratio_warn=0.01**：容�?1% 偶发噪声，超过才报警
- Files changed:
  - `backend/app/services/l3_v2/feature_extractor.py` �?dim_health_records + effort/qvel NaN/Inf + _compute_dim_health()
  - `backend/app/services/l3_v2/metric_engine.py` �?DX-02 扩展 + DI-03 _dimension_health()
  - `backend/app/models/l3_v2_config.py` �?di03_outlier_z / di03_outlier_ratio_warn
- Verification:
  - `python -m compileall backend/app/services/l3_v2` �?
  - `docker compose build backend && up -d backend` �? healthy
- Unverified items:
  - 尚未在真实异�?episode 上验�?MAD outlier 检测效�?
  - 尚未对零方差维度做真实数据验�?
- Next steps:
  - 继续对标 lerobot-doctor 下一 check 条目

## 2026-07-08 (DI-03/DI-04 新增 + 全指标中文化 + DI 截断机制重构)

- Type: feature + enhancement + bugfix
- Status: backend compile passed, Docker deployed, healthy
- Importance: high
- Reusable: yes
- Objective: 对标 lerobot-doctor episodes/anomalies 检查项，补齐维度健康、episode 完整性检测；同步 DI-01 深度路径；全指标中文化；修复 Q_motion 截断逻辑
- Decisions confirmed:
  - **DI-03 Dimension Health**：逐维度零方差检测（所有维度）+ MAD outlier 检测（�?arm_qpos/arm_actions，原因见下）
  - **DI-04 Episode Completeness**：帧数过短（<10�? manifest 声明-实际帧数不一致（>5%�?
  - **DI-03 outlier 范围三次收紧**�?
    1. 初始覆盖 arm_qpos/actions/effort/qvel + hand_qpos/actions
    2. �?移除 qvel/effort（速度/力矩天然有尖峰，误报严重�?
    3. �?移除 hand_qpos/actions（手部从全开到全闭瞬间完成，天然产生大跳变）
    4. �?最终只保留 arm_qpos + arm_actions
  - **Q_motion 截断机制重构**：从"维度均分低于阈�?改为"任一 DI 指标低于阈�?
    - 旧：data_integrity 维度均分 < 3 �?封顶 4.5�? 5 �?封顶 6.0
    - 新：任一 DI 指标 < 3.0 �?封顶 3.0�? 5.0 �?封顶 6.0
    - 理由：DI-01=10, DI-03=10, DI-04=10 不应该给 DI-02=1.6 做掩�?
  - **DI-01 深度相机路径同步**：丢帧阈值从 2.0�?.5，权重从 0.5/0.3/0.2�?.35/0.25/0.15，与主路径一�?
  - **全指标中文化**�?2 个指标的 name/unit/description + 14 �?timeline label + 8 �?evidence 标签全部中文�?
- Work completed:
  - **DI-03 新建**：feature_extractor._compute_dim_health() 逐维度扫�?+ metric_engine._dimension_health()
  - **DI-04 新建**：metric_engine._episode_completeness()，manifest frame_count �?engine→features 传入
  - **DI-01 深度路径同步**：_timestamp_regularity_depth 逻辑对齐主路�?
  - **全指标中文化**：metric_engine 全部 name/unit + quality_engine EVIDENCE_META �?DI-03/DI-04 条目
  - **证据分修�?*：weight=0 指标的证据组评分从加权平均改为等权平�?
  - **Q_motion 截断重构**：逐指标判定替代维度均分判定，新增 qf_data_cap_metric_bad/warn 参数
- Files changed:
  - `backend/app/services/l3_v2/feature_extractor.py` �?DI-03 _compute_dim_health + manifest_frame_count
  - `backend/app/services/l3_v2/metric_engine.py` �?DI-01 depth 同步 + DI-03 + DI-04 + 全中文化
  - `backend/app/services/l3_v2/engine.py` �?manifest_frame_count 透传
  - `backend/app/services/l3_v2/quality_engine.py` �?EVIDENCE_META 补条�?+ 证据分修�?+ 截断重构
  - `backend/app/services/payloads.py` �?manifest frame_count 传入
  - `backend/app/models/l3_v2_config.py` �?DI-03/DI-04 参数 + 截断参数更新
- Unverified items:
  - DI-03/DI-04 在真实异常数据上的效果尚未验�?
  - 新截断逻辑在不�?episode 上的表现尚未全面比对
- Next steps:
  - 继续对标 lerobot-doctor 剩余条目（consistency/training/portability/per_episode�?

## 2026-07-07 (DI-01 丢帧检测改用声�?FPS + FPS 一致�?+ DX-02 NaN/Inf 检�?

- Type: enhancement
- Status: backend compile passed, Docker deployed, healthy
- Importance: high
- Reusable: yes
- Objective: 对标 lerobot-doctor temporal/actions 检查项，补�?Robot QC 数据质量检测缺�?
- Decisions confirmed:
  - **丢帧检测基�?*：从 `dt_median`（自适应中位数）改为 `1.0 / declared_fps`（manifest 声明帧率），阈�?1.5 �?
  - **FPS 一致性检�?*：新�?`abs(dt_median - expected_interval) > expected_interval × 0.1` 全段时序警告
  - **NaN/Inf 兜底**：在特征提取阶段扫描 actions/qpos 数组，作�?DX-02 诊断指标展示
  - **frame_index/episode_index/global_index**：TeleDex 数据结构不需要，不加
  - **Clipping 饱和检�?*：灵巧手顶到边界属正常操作，不加
- Work completed:
  - **DI-01 重写**：丢帧检测改�?`1.5 / declared_fps`，抖动检测改�?`expected_interval` 基准，新�?FPS 一致性偏差项（权�?0.25�?
  - **DI-01 自适应降级**：无声明 FPS 时自动回退�?dt_median 模式，不影响旧数据评�?
  - **DI-01 参数重组**：`di01_jitter=0.35, di01_gap=0.25, di01_invalid=0.15, di01_fps=0.25`；`di01_drop_multiplier` 替代�?`di01_gap_multiplier`
  - **DX-02 Data Validity 新增**：扫�?actions/qpos NaN/Inf，无异常=10 分，有异�?按异常数量衰减；独立诊断，不参与 Q_motion 总分
  - **数据链路**：manifest fps �?payloads �?L3V2Engine �?FeatureExtractor �?L3V2Features.declared_fps �?MetricEngine DI-01
- Files changed:
  - `backend/app/services/l3_v2/feature_extractor.py` �?L3V2Features 新增 declared_fps/NaN/Inf 字段 + 扫描逻辑
  - `backend/app/services/l3_v2/metric_engine.py` �?DI-01 重写 + DX-02 _data_validity 新增
  - `backend/app/services/l3_v2/engine.py` �?declared_fps 透传
  - `backend/app/models/l3_v2_config.py` �?DI-01 参数默认值更�?
  - `backend/app/services/payloads.py` �?manifest fps 传入 L3V2Engine
- Verification:
  - `python -m compileall backend/app/services/l3_v2` �?
  - `docker compose build backend && up -d backend` �? healthy
- Unverified items:
  - 尚未对真实有丢帧�?FPS 不一致的 episode 做人工比�?
  - NaN/Inf 检测在健康数据上已验证不误报，尚未对损坏数据做验证
- Next steps:
  - 继续对标 lerobot-doctor 剩余 check 条目，确定下一批改�?
  - push 一版代�?

## 2026-07-07 (任务类型 arm_mode 落地：按任务类型过滤 L3 �?双臂维度)

- Type: feature + business-logic refinement
- Status: backend compile passed, frontend build passed
- Importance: high
- Reusable: yes
- Objective: 解决单臂任务被双臂统一口径误判的问题，在任务类型层新增 arm_mode，并�?L3 计算仅统计当前任务实际应使用�?arm/hand 维度
- Decisions confirmed:
  - **配置层级**：arm_mode 仅挂�?TaskType，不下沉到每�?episode
  - **字段枚举**：固定三�?`both_arms / left_arm / right_arm`
  - **展示边界**：本轮不�?manual QC 展示层，只修正后端计算口径与任务类型管理配置入口
- Work completed:
  - **后端模型与迁�?*：`TaskType` 新增 `arm_mode` 字段，默�?`both_arms`；新�?migration `20260707_0017_task_type_arm_mode.py`
  - **后端 schema/API**：任务类�?`create / update / list / detail` 全链路已打�?`armMode` 字段，并对非法值做校验
  - **L3 计算链路修正**：`payloads.py` 在构�?manual QC 真实上下文时，已�?`episode -> batch -> task_type` 读取 `arm_mode`
  - **Telemetry 维度过滤**：`TelemetryParser.parse()` �?`L3V2Engine` 已支�?`arm_mode` 入参，并�?`left_arm / right_arm / both_arms` 过滤 arm/hand 维度，不再默认把左右臂全部纳入计�?
  - **前端任务类型管理�?*：创�?编辑任务类型弹窗已增加手臂模式单选项，详情区已展示当前任务类型的手臂模式
  - **类型同步**：前�?`TaskType` / API request 类型�?mock 数据已同�?`armMode`
- Files changed:
  - `backend/app/models/task_type.py` �?新增 `arm_mode`
  - `backend/migrations/versions/20260707_0017_task_type_arm_mode.py` �?新建 migration
  - `backend/app/schemas/qc.py` �?TaskType schema / request 增加 `armMode`
  - `backend/app/api/routes/qc.py` �?task-types API 增加 `armMode` 校验与写�?
  - `backend/app/services/payloads.py` �?manual QC 真实上下文读�?task_type.arm_mode 并传�?L3
  - `backend/app/services/l3_v2/engine.py` �?透传 `arm_mode`
  - `backend/app/services/l3_v2/telemetry_parser.py` �?�?arm_mode 过滤 arm/hand dims
  - `frontend/src/types/qc.ts` �?新增 `TaskTypeArmMode` �?`TaskType.armMode`
  - `frontend/src/api/client.ts` �?task type create/update request 增加 `armMode`
  - `frontend/src/pages/task-types.vue` �?新增手臂模式配置与详情展�?
  - `frontend/src/api/mock.ts` �?mock taskTypes 补齐 `armMode`
- Verification:
  - `python -m compileall backend/app` �?
  - `npm --prefix frontend run build` �?
  - `docker compose build frontend && docker compose up -d frontend` �?
- Problems encountered:
  - **部署后全站接�?500**：前端重建部署后，backed 代码已升级为读取 `task_types.arm_mode`，但生产数据库尚未执�?migration `20260707_0017`，导�?`/api/dashboard`、`/api/database` 等接口全部抛�?`UndefinedColumn`，页面表现为数据全空
  - **根因**：代码发布与数据�?migration 未同步执行，Alembic migration 文件已存在于代码仓库，但未在容器内执�?`alembic upgrade head`
- Resolution:
  - 在生产容器内执行 `alembic upgrade head`，成功应�?`20260707_0016 -> 20260707_0017`
  - 重启 backend 容器，`/api/dashboard` 恢复正常返回 14 �?taskTypes
  - 数据库验证：`task_types` 表已包含 `arm_mode` 列，既存数据默认 `both_arms`
- Verified: backend healthy, dashboard API 正常返回
- Lesson: 今后任何涉及新增数据库列的改动，部署流程必须是：**先跑 migration �?再重�?backend**，否则代码读到不存在的列就会全站 500
- Unverified items:
  - 尚未做真实浏览器下的任务类型编辑联调
  - 尚未对具体单�?episode 做一轮人工比对验�?L3 指标变化是否符合预期
- Next steps:
  - 选一个明确右臂任务样本，验证 arm_mode=right_arm 后动作密度等指标不再被左臂静止维度稀�?

## 2026-07-07 (BUG提交增强：多图粘�?暂存草稿)

- Type: feature (enhancement)
- Status: backend compile passed, frontend build passed, Docker deployed
- Importance: high
- Reusable: no
- Objective: �?BUG 提交从单图升级为多图粘贴，并支持 localStorage 暂存草稿，避免填写过程中意外关窗丢失内容
- Work completed:
  - **多图上传**：后�?`POST /api/bug-reports` �?`image: UploadFile | None` 改为 `images: list[UploadFile]`，每张存�?`{report_id}_{idx}.{ext}`，`image_filename` �?JSON 数组
  - **多图读取**：图片接口改�?`GET /api/bug-reports/{id}/image/{index}`，按索引访问
  - **序列化兼�?*：`serialize_bug_report` 返回 `imageUrls: list[str]`，兼容旧单字符串格式
  - **Schema 更新**：`BugReportSchema.imageUrl` 改为 `imageUrls: list[str]`
  - **前端多图粘贴**：BugReportDialog 粘贴追加而非替换，网格预�?+ 单张删除按钮 + 文件选择器入�?
  - **前端暂存草稿**：新�?暂存"按钮，描�?+ 图片 base64 写入 localStorage key `bug-report-draft`；下次打开弹窗自动恢复并显示黄色提示；提交成功后自动清除草�?
  - **管理页适配**：bug-management 截图列改�?`�? �? ...` 多链�?
  - **依赖补全**：requirements.txt 新增 `python-multipart`（FormData 上传必需�?
- Files changed:
  - `backend/app/api/routes/qc.py` �?多图上传 + 按索引读�?+ 清理 Path 死代�?
  - `backend/app/schemas/qc.py` �?BugReportSchema.imageUrls
  - `backend/app/services/payloads.py` �?serialize_bug_report 多图 + 兼容旧格�?
  - `backend/requirements.txt` �?+python-multipart
  - `frontend/src/components/BugReportDialog.vue` �?多图网格 + 暂存草稿
  - `frontend/src/pages/bug-management.vue` �?多图链接展示
  - `frontend/src/api/client.ts` �?CreateBugReportRequest.imageFiles + FormData append
  - `frontend/src/types/qc.ts` �?BugReport.imageUrls
- Commit: pending

## 2026-07-07 (BUG提交/管理完整落地：后端表+API+图片存储，前端提交弹�?admin管理�?

- Type: feature (new)
- Status: backend compile passed, frontend build passed
- Importance: high
- Reusable: yes
- Objective: 为局域网使用中的问题反馈建立内置闭环：普通用户可随手提交 BUG（截�?描述），admin 可统一查看、标记已修复或删�?
- Decisions confirmed:
  - **用户侧入�?*：顶部栏�?`LAN 内网访问` �?`任务派发` 之间新增 `BUG提交` 按钮
  - **交互形式**：点击按钮弹出浮窗，支持粘贴图片、填写描述文字、提交到服务�?
  - **管理侧入�?*：admin 右上角用户下拉菜单中，命名为 `BUG管理`
  - **管理能力**：admin 可查看全�?BUG 提交，支持标记状态（open/fixed）与删除记录
  - **存储方案**：元数据�?bug_reports 表，截图文件存服务器本地 backend/data/bug_reports/，数据库仅存文件�?
- Work completed:
  - **后端模型与迁�?*：新�?BugReport 模型（qc.py），migration 20260707_0016 建表（id/description/status/image_filename/image_content_type/reporter_user_id/reporter_name/created_at/updated_at），status �?reporter_user_id 建索�?
  - **后端 API**：`GET /api/bug-reports`（admin 列表）、`POST /api/bug-reports`（multipart 表单提交，支持图�?upload）、`PATCH /api/bug-reports/{id}/status`（admin 改状态）、`DELETE /api/bug-reports/{id}`（admin 删除）、`GET /api/bug-reports/{id}/image`（读取截�?FileResponse）；所有写操作附带 AuditEvent
  - **后端配置**：config.py 新增 BUG_REPORT_UPLOAD_DIR 常量指向 backend/data/bug_reports/，main.py 启动时自动创建目�?
  - **后端序列�?*：payloads.py 新增 serialize_bug_report，返�?imageUrl 指向受控图片接口
  - **前端模板改�?*：AppLayout.vue 顶部栏新�?`BUG提交` 按钮，右上角用户区改�?el-dropdown（admin 可见 BUG管理+设置，普通用户仅退出登录），引�?BugReportDialog 组件，vue-tsc 通过
  - **前端提交弹窗**：新�?BugReportDialog.vue，支�?textarea 描述 + 剪贴板图片粘�?预览 + FormData multipart 提交
  - **前端管理�?*：新�?bug-management.vue，el-table 展示提交时间/提交�?状�?描述/截图链接，支持标记已修复/重新打开/删除
  - **前端路由**：新�?/bug-management 路由，meta.roles=['admin']
- Files changed:
  - `backend/app/models/qc.py` �?新增 BugReport 模型
  - `backend/app/models/__init__.py` �?注册 BugReport
  - `backend/migrations/versions/20260707_0016_bug_reports.py` �?新建 migration
  - `backend/app/schemas/qc.py` �?新增 BugReportSchema / BugReportListPayloadSchema / BugReportStatusUpdateRequest
  - `backend/app/api/routes/qc.py` �?新增 5 �?BUG 相关 endpoint + 导入
  - `backend/app/services/payloads.py` �?新增 serialize_bug_report
  - `backend/app/core/config.py` �?新增 BUG_REPORT_UPLOAD_DIR
  - `backend/app/main.py` �?startup �?mkdir bug_reports 目录
  - `frontend/src/components/AppLayout.vue` �?顶部 BUG提交 按钮 + 用户下拉菜单
  - `frontend/src/components/BugReportDialog.vue` �?新建提交弹窗
  - `frontend/src/pages/bug-management.vue` �?新建管理�?
  - `frontend/src/router/index.ts` �?新增 /bug-management 路由
  - `frontend/src/api/client.ts` �?新增 createBugReport/fetchBugReports/updateBugReportStatus/deleteBugReport
  - `frontend/src/types/qc.ts` �?新增 BugReport / BugReportListPayload 类型
  - `.project-log/requirements.md`
  - `.project-log/current-session.md`
  - `.project-log/progress.md`
- Commit: pending

## 2026-07-07 (清除所有启发式猜测逻辑：DOF路径修复 + 删除_detect_dims + manifest替代硬编码匹�?

- Type: refactoring
- Status: backend compile passed, Docker deployed
- Importance: high
- Reusable: yes
- Objective: 彻底清除代码中所�?猜测数据结构"的逻辑，改为读�?metadata.json/manifest.json 中的明确定义
- Work completed:
  - **DOF 路径 BUG 修复**（qc.py/payloads.py）：`hw.get('arm')` �?`dev.get('arm')`。arm/hand 节点�?device 的兄弟节点，不在 hardware_specs 内，原代码永不命中，始终回退到硬编码默认�?7/7/6/6
  - **删除 `_detect_dims()`**（telemetry_parser.py）：移除 ~15 行启发式扫描代码（`qpos_active_max <= 3.5` 阈值猜测），改为强制要�?dof_config 参数，缺失时抛出 ValueError
  - **_media_slot_and_label() 改用 manifest**（payloads.py）：不再�?`'left' in key` 子串匹配猜相机槽位，改为�?manifest `files.cameras` 构建精确映射
  - **FPS 硬编码修�?*（payloads.py）：`30.0` 硬编�?�?�?`episode.frame_count / duration_sec` 计算
  - **深度时间戳匹�?*（payloads.py）：优先�?manifest `cam_top.timestamps` 精确匹配，fallback 仍保留子串匹�?
  - **_derive_state() 改用 manifest**（scanner.py）：RGB 视频存在性判断从文件名后缀匹配 �?manifest `files.cameras.{name}.video` 检�?
  - **相机排序权重动态化**（payloads.py）：�?`{top:10, left:20, right:30}` 硬编�?�?�?manifest cameras 枚举顺序动态生�?
  - **手部值域标注**（telemetry_parser.py）：`/255.0` 归一化补充注释说明为 Linker Hand 硬件事实
- Files changed:
  - `backend/app/api/routes/qc.py` �?DOF 路径修复
  - `backend/app/services/payloads.py` �?_media_slot_and_label + 深度时间�?+ FPS + 排序权重改用 manifest
  - `backend/app/services/scanner.py` �?_derive_state 改用 manifest + 调用点传�?manifest_data
  - `backend/app/services/l3_v2/telemetry_parser.py` �?删除 _detect_dims + dof_config 必传 + 注释标注
  - `.project-log/current-session.md`
  - `.project-log/progress.md`
- Commit: pending

## 2026-07-07 (遥操作曲线视图重构：双面板拆�?+ 异常段背景叠�?+ DOF检测改用metadata)

- Type: feature + refactoring
- Status: backend compile passed, frontend build passed, Docker deployed
- Importance: high
- Reusable: yes
- Objective: 遥操作曲线视图从单面板升为左右双面板（机械臂：左�?右臂，灵巧手：左�?右手），异常段背景色改为叠加逻辑，修复维度检测依�?metadata.json 替代启发式扫�?
- Work completed:
  - **异常段背景色取消游标高亮**：timelineOverlayPlugin 移除 active 逻辑，异常段背景色固定不再随播放位置变化
  - **异常段背景色叠加逻辑**：改为逐像素列扫描——先统计每列 bad/warn/good 段重叠数，红色覆盖黄色（同一位置�?bad 时只画红），透明度随重叠数叠加（�? base 0.15 + 0.12/�?cap 0.60, �? base 0.10 + 0.08/�?cap 0.45），红色底色更深 `rgba(220,38,38,...)`
  - **删除异常段核查清单面�?*：移�?el-card + el-check-tag 列表，清�?segmentSource/segmentHasSource 死代�?
  - **双面板拆�?*（renderChart）：替换单一 chartCanvas/chartInstance �?chartL/R 双实例。每�?perSideCount = Math.round(dimCount/2)；arm 模式左臂 dims 0:7 右臂 dims 7:14；hand 模式左手 dims 0:6 右手 dims 6:12。模板改为两�?canvas 上下垂直排列�?80px �?+ 12px 间距），图例统一在顶部仅显示左侧维度配色
  - **指针事件重构**：chartTimeFromPointer / handleChartPointerMove/Down 接受 (event, chart, canvas) 参数，两�?canvas 独立绑定，共�?currentTimeSec 游标。drawChartOverlay 同时更新两个 chart 插件；updateChartCursorPosition 基于�?chart 计算光标位置
  - **维度标签修正**：机械臂按钮 `armDims / 2` 显示每臂维度�?4�?），灵巧手不除（handDims 本身就是单手维度�?
  - **DOF 检测改�?metadata**（关键修复）�?
    - �?`_detect_dims()` 启发式扫�?qpos 值域猜测维度，导�?handDims 返回 6 而非 12，灵巧手每侧只显�?3 DOF
    - 后端 `routes/qc.py` telemetry-curve API：改为读�?metadata.json �?hardware_specs �?arm/hand joints left/right_dof，按已知列序切分 qpos/actions
    - `telemetry_parser.py`：parse() 新增 dof_config 参数，传入时跳过 _detect_dims() 直接按配置索引切�?
    - `engine.py` / `payloads.py`：从 metadata.json 提取 DOF 配置传入 L3V2Engine
    - 修复�?armDims=14 (7+7), handDims=12 (6+6)，每侧显示正确的维度�?
- Files changed:
  - `frontend/src/pages/manual-qc.vue` �?双面板拆�?+ 图例重构 + 异常段叠�?+ 核查清单删除 + 维度/指针重构
  - `backend/app/api/routes/qc.py` �?telemetry-curve DOF 改为�?metadata.json
  - `backend/app/services/l3_v2/telemetry_parser.py` �?parse() 支持 dof_config 参数
  - `backend/app/services/l3_v2/engine.py` �?接收 dof_config 传入 TelemetryParser
  - `backend/app/services/payloads.py` �?�?metadata.json 提取 DOF 配置传入引擎
  - `.project-log/current-session.md`
  - `.project-log/progress.md`
- Commit: pending

## 2026-07-06 (扫描器填充时�?帧数 + 定时时区修正 + 审核锁去�?+ 锁面板样式修�?

- Type: bugfix + polish
- Status: backend compile passed, frontend build passed, Docker deployed
- Importance: medium
- Reusable: no
- Objective: 修复数据总库时长/帧数始终�?0；定时扫描北京时间触发；审核锁多处重复显示；人工质检锁面板布局混乱
- Work completed:
  - **扫描器增�?*（scanner.py）：对象遍历阶段记录 manifest_key，遍历结束后下载 manifest.json 解析 duration/frame_count，写�?Episode �?EpisodeInventory
  - **定时任务时区**（scan_scheduler.py）：CronTrigger 增加 timezone='Asia/Shanghai'
  - **审核锁去�?1**（manual-qc.vue）：无人认领�?strong fallback �?'待认�? 改为 '-'，避免与 el-tag 重复
  - **审核锁去�?2**（task-pool.vue）：移除审核锁列�?v-else span 硬编�?未认�?，仅保留 el-tag
  - **锁面板样式修�?*（manual-qc.vue）：scoped CSS 仅设置了 position/z-index，覆盖了全局�?display:flex 等属性。恢�?flex 水平布局 + align-items:center，lock-panel 背景改为 transparent �?bar 渐变融合，新�?.lock-actions flex 居中样式
- Verification: backend compileall 通过，frontend vue-tsc + vite build 通过，Docker 部署成功
- Files changed:
  - backend/app/services/scanner.py �?manifest 下载解析
  - backend/app/services/scan_scheduler.py �?时区修正
  - frontend/src/pages/manual-qc.vue �?锁面板去�?+ 样式修复
  - frontend/src/pages/task-pool.vue �?审核锁列去重
- Commit: pending

## 2026-07-01 (三层日志系统落地：DB审计 + 文件日志 + Docker轮转)

- Type: feature (new)
- Status: backend compile + migration passed, Docker rebuilt + deployed, all 3 tiers verified
- Importance: high
- Reusable: yes (middleware pattern + logging config)
- Objective: 建立专业项目级日志系统，覆盖远程网页操作和本机部署操�?
- Work completed:
  - **Tier 1 �?数据库审计日�?*:
    - Migration `20260701_0015` 增强 `audit_events` 表：新增 event_type/severity/operator_id/ip_address/user_agent/duration_ms 字段
    - 新建 `app/middleware/audit_middleware.py`：BaseHTTPMiddleware 自动捕获所�?API 请求（method/path/status/duration/user/ip/ua），排除 /api/health �?/api/auth/session
    - `get_current_user` 增加 `request.state.user = user` 使中间件能识别已认证用户
    - 补齐缺失审计点：auth login/logout、ReviewerTaskManager (revoke/reassign/release)、batch_adjudication (批次判定)、dataset_service (导出)
  - **Tier 2 �?应用文件日志**:
    - 新建 `app/core/logging_config.py`：TimedRotatingFileHandler 按天轮转，保�?30 天，写入 `/app/logs/app.log`
    - 纯文本格式：`2026-07-01 00:00:01 [INFO] app.services.scanner: 消息`
    - `scan_scheduler.py` �?`scan_queue.py` �?`print()` 替换�?`logger.info()`
  - **Tier 3 �?Docker 日志轮转**:
    - docker-compose.yml 添加 `logging: driver: json-file, max-size: 50m, max-file: 5`
  - Schema/Type 更新：serialize_audit、AuditRecordSchema、AuditRecord TS 类型全部新增对应字段
- Verification:
  - health endpoint 正确跳过（不产生 audit 记录�?
  - login 产生 api_request + auth_event 两条记录
  - 已认�?dashboard 请求正确识别 operator=admin，带 ip_address �?duration_ms
  - `/app/logs/app.log` 正常产出，scheduler 消息已写�?
  - Docker inspect 确认 `max-size=50m max-file=5`
- Files changed:
  - `backend/migrations/versions/20260701_0015_audit_enhance.py` �?新建
  - `backend/app/models/audit.py` �?新增 6 字段
  - `backend/app/middleware/__init__.py` + `audit_middleware.py` �?新建
  - `backend/app/core/logging_config.py` �?新建
  - `backend/app/main.py` �?注册中间�?+ logging 初始�?
  - `backend/app/api/routes/qc.py` �?request.state.user + login 审计
  - `backend/app/services/scan_scheduler.py` �?print �?logger
  - `backend/app/services/scan_queue.py` �?print �?logger
  - `backend/app/services/reviewer_task_manager.py` �?+audit (revoke/reassign/release)
  - `backend/app/services/batch_adjudication.py` �?+audit (批次判定)
  - `backend/app/services/dataset_service.py` �?+audit (导出)
  - `backend/app/services/payloads.py` �?serialize_audit 新增字段
  - `backend/app/schemas/qc.py` �?AuditRecordSchema 新增字段
  - `frontend/src/types/qc.ts` �?AuditRecord 新增字段
  - `software/deploy/docker-compose.yml` �?logging 轮转配置
- Commit: pending

## 2026-06-30 (每日凌晨自动扫描入库 �?APScheduler cron)

- Type: feature (new)
- Status: backend compile passed, Docker rebuilt + deployed, scheduler verified via logs
- Importance: medium
- Reusable: yes (APScheduler + FastAPI lifecycle pattern)
- Objective: 每天凌晨 00:00 UTC 自动触发 MinIO 扫描入库，无需人工点击
- Work completed:
  - `requirements.txt` 新增 `apscheduler` 依赖
  - 新建 `backend/app/services/scan_scheduler.py`：BackgroundScheduler + CronTrigger，每�?00:00 UTC 调用 `run_minio_scan`，查�?active admin 作为 operator，扫描默�?`yaocao` bucket
  - `backend/app/core/config.py` 新增 `scan_cron_hour`/`scan_cron_minute` 环境变量（默�?0/0�?
  - `backend/app/main.py` 注册 `@app.on_event('startup')` 启动 scheduler、`@app.on_event('shutdown')` 停止 scheduler
  - 日志确认：`[scan_cron] scheduler started, daily at 00:00 (UTC)`
- Files changed:
  - `backend/requirements.txt` �?+apscheduler
  - `backend/app/services/scan_scheduler.py` �?新建
  - `backend/app/core/config.py` �?+2 配置�?
  - `backend/app/main.py` �?startup/shutdown events
- Commit: 5404539 �?main

## 2026-06-30 (DI-01 改用深度相机真实时间�?+ 批量修复)

- Type: feature + bugfix
- Status: backend compile passed, Docker deployed, functional test passed
- Importance: high
- Reusable: no
- Objective: DI-01 从检测合成固定fps时间轴改为检测顶部深度相机真实时间戳；修复导出编�?QC筛�?批次选择/checkbox边框等问�?
- Work completed:
  - **DI-01 深度相机时间�?*�?
    - `feature_extractor.py`：`L3V2Features` 新增 `depth_dt` 字段，`FeatureExtractor` 接受可�?`depth_timestamps` 参数计算真实 dt
    - `metric_engine.py`：`_timestamp_regularity()` 检�?`depth_dt`，有则走 `_timestamp_regularity_depth()`（仅评分不输�?timeline 段），无则退回合成轴逻辑
    - `engine.py`：`L3V2Engine.__init__` 新增 `depth_timestamps` 参数，透传�?FeatureExtractor
    - `payloads.py`：`_build_real_manual_qc_context` �?object_rows 中按 `timestamp_npy` + key �?`cam_top_depth` 找到深度相机时间�?npy，`_read_minio_npy` 读取后传入引�?
  - **批量修复**�?
    - 导出：Content-Disposition 使用 RFC 5987 `filename*=UTF-8''...` 修复中文 task_type 报错
    - 数据库：QC 结果筛选改�?`final_dataset_status`，下拉标签中文化
    - 训练数据集：批次汇总表增加 checkbox 批量选择，导出传 batchIds
    - CSS：修�?qc-table checkbox 边框不可见（白色�?909399�?
- Verification: 合成数据两路径测试通过（depth 路径正确抑制 timeline 段）；容器内确认 depth_dt/depth_timestamps 参数存在
- Files changed:
  - `backend/app/services/l3_v2/feature_extractor.py`
  - `backend/app/services/l3_v2/metric_engine.py`
  - `backend/app/services/l3_v2/engine.py`
  - `backend/app/services/payloads.py`
  - `backend/app/api/routes/qc.py`
  - `backend/app/services/dataset_service.py`
  - `frontend/src/api/client.ts`
  - `frontend/src/pages/database-view.vue`
  - `frontend/src/pages/dataset-management.vue`
  - `frontend/src/styles/components.css`
- Commit: 51ee775 �?main

## 2026-06-30 (修复派发重生成数量不稳定 + �?QC 痕迹残留)

- Type: bugfix (high)
- Status: backend compile passed, Docker deployed, API verified
- Importance: high
- Reusable: no
- Objective: 修复 apply_dispatch_plan 重生成时抽样数量不稳定（同样�?15% 有时 5 条有�?8 条），以及进度条不归零的问题
- Root cause: 旧代�?random.sample 从所�?episode 池抽样后，对�?done �?episode 跳过（continue），导致实际任务�?= 目标�?- 随机抽中 done 的数量。同时旧任务不退役、旧手动 QC 状态不清零
- Work completed:
  - **全部归零**：重生成前先重置该批次所�?episode �?QC 字段（qc_status/qc_result/reviewer/reason_code/manual_qc_status/manual_qc_result_id/sampled_for_qc/final_dataset_status/final_decision_source/is_exportable）为初始�?
  - **_supersede_pending_batch_tasks 增强**：改为退役所有旧任务（包�?done），不再跳过
  - **in_review 检查增�?*：增加锁过期判断（lock_expires_at > now），避免过期锁永久阻塞重派发
  - **dispatch_preview_payload 加固**：改�?.get() 取值避�?KeyError
  - **db.flush() 补位**：抽样和任务创建�?flush 确保 sync_batch_metrics 查询可见
  - **返回计数修正**：apply_dispatch_plan 返回时传�?new_task_count �?superseded �?
- Verification: 3 次连�?15% 抽样均返�?sampled=10, created=10, superseded=10；Full 模式 sampled=70, created=70；DB 确认 done_count=0, manual_qc_status 全部 NOT_REVIEWED
- Files changed:
  - `backend/app/api/routes/qc.py` �?apply_dispatch_plan 核心重写 + _supersede_pending_batch_tasks 增强
  - `backend/app/services/payloads.py` �?dispatch_preview_payload 加固
- Commit: 7837de6 �?main

## 2026-06-30 (修复 manual_qc_status 历史未回�?+ 批次判定抽检过滤 + 数据库页面显�?

- Type: bugfix (medium)
- Status: backend compile + frontend build passed, Docker deployed, DB backfill + API verified
- Importance: high
- Reusable: no
- Objective: 修复 RDDQF 迁移后历�?episode �?manual_qc_status 字段未回填导致的批次判定阻塞，以及判定逻辑的抽检计数 bug
- Work completed:
  - **DB 回填**�?2 �?episodes (qc_status='done' �?manual_qc_status='NOT_REVIEWED') �?manual_qc_status �?qc_result 回填 (pass→MANUAL_PASS, fail→MANUAL_FAIL)，涉�?9 个批�?
  - **adjudicate_batch 修复**：reviewed/manual_pass/manual_fail 统计改为只考虑 sampled_for_qc=1 �?episode，修复非抽检 episode 被错误计入导�?reviewed_count vs sampled_count 永远无法对齐的问�?
  - **sync_batch_metrics 修复**：manual_pass_count/manual_fail_count 增加 sampled_for_qc=1 过滤条件
  - **database-view 修复**：PENDING_NOT_ADJUDICATED 映射�?待批次判�?（原显示"-"），新增"人工质检"列（显示 pass/fail 标签�?
  - **重判验证**�? 个批次成功重判（2 ACCEPTED + 1 REJECTED），其余 5 个批次因抽检未完成保�?PENDING（正确）
- Root cause: RDDQF 新增 manual_qc_status 字段�?migration 未回填旧 qc_status/qc_result 数据
- Verification: DB 查询确认 32 �?backfill 成功；API 重判 3 批次成功返回 correct batchDecision + failureRate；前�?database-view JS 已部署含新列和新映射
- Files changed:
  - `backend/app/services/batch_adjudication.py` �?抽检过滤修复
  - `backend/app/services/payloads.py` �?sync_batch_metrics 抽检过滤
  - `frontend/src/pages/database-view.vue` �?新列 + PENDING_NOT_ADJUDICATED 映射
- Commit: 9a3e076 �?main

## 2026-06-29 (训练数据消费与批次驳回模块完整落�?

- Type: feature (major)
- Status: backend compile + frontend build passed, Docker deployed + migration 0012 executed, API verified
- Importance: high
- Reusable: yes
- Objective: 完整落地批次驳回判定 + 训练数据集管理与导出功能，实�?LaTeX 设计文档全部内容
- Work completed:

  ### 数据库层 (migration 20260629_0012)
  - Batch 表新�?9 字段：manual_pass_count, manual_fail_count, failure_rate, reject_threshold (默认0.10), failure_rate_denominator ('SAMPLED_COUNT'), batch_decision (PENDING/ACCEPTED/REJECTED), batch_decision_reason, decision_policy_version, adjudicated_at
  - Episode 表新�?9 字段：manual_qc_status (NOT_REVIEWED/MANUAL_PASS/MANUAL_FAIL), manual_qc_result_id, final_dataset_status (PENDING/QUALIFIED/UNQUALIFIED), final_decision_source, final_decision_reason, final_decided_at, is_exportable, final_decision_policy_version, batch_decision_log_id
  - 新表 batch_decision_log：完整审计日志，包含判定快照

  ### 后端服务
  - `batch_adjudication.py` �?BatchAdjudicationService�?
    - 失败�?= N_fail_manual / N_sampled (分母=抽检�?
    - �?GeneralConfig 读取驳回阈�?
    - 幂等判定：重复执行不产生不一�?
    - 三层状态模型完整实�?(6 �?FinalDecisionSource)
    - adjudicate_batch_if_ready() 自动触发判定
  - `dataset_service.py` �?DatasetSummaryService + DatasetExportService�?
    - 任务级统�?(qualified/total/batch/accepted/rejected/source breakdown)
    - 批次汇总列�?
    - CSV/JSON 导出 (�?QUALIFIED episode)
  - QC 提交联动：submit_manual_qc 自动设置 manual_qc_status (MANUAL_PASS/MANUAL_FAIL) + 触发 adjudicate_batch_if_ready
  - sync_batch_metrics 补全 manual_pass/fail 计数

  ### API 端点
  - `GET /api/dataset/tasks` �?任务列表
  - `GET /api/dataset/tasks/{id}/summary` �?任务统计
  - `GET /api/dataset/tasks/{id}/batches` �?批次列表
  - `GET /api/dataset/tasks/{id}/episodes` �?Episode 列表 (分页+筛�?
  - `POST /api/dataset/tasks/{id}/exports` �?导出 CSV/JSON
  - `POST /api/batches/{batch_id}/recompute-decision` �?手动重判

  ### 前端
  - 新页�?`dataset-management.vue` �?训练数据集管理：
    - 任务选择�?+ 统计卡片 (合格/总数/批次判定/人工结果)
    - 判定来源分布面板
    - 批次汇总表 (失败�?+ 判定状�?+ 重判按钮)
    - Episode 列表 (最终状�?判定来源/人工结果 筛�?+ 分页)
    - CSV/JSON 导出按钮
  - 路由 `/dataset-management` 已注�?
  - 菜单�?"训练数据�? (FolderOpened icon) 已添�?

  ### API 验证结果
  - GET /dataset/tasks �?返回 8 个任务类�?
  - GET /dataset/tasks/task_type:tudou/summary �?1506 total, 15 batches, all PENDING
  - GET /dataset/tasks/task_type:tudou/episodes �?正确分页，字段完�?
  - POST /dataset/tasks/task_type:tudou/exports (CSV) �?BOM + 11 字段表头

- Business logic impact:
  - 每次质检员提�?QC 结果后，系统自动更新 episode.manual_qc_status
  - 批次完成抽检后自动执�?adjudicate_batch() 判定
  - 驳回阈值从设置�?通用"tab 读取 (默认 0.10)
  - 下游训练团队可通过 /dataset-management 查看合格数据量和导出清单

- Affected files: 16 new/modified
  - New: batch_adjudication.py, dataset_service.py, dataset-management.vue, migration 0012
  - Modified: batch.py, episode.py, qc.py (model+routes), __init__.py, payloads.py, client.ts, types/qc.ts, router/index.ts, AppLayout.vue

## 2026-06-29 (设置�?通用"tab + 批次驳回阈值参�?

- Type: feature
- Status: backend compile + frontend build passed, Docker deployed + migration executed
- Importance: high
- Reusable: yes
- Objective: 在设置页新增"通用"标签页，承载批次驳回阈值参�?(batch_reject_threshold)；新�?GeneralConfig 存储模型�?API
- Work completed:
  - �?DB 模型 `GeneralConfig`（单�?JSON 存储通用配置�? migration `20260629_0011`
  - `GET/PUT /api/admin/general-config` 端点（仅�?admin�?
  - 前端 `settings.vue` 改为�?tab 结构：`el-tabs` �?"通用" + "L3 v2 指标参数"
  - "通用"tab 包含：批次驳回阈�?θ（el-input-number，默�?0.10，step 0.01�?
  - 解释文案：失败率 = 人工不合格数 / 抽检数，超过阈值触发整批驳�?
  - 前端 API client 新增 `GeneralConfig` 类型 + `fetchGeneralConfig` / `updateGeneralConfig`
  - API 验证：GET 返回默认�?0.1，PUT 成功持久化，GET 后确�?
- Business logic impact:
  - 批次驳回阈值现在是可配置的系统参数，管理员可在设置页实时调�?
  - 后续 BatchAdjudicationService 将从 GeneralConfig 读取此阈�?
  - 失败率分母已明确�?抽检�?（非批次总数），与设计文档一�?

## 2026-06-29 (修复批次计数 BUG：completed_sample_count 与实际差 1)

- Type: bugfix
- Status: fixed + deployed, verified �?test submit shows completed_count == live done_count
- Issue: 批次页面显示已完成数比实际少 1（如 24/25 实际全部 25 已完成，5/6 实际全部 6 已完成）
- Root cause: submit handler �?`db.add(rev)` 后直接调�?`sync_batch_metrics`，但 rev �?flush 导致 episode.manual_qc_result_id 未正确赋值，同时 episode �?qc_status='done' 变更�?sync 查询时可能未�?flush
- Fix: �?`sync_batch_metrics` 前增�?`db.flush()` 确保所�?pending changes 对后续查询可�?
- Verified: 模拟 submit 测试 confirmed completed_count == live done count

## 2026-06-29 (并发登录保护：同账号多人登录互踢)

- Type: feature
- Status: backend compiled + deployed, tested �?new login kicks out old session (A=200, B=200, A_after=401)
- Objective: 防止同一账号被多人在不同设备同时使用。后登录的人会把前面登录的人踢掉
- Change:
  - migration 0014: users 表新�?session_token 字段
  - security.py: create_session_token 加入随机 nonce 确保每次登录生成不同 token
  - set_session_cookie: 登录时将 token 写入 user.session_token �?commit
  - get_current_user: 验证时检�?cookie token 是否�?user.session_token 一致，不一致返�?401
- Verified: 设备A登录→正常访问；设备B登录→正常访问；设备A再次访问�?01

## 2026-06-29 (RDDQF v1.2 平台增强完整落地)

- Type: feature (major)
- Status: backend compile + frontend build passed, Docker deployed + migration 0013 executed, APIs verified
- Importance: high
- Reusable: yes
- Objective: 落地 v1.2 增强：导出字段扩展、导出历史、管理员任务池管理、任务操作日�?
- Work completed:

  ### 数据库层 (migration 20260629_0013)
  - 新表 dataset_export_jobs：记录每次导�?(task_type_id, export_format, episode_count, created_by, created_at)
  - 新表 task_operation_log：记录任务管理操�?(task_id, episode_id, operation, from_reviewer, to_reviewer, operator_id, reason)

  ### 后端服务
  - dataset_service.py 增强�?
    - 导出字段�?11 个扩展到 14 �?(新增 final_decision_reason, reviewer, reason_code, updated_at)
    - record_export() 写入导出历史
    - export_history() 查询导出历史（支持按 task_type 筛选）
  - reviewer_task_manager.py 新增�?
    - get_reviewer_tasks() 获取审核员任务池
    - revoke_task() 撤回任务（status→new, assignee→未派发, lock clear�?
    - release_task() 释放任务回公共池
    - bulk_revoke() 批量撤回
    - 所有操作写�?TaskOperationLog

  ### API 端点
  - `GET /api/dataset/exports` �?导出历史
  - `GET /api/admin/reviewers/{id}/tasks` �?审核员任务列�?
  - `POST /api/admin/qc-tasks/{id}/revoke` �?撤回任务
  - `POST /api/admin/qc-tasks/{id}/release` �?释放任务
  - `POST /api/admin/qc-tasks/bulk-revoke` �?批量撤回
  - 导出端点增强：每次导出记录到 dataset_export_jobs

  ### 前端
  - dataset-management.vue：新增导出历史表�?
  - dashboard.vue：审核员工作量卡片增�?管理任务"按钮 �?el-drawer 任务管理面板
    - 任务列表：任务ID/Episode/任务类型/批次/状�?
    - 待处理任务支持撤回和释放操作
    - 操作原因输入�?
    - done/in_review 任务标记为不可操�?

  ### API 验证结果
  - GET /dataset/exports �?导出后记录正�?(createdBy=系统管理�? episode_count=0)
  - GET /admin/reviewers/{id}/tasks �?正确返回任务列表
  - 导出 CSV �?14 字段完整 (新增 final_decision_reason, reviewer, reason_code)

- Affected files: 12 new/modified
  - New: reviewer_task_manager.py, migration 0013
  - Modified: dataset_service.py, routes/qc.py, qc.py (models), __init__.py, dashboard.vue, dataset-management.vue, client.ts, types/qc.ts

## 2026-06-29 (抽检随机化：百分比抽检改为随机抽取)

- Type: fix
- Status: backend compiled + deployed to production
- Importance: high
- Objective: 修复百分比抽检使用 episodes[:N] �?ID 排序取前 N 条的缺陷，改�?random.sample 随机抽取，确保每次生成抽检集均匀覆盖整个批次
- Change: `routes/qc.py` `apply_dispatch_plan` �?�?`episodes[:target_count]` 替换�?`random.sample(episodes, min(target_count, len(episodes)))`；full 模式保持全量
- No frontend change required (API contract unchanged)
- Verified: sample 30% returns different episode sets on repeated calls; full mode still covers all

## 2026-06-29 (L3 v2 参数配置页面重建�?6 �?RDDQF 参数可配置化)

- Type: feature
- Status: backend compile + frontend build passed, Docker production deployed + migration executed
- Importance: high
- Reusable: yes
- Objective: �?L3 v2 四层引擎中所有硬编码参数（阈�?权重/融合系数）改为可通过设置页面配置，替代旧 L3 v1 时代的占位设置页
- Work completed:
  - �?DB 模型 `L3V2Config`（单�?JSON 存储 86 项参数），含 `default_l3_v2_params()` 完整默认值函�?
  - migration `20260629_0010` 创建 `l3_v2_config` �?
  - 后端 `GET/PUT /api/admin/l3-v2-params` 端点（仅�?admin�?
  - `L3V2Engine` / `FeatureExtractor` / `MetricEngine` / `QualityEngine` 全部接受 `params` 参数链，每个硬编码值改�?`self.p.get('key', default)`
  - `utils.py` `level_from_score` 接受可配�?good/warn 边界
  - `payloads.py` 在构�?manual QC context 时从 DB 读取参数传入引擎
  - 前端 `client.ts` 新增 `L3V2Params` 类型 + `fetchL3V2Params` / `updateL3V2Params` API 函数
  - `settings.vue` 完全重建�?12 个参数分组页�?
    - 动作示范质量：MQ-01(5) / MQ-02(5) / MQ-03(8)
    - 可学习性：LQ-01(8) / LQ-02(8) / LQ-03(8)
    - 数据完整性：DI-01(8) / DI-02(13)
    - 执行诊断：DX-01(9)
    - 特征提取(2) / 质量融合(10) / 评分等级(2)
  - synthetic 测试验证：默认参数与无参数结果一致，修改参数影响评分计算
- Business logic impact:
  - 管理员可通过 /settings 页面实时调整所�?L3 v2 指标阈值、权重和融合策略
  - 修改后下一次加�?manual QC 立即生效，无需重启服务
  - 参数为空时回退到系统默认值，保证向后兼容

## 2026-06-28 (原因码体系重构：�?RDDQF 维度重组，淘汰旧 L2/L3/L4 分类)

- Type: refactoring
- Status: frontend build + backend compile passed, deployed to production
- Importance: medium
- Reusable: yes
- Objective: 将原因码从旧 L2/L3/L4 三级分类重构�?RDDQF 六维分类（L2 视觉/动作示范质量/可学习�?数据完整�?执行诊断/L4 任务/系统），�?L3 v2 质量维度对齐
- Work completed:
  - QcReasonPicker.vue 原因码重组：
    - 删除�?"L3 轨迹�? 分组，拆为三个新分组（动作示范质量、可学习性、数据完整性）
    - 删除 `motion_abnormal`、`joint_limit_risk`、`stall`
    - 新增 `trajectory_unsmooth`(MQ-01)、`action_discontinuity`(MQ-02)、`oscillation`(MQ-03)
    - 新增 `low_effective_action`(LQ-01)、`low_information_density`(LQ-02)、`prolonged_idle`(LQ-03)
    - 新增 `timestamp_irregular`(DI-01)
    - `tracking_error` �?L3 移入"执行诊断"分组
  - payloads.py reason_stats_payload() 完整重构：覆盖所�?26 个原因码�?7 个分类的映射，保留旧码兼�?
  - types/qc.ts ReasonStat.category 改为 string（不再限制为固定枚举�?
  - qc-history.vue reasonTagType 更新为新分类�?tag 颜色映射
- Business logic impact:
  - 质检员选择 Fail 原因时，分类直接对应 L3 v2 的质量维度和指标 ID（如 MQ-01�?
  - 历史审计页的 Top 原因统计按新维度分组
  - 旧数据中�?`motion_abnormal`/`stall`/`joint_limit_risk` 自动映射到对应新分类保证兼容
- Verification:
  - `python3 -m compileall -q app/services/payloads.py` �?通过
  - `npm run build --prefix frontend` �?built in 329ms
  - Docker deploy �?backend/frontend Healthy
- Files changed:
  - `software/frontend/src/components/QcReasonPicker.vue`
  - `software/backend/app/services/payloads.py`
  - `software/frontend/src/types/qc.ts`
  - `software/frontend/src/pages/qc-history.vue`
  - `software/.project-log/progress.md`

## 2026-06-28 (DX-01 + Score Fusion 重构：lag alignment + soft-min + DI cap�? 指标全部完成)

- Type: refactoring
- Status: all 9 metrics refactored, all tests passed, pending production deploy
- Importance: critical
- Reusable: yes
- Objective: 完成 DX-01 lag alignment 诊断重构�?Training Quality Score 总分融合逻辑（soft-min + DI cap），L3 v2 9 指标重构全部完成
- Work completed:
  - DX-01 重构：lag alignment (搜索 k∈[0,min(5,N//10)] 最小化 P50)，severity = 0.5×E_p95/τ_bad + 0.3×E_mean/τ_warn + 0.2×R_persist，score = 10×(1-severity)
  - DX-01 Timeline 分两层：Execution Tracking Error (τ=0.20) + Severe Tracking Error (τ=0.35)，min_dur=0.5s
  - QualityEngine 完全重写�?
    - Motion Quality: 0.35/0.35/0.30 权重 + soft-min (0.8×mean + 0.2×min)
    - Learnability: 0.25/0.35/0.40 权重 + soft-min (0.8×mean + 0.2×min)
    - Data Integrity: 0.4/0.6 权重 + �?soft-min (0.6×mean + 0.4×min)
    - Total = 0.4×Motion + 0.4×Learn + 0.2×Data
    - DI cap: S_data < 3 �?cap 4.5, S_data < 5 �?cap 6.0
    - 新增 reliabilityWarnings �?diagnosticWarnings
  - 前端 manual-qc.vue 评分环已使用 trainingQualityScore（来自质量融合总分�?
  - 前端已显�?DX-01 �?Execution Diagnostics 折叠面板（标�?不进入训练质量总分"�?
- Business logic impact:
  - L3 v2 正式�?Motion QC 升级�?Training Data Quality Assessment
  - DX-01 不再影响训练质量总分，仅作为诊断参�?
  - Data Integrity 异常会触�?Training Quality Score 封顶
  - soft-min 确保任一分项极差时不会靠高分�?拉平�?
- Verification:
  - 合成数据完整测试：Training Quality=7.8(good), DX-01=9.8(good)
  - `python3 -m compileall -q app/services/l3_v2/` �?通过
- Files changed:
  - `software/backend/app/services/l3_v2/metric_engine.py`
  - `software/backend/app/services/l3_v2/quality_engine.py`
  - `software/.project-log/progress.md`
- Next steps:
  - Build & deploy to production containers
  - 在内网环境用真实 episode 验证 9 指标完整输出

## 2026-06-28 (DI-01 + DI-02 重构：鲁棒时间戳规则�?+ 自适应同步阈�?

- Type: refactoring
- Status: backend compile passed, synthetic data tests passed (perfect 10.0 vs degraded 0.0)
- Importance: high
- Reusable: yes
- Objective: �?DI-01 从单一 CV 改为 J_95+R_gap+R_invalid 鲁棒度量，将 DI-02 从固�?700ms 阈值改�?dt_median 自适应阈�?
- Work completed:
  - feature_extractor: `sync_bad_mask`/`timestamp_jitter_cv` 替换�?`sync_valid`/`sync_diff_sec`/`dt_jitter_cv`
  - DI-01 重构：J_95(Robust Jitter) + R_gap(长间隔比�? + R_invalid(非单调比�?，阈�?good=0.05/warn=0.15/bad=0.35
  - DI-01 Timeline: Invalid Timestamp + Timestamp Gap 两类异常�?
  - DI-02 重构：自适应 τ_warn=max(0.05,2*dt_med)、τ_bad=max(0.20,6*dt_med)，替�?700ms
  - DI-02 raw = 0.30*R_flag + 0.25*R_hard + 0.20*R_soft + 0.15*M_sync + 0.10*R_seg
  - DI-02 Timeline: Sensor Sync Warning + Severe Desync 两类（min_dur=0.5s�?
  - sync_diff 统一�?seconds
- Business logic impact:
  - DI-01 不再只看 CV，还能检测非单调/重复时间戳和丢帧
  - DI-02 自适应阈值适配不同采样率的 episode�?5Hz/30Hz/50Hz 都会有不同的合理�?
- Verification:
  - perfect: DI-01=10.0, DI-02=10.0
  - degraded (jitter+invalid+sync loss): DI-01=0.0, DI-02=0.0
  - `python3 -m compileall -q app/services/l3_v2/` �?通过
- Files changed:
  - `software/backend/app/services/l3_v2/feature_extractor.py`
  - `software/backend/app/services/l3_v2/metric_engine.py`
  - `software/.project-log/progress.md`
- Next steps:
  - 继续审查 DX-01，之后所�?9 个指标重构完�?

## 2026-06-28 (LQ-03 重构：segment-level 长持续时间低价值片段检�?

- Type: refactoring
- Status: backend compile passed, ordinal ranking verified (active < pause < idle)
- Importance: high
- Reusable: yes
- Objective: �?LQ-03 从帧级低变化比例改为 segment-level 持续性低学习价值片段占比，复用 LQ-01 有效动作判定，惩罚长时间无监督区间而非短暂停顿
- Work completed:
  - LQ-03 重构：复�?LQ-01 �?Effective Action Mask (E_t)，不再独立定义低变化阈�?
  - State low-change：Q_t = max(arm_qpos_delta, hand_qpos_delta)，τ_Q = max(5e-4, P20(Q))
  - Low-value candidate：L_t = (~E_t) AND (Q_t <= τ_Q)
  - Segment-level：连�?L_t=1 帧合并为 segment，仅统计 duration �?1.0s 的片�?
  - Ratio = T_low(�?s) / T_episode，保持原评分阈�?good=0.18/warn=0.38/bad=0.65
  - Timeline：min_dur=1.0s 的低价值片�?
  - 清理死代码：移除 FeatureExtractor 中的 low_change_mask（不再使用）
- Business logic impact:
  - �?LQ-01/LQ-02 形成 Coverage + Intensity + Low-value Duration 三者互�?
  - 短暂的停顿（<1s）不再被惩罚，只有持续缺乏学习信号的区间才会影响 LQ-03
- Verification:
  - active (continuous): 0.0%, score=10.0
  - pause (3s dead zone): 19.4%, score=9.7
  - idle (mostly static): 24.1%, score=8.5
  - Ordinal: 0.00 < 0.194 < 0.241 �?PASS
  - `python3 -m compileall -q app/services/l3_v2/` �?通过
- Files changed:
  - `software/backend/app/services/l3_v2/feature_extractor.py`
  - `software/backend/app/services/l3_v2/metric_engine.py`
  - `software/.project-log/progress.md`
- Next steps:
  - 继续审查 DI-01/DI-02/DX-01

## 2026-06-28 (LQ-02 重构：Coverage × Intensity 模型 + arm/hand 分离)

- Type: refactoring
- Status: backend compile passed, ordinal ranking verified (rich > sparse > static)
- Importance: high
- Reusable: yes
- Objective: �?LQ-02 �?`0.6*P75(Δa) + 0.4*P75(Δq)` 的全维度运动强度改为 Coverage × Intensity 模型，与 LQ-01 形成互补
- Work completed:
  - feature_extractor: 新增 `state_delta_arm_norm` / `state_delta_hand_norm`（arm/hand qpos 一阶差�?RMS�?
  - metric_engine LQ-02 重构:
    - Effective Coverage R_eff：复�?LQ-01 �?OR 融合逻辑（arm P20+0.004 / hand P20+3/255�?
    - Action Intensity I_a：P75 of max(arm_delta, hand_delta)，仅统计有效帧（E_t=1�?
    - State Intensity I_q：P75 of max(state_arm, state_hand)
    - 新公式：0.7 × (R_eff × I_a) + 0.3 × I_q
    - 新阈值：good=0.030, warn=0.012, bad=0.003（临时值）
  - LQ-02 不生�?Timeline（LQ-01 �?LQ-03 已覆盖）
- Business logic impact:
  - Coverage × Intensity：少量剧烈动作不会让 Information Density 虚高（R_eff 低会拉低总分�?
  - max 融合：arm �?hand 任一活跃即可贡献 Action Intensity，避免静态控制器拉低估计
  - �?LQ-01 形成 Coverage + Intensity 互补关系
- Verification:
  - rich continuous: raw=1.909, score=10.0
  - sparse burst: raw=0.196, score=10.0
  - nearly static: raw=0.002, score=0.0
  - Ordinal: 1.909 > 0.196 > 0.002 �?PASS
  - `python3 -m compileall -q app/services/l3_v2/` �?通过
- Files changed:
  - `software/backend/app/services/l3_v2/feature_extractor.py`
  - `software/backend/app/services/l3_v2/metric_engine.py`
  - `software/.project-log/progress.md`
- Next steps:
  - 所有阈值需用真�?episode 分布重新标定
  - 继续审查 LQ-03/DI-01/DI-02

## 2026-06-28 (LQ-01 重构：arm/hand 分离 + 绝对阈值门�?+ OR 融合)

- Type: refactoring
- Status: backend compile passed, synthetic data tests passed (3 scenarios)
- Importance: high
- Reusable: yes
- Objective: �?LQ-01 从全维度统一 P35 动态阈值改�?arm/hand 分离计算 + 绝对最小值门�?+ OR 融合，避免微小噪声被判为有效动作
- Work completed:
  - feature_extractor: 新增 `action_delta_arm_norm` / `action_delta_hand_norm`（arm/hand 分别计算 RMS），L3V2Features 新增对应字段
  - metric_engine LQ-01 重构:
    - Arm: τ_arm = max(P20(arm_delta), 0.004 rad)
    - Hand: τ_hand = max(P20(hand_delta), 3/255)
    - Effective = arm_delta > τ_arm OR hand_delta > τ_hand（OR 融合�?
    - 保留原评分区�?good=0.50 / warn=0.25 / bad=0.08
  - Timeline: 新增 Low Effective Action 段（min_dur=1.0s），标记长时间无监督信号的区�?
- Business logic impact:
  - 机械臂静止但灵巧手抓�?�?OR 融合正确判定为有效帧
  - 整体微小动作�?0.004 rad）→ 绝对阈值过滤，不被 P20 撑起
  - P20 �?P35 更严格地定义"有效"，只�?top 80% 的动作幅度通过
- Verification:
  - Test A (rich movement, arm+hand): 93.7%, score=10.0 �?PASS
  - Test B (nearly static): 0.0%, score=0.0 �?PASS (absolute gate works)
  - Test C (arm static, hand active): 70.0%, score=10.0 �?PASS (OR fusion works)
  - `python3 -m compileall -q app/services/l3_v2/` �?通过
- Files changed:
  - `software/backend/app/services/l3_v2/feature_extractor.py`
  - `software/backend/app/services/l3_v2/metric_engine.py`
  - `software/.project-log/progress.md`
- Next steps:
  - 继续审查 LQ-02/LQ-03/DI-01/DI-02

## 2026-06-28 (MQ-03 重构：幅度门控振荡检�?+ 持续占比替代 P95)

- Type: refactoring
- Status: backend compile passed, synthetic data tests passed
- Importance: high
- Reusable: yes
- Objective: �?MQ-03 从简单的方向反转 P95 + 手部颤振 P95 重构为幅度门控的持续振荡检测，区分正常精细调整与控制震�?
- Work completed:
  - 重写 `_oscillation_strength_arm()`：对 arm actions 做幅度门控方向反转检�?
    - ε_i = max(P10(|\Δa_i|), 1e-4)：每个维度的最小有效动作阈�?
    - 仅当连续两帧�?|Δa| 都超�?ε_i 且方向翻转时，才算有效反�?
    - 每个反转按振幅加权：(|Δa_t| + |Δa_{t-1}|) / 2
  - 重写 `_chatter_strength_hand()`：同样用幅度门控 + 方向反转，替代旧的单帧阈值判�?
    - 不再用固定阈�?2/255，改�?per-dimension P10 动态门�?
  - MQ-03 聚合�?P95 改为持续异常占比�?
    - R_osc = mean(oscillation > τ_osc(0.03))
    - R_chat = mean(chatter > τ_chat(0.08))
    - raw = 0.6 × R_osc + 0.4 × R_chat
  - 评分改为 score_inverse(raw, good=0.05, warn=0.15, bad=0.35)
  - Timeline 分为两类：Motion Oscillation �?Hand Chatter（独立的 mask_to_segments�?
  - `L3V2Features` 字段重命名：`reversal_rate_per_frame` �?`oscillation_strength`，`hand_chatter_strength` �?`chatter_strength`
- Business logic impact:
  - 正常正弦轨迹（平滑但持续变化）→ oscillation 0.0% �?10分，不再被误�?
  - 随机游走（高频来回修正）�?oscillation 40.7% �?0分，正确捕获
  - 微小精细调整不会被判为振荡（幅度门控过滤了低�?P10 的小动作�?
  - 持续占比�?P95 更能反映"长期处于震荡状�?的语�?
- Verification:
  - 合成测试：平滑正�?score=10.0(good) vs 随机游走 score=0.0(bad) �?PASS
  - Timeline：平滑轨迹无 oscillation/chatter 段；抖动轨迹出现 Hand Chatter(0.1-14.9s)
  - `python3 -m compileall -q app/services/l3_v2/` �?通过
- Files changed:
  - `software/backend/app/services/l3_v2/feature_extractor.py`
  - `software/backend/app/services/l3_v2/metric_engine.py`
  - `software/.project-log/current-session.md`
  - `software/.project-log/progress.md`
- Next steps:
  - 阈�?tau_osc(0.03), tau_chat(0.08) 和评分阈值需真实数据标定
  - 继续审查 LQ-01/LQ-02/LQ-03/DI-01/DI-02

## 2026-06-28 (MQ-01 + MQ-02 算法修正：差分阶数物理学错误)

- Type: bugfix
- Status: backend compile passed, synthetic data tests passed for both metrics
- Importance: high
- Reusable: yes
- Objective: 修复 MQ-01 用二阶差分（加速度）误判稳定加速为不平滑，以及 MQ-02 用一阶差分的 self-referential 归一化未能区�?快速但连续"�?忽快忽慢"两个 bug
- Work completed:
  - MQ-01：`np.diff(n=2)` �?`np.diff(n=3)` 改为真正的三�?jerk，稳定加速时 jerk�? 不再误报
  - MQ-01：新�?`joint_acc_norm`（保留二阶差分备用），阈值改为临时�?`good=0.006/warn=0.018/bad=0.045`
  - MQ-02：从 self-referential `action_discontinuity_strength`（一阶差分的 episode 内归一化）改为 `action_delta2_norm`（arm actions 的二阶差�?P95�?
  - MQ-02：新阈�?`good=0.010/warn=0.030/bad=0.080`，timeline 阈�?0.06
  - MQ-02：限制为 arm 维度（`actions_arm`），避免 hand 0-255 量级污染 RMS
  - 清理死代码：移除 `action_discontinuity_strength` feature，`L3V2Features` 新增 `action_delta2_norm`
- Business logic impact:
  - MQ-01：稳定加速（恒定加速度）→ jerk=0 �?10分，不再被判为不平滑
  - MQ-02：匀速快速动作（Δa 恒定）→ Δ²a=0 �?10分，而忽快忽慢的抖动 �?Δ²a �?�?低分
  - 两个指标现在都正确衡�?变化的变�?而非"变化本身"
- Problems encountered:
  - MQ-02 初版用全�?actions 维度导致 hand 0-255 的噪声主�?P95（�?10），改为只取 arm dims 后正�?
- Verification:
  - MQ-01 合成测试：稳定加�?score=10.0(good) vs 抖动 score=0.0(bad) �?PASS
  - MQ-02 合成测试：匀速快�?score=10.0(good) vs 忽快忽慢 score=0.0(bad) �?PASS
  - `python3 -m compileall -q app/services/l3_v2/` �?通过
- Files changed:
  - `software/backend/app/services/l3_v2/feature_extractor.py`
  - `software/backend/app/services/l3_v2/metric_engine.py`
  - `software/.project-log/current-session.md`
  - `software/.project-log/progress.md`
- Next steps:
  - 阈值需用真�?episode 分布标定（MQ-01 �?MQ-02 的阈值均为临时值）
  - 继续审查 MQ-03/LQ-01/LQ-02/LQ-03 的算法正确�?

## 2026-06-28 (MQ-01 fix: switch from 2nd-order acceleration to 3rd-order jerk)

- Type: bugfix
- Status: backend compile passed, synthetic data test passed
- Importance: high
- Reusable: yes
- Objective: 修复 MQ-01 轨迹平滑度使用二阶差分（加速度）误判稳定加速为不平滑的 bug，改为三阶差分（jerk�?
- Work completed:
  - 与用户深入讨论了 MQ-01 �?MQ-03 的数学原理和物理含义
  - 识别�?MQ-01 �?bug：`np.diff(n=2)` 是加速度，不�?jerk。稳定加速（恒定加速度）被判为抖动
  - feature_extractor.py：`np.diff(n=2)` �?`np.diff(n=3)`，新�?`joint_acc_norm`（保留二阶差分备用），`L3V2Features` 新增 `joint_acc_norm` 字段
  - metric_engine.py：MQ-01 改用 `joint_jerk_norm`，阈值从 `good=0.015/warn=0.04/bad=0.08` 改为临时保守�?`good=0.006/warn=0.018/bad=0.045`，timeline 阈值从 0.06 改为 0.035
  - 更新 description：从"基于关节轨迹二阶差分�?P95"改为"机械臂关节位置三阶差�?P95，衡量加速度变化是否突兀"
  - 分析 DROID 数据集结构（TFRecord 格式�?00 episodes�?1 shards，Franka Panda 单臂+夹爪，无灵巧�?无时间戳/�?effort/�?sync�?
  - 对比 DROID vs TeleDex 数据维度差异，明�?L3 v2 跨数据集适配需要适配�?
- Business logic impact: 稳定加速的示范不再被误判为不平滑。MQ-01 现在正确衡量"加速度的变化率"而非"加速度本身"，更符合训练数据平滑度的语义
- Problems encountered:
  - 初版合成测试数据 arm 值域超出 3.5 导致 dim detection 将其误判�?hand，修正后测试通过
- Resolution:
  - 合成数据验证：稳定加速（恒定加速度）→ jerk�?, score=10.0 (good)；抖动随机游�?�?jerk=0.111, score=0.0 (bad)
- Verification:
  - `python3 -m compileall -q backend/app/services/l3_v2/` �?通过
  - `PYTHONPATH=. python3` 合成数据测试 �?PASS: steady > jittery
- Files changed:
  - `software/backend/app/services/l3_v2/feature_extractor.py`
  - `software/backend/app/services/l3_v2/metric_engine.py`
  - `software/.project-log/current-session.md`
  - `software/.project-log/progress.md`
- Next steps:
  - 阈值需用真�?episode 分布标定（当前为临时值）
  - 继续审查其他指标的算法正确�?

## 2026-06-27 (RDDQF L3 v2 MVP migration: new four-layer engine replaces old L3 v1)

- Type: implementation
- Status: backend compile passed, frontend build passed, containers deployed healthy, pending in-network API verification
- Importance: critical
- Reusable: yes
- Objective: �?L3 从单�?Metric Engine v1�? 个孤立指�?+ Q_motion 综合分）升级�?RDDQF 四层训练数据质量评估引擎（Feature �?Evidence �?Metric �?Quality），并用新架构完全替换旧 v1 指标系统
- Work completed:
  - 深入阅读 GPT 产出�?RDDQF v1.0 完整设计文档体系（Standard、Ontology、Evidence、Metric Library、L3MetricsEngine v2 Architecture、Overall Architecture v2�?
  - 阅读 GPT 产出�?L3 v2 MVP 代码实现（backend/app/services/l3_v2/ 七文�?+ 前后�?patch�?
  - 后端新增 `backend/app/services/l3_v2/` 模块�? 文件）：
    - `telemetry_parser.py` �?解析 telemetry.npz，arm/hand 维度自动检测，手部 0-255 归一化，EE pose 可选提�?
    - `feature_extractor.py` �?14 维可复用特征（jerk、delta、reversal、chatter、tracking、low_change_mask、sync_bad_mask 等）
    - `metric_engine.py` �?9 个指标：MQ-01/02/03（Motion Quality）、LQ-01/02/03（Learnability）、DI-01/02（Data Integrity）、DX-01（Execution Diagnostics�?
    - `quality_engine.py` �?三层聚合：Metric �?Evidence �?Quality Dimension �?Training Quality Score，含中英文元信息
    - `engine.py` �?顶层入口，串联全链路
    - `utils.py` �?score_inverse/score_ratio 评分映射、mask_to_segments timeline 转换、加权平�?
  - 后端 schemas/qc.py 新增 7 �?Pydantic schema（L3V2Report 系列），ManualQcContextSchema 改为 `l3V2: L3V2ReportSchema | None`
  - 后端 payloads.py 切换�?L3V2Engine，移除旧 L3MetricsEngine 调用
  - 后端 routes/qc.py 移除�?L3 超参�?API（GET/PUT /admin/l3-params�?
  - 移除旧代码：`l3_metrics.py`（~500行）、`l3_config.py` 模型、models/__init__.py 中的 L3Config 引用
  - 前端 types/qc.ts 新增 L3V2 系列 TypeScript 类型，替换旧 MetricCard/TimelineSegment
  - 前端 api/client.ts 更新 ManualQcContext 接口，移�?L3Params API 函数
  - 前端 manual-qc.vue 重写：Training Quality 评分环、质量维度树、Evidence Group、Metric 明细、Execution Diagnostics 诊断面板、Timeline 段点击跳�?
  - 前端 settings.vue 精简为占位页（L3 v2 阈值当前为内置默认值）
  - 前端 mock.ts 清理�?metricCards/timelineSegments 常量
  - 修复 score-ring 评分环：从静�?border 装饰改为 SVG stroke-dasharray 动态进度环，根据分�?0-10 映射�?0-100% 填充
- Business logic impact: L3 从现在起正式�?"Motion QC" 升级�?"Training Data Quality Assessment"。新系统不再围绕"能算什么指�?组织，而是围绕"这条 demonstration 对下游策略学习有多大价�?来设计。Tracking Error 降级�?Execution Diagnostics（不进训练质量总分），Dead/Static/Saturation 等旧指标语义�?Evidence 层重新解释�?
- Problems encountered:
  - 测试�?Docker 容器访问 MinIO 时超时（用户确认当前不在内网，属于网络问题而非代码问题�?
  - schemas/qc.py 缺少 `from __future__ import annotations` 导致 Pydantic 前向引用 NameError，已修复
  - �?ManualQcMediaSchema 在替�?MetricCardSchema/TimelineSegmentSchema 时被误删，已恢复
  - 前端 mock.ts 仍引用已删除�?MetricCard/TimelineSegment 类型，已清理
  - GPT 产出�?manual-qc.vue 保留了旧�?metricCards fallback 路径（v-else），已移�?
- Resolution:
  - L3V2Engine 用合成数据验证通过：Training Quality Score=6.94, 3 dimensions, 7 timeline segments
  - 所有代码编�?构建通过，Docker 容器重启后健康运�?
  - 真正的端到端验证（真�?episode �?qc-context API + 浏览�?manual QC 页面）需在内网环境下进行
- Verification:
  - `python3 -m compileall -q backend/app/services/l3_v2/ backend/app/schemas/qc.py backend/app/services/payloads.py backend/app/api/routes/qc.py backend/app/models/__init__.py` �?通过
  - `python3 -c "from app.services.l3_v2 import L3V2Engine; print('OK')"` �?OK
  - `docker exec robot-qc-backend python3 -c "..." ` 合成数据测试 �?Score: 6.94, Level: warn, 3 dims, 7 timeline, OK
  - `npm run build --prefix frontend` �?built in 316ms
  - `docker compose build backend frontend && docker compose up -d` �?容器全部 Healthy
- Unverified items:
  - 内网环境下真�?episode �?`/api/episodes/{id}/qc-context` 返回 l3V2 字段验证
  - 浏览器端 manual QC 页面 RDDQF 训练质量评分完整交互验证
  - L3 v2 阈值标定（当前�?metric_engine.py 硬编码，后续需按任务类型建立阈值组�?
- Files changed:
  - `software/backend/app/services/l3_v2/__init__.py` (new)
  - `software/backend/app/services/l3_v2/engine.py` (new)
  - `software/backend/app/services/l3_v2/telemetry_parser.py` (new)
  - `software/backend/app/services/l3_v2/feature_extractor.py` (new)
  - `software/backend/app/services/l3_v2/metric_engine.py` (new)
  - `software/backend/app/services/l3_v2/quality_engine.py` (new)
  - `software/backend/app/services/l3_v2/utils.py` (new)
  - `software/backend/app/schemas/qc.py`
  - `software/backend/app/services/payloads.py`
  - `software/backend/app/api/routes/qc.py`
  - `software/backend/app/models/__init__.py`
  - `software/backend/app/services/l3_metrics.py` (deleted)
  - `software/backend/app/models/l3_config.py` (deleted)
  - `software/frontend/src/types/qc.ts`
  - `software/frontend/src/api/client.ts`
  - `software/frontend/src/pages/manual-qc.vue`
  - `software/frontend/src/pages/settings.vue`
  - `software/frontend/src/api/mock.ts`
  - `software/frontend/src/style.css`
  - `software/.project-log/current-session.md`
  - `software/.project-log/progress.md`
- Next steps:
  - 在内网环境复�?manual QC 完整链路
  - 根据真实 episode �?L3 v2 分数分布标定阈�?
  - 后续按任务类型建立阈值组（Milestone 4�?
  - 继续推进后端质量结果持久化与批次报告（Milestone 3�?

## 2026-06-25 (QcTask updated_at + pipeline auto-advance fix + reviewer dashboard bugfix)

- Type: bugfix
- Status: backend API verified, frontend deployed, auto-advance confirmed working
- Importance: high
- Reusable: yes
- Objective: 修复 reviewer dashboard 显示数据全为 0 �?bug，补�?QcTask.updated_at 字段，修复提交后页面不自动跳转的问题
- Work completed:
  - 新增 `QcTask.updated_at` 字段（Alembic migration 20260625_0006），自动回填历史数据
  - `reviewer_dashboard_payload` 修正：`assignee` 是字符串字段�?`assignee_id`；`updated_at` 用于精确计算今日完成�?
  - `manual-qc.vue` 新增 `watch(episodeId)` 监听路由参数变化，提交后自动重新加载�?episode 上下�?
  - 修正 `submitManualQc` 使用 `_active_task_for_episode` 而非 `.first()`，避免同一 episode 多任务时取到旧版�?
- Problems encountered:
  - `reviewer_dashboard_payload` 首版使用 `QcTask.assignee_id`，但模型字段实际�?`assignee`（字符串），导致 500 错误
  - 前端 try/catch 静默吞掉�?API 错误，reviewer 看到个人看板�?0 但没有任何错误提�?
  - `submitManualQc` �?`.first()` 查询 QcTask，同一 episode 存在多版本任务时拿到旧版本（version=1 而非 active �?version=4/5/6），submit 一直报版本冲突
  - Vue Router 同组件路由切换不重新挂载，`router.push` 后页面内容不更新
  - reviewer 密码过期需通过管理员接口重�?
- Resolution:
  - 查询改用 `QcTask.assignee == reviewer_name`（按名称匹配�?
  - submit 改用 `_active_task_for_episode()`（is_active=1 优先�?
  - 新增 `watch(episodeId, loadContext)` 解决同组件路由切换不刷新的问�?
- Files changed:
  - `backend/app/models/qc.py`
  - `backend/app/services/payloads.py`
  - `backend/app/api/routes/qc.py`
  - `backend/migrations/versions/20260625_0006_qc_task_updated_at.py`
  - `frontend/src/pages/manual-qc.vue`
- Verification:
  - `alembic upgrade head` 成功添加 updated_at 列并回填
  - API: reviewer dashboard 返回 pendingCount=13, doneTodayCount=4
  - API: submit 返回 remainingCount �?nextEpisodeId 正确
  - Playwright E2E: reviewer 登录 �?看板 �?开始质检 �?提交 �?自动跳转链路正常

## 2026-06-25 (Role-based view separation: reviewer dashboard + pipeline mode)

- Type: implementation
- Status: backend API verified (reviewer dashboard returns correct payload), frontend deployed, awaiting browser verification
- Importance: critical
- Reusable: yes
- Objective: 实现角色视图分离，reviewer 使用专属界面完成流水线式质检工作
- Work completed:
  - 后端新增 `GET /api/reviewer/dashboard` 接口，返�?reviewer 个人统计、按批次分组、下一条待处理任务
  - 后端 `submitManualQc` 返回 `remainingCount` + `nextEpisodeId` 支持流水线自动跳�?
  - 前端新建 `reviewer-dashboard.vue`（个人任务看板）�? 张统计卡片、一键开始质检按钮、按批次分组任务进度
  - 前端新建 `composables/useCelebration.ts`：canvas-confetti 礼花 + Web Audio API 三音上升音效
  - `manual-qc.vue` 增加流水线模式：reviewer 提交后自动跳转下一条，全部完成触发庆祝动画
  - `task-pool.vue` reviewer 版：去掉批次选择，改为按状态筛选（全部/待处�?进行�?已完成），只显示分配给自己的任务
  - 路由守卫更新：reviewer 登录 �?`/reviewer`，拦截非授权页面访问
  - `AppLayout.vue` 菜单按角色过滤：reviewer 只看个人看板+人工质检入口
  - 安装 `canvas-confetti` + `@types/canvas-confetti`
- Problems encountered:
  - `QcTask` 模型字段�?`assignee`（字符串）而非 `assignee_id`，导致首�?reviewer_dashboard �?500；已修正为按 `assignee == reviewer_name` 查询
  - reviewer 登录密码测试失败，通过管理员接口重置密�?`QcTest123!` 后恢�?
  - `ReviewerDashboardPayload` 需要正确导�?导出类型，前端构建报 TS2724；已拆分为独�?import from types/qc
- Verification:
  - `python3 -m compileall backend/app` �?通过
  - `npm run build --prefix frontend` �?通过
  - `docker compose build backend frontend && docker compose up -d` �?部署成功
  - `curl -b reviewer_cookies /api/reviewer/dashboard` �?pendingCount=17, batchGroups=2, nextTask 正确
  - `curl -b admin_cookies /api/reviewer/dashboard` �?403（admin 不可访问�?
- Unverified items:
  - 浏览器端 reviewer 登录 �?个人看板 �?开始质检 �?流水线提�?�?自动跳转 �?庆祝动画完整链路
  - task-pool reviewer 版在浏览器中的筛选按钮交�?
- Files changed:
  - `backend/app/api/routes/qc.py`
  - `backend/app/schemas/qc.py`
  - `backend/app/services/payloads.py`
  - `frontend/src/pages/reviewer-dashboard.vue` (new)
  - `frontend/src/composables/useCelebration.ts` (new)
  - `frontend/src/pages/manual-qc.vue`
  - `frontend/src/pages/task-pool.vue`
  - `frontend/src/router/index.ts`
  - `frontend/src/components/AppLayout.vue`
  - `frontend/src/api/client.ts`
  - `frontend/src/types/qc.ts`
  - `frontend/package.json`

## 2026-06-25 (Manual QC metric panel: scrollable + severity-sorted, task-type search)

- Type: implementation
- Status: validated by frontend build, production compose redeploy, and browser verification
- Importance: medium
- Reusable: yes
- Objective: 优化人工质检评分面板的子评分展示和任务类型管理页的列表浏览体�?
- Work completed:
  - manual QC 评分区域新增 `sortedMetricCards` computed，按严重程度排序（bad 红色 �?warn 黄色 �?good 绿色），让质检员优先看到问题指�?
  - 子评分列表外�?`metric-scroll` 容器，`max-height: 420px`，超出自动滚动，后期扩展条目不受高度限制
  - 任务类型管理页列表新增搜索框（按名称/描述过滤）和滚动容器（`max-height: 480px`），支持大批量任务类型高效定�?
- Files changed:
  - `frontend/src/pages/manual-qc.vue`
  - `frontend/src/pages/task-types.vue`
  - `backend/app/services/payloads.py` (temporary test metrics, reverted)
- Verification:
  - 生产容器 backend + frontend 重建部署后，进入 manual QC 确认滚动条和排序生效
- Next steps:
  - 后续如需扩展子评分条目，直接�?backend `_metric_cards_from_manifest` 中添加即可，前端自动排序+滚动

## 2026-06-25 (UI component abstraction: unified appearance system)

- Type: refactoring
- Status: validated by frontend build, production compose redeploy, and CSS class verification
- Importance: medium
- Reusable: yes
- Objective: 将散落在 style.css 和各页面 scoped style 中的组件外观样式统一提取为抽象外观类，同类组件保持一致外�?
- Work completed:
  - 新建 `frontend/src/styles/components.css`，定�?5 个抽象组件外观类�?
    - `.qc-card` �?卡片（圆�?20px、边框、阴影）
    - `.qc-stat-card` / `.qc-stat-card-blue|orange|green|purple` �?统计卡片（固定高度、无溢出、装饰圆�? 种配色）
    - `.qc-select` �?下拉框（蓝色常驻边框�?
    - `.qc-table` �?表格（深灰常驻滚动条、选中行蓝底高亮、选中行内 tag 透明融入、进度条轨道可见�?
    - `.qc-progress` �?进度条（灰色可见轨道�?
  - �?`main.ts` 中引�?`components.css`
  - 批量替换所有页面：`product-card`/`premium-card` �?`qc-card`，`stat-card accent-*` �?`qc-card qc-stat-card qc-stat-card-*`，`dispatch-overview-table` �?`qc-table dispatch-overview-table`，`batch-select` �?`qc-select batch-select`
  - 清理 `style.css`：删除已迁移�?components.css �?~100 行重复样�?
  - 清理 `task-pool.vue` scoped style：删除已�?qc-table/qc-select 覆盖的滚动条和下拉框样式
- Business logic impact: 后续新增页面或修改组件外观只需引用抽象类，不再需要逐页复制样式；同类组件自动保持外观一�?
- Files changed:
  - `frontend/src/styles/components.css` (new)
  - `frontend/src/main.ts`
  - `frontend/src/style.css`
  - `frontend/src/pages/dashboard.vue`
  - `frontend/src/pages/task-pool.vue`
  - `frontend/src/pages/database-view.vue`
  - `frontend/src/pages/qc-history.vue`
  - `frontend/src/pages/accounts.vue`
  - `frontend/src/pages/task-types.vue`
  - `frontend/src/pages/manual-qc.vue`
  - `software/.project-log/progress.md`
- Verification:
  - `npm run build --prefix frontend` �?build 通过
  - `docker compose build frontend && docker compose up -d frontend` �?部署成功
  - `curl` 确认生产 CSS 包含 `qc-card`、`qc-stat-card`、`qc-table`、`qc-select`、`qc-progress` 五个抽象�?
- Next steps:
  - 用户在浏览器端强刷新后验证各页面组件外观一致�?

## 2026-06-24 (Robot QC V1 dispatch workflow refactor: dashboard-owned dispatch + generation versioning)

- Type: implementation
- Status: validated by backend compile, frontend build, migration upgrade, runtime payload checks, and sampled/full/sampled regeneration verification
- Importance: critical
- Reusable: yes
- Objective: 把任务派发从“task-pool 页逐条指派 reviewer”重构为“工作台 batch 级生成待派发任务 + 批量派发 reviewer”的正式流程，并修复 `full -> sampled` 重生成后旧任务仍留在当前活跃视图中的 bug
- Work completed:
  - 业务逻辑文档已先完成更新，正式确立三条约束：1）派发主流程迁移到工作台�?）派发采用“两段式”（先生成待派发任务池，再批量分�?reviewer）；3）同一 batch 的任务重生成采用“活跃派发版本”语义，旧版本未开始任务退役而非继续留在当前视图�?
  - 后端 `Batch` 新增 `active_dispatch_generation`；`QcTask` 新增 `dispatch_generation`、`is_active`、`assignment_mode`，并新增 Alembic revision `20260624_0005_dispatch_generation.py`
  - `serialize_task()`、`DispatchPreviewSchema`、`TaskPoolPayloadSchema`、`DashboardPayloadSchema`、前�?`types/qc.ts` / `api/client.ts` 已同步升级，前后端都能识别任务活跃版本、是否活跃、批量分配模式和新增统计字段
  - `backend/app/services/payloads.py` 已重构：`dispatch_preview_payload()` 现在按当前活跃任务统�?`pendingAssignCount/assigned/inReview/done`，并�?`supersededTaskCount` �?`activeDispatchGeneration`；`dashboard_payload()` 已带�?`dispatchPreviews` �?`reviewerAccounts`，供工作台直接承接派发主流程
  - `backend/app/api/routes/qc.py` �?`dispatch-plan` 已从“追加式创建任务”改为“切�?batch 活跃派发版本 + 退役旧版本未开始任�?+ 生成新版本待派发任务池”；同时新增 `POST /qc/batches/{batch_id}/dispatch-assign`，支�?`even` �?`custom_counts` 两种批量派发模式
  - `dashboard.vue` 已重构为新的派发主入口：
    - 批次总览表显示待派发/已派�?进行�?已完成统�?
    - 新增右侧 `派发工作区`，支持选择 `full/sample` 生成待派发任务、选择 reviewer、选择 `平均派发/指定每人条数` 并一次性完成批量派�?
    - 工作台不再依赖跳转到�?`task-pool` 才能完成派发
  - `task-pool.vue` 已降级为“任务明细中心”：保留�?batch 查看当前任务、锁状态和进入 manual QC 的入口，不再承载生成派发和逐条派发主流�?
  - `AppLayout.vue` 菜单�?topbar 已同步收口：原“人工质检与派发”菜单改为“任务明细中心”，顶部“派发任务”快捷入口改为跳转工作台
- Business logic impact: 系统正式从“单条任务指�?+ manual QC 混合入口”切换为“工作台派发运营 / manual QC 质检执行”双层模式。管理员现在可以先在工作台看到哪�?batch 还没质检完，再先生成待派发任务池，再一次性把任务均分或按指定条数分给多个 reviewer；manual QC 页面只保�?review 执行本身，职责边界清�?
- Problems encountered:
  - 当前生产库尚�?`active_dispatch_generation` 等新字段，必须先�?Alembic migration，否�?dashboard/task-pool payload 会直接报字段不存�?
  - 首轮 sampled/full/full API 验证中出�?`audit_events.id` 冲突，原因是原审�?ID 仅基于秒级时间戳；已改为�?`generation` 也纳�?audit id，避免同秒内重复生成冲突
  - manual QC �?payload 层多处仍通过 `episode_id -> first QcTask` 取任务；在引入活跃版本后，必须改为显式读�?`is_active == 1` 的当前任务，否则 manual QC 可能拿到旧版本任�?
  - mock 数据与前端类型因新增字段报错，已补齐 `dispatchGeneration/isActive/assignmentMode` 以及新的 preview 统计字段
- Resolution:
  - 先引入最小必要字段扩展而不推翻 `QcTask` 模型，用版本语义解决“当前活跃任务池”和“历史任务审计”并存问�?
  - 将派发生成与 reviewer 分配拆成两个接口，避免继续把“采样决定”和“逐条指派”耦死在一�?
  - 用工作台承接批次级派发运营，�?`task-pool` 只保留明细和排障价�?
- Verification:
  - `cd /home/tbl/Project/data_collect/software && python3 -m compileall backend/app`
  - `npm run build --prefix /home/tbl/Project/data_collect/software/frontend`
  - `docker compose -f /home/tbl/Project/data_collect/software/deploy/docker-compose.yml build backend frontend`
  - `docker compose -f /home/tbl/Project/data_collect/software/deploy/docker-compose.yml up -d backend frontend`
  - `docker compose -f /home/tbl/Project/data_collect/software/deploy/docker-compose.yml exec -T backend python -m alembic upgrade head`
  - `curl -sS -c /tmp/robot_qc_admin.cookies -H 'Content-Type: application/json' -d '{"username":"admin","password":"Admin123!"}' http://127.0.0.1:8080/api/auth/login`
  - `curl -sS -b /tmp/robot_qc_admin.cookies http://127.0.0.1:8080/api/dashboard`
  - `curl -sS -b /tmp/robot_qc_admin.cookies http://127.0.0.1:8080/api/task-pool`
  - `curl -sS -b /tmp/robot_qc_admin.cookies -H 'Content-Type: application/json' -d '{"dispatchMode":"sampled","samplingRatio":25,"note":"api test sampled"}' http://127.0.0.1:8080/api/qc/batches/batch_871627c45789aecb/dispatch-plan`
  - `curl -sS -b /tmp/robot_qc_admin.cookies -H 'Content-Type: application/json' -d '{"dispatchMode":"full","samplingRatio":100,"note":"api test full"}' http://127.0.0.1:8080/api/qc/batches/batch_871627c45789aecb/dispatch-plan`
  - `curl -sS -b /tmp/robot_qc_admin.cookies -H 'Content-Type: application/json' -d '{"dispatchMode":"sampled","samplingRatio":25,"note":"api test sampled again"}' http://127.0.0.1:8080/api/qc/batches/batch_871627c45789aecb/dispatch-plan`
  - `docker exec robot-qc-db psql -U robot_qc -d robot_qc -c "select batch_id, count(*) filter (where is_active=1) as active_tasks, count(*) filter (where is_active=0) as superseded_tasks, max(dispatch_generation) as max_generation from qc_tasks where batch_id='batch_871627c45789aecb' group by batch_id;"`
- Unverified items:
  - 还未做浏览器肉眼验收来确认工作台右侧 `派发工作区` 的完整交互体验是否满足你的操作习�?
  - 新增�?`dispatch-assign` 虽已完成接口与前端接线，但还未在浏览器里�?`平均派发` / `指定每人条数` 两种模式各实点一�?
  - 当前 `full -> sampled -> full -> sampled` 重生成链路已经在 API 层验证了旧任务会被退役，但还没在 UI 上完成完整人工回�?
- Files changed:
  - `software/backend/app/models/batch.py`
  - `software/backend/app/models/qc.py`
  - `software/backend/migrations/versions/20260624_0005_dispatch_generation.py`
  - `software/backend/app/schemas/qc.py`
  - `software/backend/app/services/payloads.py`
  - `software/backend/app/api/routes/qc.py`
  - `software/frontend/src/types/qc.ts`
  - `software/frontend/src/api/client.ts`
  - `software/frontend/src/api/mock.ts`
  - `software/frontend/src/pages/dashboard.vue`
  - `software/frontend/src/pages/task-pool.vue`
  - `software/frontend/src/components/AppLayout.vue`
  - `software/frontend/src/style.css`
  - `software/.project-log/current-session.md`
  - `software/.project-log/progress.md`
- Next steps:
  - 让用户在真实浏览器里按新的工作流点测：选择 batch �?生成待派发任�?�?选择 reviewer �?平均/自定义派�?�?从任务明细进�?manual QC
  - 如果工作台布局仍有不顺手的地方，再继续做第二轮 UI 收口，但不再回退到旧 task-pool 逐条派发模式

## 2026-06-25 (Dashboard UI polish: scan panel removal, stat card layout, batch row selection, progress bar visibility, tag border fix)

- Type: implementation
- Status: validated by frontend build, production compose redeploy, and browser hard refresh verification
- Importance: medium
- Reusable: yes
- Objective: 收紧工作台布局并修复多处在真实使用中发现的前端瑕疵
- Work completed:
  - 删除工作�?`dashboard` 中的扫描任务面板，扫描状态只保留在数据总库页，避免功能重复
  - 顶部四个统计卡片（候选总量、已抽中样本、样本完成率、待处理任务）改为固定高�?`overflow:hidden`/`justify-content:center`，不再出现无意义横纵滚动�?
  - 批次派发总览表格新增 `highlight-current-row` + `current-row-key` + `dispatch-overview-table` class，选中批次后整行以蓝底 `#93c5fd` 区分，同时增加左侧蓝色条 `inset 4px 0 0 #2563eb`
  - 表格滚动条改为常驻显示（`opacity:1` on `.el-scrollbar__bar`），颜色深灰 `#475569`
  - 样本完成列的 `el-progress` 白色轨道改为 `#cbd5e1` 灰色，未选中行时也能看到进度�?
  - 修复选中行内 `el-tag`（派发模式、状态）边框白框残留问题：`border-color: transparent; box-shadow: none`，使选中�?tag 与行底色完全融合
- Business logic impact: 工作台页面现在更接近正式运营看板风格，不再存在布局和选中等基本体验缺�?
- Problems encountered:
  - 首轮 `highlight-current-row` 未绑�?`current-row-key`，导致选中行在 change 事件中失效，行背景始终为白色
  - el-tag 组件在选中行中即使背景设为 `transparent`，仍保留 `<el-tag>` 自身的白色边框，必须额外清除 `border-color` �?`box-shadow`
  - `el-progress` 默认轨道背景为白色，在白色行背景上完全不可见，只有选中后才因蓝底凸�?
  - 前两�?build/deploy 后用户反馈没变化，原因是只做了本�?build 但没重建 Docker frontend 容器
- Resolution:
  - 每次前端修改后统一执行 `npm run build && docker compose build frontend && docker compose up -d frontend` 确保 production 容器落地最新代�?
  - 选中行样式需要同时覆�?`td` 上的 `background`、`el-tag` 上的 `background/border/box-shadow`、`el-progress` 的轨道背景这三层才能达到完整效果
- Verification:
  - `npm run build --prefix /home/tbl/Project/data_collect/software/frontend`
  - `docker compose -f /home/tbl/Project/data_collect/software/deploy/docker-compose.yml build frontend`
  - `docker compose -f /home/tbl/Project/data_collect/software/deploy/docker-compose.yml up -d frontend`
  - 用户在浏览器强刷后确认选中效果、进度条可见性、tag 白框等问题均已修�?
- Files changed:
  - `frontend/src/pages/dashboard.vue`
  - `frontend/src/style.css`
  - `frontend/src/components/AppLayout.vue`
  - `software/.project-log/progress.md`
- Next steps:
  - 等待用户继续浏览器验收工作台、任务明细、manual QC 等完整流程，按反馈再继续收口
  - 下一步可考虑提交 git push 本版本作为里程碑
  - `cd /home/tbl/Project/data_collect/software && python3 -m compileall backend/app`
  - `npm run build --prefix /home/tbl/Project/data_collect/software/frontend`
  - `docker compose -f /home/tbl/Project/data_collect/software/deploy/docker-compose.yml build backend frontend`
  - `docker compose -f /home/tbl/Project/data_collect/software/deploy/docker-compose.yml up -d backend frontend`
  - `docker exec robot-qc-backend python -c "from app.core.db import SessionLocal; from app.services.payloads import task_pool_payload; db=SessionLocal(); p=task_pool_payload(db); print('reviewerAccounts=', [item['name'] for item in p['reviewerAccounts']]); print('reviewerWorkloads=', [item['name'] for item in p['reviewerWorkloads']]); db.close()"`
  - `docker exec robot-qc-frontend sh -lc "grep -Rni 'reviewerAccounts\|task-pool-summary-row\|task-pool-stat-card' /usr/share/nginx/html/assets/task-pool* 2>/dev/null || true"`
- Unverified items:
  - 还未做浏览器肉眼验收来确认四块统计卡片滚动条在你当前窗口尺寸下是否完全消�?
  - 还未实点一次真实任务派发按钮来确认 reviewer 新名单在 UI 下拉中可见且能成功提�?
- Files changed:
  - `software/backend/app/schemas/qc.py`
  - `software/backend/app/services/payloads.py`
  - `software/frontend/src/api/client.ts`
  - `software/frontend/src/types/qc.ts`
  - `software/frontend/src/pages/task-pool.vue`
  - `software/.project-log/current-session.md`
  - `software/.project-log/progress.md`
- Next steps:
  - 让用户在真实浏览器里刷新 `task-pool` 页面，确�?reviewer 下拉已出�?`审核�?1/02/03`
  - 继续按用户指出的具体体验问题，逐项优化任务派发中心页面

## 2026-06-24 (Robot QC V1 database page server-side pagination landing)

- Type: implementation
- Status: validated by backend compile, frontend build, runtime payload checks, and production compose redeploy
- Importance: critical
- Reusable: yes
- Objective: �?`database` 页面从“全�?episodes 拉到前端后本地过�?+ 一次性渲染整表”的短期模式，升级为适合数据持续增长与多用户远程使用的正式方案：服务端分页、服务端筛选、前端按页渲�?
- Work completed:
  - 后端 `DatabasePayloadSchema` 与前�?`DatabasePayload` 已扩展分页字段：`totalEpisodes`、`page`、`pageSize`
  - `frontend/src/api/client.ts` 新增 `DatabaseQuery`，`fetchDatabase()` 现可携带 `page/page_size/keyword/batch_id/qc_status/qc_result` 查询参数
  - `backend/app/api/routes/qc.py` �?`GET /api/database` 已切换为正式分页接口，支持页码、页大小、关键字、批次、QC 状态、QC 结果查询
  - `backend/app/services/payloads.py` �?`database_payload()` 已从“全�?episodes 返回”改为“服务端过滤 + total 统计 + offset/limit 返回当前页”；同时保留批次、任务类型、原因统计和最近扫描任务等页面所需 summary 信息
  - `frontend/src/pages/database-view.vue` 已移除本�?`filteredEpisodes` 全量过滤路径，切换为由筛选条件驱动远端请求，并新�?`el-pagination`，当前只渲染当前�?episode
  - 搜索关键字增�?250ms 前端 debounce，避免输入每个字符都立即打请求；批次/QC 状�?QC 结果/每页条数变化时自动回到第一页重新拉�?
  - backend/frontend 生产镜像已重建，compose 运行中的 `robot-qc-backend` / `robot-qc-frontend` 已完成重新部�?
- Business logic impact: `database` 页面正式从“浏览器端持有全�?episode 事实源”切换到“后端分页查询是事实源、前端只渲染当前页”。这意味着后续数据继续增长时，单次打开页面不再需要把全部 episode 拉到浏览器再过滤，远程用户和多用户场景下的网络与大表渲染压力会明显更可控
- Problems encountered:
  - 先前已确�?backend payload 构造本身已压到百毫秒级，但页面切换仍卡顿，说明瓶颈已转到前端大表渲�?
  - `database` 页面原逻辑把关键字、批次、状态、结果全部压在本�?`computed.filter()` 上，导致每次进入页面都要重新处理并渲�?4000+ �?
  - frontend `fetchBootstrap()` 保留�?`database: DatabasePayload` 类型依赖，因此分页字段需要同步进 schema/类型，避免类型合同断�?
- Resolution:
  - 直接按长期方案切换到服务端分�?服务端筛选，而不是继续堆叠本地分页或 `KeepAlive`
  - 在后端维持单一查询事实源，在前端保留轻�?debounce 和分页组件，确保交互仍然简单可�?
- Verification:
  - `cd /home/tbl/Project/data_collect/software && python3 -m compileall backend/app`
  - `npm run build --prefix /home/tbl/Project/data_collect/software/frontend`
  - `docker compose -f /home/tbl/Project/data_collect/software/deploy/docker-compose.yml build backend frontend`
  - `docker compose -f /home/tbl/Project/data_collect/software/deploy/docker-compose.yml up -d backend frontend`
  - `docker exec robot-qc-backend python -c "from app.core.db import SessionLocal; from app.services.payloads import database_payload; db=SessionLocal(); p=database_payload(db, page=2, page_size=50, keyword='', batch_id='', qc_status='', qc_result=''); print(len(p['episodes']), p['page'], p['pageSize'], p['totalEpisodes']); db.close()"`
  - `docker exec robot-qc-backend python -c "from app.core.db import SessionLocal; from app.services.payloads import database_payload; db=SessionLocal(); p=database_payload(db, page=1, page_size=100, keyword='episode', batch_id='', qc_status='', qc_result=''); print(sorted(p.keys())); print(p['page'], p['pageSize'], p['totalEpisodes'], len(p['episodes'])); db.close()"`
  - `docker exec robot-qc-frontend sh -lc "grep -Rni 'el-pagination\|page_size\|qc_status\|batch_id' /usr/share/nginx/html/assets/database-view* 2>/dev/null || true"`
- Unverified items:
  - 还未做真实浏览器肉眼验收来确认切换到 `database` 页面时的体感卡顿是否已经明显下降
  - 还未补第二层“短 TTL 页面缓存”，当前先完成了长期主方案中的服务端分页/筛选部�?
- Files changed:
  - `software/backend/app/api/routes/qc.py`
  - `software/backend/app/schemas/qc.py`
  - `software/backend/app/services/payloads.py`
  - `software/frontend/src/api/client.ts`
  - `software/frontend/src/pages/database-view.vue`
  - `software/.project-log/current-session.md`
  - `software/.project-log/progress.md`
- Next steps:
  - 让用户在真实浏览器里复验 `database` 页面切换体感、筛选、分页、进�?manual QC 等主流程
  - 若切页体感仍有可感知迟滞，再补短时内存缓存作为二级体验增强，而不是替代分页事实源

## 2026-06-24 (Robot QC V1 manual QC synchronized player landing)

- Type: implementation
- Status: validated by build and production QC-context API
- Importance: critical
- Reusable: yes
- Objective: �?manual QC 页面从“三个独立视�?+ �?frame 控制条”升级成统一同步播放器，�?frame 控制栏真正驱动三路视频，并用真实 `fps/durationSec/frameCount` 消除当前时间轴与视频时长不一致问�?
- Work completed:
  - 后端 `EpisodeRowSchema` 新增 `fps` 字段，`payloads.py` 在真�?QC context 中把 `fps` / `durationSec` / `frameCount` 一并返回给前端；fallback mock context 也补上默�?`fps=30.0`
  - `frontend/src/pages/manual-qc.vue` 已重构为受控同步播放器：新增视频 refs、全局 `currentFrame/currentTimeSec/playing` 状态、统一 `playAll/pauseAll/syncVideosToFrame` 控制函数
  - 去掉三路视频的原�?`controls`，禁止用户通过单个视频本地控制把三路画面拖不同�?
  - 底部 frame 区按钮现在真正驱动三路视频：`播放/暂停`、`上一�?下一帧`、`-1s/+1s`、slider 拖动都统一作用于当�?variant 下的所有视�?
  - 当前时间文本改为使用真实 `currentFrame / fps` �?`durationSec` 计算，并�?UI 中显式展示当前秒数、总时长和 fps
  - variant 切换时会先暂停并按当前帧位置把新 variant 同步到同一 inspection point，避�?RGB / Depth 之间切换后时间漂�?
- Business logic impact: manual QC 页面现在正式从“多视频展示页”进入“多视角同步检查工具”的语义。三路视频不再各播各的，frame control bar 成为唯一播放控制权，这使得逐帧核查、同步判断和时间轴定位真正可用，也与业务逻辑文档里定义的统一同步播放器约束保持一�?
- Problems encountered:
  - 现有页面�?frame 区原本只修改前端变量，完全没有驱�?`<video>` 元素，因此播放、暂停、拖动和逐帧操作都不生效
  - 前端原本把当前时间硬编码�?`currentFrame / 30`，与真实 episode �?`durationSec/frameCount/fps` 不一致，导致用户观察到视频显�?9s �?frame 区只�?3s �?
  - 引入 `fps` 字段后，mock 数据和前端类型约束需要同步修正，否则前端构建会报�?
- Resolution:
  - 用统一受控播放器重�?`manual-qc.vue`，让三路视频从“本地独立控件”转为“受 frame bar 控制的显示窗口�?
  - 后端把真�?`fps` 暴露给前端，前端彻底移除硬编�?`30fps` 的时间轴逻辑
  - 同步修正 `types/qc.ts`、`schemas/qc.py` �?fallback payload
- Verification:
  - `cd /home/tbl/Project/data_collect/software/backend && python3 -m compileall app`
  - `npm run build --prefix /home/tbl/Project/data_collect/software/frontend`
  - `docker compose -f /home/tbl/Project/data_collect/software/deploy/docker-compose.yml up --build -d backend frontend`
  - `curl -sS -b /tmp/robot_qc.cookies http://127.0.0.1:8080/api/episodes/batch_5a19fc03a292a170_episode_000013/qc-context`
  - 复核返回值确认：`durationSec=10.0167`、`frameCount=153`、`fps=15.1745`
- Unverified items:
  - 还未做真实浏览器层面的肉眼验收，尤其是“三路视频是否在 UI 中稳定同步播放”和“slider 拖动是否肉眼无漂移”，需要你下一步现场点�?
  - 当前实现没有加入更复杂的自动纠偏（例如某一路落后时的周期性强�?resync）；若实际浏览器解码差异明显，后续可能还需要补更强同步策略
- Files changed:
  - `software/backend/app/schemas/qc.py`
  - `software/backend/app/services/payloads.py`
  - `software/frontend/src/types/qc.ts`
  - `software/frontend/src/pages/manual-qc.vue`
  - `software/.project-log/current-session.md`
  - `software/.project-log/progress.md`
- Next steps:
  - 让用户在浏览器里实测 manual QC 的播放、暂停、拖动、逐帧�?variant 切换
  - 若同步效果稳定，再继续测试刷新预览、认�?释放锁与提交动作

## 2026-06-24 (Robot QC V1 task type management landing)

- Type: implementation
- Status: validated in production API/runtime and frontend build
- Importance: critical
- Reusable: yes
- Objective: 把“任务类型是人工维护主数据、扫描器只同步数据”的业务逻辑真正落到代码，补出任务类型管理入口、后端管�?API、批次回收到 `待分类` 的操作闭环，并增强数据总库筛选能�?
- Work completed:
  - 后端 `TaskType` 模型新增 `is_active` 字段，`Batch` 新增 `is_active` 字段，并新增 Alembic revision `20260624_0004_task_type_management.py`
  - `classification_seed.py` 已同步支�?`TaskType.is_active`，保证系统保底项 `task_type:unclassified` 正常存在
  - 扫描�?`scanner.py` 已调整：�?batch 默认落入 `task_type:unclassified` / `待分类`；已人工分类 batch 在后�?rescan 中不自动覆盖正式任务类型
  - 新增任务类型管理后端 API：`GET/POST/PATCH/DELETE /api/task-types`、`GET /api/task-types/{id}/batches`、`GET /api/batches?task_type_id=...`、`POST /api/task-types/{id}/batches:attach`、`POST /api/task-types/{id}/batches/{batchId}:detach`
  - `待分类` 被收敛为不可编辑、不可删除的系统保底任务类型；删除普通任务类型时，其关联 batch 自动回收�?`待分类`
  - `payloads.py` 已新增任务类型详情与待分类批次池 payload，并�?`database/dashboard/history` 等查询继续限制在 active batch / active list 上，避免历史脏数据重新污染主视图
  - 前端新增独立一级页�?`frontend/src/pages/task-types.vue`，完成任务类型列表、详情、创建、编辑、删除、从待分类加入批次、移出批次回到待分类等主流程
  - `AppLayout.vue` �?`router/index.ts` 已加�?`任务类型管理` 菜单与路由，并限制为 `admin/qc_manager`
  - `database-view.vue` 已补 `filterable`：批次、QC 状态、QC 结果下拉框支持键盘输入筛�?
- Business logic impact: 系统正式从“任务类型主要由扫描归类�?seed 决定”推进到“任务类型由人维护、扫描器只同步数据”。现在管理员和质检主管已经有了独立的任务类型管理入口，可以把待分类批次加入正式任务类型、把错分批次移回待分类再重新加入正确任务、删除任务类型时保留底层 batch/episode/QC 历史不丢�?
- Problems encountered:
  - 首轮实现�?`qc.py` 因插入任务类�?API 过程破坏�?`router` / account 相关结构，导�?backend 容器启动失败，已逐步修复
  - `schemas/qc.py` 中插入新 schema 时一度破坏了 `BatchSummarySchema` 定义�?Pydantic rebuild 顺序，导�?backend 启动失败�?body 解析异常，已修复
  - `attach` 接口最初因 Pydantic body rebuild 问题返回 500，后改为直接接收 `dict` + 显式校验 `batchIds`
- Resolution:
  - 逐步修复 backend 路由结构�?schema 定义，重新构建容器并通过生产 API 复核
  - 对复�?body 解析改用更直接的输入校验，优先保证生产接口稳定�?
  - 保持 `待分类` 为固定任务类型而不是空�?NULL，简化回收与查询语义
- Verification:
  - `cd /home/tbl/Project/data_collect/software/backend && python3 -m compileall app migrations/versions`
  - `npm run build --prefix /home/tbl/Project/data_collect/software/frontend`
  - `docker compose -f /home/tbl/Project/data_collect/software/deploy/docker-compose.yml up --build -d backend frontend`
  - `docker compose -f /home/tbl/Project/data_collect/software/deploy/docker-compose.yml run --rm -e APP_ENV=development backend python -m alembic upgrade head`
  - `curl -sS -b /tmp/robot_qc.cookies http://127.0.0.1:8080/api/task-types`
  - `curl -sS -b /tmp/robot_qc.cookies http://127.0.0.1:8080/api/batches?task_type_id=task_type:unclassified`
  - `curl -sS -X POST -b /tmp/robot_qc.cookies -H 'Content-Type: application/json' -d '{"name":"测试任务类型","description":"用于验证任务管理"}' http://127.0.0.1:8080/api/task-types`
  - `curl -sS -X POST -b /tmp/robot_qc.cookies -H 'Content-Type: application/json' -d '{"batchIds":["batch_1ca97b61f80e9b11"]}' http://127.0.0.1:8080/api/task-types/task_type:测试任务类型/batches:attach`
  - `curl -sS -X POST -b /tmp/robot_qc.cookies http://127.0.0.1:8080/api/task-types/task_type:测试任务类型/batches/batch_1ca97b61f80e9b11:detach`
  - `curl -sS -X DELETE -b /tmp/robot_qc.cookies http://127.0.0.1:8080/api/task-types/task_type:测试任务类型`
  - `curl -sS -i -X PATCH -b /tmp/robot_qc.cookies -H 'Content-Type: application/json' -d '{"name":"不可编辑","description":"x"}' http://127.0.0.1:8080/api/task-types/task_type:unclassified`
  - `curl -sS -i -X DELETE -b /tmp/robot_qc.cookies http://127.0.0.1:8080/api/task-types/task_type:unclassified`
- Unverified items:
  - 还未进行真实浏览器层面的任务类型管理完整点击验收；当前验证主要完成于生产 API 与前端构建层
  - `raw_data` 历史脏批次仍物理存在数据库中，但已从 active 查询面和待分类池中排除；若后续需要彻底清理，仍需单独数据迁移
- Files changed:
  - `software/backend/app/api/routes/qc.py`
  - `software/backend/app/models/task_type.py`
  - `software/backend/app/models/batch.py`
  - `software/backend/app/schemas/qc.py`
  - `software/backend/app/services/classification_seed.py`
  - `software/backend/app/services/payloads.py`
  - `software/backend/app/services/scanner.py`
  - `software/backend/migrations/versions/20260624_0004_task_type_management.py`
  - `software/frontend/src/api/client.ts`
  - `software/frontend/src/api/mock.ts`
  - `software/frontend/src/components/AppLayout.vue`
  - `software/frontend/src/router/index.ts`
  - `software/frontend/src/types/qc.ts`
  - `software/frontend/src/pages/task-types.vue`
  - `software/frontend/src/pages/database-view.vue`
  - `software/.project-log/current-session.md`
  - `software/.project-log/progress.md`
- Next steps:
  - 让用户在浏览器里实机验收 `任务类型管理` 页面�?`database` 页检索增�?
  - 如浏览器体验确认通过，再决定是否�?batch 详情页或任务类型统计增强

## 2026-06-24 (Robot QC V1 scan role gating and raw_data batch cleanup)

- Type: implementation
- Status: validated in production API runtime
- Importance: high
- Reusable: yes
- Objective: 进一步收口扫描权限与扫描结果质量，避免普通质检员误触发入库，并修复 `raw_data` 技术目录被错误识别为独立业务批次的问题
- Work completed:
  - �?`frontend/src/pages/database-view.vue` 接入 `useSessionStore()`，新�?`canScanDatabase` 角色判断，仅�?`admin` �?`qc_manager` 显示扫描卡片�?`扫描入库` 按钮
  - 复核真实异常记录 `batch_7bc7918c36426ae5_episode_000000`，确认其来源�?list prefix `double_linkerhand_task_fengqintudou_.../raw_data/` 被扫描器直接当成业务 list，导�?batch 名错误落�?`raw_data`
  - �?`backend/app/services/scanner.py` 新增技术包装目录归一化规则：`raw_data`、`processed_data`、`data` 不再作为最终业�?list 名，而会折叠回上一�?prefix
  - 保留历史脏数据在库中但标�?inactive，同时在 `backend/app/services/payloads.py` 中把 `database/dashboard` �?batch/episode 查询改为只返�?active list 对应的数据，避免旧脏记录继续污染页面
  - 通过生产 API 复核确认：`database` 返回中已经看不到 `raw_data` 批次，也看不�?`batch_7bc7918c36426ae5_episode_000000` 这条异常 episode
- Business logic impact: 现在扫描链路的对外语义更稳定了。角色层面，普通质检员不会再看到扫描入口；数据层面，MinIO 中技术包装目录不会再被误当成业务批次名称，历史脏记录也不会再出现在主页面检索结果里
- Problems encountered:
  - 首轮 `raw_data` 修复过程中，一次扫描任务因局部改动误�?`_ensure_task_type` 定义而失败，随后已修正并重新部署
  - 历史脏批�?`batch_7bc7918c36426ae5` 在数据库里仍然存�?1 �?episode 记录，因此不能只修扫描规则，还需要同步收口查询层
- Resolution:
  - 恢复 `_ensure_task_type` 正常定义后重新部�?backend
  - 采取“扫描规则修�?+ 查询层只返回 active list 数据”的双保险方式，先消除用户可见问题，再保留后续物理清理空�?
- Verification:
  - `npm run build --prefix /home/tbl/Project/data_collect/software/frontend`
  - `docker compose -f /home/tbl/Project/data_collect/software/deploy/docker-compose.yml up --build -d frontend`
  - `cd /home/tbl/Project/data_collect/software/backend && python3 -m compileall app`
  - `docker compose -f /home/tbl/Project/data_collect/software/deploy/docker-compose.yml up --build -d backend`
  - `curl -sS -b /tmp/robot_qc.cookies http://127.0.0.1:8080/api/database`
  - `curl -sS -b /tmp/robot_qc.cookies http://127.0.0.1:8080/api/dashboard`
  - 生产库复核：`lists.is_active`、异�?batch/episode 记录状态查�?
- Unverified items:
  - 历史 `raw_data` 脏批次仍物理保留在库内，但已�?API 主视图剔除；若要彻底清库，还需单独设计数据迁移/清洗步骤
- Files changed:
  - `software/frontend/src/pages/database-view.vue`
  - `software/backend/app/services/scanner.py`
  - `software/backend/app/services/payloads.py`
  - `software/.project-log/current-session.md`
  - `software/.project-log/progress.md`
- Next steps:
  - 继续�?manual QC 播放、刷新、提交与 qc-history 的真实浏览器验收
  - 如需彻底消除历史脏数据，再补一轮数据库清洗迁移

## 2026-06-24 (Robot QC V1 scan robustness and local-time display fix)

- Type: implementation
- Status: validated in real production compose runtime
- Importance: critical
- Reusable: yes
- Objective: 修复 database 扫描任务会卡死在 `scanning` 的生产缺陷，并确保页面刷�?关闭后扫描仍能继续，同时把扫描任务时间从 UTC 错显修正为本地时间显�?
- Work completed:
  - 复核 `backend/app/api/routes/qc.py`、`backend/app/services/scan_queue.py`、`backend/app/services/scanner.py`，确认当�?`/api/database/scan` 通过 FastAPI `BackgroundTasks` 触发长扫描，存在绑定 request 生命周期的风�?
  - 将扫描触发改�?`enqueue_scan_job()`：后端在 API 返回前只负责落库 queued job，随后用独立 daemon thread 启动 `process_scan_job()`，不再依�?HTTP request 的后台任务收�?
  - 保留�?bucket 单活扫描约束不变，但修复了“请求结束后 worker 没真正跑起来，任务永久停�?scanning”的缺陷
  - �?`backend/app/core/config.py` 新增 `APP_TIMEZONE` 配置，默�?`Asia/Shanghai`
  - �?`backend/app/services/payloads.py` 中把数据库内 UTC naive datetime �?UTC 解释后转换到 `APP_TIMEZONE` 再格式化，修�?`startedAt` / `finishedAt` 的本地显�?
  - 在生产库中手动标记两条历史卡死任务失败：`queued_1782269665_user_admin`、`queued_1782270935_user_admin`，解除它们对 `yaocao` bucket 后续扫描的阻�?
  - 修复后重新触发真实生产扫�?`queued_1782271083_user_admin`，并观察到其状态从 `scanning` 进入 `classifying`，最终到 `done`
- Business logic impact: 扫描任务现在与前端页面生命周期解耦。用户点�?`扫描入库` 后，即使刷新页面、关闭页面或请求已返回，扫描仍会继续在服务进程内推进，避免再出现“页面已经结束但 job 永久卡在 scanning、后续点击都被单活保护挡住”的生产事故。同时扫描时间展示已切到本地时区，现场观察与实际触发时间一�?
- Problems encountered:
  - 生产环境中出�?`queued_1782269665_user_admin` 长时间停�?`scanning` �?`total_prefixes=0`、`error_detail=''`，说�?worker 根本没真正推�?
  - 前端显示�?`02:54` 实际是数据库 UTC 时间，用户本地观察时间已是上午，造成明显误判
  - 首轮改成子进�?worker 的方案在当前容器运行时没有成功推进任务，因此改为更直接的进程内独立线程方�?
- Resolution:
  - 将扫�?worker 启动方式收敛�?API 进程�?daemon thread，避免额外子进程启动环境差异
  - 明确�?naive datetime 统一视作 UTC，再�?`APP_TIMEZONE` 转换输出
  - 对已卡死任务执行手动过期，释�?bucket 扫描锁，再用新实现重跑验�?
- Verification:
  - `cd software/backend && python3 -m compileall app`
  - `docker compose -f /home/tbl/Project/data_collect/software/deploy/docker-compose.yml up --build -d backend frontend`
  - `curl -sS -c /tmp/robot_qc.cookies -H 'Content-Type: application/json' -d '{"username":"admin","password":"Admin123!"}' http://127.0.0.1:8080/api/auth/login`
  - `curl -sS -b /tmp/robot_qc.cookies -H 'Content-Type: application/json' -d '{"bucket":"yaocao","scope":"full"}' http://127.0.0.1:8080/api/database/scan`
  - `docker exec robot-qc-db psql -U robot_qc -d robot_qc -c "select id, status, total_prefixes, confirmed_lists, total_episodes, new_episodes, error_detail, started_at, finished_at from scan_jobs order by started_at desc limit 3;"`
  - `curl -sS -b /tmp/robot_qc.cookies http://127.0.0.1:8080/api/database`
- Unverified items:
  - 目前验证的是“请求返回后扫描继续推进并最终完成”，未单独录制“浏览器关闭页签瞬间”场景，但由于新实现已与 HTTP request 生命周期解耦，这一场景与刷新页面在机制上等�?
  - 仍需继续观察长时间生产运行下是否还会产生新的 `stale queued job` 历史残留
- Files changed:
  - `software/backend/app/api/routes/qc.py`
  - `software/backend/app/core/config.py`
  - `software/backend/app/services/payloads.py`
  - `software/backend/app/services/scan_queue.py`
  - `software/.project-log/current-session.md`
  - `software/.project-log/progress.md`
- Next steps:
  - 继续在真实浏览器里复�?database 页扫描提示、manual QC 播放/刷新/提交 �?qc-history
  - 继续观察生产扫描任务在多次触发下的稳定性，确认不再出现新的无进度卡�?

## 2026-06-24 (Robot QC V1 real MinIO production deployment and database-page UX follow-up)

- Type: validation
- Status: partially validated in real production compose runtime
- Importance: critical
- Reusable: yes
- Objective: 在真实本机生产环境完�?MinIO + PostgreSQL + compose 部署收口，并继续收口 database 页面扫描入口与长列表可用性问题，给后续现场验收提供稳定基�?
- Work completed:
  - 生成并落地生产私有配�?`software/deploy/.env`，写�?`SECRET_KEY`、`POSTGRES_PASSWORD`、MinIO endpoint/credentials、默�?bucket `yaocao`、`FRONTEND_ORIGIN` �?`SESSION_COOKIE_SECURE`
  - 扩写 `software/deploy/README.txt`，补�?secret 生成、`.env` 写法、首�?bootstrap、已�?PostgreSQL 卷改密、真�?MinIO 验证与跨机器迁移流程
  - 在真�?compose 环境中完�?PostgreSQL 角色密码同步�?schema/bootstrap 初始化，确认当前部署可直接连接真�?MinIO 数据运行
  - 基于真实运行时确�?database 页面能读取真�?episode、批次与最近扫描任务，并确认扫描触发接口是 `POST /api/database/scan`，不�?`GET`
  - 复核 `frontend/src/pages/database-view.vue`，确认顶�?`扫描入库` 与卡片内 `开始扫描` 都调用同一 `submitScan()`，属于重复入�?
  - 已删除顶部重复扫描按钮，仅保留扫描卡片中的单一主入口，并把按钮文案统一�?`扫描入库`
  - 已为 database �?episode 列表增加独立滚动容器，长表格区域现在具备自己的纵向滚动条
  - 执行 `npm run build --prefix /home/tbl/Project/data_collect/software/frontend`，确认前端改动可正常生产构建
- Business logic impact: 这一步把“能跑”推进到了“真实本机生产部�?+ 用户现场可用性收口”。部署层面已经有私有 env 和迁移手册，database 页面层面则从双入口和长表格难操作的演示态，收紧为更接近实际生产使用的单一主操作入口与可滚动列�?
- Problems encountered:
  - 先前误把进度写到了仓库根目录 `/home/tbl/Project/data_collect/.project-log`，而本项目实际应写 `software/.project-log`
  - 本机 Firefox/Playwright headless 仍无法稳定启动，报错包含 `RenderCompositorSWGL failed mapping default framebuffer`，阻塞了完整浏览器自动化链路
  - database �?episode 列表在真实大数据量场景下没有独立滚动条，导致现场浏览体验明显受影�?
- Resolution:
  - 已停止向错误日志目录继续写入，并把本次记录改写到 `software/.project-log`
  - 现场验收阶段改用“真实部�?+ API 验证 + 页面源码复核 + 用户实机浏览”组合方式继续推进，而不�?Firefox 驱动问题误判成业务故�?
  - 直接删除重复按钮并为表格加独立滚动容器，优先收口当前最影响使用的页面问�?
- Verification:
  - 读取并确�?`software/deploy/.env` 当前生产私有配置
  - 读取并确�?`software/deploy/README.txt` 当前迁移部署手册内容
  - 读取并复�?`software/frontend/src/pages/database-view.vue`
  - `npm run build --prefix /home/tbl/Project/data_collect/software/frontend`
- Unverified items:
  - 仍未完成 manual QC 播放/刷新/提交 �?qc-history 的完整浏览器自动化复验，原因是本�?Firefox/Playwright headless 启动异常
  - 仍需继续观察真实生产扫描 worker 的长期稳定性，以及�?`stale queued job` 历史残留是否还会再出�?
- Files changed:
  - `software/deploy/.env`
  - `software/deploy/README.txt`
  - `software/frontend/src/pages/database-view.vue`
  - `software/.project-log/current-session.md`
  - `software/.project-log/progress.md`
- Next steps:
  - 继续在用户现场浏览器里验�?manual QC 的真实播放、刷新、提交与 qc-history 页面
  - 继续观察真实生产扫描 job 的完成情况，并根据现场体验收口剩�?database/manual QC 交互问题


- Type: implementation
- Status: partially validated on real MinIO data
- Importance: critical
- Reusable: yes
- Objective: �?Node D 合同中的 `media[]`、preview refresh、download 三条 manual QC 媒体访问链路真正落成前后端代码，并在真实 MinIO 对象上验�?payload 形状和预�?URL 发放
- Work completed:
  - 后端 `ManualQcContextSchema` 已扩�?`media[]`，新�?`ManualQcMediaSchema` �?refresh request/response schema
  - 后端 `payloads.py` 已为 processed 视频对象生成标准�?media descriptors：`objectId`、`role`、`label`、`variant`、`slot`、`previewUrl`、`previewExpiresAt`、`refreshable`、`downloadable`、`sortOrder`
  - 后端 `api/routes/qc.py` 已新�?`POST /api/episodes/{episode_id}/media/refresh` �?`GET /api/episodes/{episode_id}/objects/{object_id}/download`
  - 前端 `api/client.ts`、`types/qc.ts`、`pages/manual-qc.vue` 已切到真实媒体描述符消费，manual QC 页面不再只显示静态占位视频卡片，而是基于 `previewUrl` 渲染真实 `<video>` 播放器，并支持刷新预览与下载对象
- Business logic impact: 这一步把 Node D 合同从“结构化 telemetry 已真、视频仍占位”推进到了“结构化对象 + 预览媒体都由 MinIO 控制面统一发放”。前端现在不需要拼 bucket/key，也不需要知道对象命名规则，只消费后端归一化返回的媒体描述�?
- Problems encountered:
  - `telemetry.npz` 通过 MinIO 响应流直�?`numpy.load()` 时不支持 seek，导致真实上下文构建失败
  - `api/routes/qc.py` 插入 refresh/download endpoint 时引入了一处缩进错误，导致 backend compile 失败
  - 当前临时验证库只跑了 scan，没有进�?dispatch/claim 链路，因此媒�?descriptor �?`refreshable` 在真实数据验证中仍为 `false`
- Resolution:
  - `npz` 改为先读�?`BytesIO` 再解�?
  - 修正 route 缩进并重新通过 backend compile
  - 先确认真实媒�?descriptors 和有效预签名 URL 发放无误，refresh 行为留到完整 task 派发后再做链路验�?
- Verification:
  - `cd software/backend && .conda-env/bin/python -m compileall app`
  - `npm run build --prefix software/frontend`
  - 真实 MinIO payload 验证：manual QC payload 已返�?`media_count=3`，并带有�?`previewUrl`
  - 真实结构化上下文验证：`frameCount=394`、`q_motion=5.9`、`timelineSegments=3`
  - 真实端到端任务链验证：`scan -> dispatch -> claim -> media refresh -> submit` 已在 `yaocao` bucket + 临时 SQLite 库上跑通，结果�?`dispatch createdTaskCount=1`、`claim isMine=true`、`refresh 1 True`、`submit ok`、最�?`episode.qc_status=done` / `task.status=done`
  - 生产浏览器媒体验收：Playwright 观察�?`videos=3`、`refreshVisible=true`、`downloadButtons=3`
  - 生产 HTTP scan 验证：最�?`queued_1782241730_user_admin` 已从 `scanning -> classifying -> done` 完整跑通，结果�?`confirmedLists=42`、`totalEpisodes=4097`、`newEpisodes=69`
- Unverified items:
  - 仍需确认 queued scan worker 在连续多次触发下的长期稳定性；历史上存在部分旧 job 被标记为 `stale queued job`
  - 还未完成最终的生产�?secrets 管理收口（当�?compose 已改为环境变量注入，但部署流程尚未固化）
- Files changed:
  - `software/backend/app/schemas/qc.py`
  - `software/backend/app/services/payloads.py`
  - `software/backend/app/api/routes/qc.py`
  - `software/frontend/src/types/qc.ts`
  - `software/frontend/src/api/client.ts`
  - `software/frontend/src/pages/manual-qc.vue`
  - `software/.project-log/current-session.md`
  - `software/.project-log/progress.md`
- Next steps:
  - 继续�?batch/episode -> qc_task 自动生成或派发验证，进入真实持锁任务场景，验�?media refresh
  - 跑浏览器端真实视频播�?下载/提交链路
  - 在生�?compose 环境复现 PostgreSQL + MinIO 联调并形成可上线收尾清单

## 2026-06-23 (Robot QC V1 MinIO scanner/runtime validation and local-field cleanup)

- Type: implementation
- Status: validated on real MinIO data
- Importance: critical
- Reusable: yes
- Objective: 在下游合同切换完成后，继续把旧本地字段从运行路径移除，并用真�?`yaocao` bucket 数据验证 scanner、控制面写入�?manual QC 结构化上下文读取
- Work completed:
  - 新增 `backend/app/services/authz.py`，把权限校验从旧本地 ingestion 模块中独立出来；`api/routes/qc.py` �?`services/scanner.py` 已改为直接依赖该模块
  - 删除旧运行路径中�?`backend/app/services/ingestion.py` �?`backend/app/models/ingest.py`，不再保留本地扫描服务作为运行时入口
  - 清理后端配置与模型中的本地字段：`app/core/config.py` 去掉 `COLLECTION_DATA_ROOT` / `SAMPLE_PROCESSED_ROOT`，`models/batch.py` 去掉 `storage_path`，`models/episode.py` 去掉 `source_path/source_hash/ingest_status`
  - 更新 baseline migration，并新增 `20260623_0003_drop_local_storage_fields.py`，用于正式删�?`ingest_jobs` 表和旧本地字段；同时补上“按实际�?列存在�?drop”的兼容逻辑，保�?fresh 库与历史库都能推�?
  - 新增 `backend/app/services/classification_seed.py`，把业务文档中已经收敛的首版 `task_types + classification_rules` 种子真正写入初始化流程；`bootstrap.initialize_schema()` 现在会自动补齐这�?seed
  - 扩展 `services/scanner.py`：真实扫描后不仅�?`scan_jobs/lists/episode_inventory/episode_objects`，还会同步生�?`batches` �?`episodes` 业务层行，并按规�?seed 绑定 `task_type`
  - 修复 scanner 运行�?bug：纠�?episode inventory 构建块的缩进错误，并修复 `telemetry.npz` �?MinIO 流直�?`np.load()` 时的 seek 问题，改为先读入内存再解�?
- Business logic impact: 到这一阶段，系统已经不再只是“控制面能扫到对象”，而是可以从真�?MinIO bucket 一次扫描落到控制面和业务层，再从这些业务层/控制面数据反向构�?manual QC 所需的结构化上下文。这意味着本地目录方案在核心运行路径上已经被实际替代，而不是只停留�?schema �?UI 文案�?
- Problems encountered:
  - `20260623_0003` 初版�?fresh SQLite 库上�?`ingest_jobs` 尚不存在而直接失�?
  - MinIO SDK 运行依赖�?`.conda-env` 中不完整，导致真实扫描初次验证时缺少 `certifi` / `_cffi_backend`
  - scanner 首次接入 batch/episode 业务层时，episode inventory 构建块被错误挂在 `else` 分支下，导致只生�?list 不生�?inventory
  - `telemetry.npz` 通过 MinIO response 流直接传�?`numpy.load()` 时会因底层流不支�?seek 而失�?
- Resolution:
  - migration 改为对目标表/�?索引先做存在性判断，再执�?drop
  - �?`.conda-env` 中补�?`minio` 运行依赖并完成导入验�?
  - 修正 scanner 的批�?episode 构建逻辑缩进，重新跑真实 bucket 验证
  - `npz` 读取改为 `response.read() -> io.BytesIO -> np.load()`
- Verification:
  - `cd software/backend && DATABASE_URL=sqlite:////tmp/robot_qc_minio_phase.db .conda-env/bin/python -m alembic upgrade head`
  - `cd software/backend && DATABASE_URL=sqlite:////tmp/robot_qc_minio_phase.db .conda-env/bin/python -m app.services.bootstrap --ensure-schema-only`
  - 真实 MinIO 连通性：使用 `MINIO_ENDPOINT=192.168.21.95:9190`、真实凭据、bucket=`yaocao` 成功列出对象
  - 真实 scanner 验证：临�?SQLite 库上�?`run_minio_scan()`，结果为 `lists=39`、`episode_inventory=3699`、`episode_objects=1857532`、`batches=39`、`episodes=3699`
  - 真实 manual QC 结构化上下文验证：`episode_000000` 返回 `frameCount=394`、`q_motion=5.9`、`timelineSegments=3`
  - `cd software/backend && .conda-env/bin/python -m compileall app migrations/versions`
  - `npm run build --prefix software/frontend`
- Unverified items:
  - manual QC 的真实视�?`media[]` descriptor、presigned preview URL、refresh/download API 仍未落地
  - 还未做浏览器层真实视频播放和完整 login -> scan -> database -> manual-qc 的真对象端到端验�?
  - 还未完成阶段�?git commit/push 之后的生�?compose 级联�?
- Files changed:
  - `software/backend/app/services/authz.py`
  - `software/backend/app/services/classification_seed.py`
  - `software/backend/app/services/scanner.py`
  - `software/backend/app/services/payloads.py`
  - `software/backend/app/services/bootstrap.py`
  - `software/backend/app/api/routes/qc.py`
  - `software/backend/app/core/config.py`
  - `software/backend/app/models/__init__.py`
  - `software/backend/app/models/batch.py`
  - `software/backend/app/models/episode.py`
  - `software/backend/app/services/ingestion.py`
  - `software/backend/app/models/ingest.py`
  - `software/backend/migrations/versions/20260623_0001_baseline_schema.py`
  - `software/backend/migrations/versions/20260623_0003_drop_local_storage_fields.py`
  - `software/.project-log/current-session.md`
  - `software/.project-log/progress.md`
- Next steps:
  - 提交�?push 当前阶段版本
  - 落地 `ManualQcContext.media[]`、preview/refresh/download API 与前端真实播放器接线
  - 用真�?MinIO 数据跑浏览器端到端链路并补生�?compose 验收

## 2026-06-23 (Robot QC V1 MinIO 替换继续推进)

- Type: implementation
- Status: partially validated
- Importance: critical
- Reusable: yes
- Objective: 继续�?scan API 切换向下游闭环推进，去掉 manual QC 对本�?processed 目录的依赖，并收口批�?界面/部署中的本地存储语义
- Work completed:
  - 后端 `app/services/payloads.py` 已不再查找本�?processed 目录，manual QC 真实上下文改为通过 `EpisodeInventory + EpisodeObject + ListRecord.bucket` 定位对象，并直接�?MinIO 读取 `manifest.json`、`metadata.json`、`telemetry.npz`
  - 后端 `serialize_batch()` 已从�?`storagePath` 输出切换�?`bucket + storagePrefix`，并通过控制面映射为 batch 提供 MinIO 存储定位信息
  - 前端 `BatchSummary` mock 与下游页面文案继续切�?MinIO：登录页、侧栏、database、task-pool、manual-qc 已去掉本地存储表�?
  - `software/deploy/README.txt` 已改�?MinIO 对象存储说明，`software/deploy/docker-compose.yml` 已移除旧 `/data/collection_data` 业务挂载
  - `frontend/src/api/mock.ts` 已同步把 batch 示例与审计文案切�?MinIO 语义
- Business logic impact: manual QC 指标与时间轴链路现在已经脱离本地目录查找，开始真正依�?MinIO 控制面与对象读取；同�?scan/database/batch 的对外合同已不再继续暴露本地路径，系统运行语义进一步向“MinIO 是唯一数据面”收�?
- Problems encountered:
  - 现有 `Episode/Batch/IngestJob` 模型与旧 `app/services/ingestion.py` 仍保�?`source_path/storage_path` 等本地字段，仓库层面还没有彻底完成结构清�?
  - 当前 scanner 虽已落控制面，但还没有把 `ingested_episode_id` 做成稳定真实映射；本�?batch/minio 对位改为依赖 `episode_id_from_manifest/episode_name/ingested_episode_id` 兜底查找，避免错误绑�?
  - 当前 manual QC 页面的视频区仍是占位 UI，真�?media descriptor、presigned preview URL、refresh/download 接口尚未实现
- Resolution:
  - 先在 payload/query/view 层完成运行路径替换，确保旧本地扫描数据逻辑不再参与当前 manual QC 上下文与 batch 对外合同
  - �?batch �?episode �?MinIO 控制面关联采用查询兜底策略，保证在现有控制面首版数据下也能继续推�?downstream 清理
- Verification:
  - `npm run build --prefix software/frontend`
  - `env -u PYTHONPATH PYTHONNOUSERSITE=1 software/backend/.conda-env/bin/python -m compileall software/backend/app`
- Unverified items:
  - 尚未在真�?MinIO + 数据库样本上跑�?manual QC 页面请求，当前仅完成静态构�?编译验证
  - 尚未通过 migration 正式移除�?`source_path/storage_path` 字段�?`ingest_jobs` / `app/services/ingestion.py` 本地链路
  - 尚未做浏览器�?real media playback 验证
- Files changed:
  - `software/backend/app/services/payloads.py`
  - `software/backend/app/services/scanner.py`
  - `software/frontend/src/api/mock.ts`
  - `software/frontend/src/pages/login.vue`
  - `software/frontend/src/components/AppLayout.vue`
  - `software/frontend/src/pages/task-pool.vue`
  - `software/frontend/src/pages/database-view.vue`
  - `software/frontend/src/pages/manual-qc.vue`
  - `software/deploy/README.txt`
  - `software/deploy/docker-compose.yml`
  - `software/.project-log/current-session.md`
  - `software/.project-log/progress.md`
- Next steps:
  - 继续清理 `app/core/config.py`、`models/batch.py`、`models/episode.py`、`models/ingest.py` �?`app/services/ingestion.py` 中残留的本地存储字段/逻辑
  - 落地 manual QC `media[]` descriptor、presigned preview/refresh/download API，并做浏览器真播放验�?
  - 在真�?MinIO 样本上补一�?scan �?database �?manual QC 的端到端验证


- Type: implementation
- Status: validated
- Importance: critical
- Reusable: yes
- Objective: �?Node D 的首块实现顺序先�?MinIO 控制面数据模型落到代码里，补�?6 张新表的 SQLAlchemy models �?Alembic migration，并确认新库�?bootstrap 初始化都能正确推进到最新版�?
- Work completed:
  - 新增 `software/backend/app/models/control_plane.py`，落�?`scan_jobs`、`discovered_prefixes`、`lists`、`episode_inventory`、`episode_objects`、`classification_rules` 六个 SQLAlchemy model
  - 按业务文档中的字段约束补齐唯一键、外键、关键索引与默认值，包括 `scan_jobs(bucket, started_at)`、`lists(bucket, list_prefix)`、`episode_inventory(list_id, episode_name)`、`episode_objects(episode_inventory_id, object_key)` 等控制面约束
  - 新增 Alembic revision `software/backend/migrations/versions/20260623_0002_minio_control_plane.py`，把 6 张表和对应索引正式纳入迁移链�?
  - 更新 `software/backend/app/models/__init__.py`，把新控制面模型纳入 metadata 导入，确�?Alembic/运行时都能识别到新表
  - 修正 `software/backend/app/services/bootstrap.py`：对“已有旧业务表但尚无 Alembic 版本表”的库，不再直接 `stamp head`，而是�?`stamp 20260623_0001` �?`upgrade head`，避免旧库被错误跳过新控制面 migration
- Business logic impact: Node D 已从纯文�?handoff 进入真实代码落地阶段。系统现在已经有稳定�?PostgreSQL 控制面骨架，能承�?bucket 扫描批次、递归发现�?prefix、去重后�?list、episode 级库存、对象清单与任务分类规则，为后续扫描器实现、classification seed 装载�?manual QC MinIO 化改造提供了正式数据层基础
- Problems encountered:
  - 当前 backend 没有现成测试文件覆盖�?migration，只能先做迁移与初始化级验证
  - `.venv` 中未安装 Alembic，直接在该环境执行迁移失�?
- Resolution:
  - 改用已验证可用的 `software/backend/.conda-env` 运行 Alembic �?bootstrap 验证，保持与现有 backend 验证环境一�?
  - 用临�?SQLite 库同时验�?`alembic upgrade head` �?`python -m app.services.bootstrap --ensure-schema-only`，确�?revision 链与初始化入口都能通过
- Verification:
  - `software/backend/.venv/bin/python -m compileall app/models/control_plane.py app/models/__init__.py app/services/bootstrap.py migrations/versions/20260623_0002_minio_control_plane.py`
  - `cd software/backend && DATABASE_URL=sqlite:////tmp/robot_qc_minio_control_plane.db .conda-env/bin/python -m alembic upgrade head`
  - `rm -f /tmp/robot_qc_minio_control_plane.db && cd software/backend && DATABASE_URL=sqlite:////tmp/robot_qc_minio_control_plane.db .conda-env/bin/python -m app.services.bootstrap --ensure-schema-only`
- Unverified items:
  - 还未实现真正�?MinIO recursive scanner、deepest-match dedup �?`episode_objects` 明细落库逻辑
  - 还未�?classification seed 初始化与基于 `classification_rules` 的自动归类流�?
  - 还未把现�?ingestion/manual QC 查询链路接到 `episode_inventory` / `episode_objects` �?
- Files changed:
  - `.project-log/current-session.md`
  - `.project-log/progress.md`
  - `software/backend/app/models/control_plane.py`
  - `software/backend/app/models/__init__.py`
  - `software/backend/app/services/bootstrap.py`
  - `software/backend/migrations/versions/20260623_0002_minio_control_plane.py`
- Next steps:
  - 实现 MinIO recursive scanner，把 `scan_jobs` / `discovered_prefixes` / `lists` / `episode_inventory` 真正跑起�?
  - 补首�?`classification_rules` seed 装载逻辑，并定义未命�?list 的人工确认入�?
  - 开始把 manual QC 上下文改造为�?`episode_objects` �?MinIO 访问协议生成真实媒体 descriptors

## 2026-06-23 (Robot QC V1 Node D manual QC API contract closure)

- Type: analysis
- Status: documented for implementation handoff
- Importance: critical
- Reusable: yes
- Objective: �?manual QC �?MinIO 混合访问协议已确定后，继续把 Node D 需要的 API 合同收口到可直接指导实现的粒度，明确 `ManualQcContext.media[]` 字段形状、URL 刷新方式、显式下载边界和 review lock 约束
- Work completed:
  - 复核 `software/backend/app/schemas/qc.py` �?`software/frontend/src/api/client.ts`，确认当�?`ManualQcContext` 尚无 `media[]` 字段，Node D 仍存在明显合同缺�?
  - 回看 `control-plane-schema-v1.md` 中上一轮协议结论，把原先仍带二义性的 `url`/`expiresInSec` 方案收紧�?embedded `previewUrl` + `previewExpiresAt`
  - 明确 `media[]` V1 descriptor 最少字段：`objectId`、`role`、`label`、`variant`、`slot`、`mimeType`、`previewUrl`、`previewExpiresAt`、`refreshable`、`downloadable`、`sortOrder`，以及可选的分辨�?帧率/时长元数�?
  - 明确 preview URL 刷新采用 `POST /api/episodes/{episode_id}/media/refresh`，请求只提交 `objectIds`，响应只返回对应对象的新 preview 字段，前端按 `objectId` merge，不整页重载也不�?bucket/key
  - 明确显式下载不复�?preview 字段，而是保留独立 `GET /api/episodes/{episode_id}/objects/{object_id}/download` 受控接口，避免预览与下载权限边界混淆
  - 明确 review lock 与刷新关系：可查看页面的用户可拿到首�?preview URL，但只有当前持锁用户可以持续 refresh；锁丢失后已发出�?URL 自然过期，后端不再续�?
  - 同步更新 `control-plane-schema-v1.md`、`decision-records.md`、`open-questions.md`、`nodes.md`、`graph.md`、`current-session.md`
- Business logic impact: Node D 的实现入口现在不再停留在“以后再决定 payload 怎么长”的模糊状态，而是已经收敛成稳定合同。后端需要做的是�?`episode_objects` 构�?embedded descriptors、签�?刷新 preview URL、受控下载；前端需要做的是消费 `media[]`、按 `previewExpiresAt` 触发 refresh、绝不拼接存储路径。这�?implementation 可以直接围绕明确合同展开，而不是边写边改协�?
- Problems encountered:
  - 上一轮协议虽然已经定下混合模式，�?`qc-context` 是否直接带可�?URL、还是只返回 access endpoint，再由前端二次换取，仍有实现分叉空间
  - 如果 preview �?download 复用一个通用 `url` 字段，后续权限矩阵、审计和播放器行为都会变得含�?
- Resolution:
  - 选定 embedded `previewUrl` 方案，优先降�?manual QC 多视频播放器的首版接入复杂度
  - �?refresh �?download 都收成独立、单职责 endpoint，避免前端和后端对对象访问语义产生歧�?
- Verification:
  - 代码静态复核：`software/backend/app/schemas/qc.py`
  - 代码静态复核：`software/frontend/src/api/client.ts`
  - 文档同步复核：`control-plane-schema-v1.md`、`decision-records.md`、`open-questions.md`、`nodes.md`、`graph.md`
- Unverified items:
  - 仍未把该合同真正落成 Pydantic schema、FastAPI 路由、MinIO presign service 与前端播放器接线代码
  - 仍未确认当前 `yaocao` 样本里三�?RGB/深度视频�?UI 上的最�?`slot`/`label` 命名映射是否需要额外规则表
- Files changed:
  - `.project-log/business-logic/control-plane-schema-v1.md`
  - `.project-log/business-logic/decision-records.md`
  - `.project-log/business-logic/open-questions.md`
  - `.project-log/business-logic/nodes.md`
  - `.project-log/business-logic/graph.md`
  - `.project-log/current-session.md`
  - `.project-log/progress.md`
- Next steps:
  - 进入 Node D 实现规划，把 `ManualQcContextSchema`、前�?`ManualQcContext` 类型、media refresh/download 路由�?MinIO object mapping service 拆成代码任务
  - 再进�?migration/schema/MinIO client 接入�?manual QC 真媒体联调实�?

## 2026-06-23 (Robot QC V1 MinIO list/episode/task classification rule analysis)

- Type: analysis
- Status: documented for control-plane design
- Importance: critical
- Reusable: yes
- Objective: 基于已验证的 `yaocao` bucket 对象布局与样例元数据，先�?MinIO 接入前最关键的三条业务基础规则落地：list 是什么、什么样�?episode 才能进入流水�?进入 QC、以及任务类型应该如何归�?
- Work completed:
  - 基于已确认的真实对象结构 `bucket/<list_prefix>/{raw|processed}/episode_xxxxxx/...`，明�?list 不应等同于单个业务任务，而应视作一次采�?上传来源批次
  - �?V1 �?list 自然身份收敛�?`bucket + list_prefix`，用于稳定承接对象存储里的物理组织单位，而不是直接把 prefix 当最终业务主�?
  - 结合已读取的 `manifest.json`、`metadata.json`、`recording_info.json`，确认当�?episode 内虽�?`episode_id`、处理参数、topic/sensor 结构等丰富信息，但尚未看到可直接充当稳定业务任务主键的单字段
  - 明确 episode 需要区分三层状态：`ingestable`（可接纳入库）、`processable`（可进入处理/补处理链路）、`qc_ready`（processed �?QC 关键对象齐全，可进入 manual QC�?
  - 明确 raw �?processed 不能混为一个业务状态：raw-only episode 可以先建索引与归类，但不应直接进�?manual QC；manual QC 仍以 processed 为准入前�?
  - 明确任务类型不应从单个对象字段硬取，也不应把 MinIO 路径字符串直接当最终分类键；V1 应采用“prefix 命名线索 + episode 元数据证�?+ 后续人工确认”的分层归类方式
  - 明确 PostgreSQL 中后续至少要同时保留 `candidate_task_type` 与最终业�?`task_type` 一类字段，并记�?classification evidence / source，避免每次查询时重新临时解释 MinIO 路径
  - 更新 `.project-log/current-session.md` 与本日志，记录这三条规则，作为后�?schema/API 设计的前置约�?
- Business logic impact: 这次分析把“MinIO 对象如何动态关联到 PostgreSQL 元数据”的核心边界进一步收紧了。后续系统不应把对象路径直接当业务主键，而应先把 list 作为来源批次接住、把 episode 作为最小处理单元管理、再把任务类型沉淀�?PostgreSQL 中可推断可回写的业务字段。这样才能同时兼容“一�?list 一个任务”“多�?list 同一任务”“raw/processed 不对称存在”等真实数据湖场�?
- Problems encountered:
  - 当前样例元数据已经足够描述处理质量、设备形态与传感器结构，但还不足以证明每�?episode 都自带一个稳定显式的业务任务字段
  - MinIO 里的命名规则看起来能提供任务线索，但用户已明确一个任务可能拆散在多个 list 中，因此不能�?prefix 文本直接等价成最终业务任�?
  - raw/processed episode 数量可能不完全一致，如果系统只做二元“有/�?episode”建模，后续 QC 派发与补处理会混�?
- Resolution:
  - �?list、episode、task classification 三层职责拆开定义，避免把对象存储物理组织与上层业务管理强耦合
  - �?episode 生命周期拆成多状态推进模型，以适配“多次少量写入”以�?raw 先到、processed 后补齐的现实过程
  - 将任务类型设计为 PostgreSQL 中的控制面结果，而不�?MinIO 中天然存在的单字段事�?
- Verification:
  - 基于已实查对象路径：`yaocao/K1/.../{raw|processed}/episode_xxxxxx/...`
  - 基于已读取样例元数据：`manifest.json`、`metadata.json`、`recording_info.json`
  - 基于已观察到�?list/prefix 分布：同一 bucket 下存在多个同类命名前缀，且 raw/processed episode 数量并非严格完全对齐
- Unverified items:
  - 还未确认是否有其它任务前缀或更深层对象中存放显式任务标签、工单号或外部任�?ID
  - 还未确定 `candidate_task_type` 到最�?`task_type` 的具体规则映射表和人工确认入口如何落�?
  - 还未确定 V1 �?`qc_ready` 的最小对象清单是否要按任务类型进一步细�?
- Files changed:
  - `.project-log/current-session.md`
  - `.project-log/progress.md`
- Next steps:
  - 继续把这三条规则�?PostgreSQL 最小控制面字段收敛，先�?list / episode_inventory / episode_objects / classification 相关字段
  - 再讨�?ingestion、状态推进、任务派发和 manual QC 查询链路如何围绕这些字段实现


## 2026-06-23 (Robot QC V1 MinIO bucket validation and default-scope confirmation)

- Type: analysis
- Importance: critical
- Reusable: yes
- Objective: 在进�?PostgreSQL 表结构与 MinIO 关联设计前，先实查对象存储是否可访问、episode 实际对象组织方式是什么、以及当�?V1 应默认收敛到哪个 bucket
- Work completed:
  - 使用现有凭据直连 MinIO endpoint，确认当前运行环境可以成功完成认证并列出 bucket
  - 实查到当前可�?bucket 至少包含 `20260527`、`rokae`、`shucai`、`test`、`wen`、`yaocao`
  - 进一步检查样例对象布局，确认业务数据不是“单 episode �?object”，而是“任务前缀/raw|processed/episode_xxxxxx/...�?�?prefix 结构
  - �?`20260527` bucket 中确�?raw 层样例：`.../raw/episode_000000/` 下存�?`device_info.json`、`recording_info.json`、`raw/metadata.yaml`
  - �?`yaocao` bucket 中确�?processed 层样例：`.../processed/episode_000000/` 下存�?`manifest.json`、`metadata.json`、`telemetry.npz`、`camera_info.json`、三�?RGB `mp4`、三�?depth colormap `mp4`、时间戳 `npy` 与深�?png 序列
  - 读取样例 `manifest.json` / `metadata.json` / `recording_info.json`，确�?`episode_id`、时长、帧数、同步误差、视频文件相对路径等关键字段已经存放在对象内元数据文件里，可作为后续 PostgreSQL 建模依据
  - 从对象实查中确认 manual QC 真正依赖的是 processed prefix，而不�?raw prefix，因为当前页面所需�?`telemetry.npz`、多路视频和 manifest 都位�?processed �?
  - 结合用户新增指令，确认当前阶段后续实现默认只连接 `yaocao` 这一�?bucket，把 V1 收敛为单 bucket 版本
  - 更新 `.project-log/current-session.md` 与本日志，记�?MinIO 实查结果和“默�?bucket = yaocao”的范围约束
- Business logic impact: 这次实查把之前的“推测性架构分析”推进成了“可落地约束”。后�?PostgreSQL 不应围绕�?object 建模，而应围绕 episode prefix 建模；同�?V1 �?MinIO 接入范围可先明确收敛�?`yaocao`，这�?schema、配置项、API 解析和前端联调都可以先按�?bucket 假设实现，避免过早引入多 bucket 路由复杂�?
- Problems encountered:
  - 当前仓库里没有现成的 MinIO client 接入代码�?CLI 约定，第一次验证必须先确认本机可用工具�?
  - 对象组织方式与本地文件系统的“一个目录一�?episode”看似相似，但真实结构包�?raw/processed 双层与大量多媒体对象，如果不实查很容易误把关联键设计成单个文件名
  - 当前业务 bucket 并不唯一存在，系统层面若默认支持全部 bucket，会在首版设计时把范围放得过�?
- Resolution:
  - 使用现有 Python `boto3` 能力完成 MinIO 认证、bucket 枚举、prefix 列举、对象清单检查与样例元数据读取，不依赖额外安装工�?
  - 将“episode 关联粒度�?prefix 而不是单 object”记录为后续 schema 设计前提
  - �?`yaocao` 明确记为当前主业�?bucket，并把首版实现范围收敛为默认只连接这一�?bucket
- Verification:
  - `curl -sS -I --max-time 10 http://192.168.21.95:9190`
  - `python3` + `boto3.client('s3', endpoint_url=...)` 成功 `list_buckets()`
  - `list_objects_v2(Bucket='20260527', MaxKeys=20)`
  - `list_objects_v2(Bucket='yaocao', Prefix='K1/.../processed/episode_000000/')`
  - `get_object()` 读取 `manifest.json`、`metadata.json`、`recording_info.json`
  - `list_objects_v2(..., Delimiter='/')` 验证 `K1/<task>/raw|processed/episode_xxx/` 层级
- Unverified items:
  - 还未统计 `yaocao` bucket 在真实生产使用中的完整任务前缀分布�?episode 总量
  - 还未确认后续是否需要从 `yaocao` 之外�?bucket 做历史兼容导�?
  - 还未确认 raw/processed 是否总是成对存在，还是允许仅 processed 入库
- Files changed:
  - `.project-log/current-session.md`
  - `.project-log/progress.md`
- Next steps:
  - 在后续设计中�?`yaocao` 作为默认 bucket 配置项，而不是散落硬编码常量
  - 继续基于已验证的 `processed` prefix 结构设计 PostgreSQL episode/object 映射字段与入库逻辑

## 2026-06-23 (Robot QC V1 MinIO/PostgreSQL lakehouse architecture analysis)

- Type: analysis
- Status: documented for business-logic confirmation
- Importance: critical
- Reusable: yes
- Objective: 在不立即改代码的前提下，先确�?Robot QC 从“本�?processed 目录 + PostgreSQL”迁移到“MinIO 原始对象存储 + PostgreSQL 元数�?QC 湖仓协同”时的业务边界、表结构方向和前后端查询路径
- Work completed:
  - 复核 `software/backend/app/models/episode.py`、`batch.py`、`ingest.py`，确认当�?`episodes.source_path`、`batches.storage_path`、`ingest_jobs.source_path` 仍以宿主本地路径为主键语义，不具备对象存储身份层
  - 复核 `software/backend/app/services/ingestion.py`，确认当前入库流程依赖本地目录扫描、`manifest.json`/`metadata.json`/`telemetry.npz` 存在性判断，以及基于文件路径/mtime �?fingerprint 去重
  - 复核 `software/backend/app/services/payloads.py`，确�?manual QC 上下文仍直接从本�?processed 目录读取 `manifest.json`、`metadata.json` �?`telemetry.npz`，尚未支�?MinIO 对象读取或对象清单解�?
  - 复核 `software/backend/app/api/routes/qc.py` �?`software/frontend/src/api/client.ts`，确认前端当前已经是“只请求后端 API，不直接触达存储”的模式，这与后�?MinIO 后端代理/签名访问方向一�?
  - 复核 `software/frontend/src/pages/database-view.vue` �?`manual-qc.vue`，确认数据库检索页已经�?PostgreSQL 元数据优先的交互，但 manual QC 视频区域仍为占位 UI，尚未绑定真实对象媒�?
  - 明确目标业务边界：MinIO 只保存原�?episode 对象数据，PostgreSQL 继续保存批次、episode 元数据、账号、任务分发、QC 结果、审计日志以及对象映射关�?
  - 明确关联策略方向：保�?`episodes` 作为业务主实体，在其上补外部 episode 标识和对象存储定位字段，并新增一张一对多对象清单映射表承�?bucket/key/prefix 与对象角色信�?
  - 明确查询链路方向：前端质检检索仍先查 PostgreSQL，后端根�?episode/object 映射解析 MinIO 中对应对象，再返回可展示的媒体访问结果或代理流，不让前端直接耦合 MinIO 路径规则
  - 更新 `.project-log/current-session.md` 与本日志，记录本轮属于“先确认业务逻辑，再实施编码”的阶段性结�?
- Business logic impact: 系统后续将从“数据库记录本地路径，再由后端直接读宿主文件”转为“数据库记录业务元数据和对象映射，再由后端按映射解析 MinIO 对象”。这意味着 `episodes` 不再只是一条本地目录索引，而会成为连接批次、QC 状态、对象清单和媒体访问的中心业务实体；前端的检索入口和权限模型可以基本保持不变，但 manual QC 的上下文加载和媒体展示必须改为后端经 PostgreSQL 映射后访�?MinIO
- Problems encountered:
  - 当前入库、去重、manual QC 上下文构建都深度绑定本地文件系统，迁移到 MinIO 不是单点替换，而是一次对象身份模型重�?
  - 现有 schema 只有 `source_path/storage_path` 一类路径字段，没有 bucket、object key、prefix、object role、外�?episode ID 等可长期演进的对象层语义
  - manual QC 页面虽然已经有真�?telemetry 指标链路，但视频区域仍是占位内容，因此未来不仅要解决对象定位，还要补真实媒体访问协议
  - 已获得对象存储连接信息，但这些凭据属于敏感配置，不能以默认值方式写入仓库或进度文档
- Resolution:
  - 将本轮工作限定为业务分析和日志沉淀，不在对象命名规范未确认前提前落表或改接口，避免后续返工
  - �?PostgreSQL 定位为唯一业务查询入口和系统事实源，MinIO 仅作为原始对象数据层，明确前端继续只依赖后端 API
  - 将现�?`episodes`/`batches`/`ingest_jobs` 视为迁移骨架，而不是推倒重建；下一步以“补对象身份层”而非“直接替换成本地 MinIO 路径字符串”为原则设计 schema
- Verification:
  - 代码静态复核：`software/backend/app/models/episode.py`
  - 代码静态复核：`software/backend/app/models/batch.py`
  - 代码静态复核：`software/backend/app/models/ingest.py`
  - 代码静态复核：`software/backend/app/services/ingestion.py`
  - 代码静态复核：`software/backend/app/services/payloads.py`
  - 代码静态复核：`software/backend/app/api/routes/qc.py`
  - 代码静态复核：`software/frontend/src/api/client.ts`
  - 代码静态复核：`software/frontend/src/pages/database-view.vue`
  - 代码静态复核：`software/frontend/src/pages/manual-qc.vue`
- Unverified items:
  - 还未确认 MinIO 中“一�?episode”对应的真实对象组织规则：是单目�?prefix、单对象归档，还是多摄像�?多模态对象散列布局
  - 还未确认 MinIO 内用于关�?PostgreSQL 的稳定唯一标识究竟是对象名、prefix 名、外�?episode_id，还是额外元数据字段
  - manual QC 媒体访问协议已确定为混合模式，但具体 API 字段、签名刷新接口和前端播放器联调尚未实�?
- Files changed:
  - `.project-log/current-session.md`
  - `.project-log/progress.md`
  - `.project-log/business-logic/control-plane-schema-v1.md`
  - `.project-log/business-logic/decision-records.md`
  - `.project-log/business-logic/open-questions.md`
  - `.project-log/business-logic/nodes.md`
  - `.project-log/business-logic/graph.md`
- Next steps:
  - 进入 Node D 实现规划，先�?`ManualQcContext` �?media descriptor 合同、预签名刷新接口与受控下载接口定出来
  - 再进�?schema migration、MinIO client 接入、ingestion 改造、manual QC 媒体加载与前端联调实现阶�?

## 2026-06-23 (Robot QC V1 manual QC MinIO object-access protocol closure)

- Type: analysis
- Status: documented for Node F -> D handoff
- Importance: critical
- Reusable: yes
- Objective: 在进�?MinIO 代码改造前，先落定 manual QC �?MinIO 媒体与结构化对象的访问协议，明确哪些对象�?presigned URL、哪些对象必须继续留在后端受控路径，并把结论写回业务逻辑文档体系
- Work completed:
  - 复核 `software/backend/app/services/payloads.py`，确认当�?manual QC 上下文仍直接从宿主本�?processed 目录读取 `manifest.json`、`metadata.json`、`telemetry.npz`
  - 复核 `software/frontend/src/pages/manual-qc.vue`、`software/frontend/src/api/client.ts` �?`software/backend/app/schemas/qc.py`，确认当�?manual QC 前后端合同里尚无媒体 descriptor 字段，视频区仍为占位 UI
  - 结合已实查的 `yaocao` processed 对象结构，明�?preview/playback �?MP4 与结构化对象的访问特征不同，不能简单采用“全代理”或“全 presigned”单一路径
  - 落定 V1 混合协议：预�?播放�?MP4 由后端签发短�?presigned URL；`manifest.json`、`metadata.json`、`telemetry.npz` 等结构化对象继续由后端直接读�?解析；显式下载、导出与非预览对象访问走后端受控接口
  - �?`control-plane-schema-v1.md` 中补�?manual QC 对象访问章节，定�?media descriptor 合同、URL TTL、授权边界、review lock �?refresh 规则
  - �?Q-20260623-005 标记为已解决，并同步更新 `decision-records.md`、`nodes.md`、`graph.md`、`current-session.md`
- Business logic impact: Node F 的控制面规则至此闭环。系统后续不再讨论“manual QC 到底直接�?MinIO 还是后端代理”的抽象问题，而是按明确分工推进：浏览器用后端签发的短�?URL 直接播放媒体，业务敏感与结构化对象继续由后端掌控。这样既保住“前端只调后�?API”的架构约束，也避免把多路视频预览流量全部压�?backend
- Problems encountered:
  - 当前代码仍是本地文件系统实现，意味着对象访问协议不仅是存储方案选择，还会牵�?`ManualQcContext` payload 结构扩展
  - 如果走纯 presigned，前端会开始感�?bucket/key 语义；如果走纯代理，manual QC 多路视频预览会给 backend 带来不必要的数据面压�?
- Resolution:
  - 采用混合协议，并把“前端永远只接后端返回的 media descriptors，不�?bucket/key”作为硬约束
  - 把协议设计收敛为实现级规则：�?TTL、后端鉴权后签发、需要时刷新、显式下载单独走受控接口
- Verification:
  - 代码静态复核：`software/backend/app/services/payloads.py`
  - 代码静态复核：`software/backend/app/api/routes/qc.py`
  - 代码静态复核：`software/backend/app/schemas/qc.py`
  - 代码静态复核：`software/frontend/src/pages/manual-qc.vue`
  - 代码静态复核：`software/frontend/src/api/client.ts`
  - 文档同步复核：`control-plane-schema-v1.md`、`decision-records.md`、`open-questions.md`、`nodes.md`、`graph.md`

- Type: validation
- Status: validated in real Docker/PostgreSQL runtime
- Importance: critical
- Reusable: yes
- Objective: 收口 V1 最后一轮高风险项，完成真实 Docker/PostgreSQL 发布链路验收、补�?task-pool 多批次浏览器稳定性验证，并修正文档与运行时健康检查不一致问�?
- Work completed:
  - �?`software/frontend` 执行生产构建，确认当前前端代码可生成用于容器镜像�?`dist`
  - 运行专用 Playwright 用例 `/tmp/robot-qc-playwright-runner/tests/task-pool-batch-selection.spec.js`，覆盖空批次、全量批次、可操作批次切换与刷新后的默认选择保持，结�?`1 passed (2.8s)`
  - 复核 `software/deploy/README.txt`、`software/backend/alembic.ini`、`software/backend/app/services/bootstrap.py`，确认当前源代码�?PostgreSQL/Alembic 发布路径已切到显�?bootstrap
  - �?compose 环境启动 `db` 服务并发�?backend 镜像为旧版本；通过容器内源码检查确认仍残留�?`seed_demo_data` 启动逻辑后，重新构建 backend 镜像
  - 在真实容器验收中发现 `software/backend/app/core/config.py` �?`PROJECT_ROOT` 推导�?`/app` 场景下触�?`IndexError`，已修复�?Docker 安全路径计算并补�?`sample_processed_root` fallback
  - 重新构建并执�?`python -m app.services.bootstrap --ensure-schema-only`，确认空 PostgreSQL 数据库成功执�?Alembic `upgrade head`
  - 执行 `python -m app.services.bootstrap --admin-username admin --admin-password 'Admin123!' --admin-name '系统管理�? --admin-role admin`，完成首个管理员初始�?
  - 直接�?Postgres 中确�?9 张业务表已落库、`alembic_version=20260623_0001`、管理员账号存在
  - 重启 compose `backend` / `frontend` 服务并验�?`POST /api/auth/login` 登录成功，确�?production/postgres 基线可用
  - 补上 `software/backend/app/api/routes/qc.py` �?`/api/health` 接口，使 `software/deploy/README.txt` 中的健康检查地址与运行时一�?
  - 更新 `.project-log/current-session.md` 与本日志，移除“Docker/PostgreSQL 发布链路待验收”和“task-pool 多批次稳定性待补强”的过期风险
- Business logic impact: V1 已从“源代码具备 migration �?task-pool 修复”推进到“真�?Docker/PostgreSQL 发布链路和关键浏览器回归均已验收通过”；部署文档中的健康检查地址现已可直接用于实际生产探�?
- Problems encountered:
  - 初次 compose 验收�?backend 镜像与当前工作区源码不一致，容器内部仍然是旧 bootstrap 逻辑，因此表�?exit 0 但数据库未真正建�?
  - `app/core/config.py` 原先假设项目目录层级固定，在 Docker `/app` 运行时会�?`BASE_DIR.parents[1]` 越界而崩�?
  - `README.txt` 已声�?`/api/health`，但运行时此前返�?404，造成部署说明与实际行为不一�?
- Resolution:
  - 通过重新构建镜像消除 stale image 漂移，并以真�?Postgres 表结构与 `alembic_version` 校验发布链路是否正确落地
  - �?`PROJECT_ROOT` 计算改为容器安全逻辑，并在样例数据路径不存在时回退�?`BASE_DIR` 下的 data 目录
  - 直接补齐 `/api/health` 路由，而不是修改文档去适配缺失能力
- Verification:
  - `cd software/frontend && npm run build`
  - `"/tmp/robot-qc-playwright-runner/node_modules/.bin/playwright" test "/tmp/robot-qc-playwright-runner/tests/task-pool-batch-selection.spec.js" --config "/tmp/robot-qc-playwright-runner/playwright.config.js" --reporter=line`
  - `docker compose -f software/deploy/docker-compose.yml up -d db`
  - `docker compose -f software/deploy/docker-compose.yml build backend`
  - `docker compose -f software/deploy/docker-compose.yml run --rm -e APP_ENV=development backend python -m app.services.bootstrap --ensure-schema-only`
  - `docker compose -f software/deploy/docker-compose.yml run --rm -e APP_ENV=development backend python -m app.services.bootstrap --admin-username admin --admin-password 'Admin123!' --admin-name '系统管理�? --admin-role admin`
  - `docker exec robot-qc-db psql -U robot_qc -d robot_qc -c "select version_num from alembic_version;"`
  - `docker compose -f software/deploy/docker-compose.yml up -d --build backend frontend`
  - `curl -sS -i http://127.0.0.1:8080/api/health`
  - `curl -sS -H 'Content-Type: application/json' -d '{"username":"admin","password":"Admin123!"}' http://127.0.0.1:8080/api/auth/login`
- Unverified items:
  - 仍需在真实目标生产环境替�?`SECRET_KEY`、PostgreSQL 口令、`SESSION_COOKIE_SECURE` 与宿主数据挂载路径后做一次最终现场联�?
- Files changed:
  - `software/backend/app/core/config.py`
  - `software/backend/app/api/routes/qc.py`
  - `.project-log/current-session.md`
  - `.project-log/progress.md`
- Next steps:
  - 进入真实生产环境测试，重点验�?HTTPS/cookie、宿主挂载路径与运维口令配置

## 2026-06-23 (Robot QC V1 final account-role browser validation)

- Type: validation
- Status: validated in browser and API runtime
- Importance: high
- Reusable: yes
- Objective: 收尾账号管理页最后一处生产缺口，补齐 `admin` / `qc_manager` / `reviewer` / `viewer` 的前端展示与后端权限矩阵验证
- Work completed:
  - 复核 `software/frontend/src/pages/accounts.vue`、`src/components/AppLayout.vue`、`src/router/index.ts` �?`software/backend/app/api/routes/qc.py`，确认账号页的预期角色矩阵已经在前后端实�?
  - 使用管理员会话为现有 `manager1` / `reviewer1` 账号重置测试口令，并额外创建 `viewer1` 访客账号，补足非管理员浏览器回归前置条件
  - 新增隔离 Playwright 用例 `/tmp/robot-qc-playwright-runner/tests/accounts-role-access.spec.js`，覆盖管理员可管理账号、主管仅可只读访问、审核员/访客无账号菜单且直达 `/accounts` 被重定向回工作台
  - 在当前运行时 `http://127.0.0.1:18081` 上补�?API 级权限复核，确认 `qc_manager` 可读�?`/api/accounts`，但创建账号返回 403；`reviewer` �?`viewer` 访问 `/api/accounts` 均返�?403
  - 更新 `.project-log/current-session.md` 与本日志，移除“账号页非管理员浏览器验证缺失”的过期风险记录
- Business logic impact: 账号管理能力已从“管理员路径验证完成”推进到“完整角色矩阵已验证”，当前 V1 对账户页面的菜单可见性、路由守卫、只�?可变更边界以及后端权限拒绝都已有可信验证证据
- Problems encountered:
  - 本轮环境里原先没有可直接使用�?`qc_manager` / `reviewer` 明确测试口令，导致非管理员浏览器回归一直停留在文档缺口
  - 现有浏览器用例只覆盖管理员黄金路径，无法证明主管只读与审核员/访客重定向行�?
- Resolution:
  - 通过管理员重置账号密码并新增单独 `viewer` 账号，建立稳定的角色测试基线
  - 增加独立 Playwright 角色验证脚本，并结合 API �?200/403 结果收口角色矩阵验证
- Verification:
  - `curl -c /tmp/robot_qc_admin_cookies.txt -H 'Content-Type: application/json' -d '{"username":"admin","password":"Admin123!"}' http://127.0.0.1:18081/api/auth/login`
  - `curl -b /tmp/robot_qc_admin_cookies.txt -H 'Content-Type: application/json' -X POST -d '{"password":"Manager123!"}' http://127.0.0.1:18081/api/accounts/user_manager1/reset-password`
  - `curl -b /tmp/robot_qc_admin_cookies.txt -H 'Content-Type: application/json' -X POST -d '{"password":"Reviewer123!"}' http://127.0.0.1:18081/api/accounts/user_reviewer1/reset-password`
  - `curl -b /tmp/robot_qc_admin_cookies.txt -H 'Content-Type: application/json' -d '{"username":"viewer1","name":"测试访客","password":"Viewer123!","role":"viewer"}' http://127.0.0.1:18081/api/accounts`
  - `"/tmp/robot-qc-playwright-runner/node_modules/.bin/playwright" test "/tmp/robot-qc-playwright-runner/tests/accounts-role-access.spec.js" --config "/tmp/robot-qc-playwright-runner/playwright.config.js" --reporter=line`
  - 浏览器角色验证结果：`4 passed (3.8s)`
  - `curl -b /tmp/robot_qc_manager_cookies.txt http://127.0.0.1:18081/api/accounts` -> `200`
  - `curl -b /tmp/robot_qc_manager_cookies.txt -H 'Content-Type: application/json' -d '{"username":"forbidden_manager_create","name":"禁止创建","password":"Nope123!","role":"reviewer"}' http://127.0.0.1:18081/api/accounts` -> `403`
  - `curl -b /tmp/robot_qc_reviewer_cookies.txt http://127.0.0.1:18081/api/accounts` -> `403`
  - `curl -b /tmp/robot_qc_viewer_cookies.txt http://127.0.0.1:18081/api/accounts` -> `403`
- Unverified items:
  - Docker/production 发布链路里尚未实际执行一�?PostgreSQL `alembic upgrade head` 验收
  - task-pool 多批�?默认首批选中场景的浏览器稳定性仍可继续补�?
- Files changed:
  - `/tmp/robot-qc-playwright-runner/tests/accounts-role-access.spec.js`
  - `.project-log/current-session.md`
  - `.project-log/progress.md`
- Next steps:
  - 在有 Docker/PostgreSQL 权限的验收环境补�?`alembic upgrade head` + 显式管理员初始化，完成正式发布链路闭�?
  - 视时间补�?task-pool 多批次选择的浏览器稳定性回�?

## 2026-06-23 (Robot QC V1 migration baseline landing)

- Type: implementation
- Status: validated in isolated backend runtime and legacy DB adoption path
- Importance: critical
- Reusable: yes
- Objective: �?Robot QC V1 建立正式版本�?schema 基线，替�?`create_all()` 主导的建库方式，并验证新库初始化与旧库纳管两条路�?
- Work completed:
  - �?`software/backend/requirements.txt` 引入 `alembic==1.16.5`，将 schema migration 能力纳入项目内隔�?`.conda-env`
  - 新建 `software/backend/alembic.ini`、`software/backend/migrations/env.py`、`software/backend/migrations/script.py.mako`，补�?Alembic 基础配置与后�?revision 模板
  - 新建基线 revision `software/backend/migrations/versions/20260623_0001_baseline_schema.py`，把 `users`、`task_types`、`batches`、`episodes`、`ingest_jobs`、`qc_review_revisions`、`qc_tasks`、`audit_events` 的当前权�?schema 固化为正式版�?
  - 重写 `software/backend/app/services/bootstrap.py` �?schema 初始化路径：不再�?`Base.metadata.create_all()`，改为根据数据库状态执�?`upgrade head`、旧�?SQLite 兼容补齐 + `stamp head`、或版本�?`upgrade head`
  - 保留 SQLite 旧字�?旧索引补齐逻辑，仅作为历史本地库纳管前的兼容桥接，不再作为新库主建表方�?
  - 更新 `.project-log/current-session.md` �?`software/deploy/README.txt`，把 Alembic 基线、`--ensure-schema-only`、以及发布前执行 migration 的要求写入当前状态与部署说明
- Business logic impact: 系统从“应用内隐式建表”推进到“正�?migration 驱动�?schema 生命周期”；新环境可以按固定 revision 建库，已有历史库也能在不重灌数据的情况下纳入版本管理，为后续 PostgreSQL 生产发布提供可追踪的 schema 演进基线
- Problems encountered:
  - 当前机器运行环境不提�?shell `apply_patch`，迁移文件与 bootstrap 调整需要改用文件工具直接编�?
  - 历史本地 SQLite 库已经带有业务表但没�?`alembic_version`，不能直接按空库方式运行初始 revision
- Resolution:
  - 改用文件工具创建 Alembic 目录�?revision 文件，避免依赖缺失的 shell patch 能力
  - �?`bootstrap.initialize_schema()` 中加入数据库状态判断：已有业务表的旧库先执�?SQLite 兼容补齐，再 `stamp head`，空库与已版本化库统一�?`upgrade head`
- Verification:
  - `env -u PYTHONPATH PYTHONNOUSERSITE=1 bash -lc 'cd software/backend && .conda-env/bin/python -m pip install -r requirements.txt'`
  - `env -u PYTHONPATH PYTHONNOUSERSITE=1 bash -lc 'cd software/backend && .conda-env/bin/python -m compileall app main.py'`
  - `env -u PYTHONPATH PYTHONNOUSERSITE=1 bash -lc 'cd software/backend && DATABASE_URL="sqlite:////tmp/robot_qc_migration_baseline.db" .conda-env/bin/python -m app.services.bootstrap --ensure-schema-only'`
  - `env -u PYTHONPATH PYTHONNOUSERSITE=1 bash -lc 'cd software/backend && .conda-env/bin/python -m app.services.bootstrap --ensure-schema-only'`
  - `env -u PYTHONPATH PYTHONNOUSERSITE=1 bash -lc 'cd software/backend && DATABASE_URL="sqlite:////tmp/robot_qc_migration_baseline.db" .conda-env/bin/python - <<"PY"
from sqlalchemy import create_engine, inspect, text
engine = create_engine("sqlite:////tmp/robot_qc_migration_baseline.db")
inspector = inspect(engine)
print(sorted(inspector.get_table_names()))
with engine.connect() as conn:
    print(conn.execute(text("SELECT version_num FROM alembic_version")).scalar())
PY'`
  - `env -u PYTHONPATH PYTHONNOUSERSITE=1 bash -lc 'cd software/backend && .conda-env/bin/python - <<"PY"
from sqlalchemy import text
from app.core.db import engine
with engine.connect() as conn:
    print(conn.execute(text("SELECT version_num FROM alembic_version")).scalar())
PY'`
- Unverified items:
  - Docker/production 发布链路里尚未实际执行一�?PostgreSQL `alembic upgrade head` 验收
  - 后续新增 schema 变更�?revision 生成与上线节奏虽已有模板，但还未形成固定发布 SOP
  - 账号页的 `qc_manager` / `reviewer` 浏览器态复核仍待有效测试口�?
- Files changed:
  - `software/backend/requirements.txt`
  - `software/backend/alembic.ini`
  - `software/backend/migrations/env.py`
  - `software/backend/migrations/script.py.mako`
  - `software/backend/migrations/versions/20260623_0001_baseline_schema.py`
  - `software/backend/app/services/bootstrap.py`
  - `software/deploy/README.txt`
  - `.project-log/current-session.md`
  - `.project-log/progress.md`
- Next steps:
  - �?Docker/PostgreSQL 验收环境补跑一�?`alembic upgrade head` + 显式管理员初始化，确认生产发布链路与基线 revision 完整一�?
  - 在拿到有效非管理员测试口令后，补一轮账号页浏览器验证，确认管理�?主管/审核员前端权限呈现一�?

## 2026-06-23 (Robot QC V1 qc-history report/export landing)

- Type: implementation
- Status: validated in fresh isolated runtime and browser flow
- Importance: high
- Reusable: yes
- Objective: �?`qc-history` 从在线浏览页补齐为可交付的批次报告与 JSON 导出能力，并完成接口与浏览器级验�?
- Work completed:
  - 复核 `software/backend/app/api/routes/qc.py`，确认历史页新增 `/api/qc-history/report` �?`/api/qc-history/export` 路由，继续沿�?`admin` / `qc_manager` 角色门禁
  - 在新�?backend 运行�?`http://127.0.0.1:18081` 上验�?`report` �?`export` 接口，确�?`batch_id=all` 与指定批次都能返回有�?payload
  - 验证导出 `scope` 语义：`report` 仅返回报告摘要，`episodes` 返回 episode/revision 明细，`audits` 返回 audit 明细，三者互斥行为正�?
  - 将隔�?Playwright runner �?`playwright.config.js` 基地址切到当前 frontend `http://127.0.0.1:4174`
  - 新增专用浏览器用�?`/tmp/robot-qc-playwright-runner/tests/qc-history-report.spec.js`，覆盖登录、历史页导航、批次切换、报告内容展示、三类导出下载与退出登�?
  - 修正用例中批次名断言的宽泛选择器，避免同名文本在多个区域重复渲染时触发 strict-mode 歧义
  - 更新 `.project-log/current-session.md` 与本日志，移除“qc-history 导出/批次报告能力未实现”的过期结论
- Business logic impact: `qc-history` 已从“只能在线查看”提升到“可按批次生成报告并按范围导�?JSON 交付物”，管理员和质检主管可直接从历史页获取正式汇总与明细数据
- Problems encountered:
  - 机器上原先占�?`127.0.0.1:8001` �?backend 进程是旧构建，登录和基础历史接口可用，但缺少新加�?`/api/qc-history/report` �?`/api/qc-history/export`
  - 首轮 Playwright 用例�?`getByText('2026-06-21 下午入库')` 上命�?9 个节点，属于测试选择器过宽而非产品故障
- Resolution:
  - 不销毁已有旧进程，改为在 `127.0.0.1:18081` 启动更新后的 backend，并�?frontend 通过 `VITE_PROXY_API_TARGET` 指向该新运行�?
  - 将批次选择后的断言收敛到表格单元格级别，消�?strict-mode 歧义后重新通过浏览器验�?
- Verification:
  - `curl -c /tmp/robot_qc_cookies.txt -H 'Content-Type: application/json' -d '{"username":"admin","password":"Admin123!"}' http://127.0.0.1:18081/api/auth/login`
  - `curl -b /tmp/robot_qc_cookies.txt 'http://127.0.0.1:18081/api/qc-history/report?batch_id=all'`
  - `curl -b /tmp/robot_qc_cookies.txt 'http://127.0.0.1:18081/api/qc-history/report?batch_id=batch_20260621_002'`
  - `curl -b /tmp/robot_qc_cookies.txt 'http://127.0.0.1:18081/api/qc-history/export?batch_id=all&scope=report'`
  - `curl -b /tmp/robot_qc_cookies.txt 'http://127.0.0.1:18081/api/qc-history/export?batch_id=all&scope=episodes'`
  - `curl -b /tmp/robot_qc_cookies.txt 'http://127.0.0.1:18081/api/qc-history/export?batch_id=all&scope=audits'`
  - `"/tmp/robot-qc-playwright-runner/node_modules/.bin/playwright" test "/tmp/robot-qc-playwright-runner/tests/qc-history-report.spec.js" --config "/tmp/robot-qc-playwright-runner/playwright.config.js" --reporter=line`
  - 浏览器专�?qc-history 用例结果：`1 passed (2.5s)`
- Unverified items:
  - 账号页的 `qc_manager` / `reviewer` 浏览器态复核仍待有效测试口�?
- Files changed:
  - `/tmp/robot-qc-playwright-runner/playwright.config.js`
  - `/tmp/robot-qc-playwright-runner/tests/qc-history-report.spec.js`
  - `.project-log/current-session.md`
  - `.project-log/progress.md`
- Next steps:
  - 引入正式 migration 流程，替代当�?`bootstrap.initialize_schema()` 的过渡式 schema 修补
  - 在拿到有效非管理员测试口令后，补一轮账号页浏览器验证，确认管理�?主管/审核员前端权限呈现一�?

## 2026-06-23 (Robot QC V1 runtime alignment and browser revalidation)

- Type: validation
- Status: validated with remaining doc-level production gaps tracked
- Importance: critical
- Reusable: yes
- Objective: 修复前端 dev/runtime 与当�?backend 的对齐问题，重新跑通浏览器黄金链路，并把账号生命周期与剩余生产缺口记录到项目日�?
- Work completed:
  - 更新 `software/frontend/vite.config.ts`，引�?`VITE_PROXY_API_TARGET`，保持浏览器侧使用同�?`/api`，由 Vite 代理转发到当�?backend
  - 更新 `software/frontend/src/api/client.ts`，仅在请求实际携�?JSON body 时设�?`Content-Type: application/json`，避�?`/auth/session` �?GET 触发不必要的跨域预检
  - 重启对齐后的 frontend dev runtime，并确认此前 `OPTIONS /api/auth/session` 导致�?bootstrap 失败已消�?
  - 修正隔离 Playwright 脚本 `/tmp/robot-qc-playwright-runner/tests/robot-qc-golden-path.spec.js`：兼�?`认领任务/重新认领` 两种按钮文案，并改为点击可见 `Fail` 文本驱动 Element Plus 单�?
  - �?rerun 前释�?`episode_000124` 上的�?review lock，确�?browser flow 可重复执�?
  - 成功重跑 `login �?dashboard �?task-pool �?manual-qc �?qc-history �?logout`，结�?`1 passed (3.2s)`
  - 复核账号生命周期现状：管理员创建/重置密码/启停、self-deactivation 保护、停用后登录拒绝、reviewer 访问 `/api/accounts` 返回 403 的后端验证已完成
  - 更新 `.project-log/current-session.md` �?`.project-log/progress.md`，移除“review lock 未实现”“账号生命周期未实现”等失真记录
- Business logic impact: 当前 V1 已从“前端与后端能单点联通”推进到“浏览器黄金链路在当前真�?backend 上可稳定重跑”；账号生命周期、review lock 与会话引导逻辑都已进入已落地状�?
- Problems encountered:
  - �?`VITE_API_BASE_URL` 设为绝对地址 `http://127.0.0.1:8000/api` 时，浏览器会�?`/api/auth/session` 发起跨域预检，backend 返回 `400`，导致路�?bootstrap 直接失败
  - manual QC 页面在锁已归当前用户所有时按钮文案�?`重新认领`，旧 Playwright 仅等�?`认领任务` 会超�?
  - Element Plus 单选组件对隐藏 input �?`.check()` 不稳定，`Fail` 结果选择会卡死在脚本�?
  - 当前运行时未拿到可用�?`reviewer` / `qc_manager` 测试口令，账号页的非管理员浏览器回归无法在本轮完�?
- Resolution:
  - 恢复 dev 浏览器同源访问模式，�?backend 切换责任下沉�?`VITE_PROXY_API_TARGET`
  - 收敛请求头注入逻辑，避免无 body GET 请求携带多余 JSON �?
  - 放宽锁按钮定位条件并改用可见文本点击 `Fail`，提�?Element Plus 场景下的浏览器脚本稳定�?
  - 将账号页浏览器验证缺口明确记录为剩余验证项，而不是继续保留“能力未落地”的错误结论
- Verification:
  - `cd software/frontend && npm run build`
  - `cd /tmp/robot-qc-playwright-runner && npx playwright test --reporter=line`
  - 浏览器黄金链路结果：`1 passed (3.2s)`
- Unverified items:
  - 账号页的 `qc_manager` / `reviewer` 浏览器态复核仍待有效测试口�?
- Files changed:
  - `software/frontend/vite.config.ts`
  - `software/frontend/src/api/client.ts`
  - `/tmp/robot-qc-playwright-runner/tests/robot-qc-golden-path.spec.js`
  - `.project-log/current-session.md`
  - `.project-log/progress.md`
- Next steps:
  - 继续�?`qc-history` 导出/批次报告，收口历史页剩余占位缺口
  - 引入正式 migration 流程，替代当�?`bootstrap.initialize_schema()` 的过渡式 schema 修补
  - 在拿到有效非管理员测试口令后，补一轮账号页浏览器验证，确认管理�?主管/审核员前端权限呈现一�?

## 2026-06-22 (Robot QC V1 production hardening phase 2 ingestion validation)

- Type: implementation
- Status: phase 2 landed and locally validated
- Importance: critical
- Reusable: yes
- Objective: 打通真实扫描入库链路，修复旧本地数据库与当前模型的 schema 漂移，完�?ingestion 的本地闭环验�?
- Work completed:
  - �?`software/backend/app/services/ingestion.py` 落地真实扫描入库能力：扫描允许目录、识�?processed episode、按 source fingerprint 做幂等跳过、写�?`ingest_jobs` / `batches` / `episodes` / `audit_events`
  - �?`software/backend/app/api/routes/qc.py` 新增 `/api/database/scan` 并返回真�?ingest job 结果，同时为派发计划与人工质检提交补齐角色限制
  - 更新前端 `software/frontend/src/types/qc.ts`、`src/api/client.ts`、`src/pages/database-view.vue`，接入真实扫描表单、入库任务列表与后端错误 `detail` 展示
  - 清理剩余前端占位语义：`dashboard.vue`、`AppLayout.vue`、`task-pool.vue`、`manual-qc.vue`、`qc-history.vue` 改为仅展示当前已落地能力
  - 扩展 `software/backend/app/services/bootstrap.py`，增�?SQLite 旧库补字�?补索引逻辑，并提供 `--ensure-schema-only` 入口用于仅修复本�?schema 基线
  - 对当前本�?SQLite 运行 `python -m app.services.bootstrap --ensure-schema-only`，补�?`users.is_active`、`users.password_changed_at`、`episodes.source_*`/`ingest_status`/candidate flags 以及 `ingest_jobs` �?
  - 使用真实样例目录 `/home/tbl/Project/data_collect/data/raw/process` 执行扫描 smoke test，成功生�?`indexed` 状态入库任务并导入 1 �?episode
- Business logic impact: V1.0 从“前端有扫描入口但未完成运行时验证”推进到“真实本地数据可被后端扫描入库并在数据库中持久化”；旧开�?SQLite 库也具备继续联调当前功能的最低兼容基�?
- Problems encountered:
  - 当前机器上的历史 SQLite 库缺�?`users.is_active` 字段�?`ingest_jobs` 表，导致任何真实扫描验证都会�?ORM 查询阶段失败
  - 运行环境不提�?`apply_patch`，需要继续使用文件编辑工具修改代�?
- Resolution:
  - 将旧库兼容补丁集中收敛到 `bootstrap.initialize_schema()` 后置步骤，仅�?SQLite 执行最小补字段/补索引逻辑
  - 增加 `--ensure-schema-only` 模式，使本地修复 schema 不再要求重复创建管理员账�?
  - 重新在隔�?`.conda-env` 中执�?schema 修复�?ingestion smoke test，确认真实扫描链路已经可跑�?
- Verification:
  - `env -u PYTHONPATH PYTHONNOUSERSITE=1 bash -lc 'cd software/backend && .conda-env/bin/python -m compileall app main.py'`
  - `env -u PYTHONPATH PYTHONNOUSERSITE=1 bash -lc 'cd software/backend && .conda-env/bin/python -m app.services.bootstrap --ensure-schema-only'`
  - `env -u PYTHONPATH PYTHONNOUSERSITE=1 bash -lc 'cd software/backend && .conda-env/bin/python -c "from app.core.db import SessionLocal; from app.models import User, IngestJob; db = SessionLocal(); user = db.query(User).first(); print(user.username if user else None, user.is_active if user else None); print(db.query(IngestJob).count()); db.close()"'`
  - `env -u PYTHONPATH PYTHONNOUSERSITE=1 bash -lc 'cd software/backend && .conda-env/bin/python -c "from app.core.db import SessionLocal; from app.models import User; from app.services.ingestion import run_ingest_scan; db = SessionLocal(); user = db.query(User).filter(User.username == \"admin\").first() or db.query(User).first(); job = run_ingest_scan(db, source_path=\"/home/tbl/Project/data_collect/data/raw/process\", batch_name=\"\", operator=user); print(job.id, job.status, job.detail, job.episodes, job.imported_episodes, job.skipped_episodes); db.close()"'`
  - `cd software/frontend && npm run build`
- Unverified items:
  - 尚未在浏览器端重新完整复跑“扫描入�?�?派发 �?manual QC �?history”最新链�?
  - PostgreSQL 生产基线仍未具备正式 migration 脚本，当�?schema 修复只覆盖本�?SQLite 兼容
  - review lock / claim / release / version 冲突保护仍未实现
- Files changed:
  - `software/backend/app/services/ingestion.py`
  - `software/backend/app/api/routes/qc.py`
  - `software/backend/app/services/bootstrap.py`
  - `software/frontend/src/types/qc.ts`
  - `software/frontend/src/api/client.ts`
  - `software/frontend/src/pages/database-view.vue`
  - `software/frontend/src/pages/dashboard.vue`
  - `software/frontend/src/components/AppLayout.vue`
  - `software/frontend/src/pages/task-pool.vue`
  - `software/frontend/src/pages/manual-qc.vue`
  - `software/frontend/src/pages/qc-history.vue`
  - `software/frontend/src/api/mock.ts`
  - `.project-log/current-session.md`
  - `.project-log/progress.md`
- Next steps:
  - 实现 review lock / claim / release / lock expiry / version 控制，补齐多人并发审核保�?
  - 在浏览器端复跑最新业务闭环，并确认扫描入库后的批次可以直接进入派发和人工质检

## 2026-06-22 (Robot QC V1 production hardening phase 0/1 baseline)

- Type: implementation
- Status: phase 0 recorded, phase 1 baseline landed
- Importance: critical
- Reusable: yes
- Objective: 按“公司内网可直接投入使用”标准，先记录生产就绪性缺口，并移除默�?demo 启动路径，建立显式初始化和安全部署基�?
- Work completed:
  - �?`.project-log/current-session.md` �?`.project-log/progress.md` 记录生产就绪性审计结论，明确 P0/P1 缺口：demo 启动链路、默认口令、SQLite 部署、无真实入库、无 RBAC/lock/并发保护、前端占位入口未收口
  - 重写 `software/backend/app/main.py`，移�?`Base.metadata.create_all()` �?`seed_demo_data()` 的默�?startup 行为
  - 扩展 `software/backend/app/core/config.py`，补�?`FRONTEND_ORIGIN`、`EXTRA_FRONTEND_ORIGINS`、`SESSION_COOKIE_SECURE`、production 判定与统一 CORS origins 计算
  - �?`software/backend/app/main.py` 增加 production 守卫：生产环境若仍使用默�?`SECRET_KEY` �?SQLite，则启动直接失败
  - 调整 `software/backend/app/api/routes/qc.py` �?cookie 配置，改为读�?`SESSION_COOKIE_SECURE`
  - 重写 `software/backend/app/services/bootstrap.py` 为显式初始化脚本，提�?`python -m app.services.bootstrap --admin-username ... --admin-password ...` 建库并创建首个管理员的入�?
  - 更新 `software/frontend/src/pages/login.vue`，移除默认管理员账号/初始密码展示与预填值，避免继续传�?demo 口令
  - 更新 `software/deploy/docker-compose.yml` �?`software/deploy/README.txt`，将部署基线切到 PostgreSQL + 显式初始化流�?
- Business logic impact: 系统从“服务一启动就自动建表并灌演示数据”切换到“空库保持空、必须显式初始化管理员、生产环境拒绝默认密钥和 SQLite”，这是从演示态迈向可控生产基线的第一�?
- Problems encountered:
  - 当前工程尚未引入正式 migration 框架，Phase 1 只能先用显式初始化脚本承接建库动�?
  - 现有前端和历史验证都默认依赖 `admin/Admin@123` 演示账号，需要同步清理文案和后续验证口径
- Resolution:
  - 先把隐式 startup 行为整体拆除，避免继续扩�?demo 假设
  - �?`create_all()` 收敛到手工初始化入口，作�?migration 上线前的过渡控制�?
  - 先在 UI 和部署文档中移除默认口令，再在下一阶段补正�?migration 与真实入�?
- Verification:
  - 待执行：`env -u PYTHONPATH PYTHONNOUSERSITE=1 bash -lc 'cd software/backend && .conda-env/bin/python -m compileall app main.py'`
  - 待执行：显式初始化命�?`python -m app.services.bootstrap --admin-username ... --admin-password ...`
  - 待执行：以空库启�?backend，确认不会自动建�?灌数；production + 默认密钥/SQLite 组合应直接拒绝启�?
  - 待执行：前端重新 build，确认登录页不再展示默认口令
- Unverified items:
  - 显式初始化后�?login/session/browser golden path 还未按新基线重跑
  - PostgreSQL compose 运行时还未实际验�?
  - migration 框架与真�?batch/episode 入库 API 尚未落地
- Files changed:
  - `software/backend/app/main.py`
  - `software/backend/app/core/config.py`
  - `software/backend/app/api/routes/qc.py`
  - `software/backend/app/services/bootstrap.py`
  - `software/frontend/src/pages/login.vue`
  - `software/deploy/docker-compose.yml`
  - `software/deploy/README.txt`
  - `.project-log/current-session.md`
  - `.project-log/progress.md`
- Next steps:
  - 先在隔离 `.conda-env` 下验证显式初始化、空库启动和 production 守卫行为
  - 然后进入 Phase 2，落真实扫描入库 API �?ingest job 状态链�?

## 2026-06-22 (Robot QC V1 real manual QC sample integration)

- Type: implementation
- Status: validated in isolated runtime and browser flow
- Importance: high
- Reusable: yes
- Objective: 用本地真实样�?`episode_000099` 替换 manual QC 页面里的静态占�?metrics / timeline，并让前端入口直接走到这条样例数�?
- Work completed:
  - �?`software/backend/app/core/config.py` 增加 `COLLECTION_DATA_ROOT` �?`SAMPLE_PROCESSED_ROOT` 配置，支持优先读取仓库内 `data/raw/process/episode_000099`
  - �?`software/backend/app/services/payloads.py` 增加 processed episode 发现与解析逻辑，读�?`manifest.json`、`metadata.json`、`telemetry.npz`
  - 基于真实 telemetry 派生 `Q_motion`、平滑度、同步异常率、跟踪误差、速度 p95、力�?p95 六张指标�?
  - 基于同步异常、跟踪误差和高动态区间生�?timeline 片段，并补上相邻片段合并与最小时长裁剪，避免 UI 上出现过�?chips
  - 修正分数型指标的等级映射逻辑，避免低分被错误标记�?`good`
  - �?`software/backend/app/services/bootstrap.py` 中加�?`episode_000099` �?`task_005`，让 dashboard / task-pool / manual-qc 能从现有入口直接访问真实样例
  - 更新 `software/backend/requirements.txt`，在隔离 backend env 中补�?`numpy`
  - 重新构建前端静态资源，确保 demo 入口和页面加载的是最新数据链�?
- Business logic impact: manual QC 工作台从“后端静态占位演示”推进到“基于本地真实样例的可操�?V1”；老板演示时可以直接打开现有任务看到真实 telemetry 派生结果
- Problems encountered:
  - 初版 score level 逻辑反了，导�?`Q_motion=1.8` 被错误标�?`good`
  - 初版 timeline 片段过碎，秒�?chips 可读性差
  - `FastAPI TestClient` 依赖�?`httpx` 不在隔离环境�?
- Resolution:
  - 调整 `_metric_level(..., reverse=True)` 判定方向
  - �?timeline 增加�?label 的相邻片段合并与最小时长约�?
  - 改用隔离 uvicorn + `curl` + Playwright 做端到端验证，未额外污染 ROS/system Python
- Verification:
  - `env -u PYTHONPATH PYTHONNOUSERSITE=1 bash -lc 'cd software/backend && .conda-env/bin/python -m compileall app main.py'`
  - `cd software/frontend && npm run build`
  - `curl -c /tmp/robot_qc_cookies.txt -H 'Content-Type: application/json' -d '{"username":"admin","password":"Admin@123"}' http://127.0.0.1:18080/api/auth/login`
  - `curl -b /tmp/robot_qc_cookies.txt http://127.0.0.1:18080/api/bootstrap`
  - `curl -b /tmp/robot_qc_cookies.txt http://127.0.0.1:18080/api/episodes/episode_000099/qc-context`
  - `cd /tmp/robot-qc-playwright-runner && npx playwright test --reporter=line`
- Unverified items:
  - 若后续接入更多真�?episode，仍需验证批量样例下的 timeline 阈值是否需要按任务类型细分
- Files changed:
  - `software/backend/app/core/config.py`
  - `software/backend/app/services/payloads.py`
  - `software/backend/app/services/bootstrap.py`
  - `software/backend/requirements.txt`
  - `software/frontend/dist/*`
  - `.project-log/current-session.md`
  - `.project-log/progress.md`
- Next steps:
  - 继续�?demo seed / 本地样例模式扩展成真实批次扫描入库流�?
  - 视下一阶段优先级决定是否补更细粒度帧级质检视图或自动规则建�?

## 2026-06-22 (Robot QC V1 containerized deployment validation)

- Type: validation
- Status: validated in Docker runtime
- Importance: high
- Reusable: yes
- Objective: 在本�?Docker 权限环境中完�?Robot QC V1 compose 实机验收，确认交付版部署链路可用
- Work completed:
  - 解决 Docker Hub 拉取受限问题，完�?Docker 登录后成功拉�?`python:3.10-slim` �?`nginx:1.29-alpine`
  - �?`software/frontend/Dockerfile` 调整为直接打包宿主预构建 `dist` �?nginx 镜像，避开容器�?npm 安装超时
  - 更新 `software/frontend/.dockerignore`，确�?`dist` 会进�?Docker build context
  - 成功执行 `docker compose -f /home/tbl/Project/data_collect/software/deploy/docker-compose.yml up --build -d`
  - 验证 `http://127.0.0.1:8080` 返回 200，`/api/health` 通过 nginx 反向代理返回 `{"status":"ok"}`
  - 验证 `/api/auth/login`、`/api/auth/session`、`/api/task-pool` 通过前端入口联�?backend
  - 验证 frontend 容器内访�?`http://127.0.0.1/api/health` 可成功反代到 backend
  - 完成容器日志检查并在验收后执行 `docker compose ... down` 清理
- Business logic impact: V1.0 从“具备部署包装”推进到“已在本机完成容器级实机验收”；交付链路已覆�?compose、nginx 反代、鉴权与核心业务入口
- Problems encountered:
  - Docker Hub 匿名拉取命中限制，基础镜像无法拉取
  - 前端 lockfile �?`npm ci` 不一致，且容器内访问 npm registry 超时
  - `dist` 一度被 `.dockerignore` 排除，导�?nginx 镜像无法复制静态产�?
- Resolution:
  - 使用用户已完成的 Docker 登录恢复镜像拉取
  - 改为宿主机先执行 `npm run build --prefix software/frontend`，容器仅打包静态产�?
  - 移除 `.dockerignore` 中对 `dist` 的排�?
- Verification:
  - `npm run build --prefix /home/tbl/Project/data_collect/software/frontend`
  - `docker compose -f /home/tbl/Project/data_collect/software/deploy/docker-compose.yml up --build -d`
  - `curl -I http://127.0.0.1:8080`
  - `curl http://127.0.0.1:8080/api/health`
  - `curl -X POST http://127.0.0.1:8080/api/auth/login ...`
  - `curl http://127.0.0.1:8080/api/auth/session`
  - `curl http://127.0.0.1:8080/api/task-pool`
  - `docker exec robot-qc-frontend sh -c 'wget -qO- http://127.0.0.1/api/health'`
  - `docker compose -f /home/tbl/Project/data_collect/software/deploy/docker-compose.yml down`
- Unverified items:
  - 容器化入口下的浏览器 golden path 复跑结果
  - manual QC metrics / timeline 的真实后端数�?
- Files changed:
  - `software/frontend/Dockerfile`
  - `software/frontend/.dockerignore`
  - `software/deploy/README.txt`
  - `.project-log/current-session.md`
  - `.project-log/progress.md`
- Next steps:
  - �?`http://127.0.0.1:8080` 上复跑浏览器 golden path，补齐最终交付验�?
  - 视交付优先级决定是否继续实现 manual QC metrics / timeline 的真实数�?

## 2026-06-22 (Robot QC V1 browser golden-path validation)

- Type: validation
- Status: validated in isolated browser runtime
- Importance: high
- Reusable: yes
- Objective: 在不污染 ROS/system Python 的前提下跑通浏览器端完整业务闭环，确认真实鉴权与手�?QC 页面交互可用
- Work completed:
  - �?`/tmp/robot-qc-playwright-runner` 创建隔离 Playwright runner，并本地安装 `playwright` �?`@playwright/test`
  - 基于实际前端页面文案和可访问性结构修正登录、任务跳转、Fail 结果和主原因码选择�?
  - 跑�?`login �?dashboard �?task-pool �?manual-qc �?qc-history �?logout` 浏览器链�?
  - 验证未登录访�?`/dashboard` 会被路由守卫重定向到 `/login`
  - 验证手动 QC 提交后历史审计页能看�?`browser e2e validation`、`王主管`、`sync_bad`
  - 验证退出登录后再次访问受保护页面会重新跳转到登录页
- Business logic impact: V1.0 从“API 与页面单点可用”推进到“真实账号、会话、派发、人�?QC、审计、登出闭环已完成浏览器级验收�?
- Problems encountered:
  - 初版脚本使用了过时文�?`进入质检平台`，实际按钮文案为 `进入系统`
  - manual QC 页面 `Fail` 结果与主原因码是 Element Plus 组件，不能用朴素文本点击方式稳定驱动
- Resolution:
  - 改为基于 label / role / 组件容器的稳定选择�?
  - 使用独立临时 npm 工作区运�?Playwright，未修改项目依赖与宿�?Python 环境
- Verification:
  - `cd /tmp/robot-qc-playwright-runner && npx playwright test --reporter=line`
- Unverified items:
  - �?Docker 权限环境下的 `docker compose up --build -d` 容器实机验收
- Files changed:
  - `.project-log/current-session.md`
  - `.project-log/progress.md`
  - `/tmp/robot-qc-playwright-runner/playwright.config.js`
  - `/tmp/robot-qc-playwright-runner/tests/robot-qc-golden-path.spec.js`
- Next steps:
  - 在有 Docker 权限的环境执�?compose 启动并验收前后端联�?
  - 视交付节奏决定是否补 manual QC metrics / timeline 的真实后端数�?

# Progress Log

## 2026-06-22 (Robot QC V1 real auth integration)

- Type: implementation
- Status: validated in isolated runtime
- Importance: high
- Reusable: yes
- Objective: 用真实账号鉴权替�?demo bootstrap，并在不污染 ROS/system Python 的前提下完成登录态联�?
- Work completed:
  - 新增 `software/backend/app/core/security.py`，实�?PBKDF2-SHA256 密码哈希�?HMAC session token
  - 扩展 `software/backend/app/core/config.py`，补�?`SECRET_KEY`、cookie 名称�?session 生命周期配置
  - 更新 `software/backend/app/services/bootstrap.py`，为默认管理员写入真实密码哈希，并兼容旧 demo hash 升级
  - �?`software/backend/app/api/routes/qc.py` 增加 `/api/auth/login`、`/api/auth/logout`、`/api/auth/session`
  - �?`/api/bootstrap`、`/api/dashboard`、`/api/task-pool`、`/api/qc-history`、`/api/qc/manual/*` 等业务接口补充鉴权保�?
  - 更新 `software/backend/app/services/payloads.py`，改为基于当前登录用户返�?payload
  - 更新前端 `software/frontend/src/api/client.ts`、`src/stores/session.ts`、`src/router/index.ts`、`src/pages/login.vue`、`src/components/AppLayout.vue`，接�?cookie session、登录页、登出和路由守卫
  - 更新 `software/frontend/src/pages/manual-qc.vue`，移除前端伪�?operator，改由后端使用当前登录人落审�?
- Business logic impact: V1.0 从“demo 登录可演示”推进到“真实账�?+ 会话�?+ 审计身份可信”；人工质检提交人不再由前端伪�?
- Problems encountered:
  - 8001 端口已有�?backend 占用，初次联调命中了不含 auth 路由的旧实例
  - `apply_patch` 在当前环境不可用
- Resolution:
  - 改用 8002 端口启动�?backend 实例完成验证
  - 使用文件编辑工具替代 `apply_patch`
- Verification:
  - `env -u PYTHONPATH PYTHONNOUSERSITE=1 bash -lc 'cd software/backend && .conda-env/bin/python -m compileall app main.py'`
  - `cd software/frontend && npm run build`
  - `curl -X POST http://127.0.0.1:8002/api/auth/login ...`
  - `curl http://127.0.0.1:8002/api/auth/session`
  - `curl http://127.0.0.1:8002/api/bootstrap`
  - `curl -X POST http://127.0.0.1:8002/api/qc/manual/episode_000124 ...`
  - `curl -X POST http://127.0.0.1:8002/api/auth/logout ...`
  - logout 后再次请�?`/api/auth/session` 返回 `401`
- Unverified items:
  - 浏览器端完整 golden path 验证
  - �?Docker 权限环境下的 compose 实机验收
- Files changed:
  - `software/backend/app/core/security.py`
  - `software/backend/app/core/config.py`
  - `software/backend/app/services/bootstrap.py`
  - `software/backend/app/services/payloads.py`
  - `software/backend/app/schemas/qc.py`
  - `software/backend/app/api/routes/qc.py`
  - `software/frontend/src/api/client.ts`
  - `software/frontend/src/stores/session.ts`
  - `software/frontend/src/router/index.ts`
  - `software/frontend/src/pages/login.vue`
  - `software/frontend/src/components/AppLayout.vue`
  - `software/frontend/src/pages/manual-qc.vue`
  - `software/frontend/src/main.ts`
  - `.project-log/current-session.md`
  - `.project-log/progress.md`
- Next steps:
  - 启动前端并在浏览器走�?login �?dashboard �?task-pool �?manual-qc �?qc-history �?logout
  - 在有 Docker 权限的环境执�?`docker compose up --build -d` 并验收前后端联�?

## 2026-06-22 (Robot QC V1 internal deployment packaging)

- Type: implementation
- Status: partially validated
- Importance: high
- Reusable: yes
- Objective: �?Robot QC V1.0 增加可直接用于公司内网演示和交付的部署包装，并完成联调级校验
- Work completed:
  - 新增 `software/frontend/Dockerfile`，构�?Vue 产物并用 nginx 提供静态站�?
  - 新增 `software/frontend/nginx.conf`，前端同源代�?`/api` �?backend
  - 新增 `software/frontend/.dockerignore`
  - 新增 `software/deploy/docker-compose.yml`，编�?frontend + backend，后端持久化 SQLite 数据卷并挂载 `/data/collection_data`
  - 新增 `software/deploy/README.txt`，补充内网启�?停止/访问说明
  - 修正前端站点标题�?`Robot QC Platform`
  - 修正侧边栏重复入口，合并为“人工质检与派发�?
  - 前端生产构建通过；backend `python3 -m compileall` 通过；`docker compose config` 通过
  - 使用项目�?`software/backend/.conda-env` 建立隔离 Python 运行环境，未修改 ROS/system Python
  - 在隔离环境下启动 backend 并通过 `/api/health`、`/api/bootstrap`、`/api/task-pool` smoke test
- Business logic impact: V1.0 从“页面与 API 可编译”推进到“具备内网部署包�?+ 可在�?Docker 权限主机上做后端运行验收”；离老板演示版还差浏览器端完整验收与鉴权补齐
- Problems encountered:
  - 环境�?`apply_patch` 不可用，改用文件编辑工具完成修改
  - 本机无法访问 Docker daemon，`docker compose up --build` 无法执行
  - 宿主 ROS 环境设置�?`PYTHONPATH`，会污染隔离 Python 的依赖解�?
- Resolution:
  - 部署文件已补齐并通过 compose 配置级校�?
  - 构建与语法层校验已完�?
  - 通过 `conda create -p software/backend/.conda-env ...` 提供项目内隔离运行方�?
  - 运行时使�?`env -u PYTHONPATH PYTHONNOUSERSITE=1`，避�?ROS 路径�?user-site 包泄漏到 backend
- Verification:
  - `cd software/frontend && npm run build`
  - `python3 -m compileall software/backend`
  - `docker compose -f software/deploy/docker-compose.yml config`
  - `env -u PYTHONPATH PYTHONNOUSERSITE=1 bash -lc 'cd software/backend && .conda-env/bin/python -m uvicorn main:app --host 127.0.0.1 --port 8001'`
  - `curl http://127.0.0.1:8001/api/health`
  - `curl http://127.0.0.1:8001/api/bootstrap`
  - `curl http://127.0.0.1:8001/api/task-pool`
- Unverified items:
  - `docker compose up --build -d` 容器实际启动结果
  - 浏览器端完整 golden path 验证
  - 真实账号登录流程
- Files changed:
  - `software/frontend/src/components/AppLayout.vue`
  - `software/frontend/index.html`
  - `software/frontend/Dockerfile`
  - `software/frontend/nginx.conf`
  - `software/frontend/.dockerignore`
  - `software/deploy/docker-compose.yml`
  - `software/deploy/README.txt`
  - `.project-log/current-session.md`
  - `.project-log/progress.md`
- Next steps:
  - 在有 Docker 权限的环境执�?compose 启动并验�?`/api/health`
  - 用浏览器走�?login �?dashboard �?task-pool �?manual-qc �?qc-history
  - 继续补真实账号认证和密码校验

## 2026-06-16 (报告 01 扩展完成 �?19 数据�?生态覆�?

- Type: workflow
- Status: validated
- Importance: high
- Reusable: yes
- Objective: 补全报告 01 的空缺，覆盖 ALOHA、Dobb-E、灵巧手遥操作前沿数据集、RLBench �?
- Work completed:
  - 新增 §3.16 ALOHA / Mobile ALOHA：硬件隐�?QC、频率诊�?自动拒绝、同构主从映射、ALOHA Unleashed 质量vs多样�?trade-off
  - 新增 §3.17 Dobb-E：论文专�?QC 小节、人工视频审核、非专家操作者挑战、隐私过�?
  - 新增 §3.18 灵巧手遥操作前沿：ActionNet (LeRobot V2)、BiDex (MANUS 手套精度 ~20ms)、DexMimicGen (仿真成功率检�?
  - 新增 §3.19 RLBench：可组合成功谓词 (GraspCondition+DetectedCondition+ProximitySensor)、任务验证工�?
  - 更新 §3.20 跨数据集对比表：�?9 列扩展到 14 列，新增 ALOHA/Dobb-E/ALOHA/DobbE/LIBERO/FurnBench/UMI/BEHAVIOR/ActionNet/RLBench
  - 更新 §4 综合对照表：�?11 扩展�?18 数据�?
  - 更新 §5 可迁移规则：�?18 条扩展到 27 条（§5.3 新增 17-19，�?.4 新增 20-23，�?.5 新增 24-27 灵巧手专项建议）
  - 更新 §6 参考资料：新增 ALOHA/MobileALOHA/ALOHAUnleashed/Dobb-E/ActionNet/BiDex/DexMimicGen/RLBench
- Business logic impact: 报告 01 �?10+ 数据�?扩展�?19 数据�?生态；灵巧�?QC 空白已明确标�?
- Key findings:
  - 19 个公开数据集中�?3 个有真正的显�?QC 系统（BEHAVIOR-1K/LeRobot/RoboMimic�?
  - 灵巧�?QC 是完整研究空�?�?所有现有数据集 QC 均针对夹爪场�?
  - ALOHA 硬件隐式约束哲学�?TeleDex 有最高参考价�?
  - DexMimicGen �?仿真检查→过滤"范式可借鉴但需适配真实遥操�?
- Problems encountered: None
- Resolution: Not applicable
- Verification: 所有新增数据集信息与原论文交叉核对一�?
- Unverified items: BiDex MANUS 手套延迟实测数据；ActionNet 完整 QC 流程细节
- Files changed:
  - `doc/reports/01_public_dataset_implicit_qc.md`
  - `.project-log/progress.md`
- Next steps:
  - L3 灵巧手专项适配（per-finger chatter, 0~255 归一化）
  - 报告 03 数据策展框架调研
  - 可迁移规则落地为 TeleDex 实现规格

## 2026-06-16 (L3 遥操作质量深入调研完�?

- Type: workflow
- Status: validated
- Importance: high
- Reusable: yes
- Objective: 深入调研 L3 遥操作数据质�?�?Consistency Matters + Forge + RINSE + Python 工具生�?+ 轨迹异常检�?
- Work completed:
  - 下载并精�?Consistency Matters (arXiv:2412.14309) 全文，提�?10 项公式表�? 类维度：smoothness, path efficiency, joint limit avoidance, manipulability, effort, consistency�?
  - 确认关键结论：一致性指标预�?70-89% 任务成功�?
  - 深入调研 Forge (Tigunait, 2024)�? 项主要指�?+ 3 项扩展指标，全部公式与权重，MIT 许可，pip installable
  - 确认 Forge �?`analyze_episode_arrays()` 可直接接�?TeleDex telemetry.npz �?numpy 数组
  - 调研 monalysa (SPARC+LDLJ)、trajectopy (ATE/RPE)、PyEyesWeb、democlean (KSG MI)、DemInf (VAE+MI) �?Python 工具
  - 调研 RINSE (arXiv:2604.23000)：SAL (谱弧�? + TED (轨迹包络距离)，SAL 过滤 +16% 成功�?
  - 调研轨迹异常检测：通用方法 (GeoInformatica 2025, 10 库对�? + 机器人前�?(RC-NF/VLAConf/世界模型)
  - 发现遥操作异常检测是研究空白 �?建议从统�?启发式方法起�?
  - 更新报告 02：�?.2 (score_lerobot)、�?.3 (Consistency Matters)、�?.5 (PSD/RINSE)、�?.6 (Forge)、�?.7 (Python 工具生�?、�?.8 (异常检�?
  - 更新 §2.1 调研状态表、报告状态行
- Business logic impact: B2 节点 L3 子任务全部完成；L3 遥操作质量从 DQAF �?4 指标扩展�?11+ 指标体系；Forge 确认为主落地工具
- Problems encountered:
  - Consistency Matters agent �?DeepSeek 不支�?image_url 报错 �?改用 curl + pdftotext 直接下载提取 PDF 文本
  - �?agent 输出文件 (3.2MB, 259KB) 无法 Read �?�?python3 json 解析脚本提取最终文�?
- Resolution: 全部通过替代方法解决
- Verification: 10 �?Consistency Matters 公式�?PDF 原文交叉核对一致；Forge 8 指标�?GitHub 源码一�?
- Unverified items: monalysa/democlean/DemInf 实际运行效果；灵巧手 per-finger 改造代码未编写；异常检测前沿方�?(RC-NF) 代码未发�?
- Files changed:
  - `doc/reports/02_data_quality_assessment_frameworks.md`
  - `.project-log/progress.md`
- Next steps:
  - L2 VLM prompt 设计（视觉质量检�?prompt 模板�?
  - L3 灵巧手专项适配（per-finger chatter, 0~255 空间归一化）
  - L4 子任务计�?Π 生成机制
  - 实际 TeleDex 样本标定阈�?



- Type: workflow
- Status: validated
- Importance: high
- Reusable: yes
- Objective: 精读 DQAF 论文，将 DQAF 管线�?4 �?QC 架构融合，建�?TeleDex episode-level QC 统一框架
- Work completed:
  - 精读 DQAF 论文 (2605.26349v1) 全部内容：管线四阶段、公式体系、实验结�?
  - 分析 DQAF �?TeleDex 4 层架构中的对应位置：L1 不在 DQAF 范围、L2 对应 VLM 语义层、L3 对应 telemetry 层、L4 对应语义进度�?
  - 识别 DQAF �?7 项局限性及 TeleDex 增强方向
  - 建立完整�?4 �?QC 架构总览 (L1 硬性门�?�?L2 视觉+VLM �?L3 遥操作质量★ �?L4 任务完成�?�?聚合反馈)
  - 设计 27 项统一指标映射�?(M01-M27)，覆�?L1-L4 全部层级
  - 设计段级违规诊断机制（DQAF Section IV-D 适配 TeleDex�?
  - 提出初始聚合权重方案 (Q_motion 0.30 权重最�?
  - 设计 TeleDex 中文反馈模板
  - 更新报告 02 §1/§3.1/§4/§5
  - 阅读用户总结文档（调研报�?txt + 报告总结�?
- Business logic impact: B2 节点�?未开�?推进�?DQAF 精读完成 + 框架建立"；下一步深�?Consistency Matters + Forge 填充 L3
- Problems encountered: Edit 大段内容时触发长度限制，分批小量写入解决
- Resolution: 分批�?Edit，每�?200-400 �?
- Verification: 报告 02 内容�?DQAF 论文原文交叉核对一�?
- Unverified items: 27 项指标的具体阈值需实际样本标定；权重需人工 review 300-500 条后回归
- Files changed:
  - `doc/reports/02_data_quality_assessment_frameworks.md`
  - `.project-log/progress.md`
- Next steps:
  - 深入调研 Consistency Matters (Sakr et al., 2024) �?扩展 L3 指标
  - 调研 Forge (Tigunait, 2024) 源码 �?可复用实�?
  - 映射 L3 指标�?TeleDex telemetry.npz 字段
  - score_lerobot_episodes 文档调研 �?§3.2

## 2026-06-16 (采纳 GPT 调研路线�?2�?1�?3，DQAF 优先)

- Type: decision
- Status: validated
- Importance: high
- Reusable: yes
- Objective: 记录并采�?GPT 反馈�?2�? 周调研执行路�?
- Work completed:
  - 确认报告推进顺序�?*02 �?01 �?03**（按价值，非编号）
  - 确认第一任务�?*DQAF 精读 + TeleDex episode-level 指标映射�?*
  - 写入 Week 1�? 排期�?`handoff/pending-tasks.md` �?`00_research_plan.md`
  - 更新 `business-logic/main.md`、`decision-records.md`、`open-questions.md`（P0-4/P1-5�?
  - 明确暂缓项：QoQ/DemInf/SCIZOR 深入、score_lerobot 代码复现
  - 明确需团队确认 5 项：success 标签、task/语言字段、实际样本、关�?limit 表、tactile 启用
- Business logic impact: B2 优先�?B1/B3；当前边 B2→D；核心交付物�?`04` §7 指标映射�?
- Problems encountered: None
- Resolution: Not applicable
- Verification: 用户明确确认按此路线执行
- Unverified items: P0-1~P0-4、P1-5 待团�?平台方确�?
- Files changed:
  - `.project-log/business-logic/main.md`
  - `.project-log/business-logic/decision-records.md`
  - `.project-log/business-logic/open-questions.md`
  - `.project-log/handoff/pending-tasks.md`
  - `doc/reports/00_research_plan.md`
  - `.project-log/progress.md`
  - `.project-log/current-session.md`
- Next steps:
  - Day 1：DQAF 精读 �?`02` §1
  - Day 2：TeleDex QC 指标映射�?v0.1 �?`04` §7

## 2026-06-16 (汇总报告基线章节整�?

- Type: workflow
- Status: validated
- Importance: high
- Reusable: yes
- Objective: 将现有材料整理进汇总报告，确立 TeleDex 平台 QC 基线
- Work completed:
  - 重写 `doc/reports/04_teledex_qc_summary.md` v0.1 基线�?
  - §1–�?：项目背景、TeleDex 架构、平台已�?QC 能力详细盘点、数据资产速查、DROID 外部参照
  - §3 按采�?转换/产物三阶段梳理平台已有能力，并列出明确缺�?
  - §6–�? 占位，待三报告完成后补充
  - 提供基线 QC 读取指南（manifest �?metadata �?telemetry �?cameras�?
- Business logic impact: 节点 E �?未开�?推进�?基线章节完成"；后续调研明确为"在平台已有能力上增强"
- Problems encountered: None
- Resolution: Not applicable
- Verification: 内容与官�?PDF、teledex-data-format.md、DROID 调研报告交叉核对一�?
- Unverified items: 平台 QC 阈值需实际样本标定；OQ-01~06 仍开�?
- Files changed: `doc/reports/04_teledex_qc_summary.md`
- Next steps:
  - 按三报告计划推进深入调研
  - 调研结论回填 §6–�?

## 2026-06-16 (三报告调研结构确�?

- Type: decision
- Status: validated
- Importance: high
- Reusable: yes
- Objective: �?GPT 初稿 survey 拆分为三份深入报�?+ 汇总报告的工作结构
- Work completed:
  - 创建 `doc/reports/00_research_plan.md`（工作计划）
  - 创建报告 01/02/03 大纲（含统一调研模板、任务清单、对照表�?
  - 创建汇总报�?04 骨架
  - �?DROID 调研成果整合入报�?01
  - 更新 business-logic（B1/B2/B3 并行节点）、requirements、handoff
- Business logic impact: 主路径从单一 B 节点拆分�?B1+B2+B3 并行三报告，D/E �?TeleDex 适配与汇�?
- Problems encountered: None
- Resolution: Not applicable
- Verification: 文件结构已创建，与初�?survey 章节映射一�?
- Unverified items: 三报告内容均待深入调研填�?
- Files changed:
  - `doc/reports/00_research_plan.md`
  - `doc/reports/01_public_dataset_implicit_qc.md`
  - `doc/reports/02_data_quality_assessment_frameworks.md`
  - `doc/reports/03_data_curation_frameworks.md`
  - `doc/reports/04_teledex_qc_summary.md`
  - `.project-log/business-logic/main.md`
  - `.project-log/business-logic/graph.md`
  - `.project-log/requirements.md`
  - `.project-log/handoff/pending-tasks.md`
- Next steps:
  - 按优先级推进三报告（建议�?RH20T + DQAF�?

## 2026-06-16 (TeleDex 数据说明文档完整阅读)

- Type: workflow
- Status: validated
- Importance: high
- Reusable: yes
- Objective: 完整阅读 Linker Open TeleDex 官方数据说明文档，建�?QC 工作起点
- Work completed:
  - 阅读 `doc/Linker Open TeleDex数据采集系统-数据说明文档 .pdf`（V3.0�?9页）
  - 创建 `api/teledex-data-format.md`（完�?schema + QC 起点分析�?
  - 更新 `hardware/interface-protocols.md`、`business-logic/nodes.md`（节�?C�?
  - 部分解答 Q-20260616-002（平台内�?QC 能力�?
  - 解决 KI-20260616-003（telemetry.npz schema 已归档）
- Business logic impact: 节点 C �?部分完成"推进�?大部分完�?；QC 调研起点明确�?processed 数据 + 平台已有同步/裁剪能力
- Problems encountered: None
- Resolution: Not applicable
- Verification: PDF 全文已通过 Read 工具 + pdftotext 双重确认
- Unverified items:
  - 采集端是否有实时 QC 提示（文档未说明�?
  - 实际样本上的 QC 指标验证（仍无样本）
- Files changed:
  - `.project-log/api/teledex-data-format.md`（新建）
  - `.project-log/hardware/interface-protocols.md`
  - `.project-log/business-logic/nodes.md`
  - `.project-log/business-logic/open-questions.md`
  - `.project-log/debugging/known-issues.md`
- Next steps:
  - 基于 TeleDex 格式提出 QC 指标适配方案（节�?C→D�?
  - 继续 RH20T / DQAF 公开数据集调研（节点 B�?

## 2026-06-16 (project-log initialization complete)

- Type: workflow
- Status: validated
- Importance: high
- Reusable: no
- Objective: 完成 project-log 完整初始�?
- Work completed:
  - 创建 `business-logic/archived/archived-logic.md`（归�?KitchenDex-Data 早期方案�?
  - 创建 `architecture/`（software、hardware、communication、deployment�?
  - 创建 `hardware/`（hardware-list、sdk-mapping、interface-protocols�?
  - 创建 `api/`（internal-api、sdk-api、communication-api�?
  - 创建 `config/`（config-schema、runtime-config、parameter-mapping�?
  - 创建 `debugging/`（known-issues、debugging-history�?
  - 创建 `distillation/`（state.yaml、candidate-register、sync-status、runs/�?
  - 创建 `handoff/`（pending-tasks、next-steps、temporary-notes�?
  - 更新 `current-session.md`
- Business logic impact: None（记录结构完善，主干逻辑未变�?
- Problems encountered: None
- Resolution: Not applicable
- Verification: 目录结构符合 project-log skill 推荐完整结构；最小必需�?+ 机器人项目推荐项均已创建
- Unverified items:
  - TeleDex telemetry.npz 完整 schema 仍待补充（KI-20260616-003�?
- Files changed: `.project-log/` 下新�?architecture、hardware、api、config、debugging、distillation、handoff、archived 目录及文�?
- Next steps:
  - 继续节点 B：RH20T、DQAF 等公开数据�?QC 调研
  - 推进节点 C：Linker TeleDex QC 适配方案

## 2026-06-16 12:05 Local Time

- Type: workflow
- Status: validated
- Importance: high
- Reusable: no
- Objective: 初始化调研项目工程记�?
- Work completed:
  - 创建.project-log目录结构
  - 创建requirements.md（明确调研目标）
  - 创建business-logic目录（main.md、graph.md、nodes.md、edges.md�?
  - 创建open-questions.md（记录调研过程中的不确定问题�?
  - 创建decision-records.md（记录项目定位决策）
  - 创建constraints.md（记录调研约束）
- Business logic impact: 初始化调研流程business logic
- Problems encountered: None
- Resolution: Not applicable
- Verification: 文件创建成功，目录结构符合project-log规范
- Unverified items: None
- Files changed: .project-log/下所有文�?
- Next steps:
  - 继续公开数据集QC调研（RH20T、DQAF等）
  - 深度分析Linker TeleDex数据格式，提出QC适配方案
  - 整合调研报告

## 2026-06-16 Earlier

- Type: workflow
- Status: validated
- Importance: high
- Reusable: maybe
- Objective: 完成DROID数据集QC调研
- Work completed:
  - 下载并分析droid_100数据�?
  - 创建droid_qc_deep_research.py脚本分析数据
  - 生成DROID QC调研报告（doc/droid_qc_research/DROID_QC调研报告.md�?
  - 提取7条可迁移QC规则
- Business logic impact: 完成节点B的DROID调研部分
- Problems encountered: PDF读取工具无法提取文本
- Resolution: 使用pdftotext命令行工具成功提取PDF内容
- Verification: 调研报告已生成，数据分析脚本运行成功
- Unverified items: RH20T、DQAF等数据集调研待完�?
- Files changed:
  - scripts/droid/droid_qc_deep_research.py
  - doc/droid_qc_research/DROID_QC调研报告.md
  - doc/droid_qc_research/droid_qc_summary.json
- Next steps:
  - 继续其他数据集调�?
  - 整合公开数据集QC对比�?

---

## 2026-06-25 双视角审�?+ 批量修复轮次

- 审计：admin/reviewer 双角色真�?chromium 深度体验，产�?`audit-report-draft.md`（正确�?可用性双维度），方法论沉淀�?`~/.claude/skills/multi-role-ux-audit`
- HIGH 修复：派发抽检%静默重置（v-if→v-show+二次确认）、assigned+fail 状态机黑洞（dispatch跳过done episode+migration 0007）、根路径/白屏崩溃（自我重定向�?login�?
- MEDIUM 修复：task-pool reviewer越权（按角色裁剪payload）、删除→停用文案、跨页计数统一口径（migration 0008）、锁释放（onBeforeRouteLeave+管理员强制释放）、派发可发现性、评分环固定Q_motion、任务类型名校验
- LOW 修复：登录detail-only错误+空值校验、默认有活类型、返回按钮角色对齐、下载mimeType扩展名、无媒体禁用播放、全局中文locale
- 验证：重建镜�?alembic upgrade head�?007/0008�?生产栈重启；db/API实测矛盾�?0、待分类4/303、reviewer越权已堵；chromium实测根路径不白屏+admin dashboard正常
- 12 files changed, +335/-44, commit ec4b075 �?main

## 2026-07-15 13:30 CST

- Type: bugfix
- Status: resolved, verified
- Importance: critical
- Reusable: yes
- Objective: 修复数据资产统计页面 duration/frame_count 全为零的问题

- Root cause:
  - `backend/app/services/scanner.py` �?`_execute_minio_scan` �?manifest 读取逻辑使用 `except Exception: pass`，所�?manifest 读取异常（MinIO 连接抖动、response clean-up 异常等）被全部吞掉，`duration_sec`/`frame_count` 维持初始�?0�?
  - 5217 �?Episode 中只�?1 条有非零值——该条由手动质检页面 `manual_qc_context_payload()` 在读取详情时顺便回填�?
  - `episode_inventory` 表与 `episodes` 表的 duration/frame_count 均为 0，导致资产投影层汇总也�?0�?
  - 扫描器日志没有任何错误记录，因为异常�?`pass` 吃干净了�?
  - 4525 �?manifest JSON 文件实际存在�?MinIO 中，均包含有效的 `duration` �?`frame_count` 字段�?

- Work completed:
  1. **扫描器修�?*：新�?`_read_json_object()` �?`_extract_manifest_metrics()` 两个 helper 函数，替换原来的内联 try/except/pass。异常时至少�?warning 日志，不再静默吞掉�?
  2. **存量回填函数**：新�?`backfill_manifest_metrics()`，按 `episode_inventory �?episode_objects(manifest) �?MinIO get_object` 链路逐个读取 manifest 回填 `duration_sec`/`frame_count`，写入后自动排重算队列�?
  3. **CLI 入口**：`scan_worker.py` 新增 `repair-manifest-metrics` 命令，支�?`python -m app.services.scan_worker repair-manifest-metrics [operator_id] [bucket]`�?
  4. **存量回填执行**：重建后端镜�?�?在容器内执行回填命令�?525 条全部修复成功，0 �?manifest 读取错误�?
  5. **资产重算**：触�?`/api/data-assets/rebuild` 全量重算投影，验�?summary/batch list 接口返回正确值�?

- Business logic impact:
  - 存量数据显示正确：总时�?~50034 秒（�?21 秒），总帧�?~823320（原 633），duration 覆盖 4524 条（�?1 条）�?
  - 692 条纯 raw �?processed manifest �?Episode 继续保持零值，这是真实数据口径，不�?bug�?
  - 后续扫描器重新运行时可正常写入新 Episode �?duration/frame_count�?

- Problems encountered:
  - `docker exec` 不带 stdin 导致 heredoc 被吃掉，需要改�?`sh -lc "python -c '...'"` 内联命令形式�?
  - 后端容器内无 `psql`，获�?admin ID 需要走 DB 容器�?
  - 4525 �?manifest 回填耗时�?13 秒，吞吐�?350 �?秒，属可接受范围�?

- Resolution:
  - 对存量问题新增独立回填命令，不修改扫描器原有流程的接口签名�?
  - 扫描器本身的 fix 确保未来不再产生新数据全零的问题�?

- Verification:
  - `/api/data-assets/summary`：「episodeCount�?216，「totalDurationSec�?0034.19（原 21.07），「totalFrameCount�?23320（原 633），「durationCoveredEpisodeCount�?524（原 1�?
  - `/api/data-assets/batches`：第一�?batch 「totalDurationSec�?55.45 秒（�?0），「totalFrameCount�?5243（原 0�?
  - `SELECT count(*) FROM episodes WHERE duration_sec > 0` �?4525/5217
  - `SELECT count(*) FROM episode_inventory WHERE duration_sec > 0` �?4525/5217

- Files changed:
  - `backend/app/services/scanner.py`（新�?`_read_json_object`、`_extract_manifest_metrics`、`backfill_manifest_metrics`；修�?manifest 读取异常处理�?
  - `backend/app/services/scan_worker.py`（新�?`repair-manifest-metrics` 命令入口�?

- Next steps:
  - 后续若触发全量扫描，可验证新�?Episode �?manifest 指标能正常入�?
  - 692 条纯 raw Episode 待后处理流程完成后，重新扫描即可自动补全指标


## 2026-07-16 11:55 CST

- Type: business-logic
- Status: confirmed, not implemented
- Importance: high
- Reusable: yes
- Objective: 将“任务级数据资产画像”正式业务逻辑固化�?`.project-log`，暂不改代码

- Work completed:
  1. 审阅 GPT 给出的任务级资产画像长期架构方案，确认长期方向采�?Route T2，但实现风格需按现�?Route C' 收敛：`task_type_id` 主键、字符串 `calculation_version`、job 表承�?dirty/recompute�?
  2. �?`decision-records.md` 写入正式决策：`2026-07-16 �?任务级数据资产画像长期路线：Route T2（收敛实现）`�?
  3. 更新 `main.md`：补充任务级资产画像目标、正式对象、聚合链路、作用域、投影边界、刷新规则、最终可用�?人工质检口径�?API 边界�?
  4. 更新 `constraints.md`：固化任务投影只�?batch rollup 汇总、最终可用性主口径、比�?null 规则、job 合并、禁止假零、禁止复�?`/api/dataset/tasks/*` 等硬约束�?
  5. 更新 `graph.md` / `nodes.md` / `edges.md`：Node D 数据总库资产画像子路线扩展为 Episode / Batch / Task 三视角，任务层正式对象与 API 写入图谱�?
  6. 更新 `open-questions.md`：将“是否做任务级画�?是否建表/指标口径”收�?`Q-20260716-021` resolved；保留实现细�?open items（version 策略、inactive task 约束）�?
  7. 更新 `current-session.md`：当前目标切换为任务级资产画像业务逻辑已固化，等待用户确认后进入实现�?

- Business logic impact:
  - 数据总库正式三视角固定为：Episode 明细、Batch 资产、Task 资产�?
  - 正式聚合链路固定为：`episodes -> batch_asset_rollups -> task_asset_rollups -> GET /api/data-assets/tasks`�?
  - 全局 summary 继续：`batch_asset_rollups -> /api/data-assets/summary`�?
  - 最终可用性主口径：`final_dataset_status`；人工质检辅口径：`manual_qc_status`�?
  - `not_reviewed_count` �?`pending_dataset_count` 必须拆开�?
  - 比率分母�?0 时返�?`null`�?
  - `task_types.total_batches/total_episodes` 进入废弃流程�?
  - 任务资产不得塞进 `/api/dataset/tasks/*`�?

- Problems encountered: None
- Resolution: Not applicable
- Verification:
  - 决策、主逻辑、约束、图谱、开放问题、进度、会话七处口径已对齐 Route T2 收敛实现�?
  - 本轮仅固化业务逻辑，未改业务代码�?
- Unverified items:
  - `task_asset_rollups` / `task_asset_recompute_jobs` 代码尚未实现
  - 任务�?calculation_version 推进策略、inactive task 是否允许持有 active-scope batch 仍待实现前确�?
- Files changed:
  - `.project-log/business-logic/decision-records.md`
  - `.project-log/business-logic/main.md`
  - `.project-log/business-logic/constraints.md`
  - `.project-log/business-logic/graph.md`
  - `.project-log/business-logic/nodes.md`
  - `.project-log/business-logic/edges.md`
  - `.project-log/business-logic/open-questions.md`
  - `.project-log/progress.md`
  - `.project-log/current-session.md`
- Next steps:
  - 用户确认后，�?Route T2 实施顺序推进：Alembic 建表 �?task recompute 服务 �?接入 batch 成功链路 �?全量初始�?�?API �?前端三视�?
  - 实现前不要再回退到“请求时�?episodes / 前端按批次求�?/ 把统计堆�?task_types”的旧路�?

## 2026-07-16 12:12 CST

- Type: business-logic + implementation
- Status: confirmed + unit-tested
- Importance: high
- Reusable: yes
- Objective: 确认 Route T2 业务逻辑已固化，并完成任务资产画像代码落地与单测修复

- Work completed:
  1. 复核 `.project-log/business-logic/*`：decision / main / constraints / graph / nodes / edges / open-questions �?Route T2 口径已完整固化，无需回退重写�?
  2. 确认正式业务边界保持�?
     - `episodes -> batch_asset_rollups -> task_asset_rollups -> GET /api/data-assets/tasks`
     - 全局 summary 继续�?`batch_asset_rollups` 汇�?
     - 最终可用性主口径 `final_dataset_status`；人工质检辅口�?`manual_qc_status`
     - `not_reviewed_count` �?`pending_dataset_count` 拆开；比率分�?0 返回 `null`
  3. 实现侧已具备完整链路：模型、Alembic 迁移、服务层、API、worker、前�?Task 视角、单测�?
  4. 修复 SQLite 会话可见�?唯一性：enqueue �?rollup 查找改为 pending identity + flush 安全路径；batch rollup 写后 flush，避�?task 汇总读到空投影�?
  5. 调整 worker 相关单测期望，覆�?batch 成功后联动处理父 task job 的行为�?
  6. 跑�?`tests/test_data_assets.py`�?0/10 OK�?

- Business logic impact:
  - 业务逻辑本身无新增分叉，仍以 2026-07-16 �?Route T2 决策为准�?
  - 实现细节收敛确认：任务层 `calculation_version` 独立字符串常�?`task-asset-rollup-v1`，不�?batch 层共用同一常量�?
  - 默认任务列表优先 active task，并始终保留 `task_type:unclassified` 可见性�?

- Problems encountered:
  - `autoflush=False` 下未 flush �?pending job 导致 UNIQUE 冲突�?task 汇总为 0�?
  - worker 合并处理 batch+task 后，旧测试硬编码 processed==1 失真�?

- Resolution:
  - 服务层统一 session-safe 查找与必�?flush�?
  - 单测改为断言业务结果，而非错误的计数假设�?

- Verification:
  - `/home/tbl/Project/data_collect/software/backend/.conda-env/bin/python -m unittest tests.test_data_assets -v` �?10 tests OK

- Files changed:
  - `.project-log/current-session.md`
  - `.project-log/progress.md`
  - `.project-log/business-logic/open-questions.md`
  - `backend/app/services/data_assets.py`
  - `tests/test_data_assets.py`
  - （既有未提交实现）models / migration / API / frontend / worker

- Next steps:
  - 可选真实库迁移 + rebuild 冒烟
  - 用户要求时再 commit 实现



## 2026-07-16 12:45 CST

- Type: implementation + verification
- Status: completed
- Importance: high
- Reusable: yes
- Objective: Route T2 任务资产画像全量落地后完成完整性检查，并提交实�?

- Completeness audit:
  1. 模型/迁移字段与冻结口径一致：`task_asset_rollups` + `task_asset_recompute_jobs`
  2. 聚合链路正确：`episodes -> batch_asset_rollups -> task_asset_rollups`
  3. 最终可用�?/ 人工质检两组指标分离；比率读时计算，分母 0 �?null
  4. batch 重算成功�?enqueue �?task；task 若存�?pending/running/failed �?batch job 则等�?
  5. attach/detach/delete 任务关系变化�?dirty old/new task
  6. API 边界正确：`/api/data-assets/tasks*`，未侵入 `/api/dataset/tasks/*`
  7. 前端三视�?+ Task→Batch 钻取 + rebuild(scope=all) 已接�?
  8. worker / scheduler / rebuild scope=batch|task|all 已接�?

- Verification:
  - `backend/.conda-env/bin/python -m unittest tests.test_data_assets -v` �?10/10 OK
  - `PYTHONPATH=backend ... import app.services.data_assets / models / routes / schemas` �?OK
  - `frontend/node_modules/.bin/vue-tsc --noEmit` �?OK

- Residual / non-blocking:
  - 真实库迁移与 rebuild 冒烟尚未执行（环境相关）
  - `task_types.total_*` 仍保留兼容，待确认无调用后删�?
  - inactive task 持有 active-scope batch 的写路径禁令仍未额外收紧（Q-20260716-023 部分保留�?

- Files changed:
  - backend models / migration / services / API / schemas
  - frontend database-view / client / types
  - tests/test_data_assets.py
  - .project-log status docs

- Next steps:
  - commit 实现
  - 可选真实库迁移 + rebuild 冒烟

## 2026-07-16 Route T2 收尾：total_* 清理 + 真实库迁�?+ 前端修复

### 目标

完成 Route T2 最后两个残余步骤：`task_types.total_*` 废弃清理和真实库 rebuild 冒烟�?

### 改动

**commit `73f4c0c` �?`task_types.total_*` 清理�?*
- 删除 `task_types.total_batches` / `total_episodes` 列（Alembic `20260716_0025`�?
- `serialize_task_type` 改为接受 `db` + 可�?`counts` 映射，实时计�?
- 新增 `task_type_counts_map()` 批次查询批量避免 N+1
- 移除 `_refresh_task_type_stats` 函数及全部调用点
- 移除 `scanner.py` / `classification_seed.py` / qc router 中的 total_* 写入
- 测试构造器同步清理
- 相关文件: `backend/app/services/payloads.py`, `backend/app/api/routes/qc.py`, `backend/app/services/scanner.py`, `backend/app/models/task_type.py`, `backend/app/services/classification_seed.py`, `backend/migrations/versions/20260716_0025_drop_task_type_totals.py`, `tests/test_data_assets.py`

**commit `845a5fb` �?前端 TS 编译修复�?*
- `database-view.vue` 存在未使用的 `drillTaskToEpisodes` 变量，导�?`vue-tsc -b` 报错 `error TS6133`
- 移除后构建通过

**commit `a3b59b8` �?卡片顺序修正�?*
- 数据总库三个资产视图的顺序原�?Episode �?任务 �?批次
- 修正�?Episode �?批次 �?任务

### 线上迁移

- `docker compose --build` �?Bake/buildx 警告静默失败
- 改用 `docker compose build --no-cache frontend` 两步重建
- Alembic head: `20260716_0025`
- `rebuild-all` 完成: 52 batches / 20 tasks

### 经验教训

- Docker Compose Bake/buildx 配置�?`--build` 可能不实际重建；需要手�?`build --no-cache`
- Frontend Dockerfile �?COPY dist 模式，dist 需要本地先 `npm run build`
- Vite 8 (Rolldown) �?minification �?JS 变量名全部缩短，调试时需�?`strings` / `grep -oP` 而非精确匹配

### 待讨�?

- `index.html` �?Cache-Control 头，用户浏览器缓存旧 index.html 导致引用不存在的�?JS 哈希
  - 建议 nginx 配置 `index.html` �?`Cache-Control: no-cache`

## 2026-07-16 扫描入库架构升级 v2 决策完成

### 背景

当前扫描器使�?`threading.Thread` + `list_objects(recursive=True)` 全桶递归扫描，存在根本性缺陷：
- 线程挂死后无法终止（后台长期残留 zombie scan�?
- 无超时、无分片、无进度、无增量检�?
- 每次全量重新入库，规模增长后不可持续

### 决策过程

1. �?GPT 提供背景信息，获取初始分层并行扫描架构方�?
2. GPT 返回方案后，结合项目实际做技术评估，提出 8 个不确定问题
3. 将问题反�?GPT，获取关键决策分析反�?
4. 综合 GPT 反馈，生成最终实施方�?v2

### GPT 反馈采纳�?0 项）

| 采纳�?| 说明 |
|--------|------|
| `next_scan_at` 自适应退�?| 替代 `skip_until_next_change` |
| 删除检测限 shard 范围 | 不按 job 全局标记 |
| `rerun_requested` 幂等字段 | 修复 running→pending 竞�?|
| 独立 Docker Worker Service | 替换 FastAPI 内嵌 |
| BIGINT IDENTITY 主键 | 替换 BIGSERIAL |
| 保留旧表一个发布周�?| 不立即删�?|
| business_resolver 提前抽离 | 新旧 scanner 共用 |
| worker 初始 2 �?| Docker replica |
| 不建 object_inventory | 复用 episode_objects |
| 不做四级冷热调度 | 自适应退避等价替�?|

### 最终架�?

Prefix 分片 + PostgreSQL 持久化队�?+ 独立 Docker Worker Service + 子进程隔�?+ 流式指纹对比增量检�?+ `next_scan_at` 自适应退�?+ shard 级安全删除判�?+ `rerun_requested` 幂等资产投影联动

### 产出文件

- `docs/scan-architecture-final-plan-v2.md` �?最终实施方�?
- `docs/scan-architecture-assessment.md` �?技术评�?
- `docs/scan-architecture-open-questions.md` �?8 个不确定问题
- `.project-log/business-logic/decision-records.md` �?正式决策记录

### 下一�?

等待用户确认后启�?Step 0：基线测�?+ Feature Flag

## 2026-07-18 Annotation V1 第一阶段实现

- Type: implementation + verification
- Status: completed within confirmed first-phase scope
- Objective: 只为 active scope 内 `final_dataset_status=QUALIFIED` 的 Episode 建立 Sub Goal annotation 闭环，不改现有 QC 表单、批次裁决或历史 `UNQUALIFIED` 迁移。

- Work completed:
  - 新增 `SubGoalSchema` / `SubGoalDefinition` / `AnnotationTask` / `EpisodeAnnotation` / `EpisodeSubGoalInstance` / `AnnotationRevision` ORM 与 `20260718_0027_annotation_v1` migration。
  - 新增 annotation domain service：统一资格查询、Schema hash/version、任务幂等创建、草稿 CAS、固定 Definition occurrence、5 分钟编辑锁、完成校验、immutable revision 和审计事件。
  - 新增 `/api/annotations` 基础 API：Schema 创建/发布、eligible、ensure tasks、列表/详情、分配、公共领取、claim、lock/unlock、draft、complete。
  - 修正 reviewer 对公开领取任务的可见性；分配/领取进入 `assigned`，获取编辑锁进入 `in_progress`。
  - 新增前端 `/annotations` 人工标注工作台：任务列表、可选媒体预览、Schema 驱动 occurrence 编辑、`task_outcome`、失败原因、草稿保存、完成 revision、锁控制。
  - 更新前端类型、API client、路由和侧栏导航。

- Problems and resolutions:
  - 初版前端模板有 TS 语法错误和未使用 import，已修复并重新构建。
  - 新增 occurrence 未及时挂入 relationship 会导致完成校验看不到数据，服务层已改为 append 到 annotation relationship。
  - 草稿 CAS 应比较 task `row_version`，已移除无效的 annotation refresh 路径并统一使用 task version。
  - 默认历史 SQLite 存在 migration drift：`batches.list_id` 已存在但版本仍停在 `20260710_0022`；未修改用户库，改用全新临时库验证。

- Verification:
  - `backend/.conda-env/bin/python -m compileall -q app migrations` 通过。
  - SQLAlchemy `configure_mappers()` 通过。
  - Annotation routes present in FastAPI OpenAPI。
  - `frontend/npm run build` 通过；仅有既存 Vite/Rolldown vendor annotation 与 chunk-size warning。
  - `DATABASE_URL=sqlite:////tmp/annotation-v1-final.db .conda-env/bin/alembic upgrade head` 从 baseline 完整通过至 `20260718_0027`。
  - 新增 annotation 文件与相关改动 `git diff --check` 通过；整个工作区仍有既有 `.project-log/progress.md` trailing whitespace。

- Unverified items:
  - 尚未在真实 PostgreSQL + MinIO Compose 环境运行 annotation API/浏览器端到端验收。
  - 默认历史 SQLite migration drift 需要单独治理，不属于本轮 annotation 业务代码修复。
  - 尚未实现 Schema 管理 UI、批量任务生成 UI、VLM worker 或训练导出。

- Files changed:
  - `backend/app/models/annotation.py`
  - `backend/app/models/task_type.py`
  - `backend/app/models/__init__.py`
  - `backend/app/schemas/annotation.py`
  - `backend/app/services/annotation.py`
  - `backend/app/api/routes/annotations.py`
  - `backend/app/api/__init__.py`
  - `backend/app/api/routes/__init__.py`
  - `backend/migrations/versions/20260718_0027_annotation_v1.py`
  - `frontend/src/types/qc.ts`
  - `frontend/src/api/client.ts`
  - `frontend/src/pages/annotations.vue`
  - `frontend/src/router/index.ts`
  - `frontend/src/components/AppLayout.vue`
  - `.project-log/current-session.md`
  - `.project-log/progress.md`

- Next steps:
  - 用真实 PostgreSQL/MinIO 启动后做 annotation API + 浏览器验收。
  - 如需运营化，再补 Schema 管理和批量 ensure tasks 页面。
  - 单独处理默认历史 SQLite 的 Alembic drift；不要把它与 annotation migration 混合修复。
