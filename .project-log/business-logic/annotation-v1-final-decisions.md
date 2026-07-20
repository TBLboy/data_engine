# 数据标注模块 V1 — 最终收口决策

> 状态：已确认。`annotation-sub-goals-v1.md` 对 Sub Goal、Segment、task outcome 和 Schema 版本的规则优先于本文件及 `annotation-v1.md` 的冲突表述。
> 日期：2026-07-18
> 目的：一次性冻结 V1 的资格范围、状态恢复、权限、VLM 队列、导出快照与统计边界，作为稳定实施版本的唯一补充决策。

---

## 一、总原则

1. 标注只消费 QC 最终结论，绝不重新实现或反向修改 QC 规则。
2. 标注所有可变内容只保留一个当前草稿；完成记录、AI 调用和导出清单均为不可变审计事实。
3. 任何耗时且可重试的 VLM 工作都必须持久化，不能依赖 FastAPI 进程内后台任务。
4. 新合格 Episode 默认由后台流水线自动进入 VLM 预标注，不要求 reviewer 逐条点击启动；人工触发只承担批量控制、补漏、重试和特殊数据处理。
5. TaskType 的版本化 Sub Goal Schema 是训练语义的唯一来源；VLM 仅做固定 Definition 的 occurrence 时间对齐，reviewer 不创建自由训练标签。
6. 复用已有 `active_list_active_batch_indexed_episodes`、`DatasetExportJob`、扫描 worker 租约和审计模式；不创造平行的作用域或临时事实源。
7. V1 以“人工最终确认的稳定训练标注”为目标，不为了自动化而允许 AI 静默覆盖人工草稿。

---

## 二、标注资格与 TaskType 归属

### 2.1 可用标注池的正式条件

Episode 进入标注池必须同时满足：

```text
Episode.final_dataset_status = 'QUALIFIED'
AND Episode 位于 active_list_active_batch_indexed_episodes 统一作用域
```

这意味着：

- `final_dataset_status` 是唯一的质检资格判据；标注模块不再判断 L2/L3/L4、批次驳回或 QC 原因。
- 统一 active scope 负责排除 inactive List、inactive Batch、inactive Episode、确认缺失或不可索引的来源数据。
- `is_exportable` 只作为现有系统的派生便利字段，不替代上述两个正式条件。

### 2.2 TaskType 的唯一来源

```text
Episode → Batch.task_type_id → TaskType
```

- `Batch.task_type_id` 是 Episode 的唯一标注分组依据。
- `ListRecord.final_task_type_id` 属于扫描控制面分类，不直接驱动已入库 Episode 的标注归属。
- 创建 `annotation_task` 时，复制当时的 `Batch.task_type_id` 到 `annotation_tasks.task_type_id`。
- 后续 Batch 改挂 TaskType 时：尚未开始的 Episode 随当前 Batch 归属进入新池；已有 annotation task、草稿、revision 和导出历史不自动迁移。管理人员必须使用“重新归类标注任务”操作显式迁移，操作必须审计并记录旧、新 TaskType。

### 2.3 TaskType 描述快照

- `TaskType.description` 是 VLM 的任务语义基准。
- 每次创建 VLM generation job 时都保存 `task_description_snapshot`。
- 修改 TaskType.description 不自动重写既有 Episode 标注，也不自动重跑 VLM。
- Episode 的 `canonical_instruction_*` 和 variants 始终是 Episode 自身事实，不是 TaskType 描述的缓存。

---

## 三、标注状态、失效与恢复

### 3.1 annotation_tasks 工作状态

```text
pending      已创建，尚未由人工确认完成
completed    当前草稿已通过最终校验且人工确认完成
invalidated  失去标注资格，停止正常工作流和导出
```

“未标注”是计算状态：可用 Episode 且不存在 `annotation_task`。

### 3.2 资格失效

当 Episode 从可用标注池退出时：

