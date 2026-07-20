# 数据标注模块 V1 — Sub Goal Schema 体系

> 状态：已确认。本文件定义 V1 的主训练语义模型，优先级高于 `annotation-v1.md` 中关于自由 `annotation_segments`、`execution_observation` 与自由动作标签的历史表述。
> 日期：2026-07-18
> 关联：`annotation-v1-final-decisions.md`、`annotation-v1.md`

---

## 一、目标与原则

V1 的标注语义固定为：

```text
TaskType 定义语义
  → Sub Goal Schema 定义固定标签空间
  → VLM 对固定标签做状态判定和时间对齐
  → reviewer 修正状态、边界和任务结果
  → revision 冻结 Schema 与 Episode 实例
```

不采用“VLM 或 reviewer 对每个 Episode 自由创建 Segment 名称”的模式。

原则：

1. 同一 TaskType 的训练标签必须稳定、可统计、可比较。
2. Sub Goal 的语义属于 Task 层资产；Episode 层只记录固定定义的实际执行情况。
3. VLM 不能创造 Schema 外标签、改变 Task 语义或修改已发布 Schema。
4. reviewer 不编辑 Sub Goal 名称，只编辑状态、出现次数、时间边界、代表帧、失败信息和整体任务结果。
5. 空白时间区间允许存在，不要求 Sub Goal 覆盖完整 Episode。

---

## 二、层级与正式数据对象

```text
TaskType
  └── sub_goal_schemas
        └── sub_goal_definitions

annotation_task
  ├── frozen_sub_goal_schema_id / version / content_hash
  └── episode_annotations
        └── episode_sub_goal_instances
```

### 2.1 `sub_goal_schemas`

一个 TaskType 可以拥有多个 Schema 版本。

最小字段：

```text
id
task_type_id
version_no                    同一 TaskType 下单调递增、唯一
status                        draft / published / retired
schema_payload                完整 Definition 语义快照
content_hash
created_by / created_at
published_by / published_at
retired_by / retired_at
retirement_reason
```

### 2.2 `sub_goal_definitions`

Definition 是 Schema 内不可自由修改的固定训练标签。

最小字段：

```text
id
sub_goal_schema_id
sequence_no
code                          稳定机器标识，如 GRASP_PRIMARY_OBJECT
name_en
name_zh
description
action_verb
is_required
is_conditional
max_occurrences               nullable；空表示不设固定上限
object_role_hints             JSONB
```

约束：

- `(sub_goal_schema_id, code)` 和 `(sub_goal_schema_id, sequence_no)` 唯一。
- `code` 是训练和 API 的稳定标识，显示名称不是主键。
- Definition 的 `name_*`、语义、排序和约束由 Schema 控制，Episode 不得覆盖。

### 2.3 `annotation_tasks` 的 Schema 冻结字段

创建标注任务时必须保存：

```text
sub_goal_schema_id
sub_goal_schema_version
sub_goal_schema_content_hash
```

任务、草稿和 revision 一律读取该冻结 Schema；后续 TaskType 发布新 Schema 不会自动影响历史任务。

### 2.4 `episode_sub_goal_instances`

一个固定 Definition 在同一 Episode 中可以出现零次或多次。

```text
id
episode_annotation_id
sub_goal_definition_id
occurrence_no
status
start_step                    nullable
end_step_exclusive            nullable
representative_step           nullable
failure_reason                nullable
notes                         nullable
source                        vlm_initial / human / vlm_candidate
created_at / updated_at
```

约束：

- `(episode_annotation_id, sub_goal_definition_id, occurrence_no)` 唯一。
- `occurrence_no` 从 1 开始连续编号。
- 同一 Definition 的 occurrence 不得时间重叠。
- 不同 Definition 可以时间重叠；V1 不假设所有动作严格串行，支持双臂或并行行为。
- `max_occurrences` 不为空时，实例数量不得超过 Definition 限制。
- 任何实例都必须引用任务冻结 Schema 中的 Definition。

示例：

```text
GRASP_PRIMARY_OBJECT #1: failed,   [82, 126)
GRASP_PRIMARY_OBJECT #2: observed, [158, 201)
```

这保留了“失败后重试成功”的过程信息，同时不创建新的自由标签。

---

## 三、Schema 生命周期与默认版本

Schema 只允许以下生命周期：

