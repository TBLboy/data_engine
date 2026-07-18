# Robot QC V1 数据标注模块

## 给 GPT 的项目背景与讨论任务

> 文档用途：将本项目当前已确认的标注业务逻辑、VLM 自动流水线和现有系统背景完整交给 GPT，继续讨论业务边界、前端工作流和页面设计。
>
> 使用方式：可以将本文件整体复制给 GPT。请 GPT 先理解并检查业务逻辑，再提出前端工作流设计，不要直接假设未确认的规则已经确定，也不要直接开始写代码。
>
> 当前版本：Robot QC V1 / 数据标注模块 V1
>
> 最后整理日期：2026-07-18

---

## 1. 我希望 GPT 帮助解决什么

我正在为一个机器人数据质量控制平台设计“质检后数据标注”模块。当前标注模块的核心业务逻辑已经基本确定，下一步需要继续讨论：

1. 业务逻辑是否完整、是否存在隐藏冲突。
2. VLM 自动标注流水线是否合理、高效、可运营。
3. admin、qc_manager、reviewer、viewer 四类用户分别应该如何工作。
4. 标注首页、TaskType 工作区、Episode 工作池、标注工作台、VLM 任务管理和导出页面应该如何组织。
5. 前端页面中的状态、按钮、批量操作、筛选、进度、失败提示和权限控制应该如何设计。
6. 哪些问题必须在编码前继续冻结，哪些内容可以作为实现配置。

请重点从真实生产使用角度审查方案：

- 标注员白天是否能直接进入已经完成 VLM 预标注的工作池。
- 夜间自动标注是否真正减少人工等待和人工点击。
- 批量任务是否可控、可追踪、可重试、可暂停。
- VLM 结果是否可能覆盖人工修改。
- 业务状态、VLM 状态、人工工作状态和导出状态是否混淆。
- 前端是否会让用户误以为“自动标注”仍然需要逐条启动。

请不要直接实现代码。先给出：

1. 对当前业务逻辑的审查。
2. 需要进一步澄清的业务问题。
3. 推荐的前端信息架构和用户工作流。
4. 页面状态机、按钮行为和异常流程。
5. 最后再给出适合进入实现阶段的页面/API/数据模型建议。

---

## 2. 项目背景

这是一个机器人数据采集与质量控制平台，目标是将机器人采集数据从原始数据逐步处理为可用于训练的数据集。

总体链路如下：

```text
机器人数据采集
  → TeleDex 数据写入 MinIO
  → 扫描入库与 Episode 索引
  → Batch / TaskType 管理
  → L3 自动质量评估
  → L2/L4 人工质检
  → Batch adjudication / 最终质量裁定
  → 合格 Episode 进入数据标注池
  → VLM 自动预标注
  → 人工审核、修改、确认
  → revision 快照
  → 带标注训练集导出
```

数据标注是质检之后的独立环节。

标注模块：

- 只消费 QC 的最终结论。
- 不重新实现 L2/L3/L4 或 Batch 驳回判断。
- 不能修改 `Episode.final_dataset_status`。
- 不能反向修改任何 QC 状态。
- 负责生成和维护训练数据所需的结构化语义标注。

---

## 3. 现有技术栈与架构

以下内容是当前项目已知背景：

### 后端

- Python。
- FastAPI。
- SQLAlchemy。
- Alembic。
- PostgreSQL 作为业务事实源。
- 后端 API 位于 `backend/app/api/routes/`。
- ORM 模型位于 `backend/app/models/`。
- 业务服务位于 `backend/app/services/`。
- 后台扫描与重算采用持久化队列、coordinator/worker、lease/heartbeat 等模式。

### 前端

- Vue 3。
- Element Plus。
- Pinia。
- Vue Router。
- Chart.js。
- 前端只调用后端 API，不直接访问 MinIO。
- 媒体预览通过后端生成短时 presigned URL。

### 存储

- MinIO：原始视频、telemetry、manifest 等对象存储。
- PostgreSQL：Episode、Batch、TaskType、QC 状态、标注草稿、标注任务、revision、AI 调用和导出记录。
- PostgreSQL 是业务查询的唯一事实源。

### AI/VLM

