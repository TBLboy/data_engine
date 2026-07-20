# 数据标注模块 V1 — 业务逻辑固化稿

> 状态: 已确认。`annotation-sub-goals-v1.md` 对 Sub Goal、Segment 和任务结果的规则优先于本文件；其余最终收口以 `annotation-v1-final-decisions.md` 为准。
> 固化日期: 2026-07-18
> 补充决策: §4.4 revision 机制、§6.7 JSONB Schema 校验、§9 多人编辑锁、§10.5 结构化 AI 操作、§11.6 VLM 三阶段抽帧策略；最终收口见 `annotation-v1-final-decisions.md`
> 相关调研: `.project-log/标注工具调研.md`（2026-07-14）

---

## 一、模块定位

数据标注模块是平台 pipeline 的最后一块拼图，补齐后形成完整闭环：

```text
采集(TeleDex) → MinIO 扫描入库(v3) → 批次管理/任务分类 →
任务派发 → L3 自动评估 → 人工质检(L2+L4) → 批次驳回判定 →
数据标注 → 数据集导出
```

标注模块与质检模块**解耦**：
- 质检模块**不依赖**标注状态
- 标注模块**只消费**质检的最终结论（`Episode.final_dataset_status`）
- 标注不能反向改变质检状态

---

## 二、核心业务定义

### 2.1 按 TaskType 组织

标注按 `TaskType`（任务类型）聚合数据，**不引入"标注批次"概念**。

同一任务类型下，所有满足标注条件的 Episode 统一进入该任务类型的可用标注池：

```text
任务类型：切黄瓜

可用 Episode：320
├── 未标注：100
├── 待标注：80
└── 完成标注：140
```

Episode → TaskType 的关系链路：

```text
Episode.batch_id → Batch.task_type_id → TaskType
```

### 2.2 标注主线流程

```text
Episode 质检完成（final_dataset_status = 'QUALIFIED'）
    ↓
进入对应 TaskType 的可用标注池
    ↓
VLM 预标注 或 人工从零标注
    ↓
人工检查、修改
    ↓
确认完成
    ↓
进入可导出状态（训练集导出）
```

---

## 三、Episode 标注资格

### 3.1 判据字段

标注是否可进行，只读取一个字段：

```text
Episode.final_dataset_status = 'QUALIFIED'
AND Episode 位于 active_list_active_batch_indexed_episodes 统一作用域
```

注：项目模型中的字段名为 `final_dataset_status`，不是 `final_status`。该字段定义在 `backend/app/models/episode.py`，由 `batch_adjudication.py` 统一计算。

| 值 | 含义 | 是否可标注 |
|----|------|-----------|
| `QUALIFIED` | 通过批次裁定，可用于训练 | ✅ 可标注 |
| `UNQUALIFIED` | 未通过批次裁定 | ❌ 不可标注 |
| `PENDING` | 尚未完成裁定 | ❌ 不可标注 |

### 3.2 不复算质检逻辑

以下判断**全部由质检模块闭环**，标注模块不再重复解释：

- L2 视觉质量是否通过
- L3 自动指标是否达标
- L4 任务完成度是否合格
- 所属批次是否被驳回（`Batch.batch_decision = 'REJECTED'`）
- 是否存在数据缺失

这些复杂规则收敛为 `final_dataset_status` 的最终值，标注模块只消费结果。

### 3.3 标注资格变化

如果 Episode 已进入标注流程，之后 `final_dataset_status` 从 `QUALIFIED` 变为非 `QUALIFIED`（如批次重新裁定后被驳回）：

1. Episode 立即退出可用标注池
2. 未完成的标注任务（`work_status = 'pending'`）停止继续处理
3. 已有标注内容保留，不物理删除
4. 数据不得进入标注训练集导出
5. 如果重新变为 `QUALIFIED`，可恢复原有标注内容继续检查

该类 Episode 不计入"未标注、待标注、完成标注"三项统计，作为失效历史数据保留。

---

## 四、标注池的三个用户状态

三个状态为**计算字段**，不由数据库字段直接存储，而是从 `annotation_tasks` 和 `episode_annotations` 联合查询得出。

### 4.1 未标注

**定义**：

```text
Episode.final_dataset_status = 'QUALIFIED'
AND Episode 位于 active_list_active_batch_indexed_episodes 统一作用域
AND NOT EXISTS annotation_task（无任何 annotation_task 记录）
```

**表现**：
- 没有 VLM 生成结果
- 没有人工草稿
- 默认由后台夜间流水线自动创建 VLM 初始标注任务；人工从零标注仅作为显式例外或 VLM 失败后的补救路径

### 4.2 待标注

**定义**：

```text
Episode.final_dataset_status = 'QUALIFIED'
AND EXISTS annotation_task（有 annotation_task 记录）
AND annotation_task.work_status = 'pending'（未确认完成）
```

以下情况统一归入"待标注"，前端按该任务最新 `annotation_generation_jobs.status` 显示不同标签：

| generation job 状态 | 前端标签 |
|-------------------|---------|
| `queued` | 等待 VLM 生成 |
| `running` | VLM 正在生成 |
| `failed` | VLM 生成失败 |
| `succeeded` | 等待人工检查 |
| 无 generation job（initial_source=manual） | 人工标注中 |

### 4.3 完成标注

**定义**：

```text
Episode.final_dataset_status = 'QUALIFIED'
AND EXISTS annotation_task
AND annotation_task.work_status = 'completed'（已由人工确认提交）
```

**完成条件**：
1. `episode_annotations` 数据结构校验通过
2. 必填内容完整（`canonical_instruction_en` 不为空）
3. 已由人工检查并确认

完成后仍可由有权限人员重新编辑。

### 4.4 Revision 机制

采用"**草稿直接更新，完成后生成不可变快照**"的混合机制。

**`episode_annotations`**：保存当前正在编辑的草稿。待标注阶段保存时直接 UPDATE 同一条记录。