| 状态 | 含义 | 是否可编辑 | 是否可给新任务使用 |
|---|---|---|---|
| `draft` | 编辑中的候选 Schema | 可编辑 | 否 |
| `published` | 已发布的不可变 Schema | 不可编辑 | 是 |
| `retired` | 不再给新任务使用的历史 Schema | 不可编辑 | 否 |

冻结规则：

1. 已发布 Schema 不得原地修改或删除 Definition；任何语义变化必须从已发布版本复制创建新的 draft。
2. 每个 TaskType 同一时刻只能有一个 `default_published_sub_goal_schema_id`。
3. 发布新版本时，管理员显式切换默认版本；新创建 annotation task 使用新版本，已有任务保持原 Schema。
4. retired Schema 的历史 task、草稿、revision 和导出必须继续可读、可审计、可导出。
5. 已被 annotation task 引用的 Schema 或 Definition 禁止物理删除。

### 3.1 缺少 Published Schema 的异常流程

`QUALIFIED` 且位于 active scope 的 Episode 仍是“数据资格有效”，但没有 Published Schema 时不具备“Sub Goal 标注就绪”条件。

```text
数据资格有效
AND TaskType 没有 default published Schema
→ 不创建 annotation_task
→ 不创建 initial VLM job
→ 创建/刷新 annotation configuration exception:
  missing_published_sub_goal_schema
→ 在管理端异常池展示
```

V1 不允许没有 Published Schema 的 TaskType 走自由 Segment 或从零自由标签标注。

管理员发布默认 Schema 后，可立即执行“补漏扫描”创建任务；夜间扫描作为兜底，不必等待下一日。

---

## 四、任务结果、失败样本与 QC 资格

### 4.1 `task_outcome` 是独立语义

`task_outcome` 表示机器人任务行为结果，不是数据质量判据。它取代历史 `execution_observation` 作为唯一权威的整体任务结果字段：

```text
completed_normally
completed_with_retry
partially_completed
failed
uncertain
```

`episode_annotations` 新增：

```text
task_outcome
failure_sub_goal_instance_id       nullable
last_successful_sub_goal_instance_id nullable
failure_reason                     nullable
```

规则：

- `failed` 时必须填写 `failure_sub_goal_instance_id` 和 `failure_reason`，除非没有可定位的失败阶段；这种情况使用 `uncertain` 并在 notes 解释。
- `completed_with_retry` 可指向最后成功 instance；失败尝试由对应 failed occurrence 保留。
- `failure_sub_goal_instance_id` 和 `last_successful_sub_goal_instance_id` 必须属于本 Episode 草稿和冻结 Schema。
- `execution_observation` 废弃，不再新写。历史值按可逆映射读取：`completed_normally`、`completed_with_retry`、`partially_completed`、`uncertain`；历史字段没有 `failed` 映射。

### 4.2 失败 Episode 是正式标注与训练样本

从 V1 新规则开始，以下概念必须拆开：

```text
final_dataset_status
  = 数据介质、可访问性、视觉/telemetry 完整性和质量是否合格

task_outcome
  = 机器人任务行为是否成功、重试、部分完成、失败或不确定
```

因此，数据质量合格但机器人动作失败的 Episode 必须能够是：

```text
final_dataset_status = QUALIFIED
annotation_task.work_status = completed
```

它会作为统一质检合格数据导出中的已完成标注项出现；导出 manifest 必须携带 `task_outcome`，并支持下游按 outcome 筛选。默认训练子集包含所有已完成、数据质量合格的 outcome，包含 `failed`，但默认排除 `uncertain`，以保留失败恢复、失败识别和行为分析训练样本，同时避免不确定监督信号默认进入训练。

### 4.3 当前 QC 模型的迁移边界

当前代码中的 `manual_qc_status = MANUAL_FAIL` 会被 `batch_adjudication.py` 映射为 `final_dataset_status = UNQUALIFIED`，该字段目前混合表达“数据质量失败”和“任务行为失败”。

新规则仅对实现新的 QC 判据后产生或经过复核的数据生效：

- QC 表单和判定服务必须将“数据质量/介质合格性”与“任务行为结果”分开记录。
- 新的 `MANUAL_FAIL` 或等价质量失败只能表示数据质量不合格；任务未完成必须写入 `task_outcome`，不得单独导致 `UNQUALIFIED`。
- 历史 `UNQUALIFIED` Episode 不自动迁移、不自动创建标注任务、不自动进入导出，因为无法可靠识别其失败原因。
- 管理人员可通过明确的“质量复核”重新判定历史数据；只有复核后 `final_dataset_status = QUALIFIED` 的历史失败 Episode 才进入标注主流程。