1. 将 `work_status` 改为 `invalidated`。
2. 保存 `status_before_invalidation`（`pending` 或 `completed`）、`invalidated_at`、`invalidation_reason`。
3. 请求取消该 Episode 的 queued/running generation job；worker 发布任何结果前必须重新校验资格。
4. 保留草稿、revision、AI run、导出历史，不物理删除。
5. 从未标注、待标注、完成标注统计和默认导出中排除。

### 3.3 资格恢复

Episode 再次满足 §2.1 时：

1. 服务原子恢复 `status_before_invalidation`。
2. 原来为 `pending` 的恢复到待标注。
3. 原来为 `completed` 的恢复到完成标注，可立即进入标注训练集导出。
4. 不自动重新生成 VLM，不创建新 revision。
5. 恢复、失效均写审计事件。

---

## 四、完成校验与 Schema

### 4.1 草稿与完成的区别

`episode_annotations` 是草稿，允许字段不完整；因此 `canonical_instruction_en` 在数据库层必须 nullable 或默认空字符串，不能设置为物理 `NOT NULL`。

确认完成时，服务端执行以下最终校验：

1. `canonical_instruction_en` 为非空、规范化后的英文文本。
2. annotation task 已冻结且可读取 published Sub Goal Schema。
3. 每个 `episode_sub_goal_instance` 引用该 Schema 中的固定 Definition；有时间范围的 observed/failed occurrence 满足边界、代表帧和同 Definition 非重叠规则。
4. `task_outcome` 取值为 `completed_normally`、`completed_with_retry`、`partially_completed`、`failed` 或 `uncertain`。
5. `task_outcome = failed` 时具有失败 instance 和失败原因；无法定位失败阶段时使用 `uncertain` 并说明原因。
6. Sub Goal Definition 的对象提示和 Episode 对象引用若都存在，必须一致；`instruction_variants_en`、`objects` 和 Sub Goal occurrence 均通过 `annotation_schema_version = '1.0'` 对应的 Pydantic 与业务校验。

### 4.2 可选字段的固定口径

| 字段 | V1 最终要求 |
|---|---|
| `canonical_instruction_zh` | 选填 |
| `instruction_variants_en` | 选填，`0..5` 条 |
| `episode_summary` | 选填 |
| `objects` | 选填；填写后必须符合固定对象 Schema |
| `task_outcome` | 完成时必填；取代 `execution_observation` |
| `annotation_notes` | 选填 |

`instruction_variants_en` 统一为 `0..5` 条，不再使用“2..5 条”的旧表述。它们不得为空、不得重复、不得与 canonical instruction 完全相同。

---

## 五、权限和协作

### 5.1 V1 角色策略

当前用户模型仅支持单个 `role`，不能声称同一账号同时是 `reviewer` 与独立 `annotator`。

V1 不改造为多角色集合。标注权限固定如下：

| 当前角色 | 标注权限 |
|---|---|
| `admin` | 全部操作 |
| `qc_manager` | 全部操作，含分配、退回、强制释放锁、导出 |
| `reviewer` | 查看、领取、编辑、保存、确认完成本人任务；不能分配、退回他人成果、导出 |
| `viewer` | 只读查看 |

不新增单独 `annotator` role；如未来存在专职标注人员，再以“用户多角色集合”作为一次独立权限模型迁移处理。

### 5.2 VLM 自动触发方式

自动标注分为三种触发源，优先级和职责不同：

| 触发源 | 默认用途 | 触发对象 | 是否需要 reviewer 逐条操作 |
|---|---|---|---|
| 后台夜间调度 | 主流程，处理新合格 Episode | 所有满足资格且尚未创建初始标注任务的数据 | 不需要 |
| `admin` / `qc_manager` 手动批量触发 | 任务级启动、补漏、失败重试、指定范围重跑 | 某个 TaskType 或筛选出的 Episode 集合 | 不需要 |
| `reviewer` 工作池操作 | 补漏或本人工作池中的新数据批量启动 | 自己可见且尚未生成初始结果的数据 | 只需一次批量操作，不逐条点击 |