**`annotation_revisions`**：每次人工"确认完成"时，生成一条不可变历史快照（完整 JSONB payload）。

工作流程：

```text
第一次完成：
  编辑草稿 → 点击"确认完成" → 校验通过 → 生成 revision 1 → work_status = completed

重新编辑：
  work_status = completed → 点击"重新编辑" → work_status 回到 pending
  → 基于当前草稿继续修改 → 再次确认完成 → 生成 revision 2 → work_status = completed
```

系统始终只有一份"当前有效结果"（`episode_annotations` 的最新草稿内容）。旧 revision 是不可变历史记录，不会形成两套并行标注结果。

导出时记录 `(episode_id, revision_no, content_hash)`，确保后续训练数据可追溯到具体版本。

---

## 五、标注任务的生成方式

### 5.1 两种路径

| 路径 | 触发 | initial_source | generation job 状态 | 初始数据 |
|------|------|---------------|-------------------|---------|
| 自动标注 | 后台夜间调度默认触发；admin/qc_manager 可批量手动触发 | `vlm` | `queued → running → succeeded/failed` | 首次成功结果自动写入空白草稿 |
| 人工标注 | admin/qc_manager 创建并派发从零标注任务；reviewer 接手本人已派发任务 | `manual` 或保留 `vlm` | 无 initial job，或 initial job 已失败 | 全空字段 |

两种路径产生的结果写入**同一份 `episode_annotations` 表**，不存在"VLM 结果"和"人工结果"两套数据。

### 5.2 自动标注流程

```text
新合格 Episode 被后台夜间扫描发现
  ↓ 自动创建 annotation_task（initial_source=vlm）+ annotation_generation_job（status=queued）
进入待标注
  ↓ 后端异步执行 VLM 调用
VLM 首次成功结果写入空白 episode_annotations 草稿，并记录 annotation_ai_runs
  ↓ annotation_generation_job.status=succeeded
等待人工检查
  ↓ 人工打开、修改或直接确认
完成标注（work_status=completed）
```

VLM 生成失败时：
1. `max_attempts = 3`，即首次调用加最多两次重试
2. 仍然失败 → `annotation_generation_job.status = 'failed'`
3. 保留待标注状态
4. 管理员可将任务派发为从零标注，写入 `manual_from_scratch_reason=vlm_failed`；保留 `initial_source=vlm` 和既有 AI run，人工保存后 `human_modified=true`

### 5.3 人工标注流程

```text
未标注、VLM 失败或明确跳过 VLM
  ↓ admin/qc_manager 创建或更新 annotation_task，填写 manual_from_scratch_reason
  ↓ 派发给 reviewer；首次即人工创建时 initial_source=manual，VLM 失败转人工时保持 initial_source=vlm
进入待标注
  ↓ 人工从空白字段逐项填写
保存草稿 / 确认提交
  ↓
完成标注（work_status=completed）
```

### 5.4 三种真实来源

通过 `initial_source` + `human_modified` 字段区分：

| 情况 | initial_source | human_modified | 含义 |
|------|---------------|----------------|------|
| VLM 生成后人工直接确认 | `vlm` | `false` | 完全信任 VLM |
| VLM 生成后人工修改 | `vlm` | `true` | VLM 为基础，人工修正 |
| 人工从空白开始标注 | `manual` | `true` | 纯手工标注 |

---

## 六、V1 标注内容

### 6.1 Episode 级标注（`episode_annotations` 表）

| 字段 | 类型/格式 | 说明 | 必填 |
|------|----------|------|------|
| `canonical_instruction_zh` | Text | 标准中文指令，描述该 Episode 实际完成的任务 | V1 选填 |
| `canonical_instruction_en` | Text | 标准英文指令 | ✅ 必填 |
| `instruction_variants_en` | JSONB `string[]` | 0~5 条语义等价的英文表达变体 | 选填 |
| `episode_summary` | Text | 比标准指令更详细的过程描述 | 选填 |
| `objects` | JSONB | 结构化物体列表（name_en, name_zh, role, attributes） | 选填 |
| `execution_observation` | Text | 执行过程观察（不改变质检状态） | 选填 |
| `annotation_notes` | Text | 标注备注 | 选填 |

**示例**：

```json
{
  "canonical_instruction_zh": "拿起桌面上的红色杯子并放到托盘中。",
  "canonical_instruction_en": "Pick up the red cup from the table and place it on the tray.",
  "instruction_variants_en": [
    "Move the red cup from the table to the tray.",
    "Grasp the red cup and set it down on the tray.",
    "Transfer the red cup onto the tray."
  ],
  "objects": [
    {
      "name_en": "red cup",
      "name_zh": "红色杯子",
      "role": "primary_object",
      "attributes": { "color": "red" }
    },
    {
      "name_en": "tray",
      "name_zh": "托盘",
      "role": "target_container"
    }
  ]
}
```

**约束**：
- `instruction_variants_en` 变体不得增加视频中不存在或无法确认的信息
- 变体语义应与 `canonical_instruction_en` 等价

### 6.2 历史自由 Segment 说明（已由 Sub Goal Schema 替换）

本节的自由 `annotation_segments`、`label_en`、`action_verb` 和 VLM 自由 Segment 仅保留为历史设计记录。新 V1 实现必须采用 `annotation-sub-goals-v1.md` 定义的 `sub_goal_schemas`、`sub_goal_definitions` 与 `episode_sub_goal_instances`，不得以本节作为数据库或前端实现依据。