- 当前已部署 Ollama。
- 当前使用 Qwen3-VL-32B，约 24GB GPU 环境。
- 当前约束：全局 VLM 并发固定为 1。
- VLM 应通过独立持久化 `annotation-worker` 执行，不应将 FastAPI `BackgroundTasks` 作为可靠主路径。

### 重要现有模式

- `active_list_active_batch_indexed_episodes` 是项目统一的有效数据作用域标识。
- 统计不应在请求时回扫全部 Episode，也不应让前端拉取全量数据后本地聚合。
- 已有资产统计使用持久化 rollup 和 recompute job。
- 扫描 worker 使用持久化 job、lease、heartbeat、重试和取消机制。

---

## 4. 相关代码和项目日志

以下路径是当前讨论最相关的文件：

### 业务逻辑文档

- `.project-log/business-logic/annotation-v1.md`
  - 标注模块初始规范，包含历史自由 Segment 设计。
  - 仅作背景；新实现不得以其 Segment 模型为依据。

- `.project-log/business-logic/annotation-sub-goals-v1.md`
  - TaskType 版本化 Sub Goal Schema 的主语义规范。
  - 对 Sub Goal、任务行为结果和失败样本规则优先于其他标注文档。

- `.project-log/business-logic/annotation-v1-final-decisions.md`
  - 当前标注 V1 的最终补充决策。
  - 如果与 `annotation-v1.md` 冲突，以本文件为准。

- `.project-log/business-logic/main.md`
  - 项目主业务路径和稳定约束。

- `.project-log/business-logic/decision-records.md`
  - 标注模块初始决策、最终收口决策和“VLM 改为后台流水线默认触发”的决策记录。

### 现有后端模型和服务

- `backend/app/models/episode.py`
  - 真实 Episode 字段。
  - 重点字段：`final_dataset_status`、`is_exportable` 等。

- `backend/app/models/batch.py`
  - 真实 Batch 字段。
  - 重点字段：`task_type_id`、`is_active` 等。

- `backend/app/models/task_type.py`
  - 真实 TaskType 字段。
  - `description` 是当前任务描述字段，也是 VLM 任务语义基准。

- `backend/app/models/qc.py`
  - 当前已有 `DatasetExportJob` 等导出相关模型。

- `backend/app/services/batch_adjudication.py`
  - `final_dataset_status` 的统一计算来源。

- `backend/app/services/dataset_service.py`
  - 现有训练数据集和导出服务。

- `backend/app/services/scan_worker.py`
  - 可参考持久化 worker、lease、heartbeat、重试和取消模式。

---

## 5. 当前已确认的业务规则

以下规则视为已确认，不要在讨论中无理由推翻。如果发现它们互相冲突，请明确指出冲突位置和影响。

### 5.1 标注资格

Episode 进入标注池必须同时满足：

```text
Episode.final_dataset_status = 'QUALIFIED'
AND Episode 位于 active_list_active_batch_indexed_episodes
```

含义：

- `final_dataset_status` 是 QC 合格资格的唯一业务判据。
- 标注模块不重新判断 L2/L3/L4、Batch 驳回原因或其他 QC 细节。
- active scope 排除 inactive List、inactive Batch、inactive Episode、缺少必要索引或来源不可访问的数据。
- `is_exportable` 是现有派生便利字段，不替代正式标注资格条件。

### 5.2 TaskType 归属

唯一正式关系是：

```text
Episode → Batch.task_type_id → TaskType
```

规则：

- `Batch.task_type_id` 是 Episode 标注分组的唯一来源。
- `ListRecord.final_task_type_id` 属于扫描控制面分类，不直接驱动已入库 Episode 的标注归属。
- 创建 `annotation_task` 时保存当时的 `Batch.task_type_id` 快照。
- 后续 Batch 改挂 TaskType 时，已有 annotation task、草稿、revision 和导出历史不自动迁移。
- 如需迁移，必须由管理人员执行显式“重新归类标注任务”操作，并记录旧、新 TaskType 和操作者。

### 5.3 标注任务状态

`annotation_tasks.work_status` 是人工标注工作流状态：

```text
pending      已创建，尚未人工确认完成
completed    草稿通过最终校验并人工确认完成
invalidated  Episode 失去标注资格，停止正常工作流和导出
```

“未标注 / 待标注 / 完成标注”是面向用户的计算状态，不是额外业务状态字段：