后台调度规则：

1. 调度器按固定周期扫描标注资格视图，筛选 `QUALIFIED` 且位于 `active_list_active_batch_indexed_episodes`、没有初始 `annotation_generation_job` 的 Episode。
2. 默认运行窗口为北京时间 00:00 后的低峰时段；具体起止时间、每日最大数量和优先级作为部署配置，不改变业务规则。
3. 调度器按 TaskType 分组批量创建 `annotation_task` 和 `initial` generation job，写入同一 `request_group_id`。
4. 扫描必须幂等：同一 Episode 已有 `annotation_task` 或 active/succeeded 的初始 job 时，不得重复创建初始任务。
5. 夜间窗口外仍允许 worker 继续处理已经入队的任务；是否允许新任务继续入队由管理员配置的运行策略决定，不能依靠前端页面停留。
6. Episode 在扫描、排队或执行期间失去资格时，按 §3 的失效流程取消或阻止发布结果。

手动批量触发规则：

- `admin` / `qc_manager` 可在标注工作区选择 TaskType、批次、Episode 或筛选条件，执行“启动自动标注”“补漏扫描”“失败重试”“重新生成”。
- 手动操作只创建缺少对应 job 的任务；默认不重复覆盖已有成功结果。
- 对已有草稿或已完成任务的重新生成，必须使用明确的 `all/instruction/variants/segments` 操作，并遵守候选结果、差异预览和显式应用规则。
- `reviewer` 可在自己的工作池对新数据执行一次批量“启动自动标注”，但不能把它变成逐 Episode 的必经步骤。

### 5.3 派发与受控公共认领

- V1 采用后台预创建：合格 Episode 被发现后自动创建 `annotation_task` 和初始 generation job；人工从零标注是显式例外路径。
- 管理员批量派发是标准路径。`admin` / `qc_manager` 可将 pending task 按 TaskType、Batch 或筛选结果批量分配给 reviewer。
- 标准待派发池只包含：资格有效、`work_status = pending`、initial job 已 `succeeded`、无 `assigned_to` 的任务。前端标签为“VLM 已完成，待派发”。
- 无 VLM 结果的 pending task 必须进入单独的“从零标注待派发池”，不可与标准池无提示混合派发。派发前必须显示从零标注原因和人工成本提示，并要求二次确认。
- 管理员可将某个 TaskType 的标准待派发任务显式开放为“公共领取池”。reviewer 只能领取被开放、尚未分配且 VLM 初始结果已成功的任务；领取使用原子条件更新 `assigned_to IS NULL`，成功后立即归属本人。
- 公共领取是 task 级持久化开关，不是前端临时筛选。`annotation_tasks` 保存 `public_claim_enabled`、`public_claim_enabled_by`、`public_claim_enabled_at`；manager/admin 的批量开放或关闭操作必须审计。领取条件还必须包含 `public_claim_enabled = true`。
- 派发或成功领取时，必须在同一事务内设置 `assigned_to` 并关闭 `public_claim_enabled`。任务后续被取消分配、退回或恢复资格时，不得自动重新开放公共领取；只有 manager/admin 可以再次显式开放。completed 或 invalidated task 不得开启公共领取。
- V1 不设置 reviewer 的硬性任务上限，以避免因僵化配额阻塞生产；个人看板和管理端必须显示可配置的“积压预警阈值”，超过阈值时警告但不禁止领取或派发。
- reviewer 只能编辑自己被分配或成功领取的 pending task；manager/admin 可编辑任何 pending task。

### 5.4 分配、重新分配与编辑锁边界

`assigned_to` 是长期任务归属，`lock_owner` 是最多 5 分钟的临时编辑排他锁，二者绝不互相替代。

`annotation_tasks` 至少保存：

```text
assigned_to
assigned_by
assigned_at
assignment_note
```