| 字段 | 类型 | 说明 |
|------|------|------|
| `sequence_no` | Integer | 在该 Episode 标注中的顺序号 |
| `start_step` | Integer | 起始 step（左闭） |
| `end_step_exclusive` | Integer | 结束 step（右开） |
| `start_timestamp` | Float | 起始时间戳（秒，辅助） |
| `end_timestamp` | Float | 结束时间戳（秒，辅助） |
| `label_zh` | String | 中文标签 |
| `label_en` | String | 英文标签 |
| `action_verb` | String | 动作动词（reach/grasp/lift/place/release 等） |
| `primary_object` | String | 主要操作物体 |
| `target_object` | String | 目标物体 |
| `target_location` | String | 目标位置 |
| `active_arm` | String | 活动手臂（left/right/both） |
| `active_hand` | String | 活动手（left/right/both） |
| `interaction_type` | String | 交互类型枚举 |
| `representative_step` | Integer | 代表帧 step |
| `segment_notes` | Text | 段备注 |

**示例**：

```text
Segment 1: 0~82, reach, 伸手接近红色杯子
Segment 2: 82~136, grasp, 抓住红色杯子
Segment 3: 136~258, move, 将杯子移动到托盘上方
Segment 4: 258~324, place, 将杯子放入托盘并松开
```

**`interaction_type` 枚举值**：

```
none / approach / contact / grasp / hold / move / place / release /
push / pull / rotate / pour / cut / other
```

### 6.3 历史自由 Segment 时间规则

1. 以 telemetry step 为时间基准，timestamp 为辅助
2. 使用左闭右开区间：`[start_step, end_step_exclusive)`
3. Segment 不允许互相重叠
4. Segment 按 `start_step` 排序
5. `start_step < end_step_exclusive`（强制性）
6. Segment 步数范围不得超出 Episode 总步数
7. **允许空白段**：不要求所有 Segment 全覆盖整个 Episode（等待/停顿段可留空或以 `idle` 显式标记）

### 6.4 关键帧

不单独建设复杂标注流程。默认从 Segment 边界自动产生：

```text
关键帧候选：start_step / (end_step_exclusive - 1) / representative_step
```

人工可调整 `representative_step`。

### 6.5 历史 execution_observation 说明

`execution_observation` 已被 `task_outcome` 替代；本节仅描述历史字段：

```
completed_normally / completed_with_retry / partially_completed / uncertain
```

新 `task_outcome` 也不直接改变 `Episode.final_dataset_status`。新 QC 规则会将数据质量资格与任务行为结果拆分，详见 `annotation-sub-goals-v1.md` §4。

### 6.6 task_description 的利用

平台在创建 TaskType 时已填写 `TaskType.description`（任务描述文本）。标注时：

- 描述作为 VLM prompt 的输入基准
- VLM 基于描述生成符合该任务语义的 `canonical_instruction_en`
- 变体生成也以描述为锚点
- 前端标注工作台顶部展示 TaskType.description，供标注员参考

### 6.7 JSONB 字段 Schema 校验

JSONB 字段必须固定 Schema，由 FastAPI/Pydantic 应用层完成校验，不在 PostgreSQL 中实现全部业务 JSON 校验。

每份标注记录 `annotation_schema_version = "1.0"`。

#### `instruction_variants_en`

固定格式：字符串数组。

```json
[
  "Move the red cup onto the tray.",
  "Grasp the red cup and place it on the tray."
]
```

校验规则：
- 必须是 `string[]`
- 0~5 条
- 每条不能为空
- 自动去除首尾空格
- 不允许与 `canonical_instruction_en` 完全重复
- 不允许数组内重复

#### `objects`

固定结构：对象数组，每个对象含固定字段。

```json
[
  {
    "name_en": "red cup",
    "name_zh": "红色杯子",
    "role": "primary_object",
    "attributes": { "color": "red" }
  }
]
```

| 字段 | 约束 |
|------|------|
| `name_en` | 必填，非空字符串 |
| `name_zh` | 必填，非空字符串 |
| `role` | 枚举：`primary_object` / `secondary_object` / `tool` / `source_container` / `target_container` / `target_location` / `environment_object` / `other` |
| `attributes` | 可选，开放 object（建议含 color / shape / material / size / state） |

**三段校验层级**：

| 层级 | 位置 | 内容 |
|------|------|------|
| 第一层 | Pydantic schema | 类型、必填字段、字符串长度、枚举值、数组数量、空值检查 |
| 第二层 | 业务校验函数 | 对象名称是否重复、变体是否与标准指令重复、Segment 引用的对象是否存在于 objects 列表 |
| 第三层 | 数据库 | JSONB 不为空、顶层必须为数组、schema_version 不为空 |

后续 Schema 升级时通过 `annotation_schema_version` 区分版本，避免 PostgreSQL 端复杂 JSON 校验阻塞迁移。

---

## 七、数据模型

### 7.1 annotation_tasks

表示 Episode 是否已进入标注工作流。

```text
表名: annotation_tasks

id                      String(64) PK
episode_id              String(64) UNIQUE FK → episodes.id, indexed
task_type_id            String(64) FK → task_types.id
work_status             String(32)  'pending' / 'completed' / 'invalidated'
assigned_to             String(64)  标注人员 ID，对应 users 表
assigned_by             String(64)  nullable，最近一次派发/改派操作者
assigned_at             DateTime    nullable，最近一次派发/改派时间
assignment_note         Text        nullable，派发备注
public_claim_enabled    Boolean     default=false，仅 VLM 初始成功且未分配任务可开启
public_claim_enabled_by String(64)  nullable，最近一次开放/关闭操作者
public_claim_enabled_at DateTime    nullable，最近一次开放/关闭时间
lock_owner              String(64)  当前编辑锁持有者 ID
lock_acquired_at        DateTime    nullable
lock_expires_at         DateTime    nullable
initial_source          String(16)  'vlm' / 'manual'
manual_from_scratch_reason String(32) nullable，见最终收口决策 §5.5
completed_by            String(64)  nullable
completed_at            DateTime    nullable
returned_by             String(64)  nullable，最近一次退回操作者
returned_at             DateTime    nullable，最近一次退回时间
return_reason           Text        nullable，最近一次退回原因
status_before_invalidation String(32) nullable
invalidated_at          DateTime    nullable
invalidation_reason     String(128) nullable
created_at              DateTime
updated_at              DateTime
```