| 用户状态 | 条件 |
|---|---|
| 未标注 | 满足标注资格且没有 `annotation_task` |
| 待标注 | 有 `annotation_task` 且 `work_status = pending` |
| 完成标注 | 有 `annotation_task` 且 `work_status = completed` |
| 失效历史 | `work_status = invalidated` |

### 5.4 VLM 自动标注的默认触发方式

VLM 初始自动标注不是由 reviewer 逐条点击启动，而是自动化流水线的默认环节。

#### 后台夜间自动触发

后台调度器按固定周期扫描所有满足以下条件、且没有初始 VLM 任务的数据：

```text
final_dataset_status = 'QUALIFIED'
AND 位于 active_list_active_batch_indexed_episodes
AND 尚未创建 annotation_task / 初始 annotation_generation_job
```

默认在北京时间午夜之后的低峰时段运行，避免占用白天人工工作资源。具体起止时间、每日最大数量、优先级和暂停策略属于部署配置，但必须支持后台可靠运行。

后台调度行为：

1. 按 TaskType 分组发现新数据。
2. 批量创建 `annotation_task`。
3. 批量创建 `annotation_generation_jobs`，`job_type = initial`、`status = queued`。
4. 通过同一个持久化队列交给 `annotation-worker`。
5. 白天 reviewer 进入工作池时，原则上面对已经完成 VLM 初始预标注的任务，只需要审核和微调。

#### admin / qc_manager 手动触发

`admin` 和 `qc_manager` 在标注工作区可以按以下范围手动控制：

- TaskType。
- Batch。
- Episode。
- 筛选条件。

支持的操作：

- 启动新数据自动标注。
- 补漏扫描。
- 失败任务重试。
- 指定范围重跑。
- 对已有草稿执行局部或全部重新生成。

手动操作默认只补充缺失任务，不重复覆盖已有成功结果。

#### reviewer 批量补漏

reviewer 可以对自己工作池中尚未生成初始结果的数据批量启动自动标注，但这只是补漏入口，不是主流程，也不要求逐 Episode 点击。

### 5.4a 派发、公共领取、人工从零标注与异常协作

以下规则已经冻结：

- `admin` / `qc_manager` 的批量派发是 reviewer 进入标注任务的标准路径。
- 标准待派发池只包含资格有效、`work_status = pending`、initial VLM job 已成功且尚未分配 reviewer 的任务。
- 管理人员可将标准任务显式开放为公共领取池。只有 `public_claim_enabled = true`、initial VLM 已成功、尚未分配的任务可由 reviewer 原子领取；这不是任何未分配任务都可领取的开放抢单池。
- 派发或成功领取时，系统必须在同一事务写入 `assigned_to` 并关闭 `public_claim_enabled`。取消分配、退回或资格恢复不会自动重新开放，必须由管理人员再次显式开放。
- V1 没有 reviewer 硬任务上限；个人看板和管理端使用可配置积压预警阈值，超出时警告但不阻塞派发或领取。
- 无 VLM 结果的任务必须进入单独的“从零标注待派发池”，派发时显示原因和人工成本提示，并要求二次确认。
- `assigned_to` 是长期任务归属，`lock_owner` 是五分钟编辑锁，不能混用。含有效编辑锁的任务不能普通改派；强制改派必须先释放锁、填写原因并审计。
- 已完成任务必须先退回至 `pending`，才可以改派。
- reviewer 可以请求管理员处理本人 pending 任务。正式异常上报使用 `annotation_task_escalations`，而不是只写自由备注；类别包括数据、TaskType、VLM、阻塞和其他问题。

人工从零标注来源规则：

- `initial_source = manual`：首次即由人工创建空白草稿。
- `initial_source = vlm`：系统曾创建 initial VLM job，即使该 job 后来失败也不改写为 `manual`。
- `manual_from_scratch_reason` 记录人工接管原因：`admin_skip_vlm`、`vlm_failed`、`task_type_vlm_disabled`、`urgent_manual`、`unsupported_media`。

### 5.4b 已冻结的前端状态边界

不要将所有标签塞进 `annotation_tasks.work_status`。权威来源如下：