所有分配、领取、重新分配和取消分配写入不可变审计事件，至少包含旧/新 reviewer、操作者、原因、时间和 task 当前 row_version。

- 对于 pending 且没有有效编辑锁的任务，`admin` / `qc_manager` 可以直接重新分配或取消分配；如果草稿已被人工修改，前端必须提示新接收人将接手已有草稿，而不是清空它。
- 对于存在有效编辑锁的任务，普通重新分配被禁止。强制改派必须在一个事务内执行“强制释放锁 + 重新分配”，要求填写原因并审计。
- 已完成任务不得直接改派。manager/admin 必须先执行退回，使其 `completed → pending`，再分配或改派。
- reviewer 不能自行将已领取任务转给其他 reviewer。

### 5.5 人工从零标注的来源和原因

`initial_source` 只记录首次进入草稿的来源，永不回写：

```text
manual    首次即由人工创建空白草稿
vlm       系统曾为该任务创建 initial VLM job
```

`annotation_tasks` 新增 nullable `manual_from_scratch_reason`，只在任务需要人工从零处理时填写：

```text
admin_skip_vlm          管理员明确跳过 VLM
vlm_failed              initial VLM 达到最大重试后失败
task_type_vlm_disabled  此 TaskType 禁用 VLM 初始标注
urgent_manual           紧急任务要求立即人工处理
unsupported_media       媒体或 telemetry 不满足 VLM 输入条件
```

- 管理员直接创建人工任务：`initial_source = manual`，且必须填写上述原因之一。
- initial VLM 已失败后转人工：保留 `initial_source = vlm`，`manual_from_scratch_reason = vlm_failed`，不得改写来源或删除 AI run。
- 从零标注原因一经设置保留为审计事实；若后续成功生成 VLM 候选，仍不改变该初始人工处理原因。

### 5.6 重新编辑、退回与异常上报

- reviewer 可以重新编辑本人完成的标注；此操作将 task 从 `completed` 改为 `pending`，保留 `assigned_to`，并在再次确认后创建新 revision。
- 只有 `qc_manager` / `admin` 可以退回任何 completed 标注，必须填写 `return_reason`。退回将 task 改为 `pending`，默认仍分配给原 reviewer；管理人员可在退回时显式选择改派或取消分配。
- 退回必须记录 `returned_by`、`returned_at`、`return_reason` 和被退回 revision_no；完整历史写入不可变审计事件，不能只保留最后一次原因。
- completed → pending、TaskType 显式迁移、强制释放锁、强制改派均写独立审计记录，包含操作者、原因、旧 revision_no（如有）和时间。
- reviewer 可对本人 pending task 发起“请求管理员处理”，不得只写自由备注。新增 `annotation_task_escalations`，字段至少包括：

```text
id
annotation_task_id
category                 data_problem / task_type_problem / vlm_problem / blocked / other
description
reported_by / reported_at
status                   open / acknowledged / resolved / dismissed
resolved_by / resolved_at
resolution_note
```

- open/acknowledged escalation 在 reviewer 工作池和管理端异常列表中可见；resolved/dismissed 保留历史。escalation 不自动改变 `work_status`，但 `blocked` 类别可在前端显示“等待管理员处理”。

### 5.7 编辑锁

- `annotation_tasks` 保存 `lock_owner`、`lock_acquired_at`、`lock_expires_at`。
- 租约为 5 分钟，编辑页每 30 秒心跳续期。
- 锁持有者可保存；非持有者只读。
- 保存时同时使用 `episode_annotations.row_version` CAS 乐观锁。
- manager/admin 可强制释放锁，必须记录原因。

---

## 六、草稿、Revision 与重新生成

### 6.1 Revision 规则

- 草稿保存：直接 UPDATE `episode_annotations`，并递增 `row_version`。
- 确认完成：事务内校验草稿、创建 `annotation_revisions` 完整 JSONB 快照、计算 `content_hash`、更新 `current_revision_no`、将 task 改为 completed。
- `annotation_revisions` 一经创建不可修改、不可删除。
- 导出只引用 revision 快照，绝不读取未来可能变化的草稿。