**字段说明**：

| 字段 | 值域 | 语义 |
|------|------|------|
| `work_status` | `pending` | 标注进行中，尚未确认完成 |
| | `completed` | 人工确认完成，可进入导出 |
| | `invalidated` | Episode 最终状态变为不可用，标注停止参与正常流程 |
| `assigned_to` | user_id | 该标注任务主要由谁负责 |
| `assigned_by` / `assigned_at` | user_id / datetime | 最近一次由谁、何时派发或改派 |
| `public_claim_enabled` | boolean | 管理人员是否将该 VLM 已成功、未分配任务开放给 reviewer 公共领取 |
| `lock_owner` | user_id | 当前正在编辑的用户 |
| `completed_by` | user_id | 最终由谁确认完成 |

`assigned_to`、`lock_owner`、`updated_by`（在 episode_annotations）、`completed_by` 是四个独立概念，不合并；分配、退回和异常上报的完整历史以审计事件及 `annotation_task_escalations` 为准。

**三状态的查询计算**：

| 用户状态 | SQL 条件 |
|---------|---------|
| 未标注 | `NOT EXISTS (SELECT 1 FROM annotation_tasks WHERE episode_id = episodes.id)` |
| 待标注 | `EXISTS ... AND work_status = 'pending'` |
| 完成标注 | `EXISTS ... AND work_status = 'completed'` |

前置条件始终为 `episodes.final_dataset_status = 'QUALIFIED'` 且位于 `active_list_active_batch_indexed_episodes` 统一作用域。
（`work_status = 'invalidated'` 的 Episode 不计入上述三状态，作为失效历史数据保留）

### 7.2 episode_annotations

一个 Episode 只有一条当前编辑草稿（`UNIQUE episode_id`）。完成后生成 `annotation_revisions` 不可变快照。

```text
表名: episode_annotations

id                      String(64) PK
episode_id              String(64) UNIQUE FK → episodes.id, indexed
annotation_task_id      String(64) FK → annotation_tasks.id
annotation_schema_version  String(16)  '1.0'

canonical_instruction_zh    Text
canonical_instruction_en    Text        草稿允许为空；完成标注时必须非空
instruction_variants_en     JSONB
episode_summary             Text
objects                     JSONB
execution_observation       Text
annotation_notes            Text

initial_source          String(16)  'vlm' / 'manual'
human_modified          Boolean     false / true
current_revision_no     Integer     default=0（每次确认完成时递增）
row_version             Integer     default=1（乐观锁）

created_by              String(64)
updated_by              String(64)
created_at              DateTime
updated_at              DateTime
```

**乐观锁说明**：每次保存草稿时：

```sql
UPDATE episode_annotations
SET ..., row_version = row_version + 1
WHERE id = :id AND row_version = :client_row_version
```

受影响行数为 0 表示内容已被其他操作修改，前端提示"当前标注已发生变化，请刷新后重新确认"。

**注意**：`episode_annotations` 不再包含 `is_finalized` 字段。V1 中完成标注的唯一判据是 `annotation_tasks.work_status = 'completed'`。

### 7.3 历史 annotation_segments（不用于新 V1 migration）

新 V1 使用 `episode_sub_goal_instances`，字段、约束和 Schema 版本冻结规则以 `annotation-sub-goals-v1.md` 为准。本节旧表定义仅供历史草稿追溯。

```text
表名: annotation_segments

id                      String(64) PK
episode_annotation_id   String(64) FK → episode_annotations.id
sequence_no             Integer     在该 Episode 中的顺序号

start_step              Integer
end_step_exclusive      Integer
start_timestamp         Float
end_timestamp           Float

label_zh                String
label_en                String
action_verb             String
primary_object          String
target_object           String
target_location         String
active_arm              String
active_hand             String
interaction_type        String      枚举值见 §6.2
representative_step     Integer
segment_notes           Text
```

**约束**：
- `representative_step` 必须在 `[start_step, end_step_exclusive)` 范围内
- segment 按 `(episode_annotation_id, sequence_no)` 排序，不重叠

### 7.4 annotation_generation_jobs

VLM 生成、重生成和结构化检查的可靠生命周期由持久化队列表承担，字段与 worker 规则以 `annotation-v1-final-decisions.md` §7 及 `annotation-sub-goals-v1.md` §7 为准。`annotation_tasks` 不保存 generation 状态。

### 7.5 annotation_ai_runs

记录每次 VLM 自动生成尝试。

```text
表名: annotation_ai_runs

id                      String(64) PK
annotation_task_id      String(64) FK → annotation_tasks.id
attempt_no              Integer     第几次尝试（1/2/3）
model_name              String      模型名称（如 qwen3-vl-32b-thinking）
prompt_version          String      prompt 模板版本号
input_summary           Text        输入摘要（采样的帧数/时间点）
raw_response            Text        VLM 原始返回
parsed_response         JSONB       解析后的结构化结果
status                  String      'queued' / 'running' / 'succeeded' / 'failed'
error_message           Text        失败原因
duration_ms             Integer     耗时（毫秒）
created_at              DateTime
```

**用途**：
- 定位模型异常
- 分析 VLM 标注质量
- 统计失败率
- 后续更换模型时对比效果

### 7.6 annotation_revisions

每次人工"确认完成"时生成一条不可变历史快照。

```text
表名: annotation_revisions

id                      String(64) PK
episode_annotation_id   String(64) FK → episode_annotations.id
revision_no             Integer     每次确认完成递增
annotation_payload      JSONB       完整标注内容快照（含所有字段 + segments）
content_hash            String(64)  标注内容哈希（用于导出追溯）
source                  String(16)  'manual_confirm' / 'reedit_confirm'
completed_by            String(64)
completed_at            DateTime
```

**工作流程**：