| 前端含义 | 权威来源 |
|---|---|
| `pending/completed/invalidated` | `annotation_tasks.work_status` |
| 等待/运行/成功/失败 VLM | `annotation_generation_jobs.status` |
| 未分配/已分配 | `assigned_to` |
| 编辑中 | 有效 `lock_owner` 租约 |
| 被退回 | 退回审计事件和 `returned_*` 字段 |
| 已导出 | 对应 `dataset_export_items`，不是 Episode 单值状态 |
| 等待管理员处理 | open/acknowledged 的 blocked escalation |

### 5.5 VLM 队列和执行

VLM 工作由持久化 `annotation_generation_jobs` 承担，不能依赖 FastAPI 进程内后台任务。

支持的 `job_type`：

| job_type | 用途 | 是否直接改变草稿 |
|---|---|---|
| `initial` | 空白 Episode 的首次预标注 | 首次成功时可自动写入空白草稿 |
| `all` | 重新生成整份标注 | 只生成候选，人工显式应用 |
| `instruction` | 重新生成标准指令 | 只生成候选，人工显式应用 |
| `variants` | 重新生成英文变体 | 只生成候选，人工显式应用 |
| `sub_goals` | 重新生成固定 Sub Goal occurrence | 只生成候选，人工显式应用 |
| `check` | 检查标注问题并给出建议 | 永不直接修改草稿 |

job 状态：

```text
queued / running / succeeded / failed / cancelled / superseded
```

关键执行约束：

- 全局 VLM 并发固定为 1。
- 同一 annotation task 同时最多一个 active mutating job：`initial/all/instruction/variants/sub_goals`。
- `check` 是只读 job，可以并行，但必须绑定草稿版本。
- `max_attempts = 3`，即首次调用加最多两次重试。
- 每次失败、重试和候选结果发布前重新检查 Episode 资格。
- 夜间、管理员、质检主管和 reviewer 的所有触发方式都必须进入同一个持久化队列。
- 后台扫描必须幂等：同一 Episode 已经存在 task 或 active/succeeded 初始 job 时，不得重复创建初始任务。

### 5.6 VLM 结果与人工草稿

每个 Episode 只有一份当前可变草稿：

```text
episode_annotations
```

VLM 和人工都围绕这份草稿协作。

- 首次自动标注：空白草稿第一次成功时可以自动填入结果。
- 后续重新生成：结果先保存为候选，不得静默覆盖草稿。
- 用户点击“应用候选结果”后，才更新草稿。
- “重新生成全部”必须展示差异；如果已有人工修改或任务已完成，还需要二次确认。
- 局部重生成只能修改对应字段。
- `check` 只返回问题、建议和定位信息。
- AI 检查结果绑定 `requested_draft_version`，草稿变化后自动过期。
- 所有 AI 调用都保留 `annotation_ai_runs` 审计记录。

### 5.7 人工标注内容

Episode 级字段：

- `canonical_instruction_en`：标准英文指令，完成时必填。
- `canonical_instruction_zh`：选填。
- `instruction_variants_en`：选填，`0..5` 条不重复英文变体。
- `episode_summary`：选填。
- `objects`：选填，结构化对象列表。
- `task_outcome`：完成时必填，表示任务行为结果，不等于数据质量资格。
- `annotation_notes`：选填。

Sub Goal 训练语义由 TaskType 的版本化 Schema 固定。每个 Episode 只能创建固定 Definition 的 occurrence，不能创建自由 Segment 名称。

每个 occurrence 包括固定 `sub_goal_definition_code`、`occurrence_no`、`status`、`start_step`、`end_step_exclusive`、`representative_step`、`failure_reason` 和 `notes`。

`status` 取值为 `observed`、`failed`、`skipped`、`not_observed`、`not_applicable` 或 `uncertain`。

Sub Goal occurrence 规则：

- 使用 telemetry step 作为主时间轴。
- 使用左闭右开区间 `[start_step, end_step_exclusive)`。
- `start_step < end_step_exclusive`。
- 不得超出 Episode 总 step 范围。
- 同一 Definition 的 occurrence 不得重叠；不同 Definition 可重叠。
- `representative_step` 必须位于该 occurrence 内。
- 可以存在等待、停顿和未覆盖区间。

### 5.8 确认完成

草稿阶段允许字段不完整；确认完成时才执行严格校验。

最低完成要求：