### 6.2 VLM 重生成规则

- 所有 VLM 结果先进入候选结果（`annotation_ai_runs.parsed_response`），不能静默覆盖草稿。
- 用户必须点击“应用候选结果”才可改变草稿。
- “重新生成全部”覆盖范围最大；如果草稿存在人工修改或 task 已完成，必须显示差异预览并二次确认。
- “重新生成标准指令 / 变体 / Sub Goal occurrence”只能修改其对应字段，不得覆盖其他字段。
- `initial_source` 记录首次创建来源，永不回写；`human_modified` 一旦人工保存任何内容即为 true。
- 每次重新生成均创建新的 generation job 与 AI run；历史候选结果保留。

### 6.3 结构化 AI 检查

- `check` 只能产生问题、建议、定位信息，绝不直接修改草稿。
- 检查结果绑定 `requested_draft_version`；草稿版本变化后结果显示为过期。
- 用户可以逐项应用建议、忽略建议或定位到字段；应用动作走普通草稿保存与审计。

---

## 七、持久化 VLM 队列

### 7.1 正式对象

新增 `annotation_generation_jobs`，字段至少包括：

```text
id
annotation_task_id
request_group_id
job_type                 initial / all / instruction / variants / sub_goals / check
status                   queued / running / succeeded / failed / cancelled / superseded
requested_draft_version
task_description_snapshot
sub_goal_schema_id / version / content_hash
priority
attempt_count
max_attempts
lease_owner
lease_expires_at
heartbeat_at
next_retry_at
requested_by
cancel_requested_at
created_at / started_at / finished_at
```

### 7.2 worker 规则

1. 独立 `annotation-worker` 进程以 lease + heartbeat 领取 job，模式对齐 scan-worker。
2. 当前 Qwen3-VL-32B 使用单张 24GB GPU；全局 VLM 并发固定为 1。夜间批量任务也必须经过同一队列，不能绕过 worker 直接调用模型。
3. 同一 annotation task 同时最多一个 active mutating job：`initial/all/instruction/variants/sub_goals`。
4. `check` 是只读 job，可并行执行，但必须绑定草稿版本。
5. 每次失败最多重试 3 次，按退避时间进入 `next_retry_at`。
6. job 开始、发布候选结果、重试和失败前均重新检查 Episode 资格与取消请求。
7. 初始自动标注可以在空白草稿上自动应用首次成功结果；除此以外，所有生成结果都要人工显式应用。worker 必须校验 job 与 task 冻结的 Sub Goal Schema 一致，不一致时 supersede job。

### 7.3 三阶段取帧的正式版本

复合抽帧策略是正式规则：

```text
均匀时间采样
  + telemetry motion_score 事件峰值
  + 三路同步组合图
  + VLM 固定 Sub Goal occurrence 粗对齐
  + telemetry 吸附边界
  + 人工时间轴最终确认
```

局部密集抽帧仅用于 VLM 或系统需要细化的候选边界，不能阻塞人工编辑。抽帧阈值、权重、图片尺寸、最大候选数均作为 `frame_sampler_version` 对应的配置，不属于业务状态。

---

## 八、统一训练数据集、标注覆盖统计与导出快照

### 8.1 标注统计

标注首页必须使用持久化投影，不在请求时回扫全部 Episode。

新增：

```text
task_annotation_rollups
annotation_recompute_jobs
```

`task_annotation_rollups` 以 `task_type_id` 唯一，保存：

```text
eligible_episode_count
unannotated_count
pending_count
completed_count
invalidated_count
vlm_queued_count
vlm_running_count
vlm_failed_count
refreshed_at
calculation_version
```

触发 dirty/recompute：Episode 资格变化、annotation task 创建/状态变化/TaskType 显式迁移、generation job 状态变化。模式对齐现有 batch/task asset rollup，不从前端临时统计。