```text
第一次完成：
  编辑当前草稿 → 点击"确认完成" → 校验通过
  → INSERT annotation_revisions (revision_no=1)
  → annotation_tasks.work_status = 'completed'
  → episode_annotations.current_revision_no = 1

重新编辑：
  completed → 点击"重新编辑" → work_status 回到 pending
  → 基于当前草稿继续修改 → 再次确认完成
  → INSERT annotation_revisions (revision_no=2)
  → work_status = 'completed'
  → current_revision_no = 2
```

**导出追溯**：每次训练集导出记录 `(episode_id, revision_no, content_hash)`，即使后续标注被重新编辑，也能确定训练数据使用的具体版本。

### 7.7 annotation_task_escalations

记录 reviewer 对本人 pending task 发起的正式异常上报；它不取代 `annotation_notes`，也不自动改变 task 的 `work_status`。

```text
表名: annotation_task_escalations

id                      String(64) PK
annotation_task_id      String(64) FK → annotation_tasks.id, indexed
category                String(32)  'data_problem' / 'task_type_problem' / 'vlm_problem' / 'blocked' / 'other'
description             Text
reported_by             String(64)
reported_at             DateTime
status                  String(32)  'open' / 'acknowledged' / 'resolved' / 'dismissed'
resolved_by             String(64)  nullable
resolved_at             DateTime    nullable
resolution_note         Text        nullable
```

- reviewer 只能为自己被分配的 pending task 创建 escalation。
- manager/admin 可确认、解决或驳回 escalation，所有状态变化写审计事件。
- `blocked` 类别在前端显示“等待管理员处理”；它是协作提示，不是新的 `work_status`。

### 7.8 与现有模型的关系

```
TaskType ───────────────┐
                         │ 1:N (via Batch.task_type_id)
Batch ──────────────────┤
  │ 1:N                  │
  │                      │
Episode ◄─────────────── annotation_tasks (1:1, UNIQUE episode_id)
  │                           │ 1:1
  │                           ▼
  │                      episode_annotations (UNIQUE episode_id)
  │                           │ 1:N           │ 1:N
  │                           ▼               ▼
  │                      annotation_segments  annotation_revisions （不可变快照）
  │
   └────────────────────── annotation_ai_runs (via annotation_task_id)
                                   │ 1:N
                                   ▼
                        annotation_task_escalations
```

---

## 八、角色与权限

### 8.1 V1 角色策略

现有角色体系为扁平化设计：

```typescript
type UserRole = 'admin' | 'qc_manager' | 'reviewer' | 'viewer'
```

V1 不新增 `annotator`，也不把现有单角色模型改造成角色集合。`reviewer` 承担本人标注工作；专职标注员的多角色支持留给未来独立权限模型迁移。

### 8.2 路由权限

新增两个路由：

| 路由 | 允许角色 | 说明 |
|------|---------|------|
| `/annotation` | `admin`, `qc_manager`, `reviewer`, `viewer` | 标注首页（TaskType 卡片） |
| `/annotation/:taskTypeId` | `admin`, `qc_manager`, `reviewer`, `viewer` | 具体任务的标注 Episode 列表 |
| `/annotation/:taskTypeId/edit/:episodeId` | `admin`, `qc_manager`, `reviewer` | 标注工作台 |

`viewer` 可查看标注结果但不能编辑，在工作台页面上通过 `v-if` 禁用编辑控件。

### 8.3 页面内权限

| 操作 | 权限要求 |
|------|---------|
| 查看标注结果 | 所有角色 |
| 启动 VLM 自动标注 | 后台调度默认执行；`reviewer`（本人工作池批量补漏）, `qc_manager`, `admin` 可手动批量触发 |
| 编辑标注内容 | `reviewer`（本人任务）, `qc_manager`, `admin` |
| 确认完成标注 | `reviewer`（本人任务）, `qc_manager`, `admin` |
| 退回已完成的标注 | `qc_manager`, `admin` |
| 分配标注人员 | `qc_manager`, `admin` |
| 开放公共领取池 / 强制改派 | `qc_manager`, `admin` |
| 请求管理员处理 | `reviewer`（本人 pending 任务）, `qc_manager`, `admin` |
| 导出带标注训练集 | `qc_manager`, `admin` |

### 8.4 标注员与质检员的关系

- V1 沿用单角色体系，reviewer 具有本人标注任务权限
- V1 不做强制双人审核：标注员自行检查后确认完成
- `qc_manager` 或 `admin` 可对完成标注进行抽查，发现问题时退回待标注状态

---

## 九、多人编辑安全机制

`assigned_to` 只能表示任务归属，不能防止多人同时编辑。需要两层保护。

### 9.1 编辑锁

`annotation_tasks` 上的排他编辑锁：

| 字段 | 说明 |
|------|------|
| `lock_owner` | 当前编辑锁持有者 user_id |
| `lock_acquired_at` | 获取时间 |
| `lock_expires_at` | 过期时间（5 分钟） |

用户进入编辑页面时：
- 尝试获取锁：`UPDATE ... SET lock_owner=:uid, lock_expires_at=now()+5min WHERE lock_owner IS NULL OR lock_expires_at < now()`
- 获取成功 → 可编辑
- 获取失败 → 该 Episode 正由其他用户编辑，页面只读

锁续期：页面打开期间每 30 秒发送心跳，刷新 `lock_expires_at`。

锁释放条件：
- 用户主动退出页面
- 提交完成
- 切换到下一条
- 长时间没有心跳（锁自然过期）
- 管理员强制释放（`qc_manager` / `admin` 权限）

### 9.2 乐观锁

`episode_annotations` 上的乐观锁——防止编辑锁持有者和锁续期之间的窗口被绕过：

每次保存草稿时用 `row_version` 做 CAS（Compare-And-Swap）：

```sql
UPDATE episode_annotations
SET ..., row_version = row_version + 1
WHERE id = :id AND row_version = :client_row_version
```

受影响行数为 0 → 内容已被其他操作修改 → 前端提示"当前标注已发生变化，请刷新后重新确认"。