1. `canonical_instruction_en` 非空。
2. annotation task 已冻结并可读取 Published Sub Goal Schema。
3. observed/failed occurrence 的边界、代表帧和同 Definition 重叠规则合法。
4. `task_outcome` 使用合法枚举：
   - `completed_normally`
   - `completed_with_retry`
   - `partially_completed`
   - `failed`
   - `uncertain`
5. `task_outcome = failed` 时具有失败 occurrence 和失败原因；无法定位时使用 uncertain 并说明。
6. Definition 对象提示和 Episode 对象引用若都存在，必须一致。
7. JSONB 通过 `annotation_schema_version = '1.0'` 对应的 Schema 和业务校验。

确认完成事务：

```text
校验当前草稿
  → 创建 annotation_revision 完整快照
  → 计算 content_hash
  → 更新 current_revision_no
  → annotation_task.work_status = completed
  → 记录 completed_by / completed_at
```

### 5.9 Revision 和导出

草稿保存直接更新 `episode_annotations`，并使用 `row_version` CAS 乐观锁。

每次确认完成创建不可变 `annotation_revisions`。revision 不可修改、不可删除。

带标注训练集导出条件：

```text
Episode 位于 active_list_active_batch_indexed_episodes
AND Episode.final_dataset_status = 'QUALIFIED'
AND annotation_task.work_status = 'completed'
AND 存在当前 annotation_revision
```

创建导出任务时，在一个事务中为每个 Episode 冻结：

- `annotation_revision_id`。
- `revision_no`。
- `content_hash`。

后续标注重新编辑不会影响已经创建的导出任务。要使用新 revision，必须创建新的导出任务。

普通数据导出和带标注训练集导出是两个不同语义，不要混淆。

### 5.10 资格失效和恢复

如果 Episode 后来不再满足标注资格：

1. `annotation_tasks.work_status → invalidated`。
2. 保存 `status_before_invalidation`、`invalidated_at`、`invalidation_reason`。
3. 取消 queued/running generation job，worker 发布结果前重新校验资格。
4. 保留草稿、revision、AI run 和导出历史。
5. 从默认标注统计和默认带标注导出中排除。

如果 Episode 恢复资格：

- 原来是 `pending`，恢复为 `pending`。
- 原来是 `completed`，恢复为 `completed`。
- 不自动重新生成 VLM。
- 不自动创建新 revision。
- 失效和恢复都需要审计。

### 5.11 权限

当前用户模型是单个 `role`，V1 不新增独立 `annotator` 角色，也不改造成多角色集合。

| 角色 | 标注能力 |
|---|---|
| `admin` | 全部操作，包括批量触发、任务管理、强制释放锁和导出 |
| `qc_manager` | 全部标注管理操作，包括批量触发、分配、退回、强制释放锁和导出 |
| `reviewer` | 查看、领取、编辑、保存、确认本人任务；可对本人工作池批量补漏；不能管理他人任务和导出 |
| `viewer` | 只读查看 |

多人编辑保护：

- `annotation_tasks` 使用 `lock_owner` + 5 分钟租约。
- 编辑页面每 30 秒心跳续租。
- `admin` / `qc_manager` 可以强制释放锁，但必须记录原因。
- 草稿保存使用 `episode_annotations.row_version` CAS 乐观锁。

---

## 6. VLM 输入、输出和实际任务画像

### 6.1 VLM 输入

一次 VLM 调用使用以下多模态证据：

1. `TaskType.description`，并保存 `task_description_snapshot`。
2. Episode 时长、总 step 数、帧率等元数据。
3. 三路同步视频：
   - `cam_top`
   - `cam_left_wrist`
   - `cam_right_wrist`
4. telemetry 运动摘要。
5. 候选动作事件和边界。
6. 当前草稿内容与 `requested_draft_version`，如果本次不是初始标注。

### 6.2 抽帧策略

正式策略是：

```text
均匀时间采样
  + telemetry motion_score 事件峰值
  + 三路同步组合图
  + VLM 固定 Sub Goal occurrence 粗对齐
  + telemetry 边界吸附/局部细化
  + 人工时间轴最终确认
```

具体采样数量、阈值、图片尺寸、telemetry 权重和最大候选数属于版本化配置，不是业务状态。

### 6.3 VLM 输出

VLM 输出必须是结构化 JSON，核心内容包括：