---

## 五、Sub Goal Instance 状态

| 状态 | 含义 | 时间范围 |
|---|---|---|
| `observed` | 明确发生且完成该 Sub Goal | 必填 |
| `failed` | 明确开始尝试，但该 occurrence 未成功完成 | 必填；无法定位时改用 `uncertain` |
| `skipped` | 明确应该执行但被跳过 | 禁止填写 |
| `not_observed` | 可观察证据充分，但未发现该动作 | 禁止填写 |
| `not_applicable` | 该 Episode 条件下不适用的条件性 Definition | 禁止填写 |
| `uncertain` | 证据不足，无法确定是否发生 | 默认禁止；可选候选范围仅用于辅助展示，不作为训练边界 |

所有有时间范围的 instance 必须满足：

```text
0 <= start_step < end_step_exclusive <= episode.frame_count
representative_step ∈ [start_step, end_step_exclusive)
```

### 5.1 空白区间

Sub Goal Instance 不要求覆盖完整 Episode。等待、停顿、过渡、无关动作和起止静止区间都是允许的空白。

前端显示空白区间；仅当单段空白超过该 TaskType 配置的提醒阈值时提示 reviewer 检查，不阻止保存或完成。

---

## 六、VLM 与 reviewer 职责

### VLM

输入必须包含冻结 Schema 的 Definition 列表、稳定 code、描述、排序和对象提示。

VLM 只可：

1. 为每个固定 Definition 生成零到多个 occurrence。
2. 判定 instance 状态。
3. 对 observed/failed instance 给出时间范围和 representative step。
4. 提议 `task_outcome`、失败 instance、失败原因、instruction variants 和 summary。
5. 生成检查建议与置信度/警告。

VLM 不可创建 Schema 外 code、改名 Definition、改写 Schema、将空白区间伪造为 Sub Goal。

### Reviewer

reviewer 主要完成：

1. 修正 fixed Definition 的 occurrence 状态、次数、时间边界和代表帧。
2. 修正对象信息、`task_outcome`、失败阶段和失败原因。
3. 检查大面积空白提示。
4. 确认完成 revision。

reviewer 不创建自由 Segment 标签或改写 Sub Goal 名称。

---

## 七、Revision、VLM 和导出

### Revision

确认完成的 `annotation_revisions.annotation_payload` 必须包含：

```text
sub_goal_schema_id
sub_goal_schema_version
sub_goal_schema_content_hash
task_outcome
failure_sub_goal_instance_id
last_successful_sub_goal_instance_id
failure_reason
```

这保证每次导出可重建当时的固定标签空间和 episode 对齐结果。

### VLM job

`annotation_generation_jobs` 除已有 `task_description_snapshot` 外，必须保存：

```text
sub_goal_schema_id
sub_goal_schema_version
sub_goal_schema_content_hash
```

worker 在执行和发布结果前校验 job 的 Schema 与 annotation task 冻结值一致；不一致则将 job 标为 `superseded`，不发布结果。

### 导出

带标注导出除现有 revision 快照外，必须导出：

```text
task_outcome
failure_reason
sub_goal_schema_version
sub_goal_schema_content_hash
sub_goal_definition_code
```

导出器不读取当前 TaskType 的最新 Schema，只读取被冻结在 revision 中的 Schema 版本。

---

## 八、替换旧模型的规则

| 历史模型/表述 | V1 正式替换 |
|---|---|
| 自由 `annotation_segments` 作为训练标签主表 | `episode_sub_goal_instances` 引用版本化 `sub_goal_definitions` |
| Episode 自由 `label_zh` / `label_en` / `action_verb` | Definition 固定语义；Episode 仅记录 occurrence 执行信息 |
| Segment 全局不重叠 | 同一 Definition occurrence 不重叠；不同 Definition 可重叠；Episode 空白允许 |
| `execution_observation` | `task_outcome`，增加 `failed` 并关联失败/最后成功 instance |
| VLM 粗粒度自由 Segment | VLM 仅对固定 Definition 进行 occurrence 对齐 |
| 人工新建 Segment 并命名 | 人工增删 fixed Definition 的 occurrence，不创建新标签 |

`annotation_segments` 不作为新 V1 数据库 migration 的主表。若未来需要记录自由辅助事件，必须另建非训练主标签对象，不能混入 Sub Goal 标签空间。