### 9.3 四者区分

| 字段 | 表 | 含义 |
|------|-----|------|
| `assigned_to` | annotation_tasks | 这个任务主要由谁负责 |
| `lock_owner` | annotation_tasks | 当前是谁正在编辑 |
| `updated_by` | episode_annotations | 最近一次是谁保存 |
| `completed_by` | annotation_tasks | 最终由谁确认完成 |

四个概念不合并。

---

## 十、前端设计

### 10.1 导航

侧边栏新增一级菜单：

```text
数据标注     roles: ['admin', 'qc_manager', 'reviewer', 'viewer']
```

参考现有 `AppLayout.vue` 的 `menuItems` 模式。

### 10.2 标注首页

按 TaskType 展示任务卡片，类似于现有 dashboard 的批次卡片风格：

```text
┌─────────────────────────────┐
│ 任务名称：切黄瓜            │
│ 任务描述：将黄瓜切成片      │
│ 可用 Episode：320           │
│ 未标注：100  待标注：80     │
│ 完成标注：140  完成率：44%  │
│ [进入标注]                  │
└─────────────────────────────┘
```

- 只显示有可用 Episode 的 TaskType
- 卡片内进度条展示三状态占比
- 点击"进入标注"跳转到该任务的 Episode 列表

### 10.3 Episode 列表页

支持筛选：
- 三种状态（未标注/待标注/完成标注）
- 标注人员
- VLM 生成状态
- 更新时间

操作：
- 批量启动 VLM 标注
- 批量分配标注人员
- 对管理员开放的“VLM 已完成公共池”领取下一条 Episode（reviewer 快捷按钮）
- 点击单条进入标注工作台

### 10.4 标注工作台

```text
┌──────────────────────────────────────────────────┐
│ TaskType: 切黄瓜 | Episode: episode_000123       │
├────────────────────┬─────────────────────────────┤
│                    │ 标准中文指令：______________ │
│  左：三路同步视频  │ 标准英文指令：______________ │
│  (top/left_wrist/  │ 英文变体：                   │
│   right_wrist)     │   [+] 添加变体               │
│                    │                             │
│                    │ 物体列表：                   │
│  底部：动作时间轴  │   [+] 添加物体              │
│  + Sub Goal 对齐表 │                             │
│                    │ 固定 Sub Goal occurrence：   │
│                    │   Reach #1 [0~82] observed   │
│                    │   Grasp #1 [82~136] failed   │
│                    │   3. ...                     │
│                    │                             │
│                    │ [保存草稿] [确认完成]        │
└──────────────────────────────────────────────────┘
```

参考现有 `manual-qc.vue` 的布局模式（视频 + 编辑面板 + 时间轴联动）。

### 10.5 结构化 AI 操作（不复用聊天面板）

V1 **不复用现有自由对话式 AI 助手面板**。标注工作台的核心是结构化编辑，不是与 AI 聊天。直接复用聊天面板会出现：
- AI 建议和实际标注字段不同步
- 用户不知道 AI 是否已经修改数据
- 修改行为难以审计
- 对话内容无法稳定转换为结构化字段

V1 提供结构化 AI 操作按钮：

```text
[重新生成全部标注]     — VLM 根据视频重新生成全部字段
[重新生成标准指令]     — 只重新生成语言指令
[重新生成英文变体]     — 只生成 instruction_variants_en
[重新生成 Sub Goal 对齐] — 只生成固定 Definition 的 occurrence 候选
[检查当前标注]         — AI 检查当前标注，返回问题列表（不自动修改）
```

"检查当前标注"的输出示例：

```text
发现 3 个可能问题：

1. Grasp #1 的 representative step 不在其时间范围内。
2. 英文变体 1 与标准指令内容基本重复。
3. Move #1 的对象提示包含 "knife"，但对象列表中没有该物体。
```

用户点击具体建议后选择：接受建议 / 忽略建议 / 定位到相关字段。AI 检查不能自动覆盖现有内容。

---

## 十一、VLM 自动标注方案

### 11.1 现有基础设施

| 已有资源 | 状态 |
|---------|------|
| Ollama 服务（systemd 常驻） | 已部署，`192.168.20.147:11434` |
| Qwen3-VL-32B-Thinking（Q4_K_M, 24GB 显存） | 已注册，`KEEP_ALIVE=8760h` |
| `backend/app/ai_qc/llm_client.py` | `call_ollama()` + `call_ollama_stream()` |
| `backend/app/ai_qc/prompt_builder.py` | prompt 构建模式可参考 |
| 后端 AI 对话 SSE stream | 已工作 |

### 11.2 VLM 输入

1. TaskType.description（任务描述基准）
2. 三路 RGB 视频同步组合图（均匀采样 + telemetry 事件检测 + 局部边界细化，见 §11.6）
3. Episode 元数据（时长、总 step 数、帧率）
4. telemetry 摘要（动作变化幅度、手部开合变化、轨迹速度峰值）
5. 冻结 Sub Goal Schema 的固定 Definition、对象提示和候选动作边界

### 11.3 VLM 输出

统一 JSON 结构（写入 `annotation_ai_runs.parsed_response`）：

```json
{
  "canonical_instruction_zh": "...",
  "canonical_instruction_en": "...",
  "instruction_variants_en": ["...", "..."],
  "episode_summary": "...",
  "objects": [...],
  "task_outcome": "completed_with_retry",
  "sub_goal_occurrences": [
    {
      "sub_goal_definition_code": "GRASP_PRIMARY_OBJECT",
      "occurrence_no": 1,
      "status": "observed",
      "start_step": 0,
      "end_step_exclusive": 82,
      "representative_step": 42
    }
  ],
  "warnings": []
}
```

### 11.4 失败处理

```text
attempt 1: failed
  ↓ 等待 5s
attempt 2: failed
  ↓ 等待 10s
attempt 3: failed
  ↓ annotation_generation_jobs.status = 'failed'
保留待标注状态 + 人工从零标注
```