```json
{
  "canonical_instruction_zh": "...",
  "canonical_instruction_en": "...",
  "instruction_variants_en": ["..."],
  "episode_summary": "...",
  "objects": [],
  "task_outcome": "completed_normally",
  "sub_goal_occurrences": [],
  "warnings": []
}
```

后端必须先进行 Schema 解析和业务校验，再保存候选结果或写入空白草稿。不能把模型返回的自由文本直接当作最终标注。

### 6.4 VLM 任务和 AI 调用的关系

```text
一个 Episode
  → 最多一个 annotation_task
  → 可以有多条 annotation_generation_jobs
  → 每个 generation_job 可以有多条 annotation_ai_runs
```

区别：

- `annotation_task`：Episode 是否进入标注工作流，以及人工工作状态。
- `annotation_generation_job`：系统希望 VLM 执行的一项具体工作。
- `annotation_ai_run`：实际发生的一次模型调用、输入、输出、错误和耗时。

---

## 7. 前端需要设计的主要工作区

以下是待继续讨论和设计的前端范围，不代表页面细节已经最终确定。

### 7.1 标注首页

预期功能：

- 按 TaskType 展示标注任务卡片。
- 展示 eligible、unannotated、pending、completed、invalidated 等统计。
- 展示 VLM queued、running、failed 等队列状态。
- 展示最近一次后台扫描时间、最近一次 VLM 批处理时间和失败提示。
- 提供 admin/qc_manager 的任务级批量控制入口。
- 让 reviewer 快速进入自己的待审核工作池。
- 显示没有 TaskType、来源不可访问、VLM 失败和待处理异常数据。

### 7.2 TaskType 标注工作区

预期功能：

- 查看当前 TaskType 的 Episode 标注进度。
- 按 Batch、Episode、标注状态、VLM 状态、分配人、更新时间筛选。
- 区分“等待 VLM”“等待人工审核”“人工编辑中”“VLM 失败”“已完成”“已失效”。
- 支持批量分配、领取、启动补漏、失败重试和导出。
- admin/qc_manager 能看到更完整的任务管理信息。
- reviewer 默认看到自己的工作池，并能批量处理待审核 Episode。

### 7.3 标注工作台

预期功能：

- 三路视频同步查看。
- 时间轴和固定 Sub Goal occurrence 编辑。
- telemetry 事件、候选边界和代表帧展示。
- Episode 级字段编辑。
- 对象列表编辑。
- VLM 生成结果和人工修改结果的清晰区分。
- 结构化 AI 操作：重新生成全部、标准指令、变体、Sub Goal occurrence、检查当前标注。
- 候选结果差异预览和显式应用。
- 草稿保存、乐观锁冲突提示、编辑锁状态、心跳和锁过期提示。
- 确认完成前的校验错误汇总。
- revision 历史查看。

### 7.4 VLM 任务管理区

是否需要独立页面或作为标注首页抽屉/面板，需要进一步讨论。可能包含：

- 后台批次的 request group。
- queued/running/succeeded/failed/cancelled/superseded 任务。
- 每个 TaskType 的队列数量。
- retry 次数和失败原因。
- 当前 worker 和 GPU 占用状态。
- 暂停/恢复夜间自动调度。
- 手动批量触发和补漏扫描。
- 失败任务重试。
- 任务取消。

### 7.5 导出页面

预期功能：

- 创建普通数据导出。
- 创建带标注训练集导出。
- 显示导出筛选条件。
- 显示冻结的 Episode 数量和 revision 版本。
- 显示成功、失败、跳过和待处理项。
- 显示 `content_hash` 和导出时间。
- 区分正在执行的导出和已经完成的历史导出。

---

## 8. 当前仍需 GPT 重点审查的开放问题

以下问题尚未完全冻结。请逐项给出建议，并说明不同选择对业务、数据库、API 和前端的影响。

### 已冻结的 Sub Goal 与失败样本边界