### 8.2 统一训练数据集视图与标注覆盖

训练数据集管理页只有一套“质检合格数据导出”能力，不拆分普通导出与带标注导出两个产品入口。统一数据集范围固定为：

```text
Episode 位于 active_list_active_batch_indexed_episodes
AND Episode.final_dataset_status = 'QUALIFIED'
```

该范围内每个 Episode 都进入页面表格和统一导出，无论是否已完成标注。标注不是第二道导出门禁，而是 Episode 的增强信息和下游训练筛选依据。

页面必须同时展示：

```text
质检合格 / 完成标注
```

- 质检合格数：上述统一范围内的全部 Episode 数。
- 完成标注数：上述 Episode 中，`annotation_tasks.work_status = 'completed'` 且存在 `annotation_revisions.revision_no = annotation_tasks.current_revision_no` 的数量。
- 标注覆盖率：`完成标注数 / 质检合格数`；分母为 0 时返回 `null`。
- Episode 表格至少展示“是否完成标注”；运营视图可进一步展示未创建、待标注、标注中、已完成、失效或 revision 缺失等原因，后端不得将这些状态折叠为持久化布尔事实。

### 8.3 统一导出内容与训练使用规则

统一导出包含全部质检合格 Episode 的基础 QC、Episode、资产定位和质量字段。每条记录必须带：

```text
annotation_completed
annotation_status
annotation_revision             # 已完成时为冻结 revision 信息，否则 null
annotation_schema               # 已完成时为冻结 Schema 信息，否则 null
annotation                      # 已完成时为 immutable revision payload，否则 null
training_default_included
```

`annotation_completed = true` 的唯一判据：

```text
annotation_tasks.work_status = 'completed'
AND 存在 annotation_revisions(revision_no = current_revision_no)
```

未完成标注的 Episode 必须仍导出基础数据，但其 `annotation_revision`、`annotation_schema` 和 `annotation` 为 `null`，`training_default_included = false`。导出不得读取可变 `episode_annotations` 草稿作为训练事实。

已完成标注的 Episode 默认 `training_default_included = true`，包括 `completed_normally`、`completed_with_retry`、`partially_completed` 与 `failed`。`failed` 是正式训练样本，不能因行为失败被质量导出逻辑丢弃。`task_outcome = uncertain` 也属于完成标注，但默认 `training_default_included = false`；下游研究性训练只能显式选择纳入，并在 manifest 中记录该选择。

CSV 用于人工审计，必须包含标注完成、revision、Schema、outcome 和序列化 annotation payload 列。训练主产物采用可流式处理的 JSONL 数据包：

```text
dataset-export-{job-id}.zip
  manifest.json
  episodes.jsonl
  schemas.json
```

`manifest.json` 必须声明统一 QC 门禁、请求筛选条件、实际范围、计数、操作者、导出时间、产物 hash，以及 `task_outcome` 默认筛选策略。`schemas.json` 保存本次导出实际引用的完整冻结 Schema 内容；数据库内部模型与后续 LeRobot 转换器保持解耦。

### 8.4 导出快照与审计

扩展现有 `dataset_export_jobs` 并新增 `dataset_export_items`。`filters_json` 只保存请求和解析后的筛选条件，不作为海量 Episode 逐条快照的唯一载体。

```text
dataset_export_jobs
  export_type = qualified_dataset
  export_format
  requested_filters_json
  resolved_filters_json
  candidate_count
  included_count
  artifact_object_key / artifact_sha256 / artifact_size_bytes
  manifest_json
  created_by / created_at / finished_at

dataset_export_items
  export_job_id
  episode_id
  inclusion_status
  episode_snapshot_json
  annotation_task_id                nullable
  annotation_revision_id            nullable
  revision_no                       nullable
  content_hash                      nullable
  schema_id                         nullable
  schema_version                    nullable
  schema_content_hash               nullable
  created_at
```