每次尝试写入 `annotation_ai_runs`。VLM 失败不影响 Episode 的 `final_dataset_status`。

### 11.5 新增后端模块

建议在 `backend/app/` 下新增 `annotation/` 模块：

```text
backend/app/annotation/
├── __init__.py
├── prompt_builder.py       # 标注 prompt 构建（参考 ai_qc/prompt_builder.py）
├── annotation_service.py   # 标注 CRUD 业务逻辑
├── vlm_service.py          # VLM 调用（复用 ai_qc/llm_client.py）
├── frame_sampler.py        # 视频抽帧（从 MinIO 读取 MP4）
└── schemas.py              # Pydantic schemas
```

### 11.6 视频抽帧策略（三阶段复合策略）

采用 **均匀采样 + telemetry 事件检测 + 局部边界细化** 的组合策略。不只用固定帧率（会漏快速动作），也不只依赖 telemetry（无法识别语义）。

#### 第一阶段：生成候选时间点

**A. 均匀时间采样**（自适应 Episode 时长）

| Episode 时长 | 均匀采样点 |
| ---------- | ----: |
| ≤15 秒      |   6 个 |
| 15～30 秒    |   8 个 |
| 30～60 秒    |  10 个 |
| 60～120 秒   |  12 个 |
| >120 秒     | 先分段处理 |

采样规则：
- 包含开始附近（开始后 0.3~0.5s）和结束附近（结束前 0.3~0.5s），避开可能的黑帧/静止帧
- 中间均匀分布

**B. telemetry 变化检测**

从以下信号计算综合运动分数 `motion_score`：

```text
motion_score =
    w1 × arm_velocity      （关节速度 qvel）
  + w2 × ee_linear_velocity （末端线性速度）
  + w3 × ee_angular_velocity（末端旋转速度）
  + w4 × hand_state_change  （灵巧手开合变化）
  + w5 × action_change      （遥操作指令变化）
  + w6 × effort_change      （力矩突增）
```

从 `motion_score` 序列中提取局部峰值作为候选动作边界点。相邻候选点之间最小间隔 0.5~1.0 秒。

**C. 候选点合并**

均匀采样点 + telemetry 变化点合并去重，总量控制：

```text
普通 Episode：最多 12~16 个时间点
较长 Episode：最多 20 个时间点
```

#### 第二阶段：三路视频同步取帧 + 拼接

每个候选时间点同时从 MinIO 抽取三路视频帧：

```text
cam_top + cam_left_wrist + cam_right_wrist
```

三帧拼接为一张组合图：

```text
┌──────────────┬──────────────┬──────────────┐
│ Top Camera   │ Left Wrist   │ Right Wrist  │
└──────────────┴──────────────┴──────────────┘
时间：6.42 秒  Step：193
```

16 个时间点 = 16 张组合图（而非 48 张独立图片）。

组合图统一缩放到 `1280×360` 或 `1440×480`，保留摄像头名称、timestamp、step index、候选点来源（uniform / telemetry_event）。

#### 第三阶段：向 VLM 提供 telemetry 摘要

不向 VLM 直接输入完整 NPZ 数组，而是输入结构化摘要：

```json
{
  "task_description": "切黄瓜",
  "duration_seconds": 24.6,
  "total_steps": 738,
  "candidate_events": [
    { "step": 92, "timestamp": 3.07, "reasons": ["left_hand_closing"] },
    { "step": 351, "timestamp": 11.70, "reasons": ["motion_direction_change"] }
  ],
  "idle_ranges": [
    { "start_step": 0, "end_step": 28 }
  ]
}
```

#### 第四阶段：Sub Goal occurrence 边界局部细化

VLM 首次输出的是粗边界（如"约在 8.5 秒发生 grasp"）。

系统在该边界附近执行局部密集抽帧：

```text
时间窗口：前后各 1 秒
频率：4~6 FPS
得到 8~12 个局部帧
```

结合手部开合变化、effort 峰值、末端速度变化、局部画面，将粗边界映射到更精确的 telemetry step。

#### V1 简化方案

若两阶段 VLM 调用成本过高，V1 可采用：

```text
VLM 负责对固定 Definition 做语义对齐（第一阶段粗 occurrence）
  →
telemetry 事件点自动吸附边界
  →
人工在时间轴上拖动最终确认
```

即：**VLM 负责语义、telemetry 提供候选边界、人工最终把关**。这比要求 VLM 仅凭 12 张图片精确输出 step 更可靠。

---

## 十二、统一训练数据集导出规则

### 12.1 单一导出范围

页面和 API 只保留一套“质检合格数据导出”。它导出统一 active scope 内全部 `final_dataset_status = 'QUALIFIED'` 的 Episode，不因标注未完成而排除数据。

```text
Episode 位于 active_list_active_batch_indexed_episodes
AND Episode.final_dataset_status = 'QUALIFIED'
```

该统一导出同时服务数据盘点、迁移、非语言训练和带标注训练；下游按每条记录的标注字段筛选所需子集，而不是要求平台生成相互排斥的两份数据集。

### 12.2 标注增强字段与训练筛选

每个导出 Episode 必须包含 `annotation_completed` 与 `annotation_status`。

- 未完成标注：保留基础数据；`annotation_completed=false`，标注 revision、Schema 和 payload 为 `null`，`training_default_included=false`。
- 完成标注：只有 `work_status=completed` 且存在 `current_revision_no` 对应 immutable revision 时，`annotation_completed=true`；导出该 revision payload、revision hash 与冻结 Schema 信息，绝不导出当前草稿。
- `failed` 是默认训练包含样本；`uncertain` 属于完成标注但默认 `training_default_included=false`，必须由下游显式选择。

导出格式：
- **Robot QC JSONL 数据包**：V1 训练主格式，包含 `manifest.json`、`episodes.jsonl` 和 `schemas.json`。
- **CSV**：人工审计格式，包含标注状态、revision、Schema、outcome 与序列化标注 payload。
- **LeRobot 兼容格式**：通过导出转换器适配。