- 每个 TaskType 同时只能有一个默认 `published` Sub Goal Schema；`draft` 和 `retired` Schema 不得用于新任务。
- 创建 annotation task 时冻结 Schema 的 id、版本和内容哈希；后续发布新版本不迁移已有任务。
- 没有默认 Published Schema 的合格 Episode 不创建 annotation task 或 initial VLM job，而是进入 `missing_published_sub_goal_schema` 管理异常池。
- `final_dataset_status` 只表达数据质量/介质资格，`task_outcome` 只表达任务行为结果。数据质量合格但任务失败的 Episode 是正式标注和默认带标注导出样本。
- 当前 `MANUAL_FAIL -> UNQUALIFIED` 的后端行为尚未拆分质量失败和任务失败。历史 `UNQUALIFIED` Episode 不得自动迁移到失败训练样本，必须先经过显式质量复核。

### 8.1 没有 TaskType 的合格 Episode

已知正式归属来源是 `Batch.task_type_id`，但需要明确：

- `Batch.task_type_id` 为空时，是否完全不进入 VLM 自动标注队列。
- 是否在标注首页显示“待归类”数量。
- 谁负责补齐 TaskType。
- 补齐后是否等待下一次夜间扫描，还是立即进入队列。

### 8.2 TaskType 停用或删除

需要明确：

- TaskType 停用后，已有 completed 标注是否仍可导出。
- 停用 TaskType 是否只隐藏工作入口，还是阻止新 VLM 任务。
- 默认导出是否排除停用 TaskType。
- 是否允许 admin 显式导出停用 TaskType。
- TaskType 是否允许物理删除，还是只能停用。

### 8.3 夜间自动标注窗口

业务方向已确定为低峰时段，但仍需决定：

- 北京时间具体起止时间。
- 白天是否允许新任务继续入队。
- 夜间未完成的任务是否继续运行到白天。
- 是否支持管理员暂停自动调度但保留人工补触发。
- 每夜最大 Episode 数量和 GPU 预算如何配置。

### 8.4 自动调度发现粒度

需要明确后台扫描的触发来源：

- 只靠定时周期扫描。
- QC 状态变为 `QUALIFIED` 时同时写 dirty 事件，再由调度器入队。
- 两者结合：事件提高实时性，夜间扫描用于兜底对账。

建议 GPT 重点评价幂等、漏任务恢复和数据库负载。

### 8.5 初始 VLM 结果的自动应用边界

当前规则是空白草稿的首次成功结果可以自动写入草稿。需要进一步确认：

- 什么叫“空白草稿”。
- 如果后台任务执行时用户刚创建了人工草稿，如何判定不能自动写入。
- `row_version`、`human_modified` 和字段级修改时间如何共同判断。
- 初始结果部分字段无效时，是整体拒绝，还是允许部分字段写入。

### 8.6 VLM 任务优先级

当前全局并发为 1，需要设计队列优先级：

- 后台初始任务。
- admin/qc_manager 手动补漏。
- reviewer 工作池补漏。
- 失败重试。
- 局部重生成。
- `check` 任务。

请建议优先级规则，避免手动任务饿死夜间任务，也避免初始自动标注永远被重生成占用。

### 8.7 过期候选结果

需要确认：

- 新同类 job 创建后，旧 queued/running job 是否立即 `superseded`。
- 应用候选结果时是否必须满足 `requested_draft_version == 当前 row_version`。
- 版本过期后是否允许用户强制查看并手动合并。
- `check` 结果过期后，前端如何显示和处理。

### 8.8 标注任务分配运营细节

派发和公共领取的核心边界已冻结，仍可讨论以下运营参数：

- 管理人员应该按什么策略决定哪些 TaskType 或任务开放公共领取。
- 是否显示其他 reviewer 已领取任务的只读进度。
- 长时间未处理的积压预警阈值、提醒频率和管理员改派节奏。
- 是否为特定 TaskType 设置更严格的 reviewer 工作池建议上限。

### 8.9 reviewer 与 VLM 的交互

需要明确默认交互：

- reviewer 打开 Episode 时默认直接进入审核模式。
- VLM 失败时显示“人工从零标注”。
- VLM 成功但结果不完整时显示问题清单。
- reviewer 是否可以对单个字段重生成。
- reviewer 是否可以触发“重新生成全部”。
- completed 任务重新编辑是否需要 manager 审批。

### 8.10 导出格式契约

revision 冻结规则已确定，但以下还没有完全冻结：

- Robot QC JSON 的正式字段结构。
- LeRobot 转换器的字段映射。
- 视频或 telemetry 缺失时的处理。
- 导出任务中单个 Episode 失败时，是整批失败还是允许部分成功。
- manifest、统计文件、content hash 和版本信息的格式。