创建 export job 时，在同一数据库事务内确定每个 Episode 是否已完成标注；对已完成项写入其当前 immutable revision 和 Schema 快照引用，对未完成项写入空标注快照及当时状态。之后标注被重新编辑或生成新 revision，不影响历史 export job 的内容和审计事实。worker 只能从 `dataset_export_items` 和 job manifest 构建文件，不得重新读取当前草稿或重新解析当前标注状态。

---

## 九、实施数据对象总表

| 对象 | 类型 | 作用 |
|---|---|---|
| `annotation_tasks` | 主流程表 | 标注归属、work_status、资格失效信息、锁、完成者 |
| `episode_annotations` | 当前草稿 | 唯一可变的当前内容，含 Schema/row_version |
| `episode_sub_goal_instances` | 草稿子表 | 当前草稿的固定 Sub Goal occurrence |
| `sub_goal_schemas` / `sub_goal_definitions` | TaskType 语义资产 | 版本化固定训练标签空间 |
| `episode_sub_goal_instances` | 草稿子表 | 固定 Definition 的状态、occurrence、时间对齐和失败信息 |
| `annotation_revisions` | 不可变审计表 | 每次完成时完整快照 |
| `annotation_generation_jobs` | 持久化队列表 | VLM 生成、重生成、检查任务 |
| `annotation_ai_runs` | 模型审计表 | 每次实际 VLM 调用及候选结果 |
| `annotation_task_escalations` | 异常协作表 | reviewer 上报、管理人员处理和关闭任务阻塞问题 |
| `task_annotation_rollups` | 读模型 | TaskType 首页统计 |
| `annotation_recompute_jobs` | 持久化 dirty 队列 | 标注统计重算 |
| `dataset_export_items` | 导出快照表 | 每个统一导出 Episode 的资产快照及可选 annotation revision/Schema 引用 |

---

## 十、替换旧表述

以下旧表述以本文件为准：

| 旧表述 | 正式替换 |
|---|---|
| 标注资格只看 `final_dataset_status` | 使用 `final_dataset_status = QUALIFIED` 加统一 active scope |
| `annotation_tasks.generation_status` | generation 生命周期迁移到 `annotation_generation_jobs` |
| VLM 可用 FastAPI background task | V1 正式使用独立持久化 `annotation-worker` |
| 新增 `annotator` 且可与 reviewer 并存 | V1 不新增 annotator；沿用现有单角色，reviewer 具备标注权限 |
| 未明确 invalidated 恢复 | 保存并原子恢复 `status_before_invalidation` |
| 变体 2..5 条 | 统一为 0..5 条 |
| 草稿 canonical 英文 NOT NULL | 草稿允许为空，完成时服务端强校验 |
| 导出读取当前草稿 | 导出冻结 `annotation_revisions` 快照 |
| 普通导出与带标注训练集导出必须拆成两个入口 | 只保留一套“质检合格数据导出”；标注以每条 Episode 的可选增强字段随同导出 |
| 首页实时统计 | 使用 task_annotation_rollups 持久化读模型 |
| reviewer 逐条点击自动标注 | 后台夜间扫描默认自动创建初始任务；人工入口只做批量补漏或重跑 |
| 任意未分配 pending task 都可被 reviewer 领取 | 只有管理人员显式开放、VLM 初始成功的标准任务可进入公共领取池 |
| VLM 失败后改写 initial_source 为 manual | 保留 initial_source=vlm，并以 manual_from_scratch_reason=vlm_failed 记录人工接管 |
| returned/editing/exported 作为 work_status | 分别由退回审计、有效编辑锁和 dataset_export_items 推导，work_status 仍仅为 pending/completed/invalidated |
| 自由 annotation_segments 是训练主语义 | TaskType 版本化 Sub Goal Schema + Episode occurrence 是唯一训练主语义 |
| execution_observation | task_outcome；新增 failed 并关联失败/最后成功 occurrence |