LeRobot 导出映射：

| 内部字段 | LeRobot v3.x 字段 | 说明 |
|---------|-------------------|------|
| `canonical_instruction_en` | `language_persistent[task]` | Episode 级任务描述 |
| `instruction_variants_en` | 自定义元数据 | 保留为 language 变体池 |
| Sub Goal occurrence `(definition_code, occurrence_no, start_step, end_step_exclusive, status)` | `language_events` | 帧级固定子目标标签 |
| `objects` | 自定义元数据 | 保留物体信息 |
| `task_outcome` | `language_persistent[observation]` | 任务行为结果 |

采用转换层模式：

```text
内部标准模型 → 导出转换器 → LeRobot v3.x 格式
```

数据库不直接绑定 LeRobot 表结构。

每次导出为所有 Episode 创建 item 快照。已完成标注项记录 `(episode_id, annotation_task_id, annotation_revision_id, revision_no, content_hash, schema_id, schema_version, schema_content_hash)`；未完成项也记录当时标注状态与空 revision。这样既能追溯训练数据使用的具体标注版本，也能解释同一统一导出中哪些数据没有标注增强内容。

---

## 十三、V1 明确不做

| 内容 | 原因 |
|------|------|
| SAM2 分割掩码 | 高成本，V2 考虑 |
| 每帧检测框 / 接触状态 | 高成本 |
| 3D 点云标注 | 技术复杂度高 |
| 抓取点标注 | 非 V1 范围 |
| 多人重复标注（一致性校验） | V1 不做，不做双人审核 |
| 全量双人强制审核 | V1 只做 manager 抽查 |
| 在线训练效果评估闭环 | 超出标注模块范围 |
| 独立"标注批次"概念 | 按 TaskType 聚合，不额外引入概念 |
| 标注不能改变质检状态 | 硬约束 |
| AI 自由聊天式修改标注 | V1 只提供结构化 AI 操作按钮，不复用自由对话面板 |
| `is_finalized` 字段 | 已删除，以 `work_status = 'completed'` 为唯一完成判据 |

---

## 十四、实施路径建议

### Phase 1：标注基础数据模型 + 人工标注 UI

1. Migration：创建 `sub_goal_schemas` / `sub_goal_definitions` / `annotation_tasks` / `episode_annotations` / `episode_sub_goal_instances` / `annotation_revisions` / `annotation_ai_runs`
2. 后端 CRUD API：`/api/annotation/*`
3. 后端：编辑锁 + 乐观锁中间件
4. 后端：Pydantic + 业务层 JSONB Schema 三段校验
5. 前端：标注首页（TaskType 卡片）+ Episode 列表 + 标注工作台（纯人工编辑 + 结构化 AI 操作按钮）
6. 前端：编辑锁 UI（只读模式 / 锁过期提示 / 乐观锁冲突处理）
7. 权限：沿用现有单角色体系，reviewer 具备本人标注任务权限；VLM 初始自动标注由后台流水线默认触发
8. 导出：Robot QC JSON 格式（带标注字段 + revision 追溯）

### Phase 2：VLM 自动标注

1. `annotation/vlm_service.py` + `prompt_builder.py` + `frame_sampler.py`（三阶段复合抽帧策略）
2. 独立 `annotation-worker` 通过持久化 `annotation_generation_jobs` 队列异步执行
3. 标注工作台：VLM 结果展示 + 人工修改 + 结构化 AI 操作按钮（重新生成/检查）
4. `annotation_ai_runs` 记录与统计面板
5. LeRobot 格式导出转换器

### Phase 3：高级功能

1. task_description 变体自动生成
2. 标注质量抽查面板（manager 退回机制）
3. 标注进度统计与报表
4. 标注内容分析（常见错误类型、标注一致性等）

---

## 十五、最终规则总结

1. 标注按 `TaskType` 聚合，不按数据批次组织
2. 标注资格固定为 `Episode.final_dataset_status = 'QUALIFIED'` 加 `active_list_active_batch_indexed_episodes` 统一作用域
3. 所有可用 Episode 自动汇总到对应任务的可用标注池
4. 页面只展示"未标注 / 待标注 / 完成标注"三种计算状态
5. VLM 标注和人工标注共用同一个结果模型（`episode_annotations`）
6. 每个 Episode 只有一份当前有效标注草稿（`UNIQUE episode_id`），完成后生成 `annotation_revisions` 不可变快照
7. 人工修改 VLM 结果是更新同一份草稿，确认完成时创建 revision 历史
8. 标注允许保存适量冗余的结构化语义信息（`objects`、`instruction_variants_en` 等 JSONB），JSONB 字段固定 Schema（三段校验）
9. 关键帧主要由 Sub Goal occurrence 边界和 `representative_step` 产生，不单独标注
10. 标注不能反向改变 Episode 的 `final_dataset_status`
11. 内部标注数据存 PostgreSQL，MinIO 原始数据不回写
12. LeRobot 通过导出转换层适配，数据库不直接绑定外部格式
13. 训练数据集统一导出全部 active-scope `QUALIFIED` Episode；已完成标注为可选增强字段，默认训练子集由 `annotation_completed=true` 和 `task_outcome != uncertain` 确定，导出记录 revision 与 Schema 快照
14. V1 不建设标注批次、像素级标注和复杂双人审核流程
15. `is_finalized` 字段已删除，`work_status = 'completed'` 是完成标注的唯一判据
16. 草稿阶段直接 UPDATE，不使用 revision；完成时生成不可变快照
17. 多人编辑保护使用编辑锁（`lock_owner` + 心跳续期）+ 乐观锁（`row_version` CAS）
18. V1 不复用自由对话式 AI 面板，改用结构化 AI 操作按钮
19. VLM 抽帧采用均匀采样 + telemetry 事件检测 + 局部边界细化三阶段策略