---

## 9. 推荐的前端讨论顺序

请 GPT 按以下顺序讨论，不要一开始就陷入组件细节：

1. 先确认用户角色和每天的真实工作目标。
2. 再确认后台自动标注和人工审核之间的状态边界。
3. 再设计标注首页的信息架构。
4. 再设计 TaskType 工作区和 reviewer 工作池。
5. 再设计单 Episode 标注工作台。
6. 再设计 admin/qc_manager 的 VLM 批处理和失败管理。
7. 再设计导出页面。
8. 最后才讨论 Vue 组件、API 结构、路由和状态管理。

请优先产出以下内容：

- 页面层级树。
- 各角色进入页面后的默认落点。
- 页面状态和状态转换图。
- 每个按钮的显示条件、触发动作、成功反馈和失败反馈。
- 批量操作的选择范围、确认弹窗、进度显示和可取消行为。
- VLM 处理中、成功、失败、失效和过期结果的用户体验。
- reviewer 一天的最短操作路径。
- admin/qc_manager 对自动标注流水线的运营路径。

---

## 10. 重要约束

- 不要把 VLM 自动标注设计成 reviewer 逐条启动的主流程。
- 不要让前端直接调用 VLM。
- 不要使用 FastAPI 内存后台任务作为可靠任务队列。
- 不要让 AI 静默覆盖人工草稿。
- 不要让标注模块修改 QC 状态。
- 不要重新实现 QC 资格判定。
- 不要新增“标注批次”概念。
- 不要默认增加 `annotator` 角色；当前 V1 使用现有单角色体系。
- 不要把 `generation_status` 继续放在 `annotation_tasks` 作为权威字段；generation 生命周期属于 `annotation_generation_jobs`。
- 不要把可变草稿当成导出历史事实；导出必须绑定不可变 revision。
- 不要让首页每次请求回扫全部 Episode 进行统计。
- 不要假设具体前端视觉样式已经确定。
- 不要假设尚未确认的开放问题已经有答案。

---

## 11. 当前实现状态

截至本 brief 整理时：

- 标注模块业务逻辑文档已经完成多轮讨论和收口。
- VLM 初始标注已从“人工逐条触发”修正为“后台低峰时段默认自动触发”。
- admin/qc_manager 的批量手动控制已纳入规则。
- reviewer 的批量补漏入口已纳入规则，但不是主流程。
- 持久化 VLM generation queue、worker、统计 rollup、导出 revision 快照等已确定为实施方向。
- 标注模块实际数据库 migration、后端 API、前端页面和 worker 代码尚未在本阶段实现。
- 本 brief 不是代码实现方案，而是用于继续讨论业务逻辑和前端工作流的上下文材料。

---

## 12. 请 GPT 最终回答的问题

请基于以上背景完成以下任务：

1. 审查当前标注业务逻辑，指出明确冲突、遗漏和潜在反人类流程。
2. 判断后台夜间自动 VLM 标注、admin/qc_manager 批量控制、reviewer 批量补漏这三种触发方式是否合理。
3. 设计 admin、qc_manager、reviewer、viewer 的完整前端工作流。
4. 设计标注首页、TaskType 工作区、reviewer 工作池、Episode 标注工作台、VLM 任务管理和导出页面的信息架构。
5. 为每个页面给出关键状态、按钮、权限、批量操作和错误反馈。
6. 重点说明 reviewer 如何做到“打开工作池即可审核”，而不是等待 VLM 或逐条启动自动标注。
7. 给出 VLM 队列优先级、失败重试、过期结果、暂停恢复和幂等处理建议。
8. 逐项回答第 8 节开放问题，并区分：
   - 必须作为业务规则冻结的内容。
   - 可以作为配置项的内容。
   - 可以延后到 V2 的内容。
9. 最后给出一份推荐的 V1 前端实施顺序，但不要直接编写代码。

回答时请明确标记：

- **Confirmed：** 已由本项目确认的事实。
- **Recommendation：** 你建议采用的方案。
- **Need Decision：** 仍需要项目负责人确认的业务问题。
- **Implementation Detail：** 可以留给后端/前端实现的技术细节。
- **Risk：** 可能导致数据错误、人工成本增加或用户误操作的风险。
