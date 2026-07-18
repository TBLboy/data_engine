# Main Business Logic

## Status

- Research phase: Complete（公开数据集调研 + TeleDex 格式分析 + MinIO 数据湖实查均已完成）
- Current phase: 数据标注模块 V1 业务逻辑已固化，进入实施阶段

## Main Path

```text
A → B1 + B2 + B3 → C → F → D → G → E
```

## Path Summary

- **A**: 项目启动，调研目标确定
- **B1**: 报告 01 — 公开数据集隐式 QC 策略（DROID/RH20T/LeRobot/RoboMimic/OXE/RoboCasa）
- **B2**: 报告 02 — 数据质量检测框架（DQAF/score_lerobot/Consistency/Green-VLA/PSD）
- **B3**: 报告 03 — 数据筛选/策展框架（Data Quality in IL/DemInf/QoQ/SCIZOR/S2I）
- **C**: Linker TeleDex 数据格式深度分析 + MinIO 对象存储实地验证
- **F**: MinIO 数据湖控制面方案设计（业务规则已闭环）
- **D**: 基于 MinIO 数据湖架构的 QC 方案落地（含质检/批次驳回/数据集管理）
- **G**: 数据标注模块建设（VLM 自动标注 + 人工标注，质检后独立环节）
- **E**: 完整项目交付

## Deliverables

| 文件 | 节点 | 状态 |
|------|------|------|
| `doc/reports/01_public_dataset_implicit_qc.md` | B1 | 进行中（DROID 已完成，扩展到 19 数据集） |
| `doc/reports/02_data_quality_assessment_frameworks.md` | B2 | 进行中（DQAF + Consistency Matters + Forge 已完成） |
| `doc/reports/03_data_curation_frameworks.md` | B3 | 未开始 |
| `doc/reports/04_teledex_qc_summary.md` | E | 基线章节完成（v0.1）；§6–§9 待补充 |
| `control-plane-schema-v1.md` | F | 已产出（schema v0.2 + 扫描/分类/对象访问规则） |
| `dataset_consumption_batch_rejection_agent_guide.tex` | D2 | 已产出（批次驳回 + 数据集管理 + 导出，v1.0） |
| MinIO → PostgreSQL ingestion / manual QC 改造方案 | D | 待实现 |
| 训练数据消费与批次驳回模块 | D2 | 待实现（代码未开始，业务规则已确认） |

## Transition Phase — F Closed, D Active

当前业务逻辑主线已经从“定义 MinIO 控制面规则”推进到“按既定规则实施 Node D 改造”。Node F 已完成的实现前规则包括：

- `yaocao` bucket 对象布局实查确认：`<bucket>/<list_prefix>/{raw|processed}/episode_xxxxxx/...`
- list 定义、deepest-match 排重、任意深度按层 namespace discovery + 已知 List 分片扫描策略
- `ingestable / processable / qc_ready` 三层 episode 状态模型
- `scan_jobs / discovered_prefixes / lists / episode_inventory / episode_objects / classification_rules` 六张控制面表设计
- `task_types` / `lists` / `qc_tasks` 三类实体区分，以及 bind / unbind / retire 语义
- manual QC 的 MinIO 对象访问协议：媒体预览走短时 presigned URL，结构化对象与显式下载走后端受控接口
- Node D manual QC API 合同：`qc-context` embedded `media[]`、按 `objectId` 定向 refresh、下载走独立 endpoint
- `database` 页面长期性能方向已明确：不能继续依赖“全量 episodes 拉到前端后本地过滤”，后续正式方案应切换为“服务端分页 + 服务端筛选 + 前端短时缓存”
- `数据总库` 的总体资产统计与批次级资产画像路线已确认：正式采用 Route C'，即显式 Batch–List 关系 + 批次级派生投影 + PostgreSQL 持久化重算队列 + 周期性对账

## Stable Assumptions

- 数据采集平台已确定使用 Linker Open TeleDex，数据格式不改动
- MinIO 在 V1 中仅作为原始对象存储层，不承担业务查询职责
- PostgreSQL 是唯一业务查询入口和系统事实源
- 前端继续只调后端 API，不直接耦合 MinIO 路径
- `database` 页面不能长期依赖全量 episodes 前端本地过滤；随着数据规模和多用户远程访问增长，正式形态应由后端负责分页、筛选与总数统计，前端只渲染当前页
- `数据总库` 后续的总体资产卡片和批次资产画像不再继续依赖实时 Episode 聚合主路径，也不直接堆叠在 `batches` 表中；正式形态采用可重建的批次级统计投影层 `batch_asset_rollups`
- `batches` 与 `lists` 的正式业务关系固定为显式 `batches.list_id`；任何基于 ID 约定的推导只允许作为历史兼容，不再作为正式统计主路径
- `batches.list_id` 第一阶段保持可空，以承接历史回填、兼容观察与异常批次识别；是否进一步收紧为 `NOT NULL` 留待单独决策
- 批次级统计投影层只保存可重建的派生统计值，不复制 `qc_status`、`batch_decision`、`task_type_id`、`reject_threshold`、`batch_name`、`failure_rate` 等业务状态作为新的权威字段
- 顶部 summary 与批次画像必须使用完全相同的 active scope，内部统一标识为 `active_list_active_batch_indexed_episodes`
- 时长/帧数统计口径固定为扫描阶段持久化到 PostgreSQL 的 manifest 派生字段，其中 `frame_count` 是 manifest 声明的 episode 级帧数，不是多相机视频帧总和
- 统计刷新采用 PostgreSQL 持久化 dirty 队列 `batch_asset_recompute_jobs` + worker 整批重算，并由周期性对账做低频兜底，不依赖 FastAPI 内存后台任务作为唯一可靠机制
- 任务级资产画像正式采用 `task_asset_rollups` + `task_asset_recompute_jobs`，只从 `batch_asset_rollups` 汇总，不回扫 episodes
- 任务级最终可用性主口径固定为 `final_dataset_status`；人工质检进度只作为辅口径
- `task_types.total_batches` / `total_episodes` 不再作为长期资产计数权威源，进入废弃流程
- 扫描入库正式采用 v3：每日 smart + 每周 full + manual_prefix，任意深度 namespace discovery，List 分片持久队列，独立 coordinator/worker，可终止子进程，Episode 指纹与选择性对象索引，二次确认软删除/自动恢复
- `scan_jobs` 在现有字符串主键表上原地演进；不得按旧 v2 方案重建 BIGINT `scan_jobs`
- 普通用户扫描操作固定为一次点击 `开始扫描`；后端自动完成 discovery、模式选择、分片、并行、重试、缺失确认和资产重算
- 标注按 TaskType 聚合组织，不引入独立的"标注批次"概念
- 标注资格判据固定为单一字段 `Episode.final_dataset_status = 'QUALIFIED'`，标注模块不复算 L2/L3/L4 或批次驳回逻辑
- 每个 Episode 只有一份当前有效标注结果（`episode_annotations` UNIQUE episode_id），VLM 和人工标注写入同一记录
- 标注不能反向改变 Episode 的 `final_dataset_status` 或任何质检字段
- 标注结果的内部存储格式与导出格式解耦：PostgreSQL 存内部模型，LeRobot 格式通过导出转换器生成
- 标注新增 `annotator` 角色，纳入现有扁平化角色体系

## 数据总库资产画像升级 — 已确认业务逻辑

### 目标

把当前以 Episode 明细浏览为主的 `数据总库`，扩展为同时具备：

- 总体资产规模卡片；
- 批次级资产画像；
- 任务级资产画像；
- 与 Episode / Batch 明细联动的服务端分页/筛选；
- 面向后续大规模数据增长的稳定统计架构。

### 正式路线

批次/全局层正式采用 **Route C'**；任务层正式采用 **Route T2**：

```text
显式 Batch–List 关系（`batches.list_id`）
  +
批次级派生统计投影（`batch_asset_rollups`）
  +
PostgreSQL 持久化 batch dirty 队列（`batch_asset_recompute_jobs`）
  +
任务级派生统计投影（`task_asset_rollups`）
  +
PostgreSQL 持久化 task dirty 队列（`task_asset_recompute_jobs`）
  +
周期性对账修复
```

正式聚合链路：

```text
episodes
  -> batch_asset_rollups
  -> task_asset_rollups
  -> GET /api/data-assets/tasks

batch_asset_rollups
  -> GET /api/data-assets/summary
  -> GET /api/data-assets/batches
```

### 正式数据对象

- `batches.list_id`：Batch 与 List 的显式关联，作为长期正式关系字段
- `batch_asset_rollups`：批次级可重建统计投影，承接 summary 与 batch profile 的聚合来源
- `batch_asset_recompute_jobs`：按 batch 粒度持久化 dirty/recompute 请求的数据库队列
- `task_asset_rollups`：任务级可重建统计投影，承接 task profile 的聚合来源；只从子 batch rollup 汇总，不回扫 episodes
- `task_asset_recompute_jobs`：按 task_type 粒度持久化 dirty/recompute 请求；同一 task 的 pending/running 请求合并
- `/api/data-assets/*`：数据资产专用读接口；`/api/database` 保持 Episode 明细浏览语义

### 作用域规则

- 总体统计、批次画像、任务画像统一只统计：active list + active batch + 位于该 active 作用域中的业务 Episode
- 内部统计作用域名称固定为 `active_list_active_batch_indexed_episodes`
- 不允许顶部 summary、batch 列表、task 列表使用不同过滤口径
- 不把 inactive list 外的历史残留 batch 混入当前数据资产画像

### 时长与帧数规则

- `duration_sec` 权威来源：扫描阶段写入 PostgreSQL 的 manifest 派生时长
- `frame_count` 权威来源：扫描阶段写入 PostgreSQL 的 manifest 派生帧数
- `frame_count` 定义为 manifest 声明的 episode 级帧数，不做多相机视频帧总和
- `duration_sec > 0` 视为时长覆盖有效
- `frame_count > 0` 视为帧数覆盖有效

### 投影层边界规则

- 新增批次级统计投影层，保存可确定性重建的统计值
- 新增任务级统计投影层，保存可确定性重建的任务聚合值；任务投影以 `batch_asset_rollups` 为唯一聚合基座
- 第一版不在 batch 投影层复制 `qc_status`、`batch_decision`、`task_type_id`、`batch_name`、`reject_threshold`、`failure_rate` 等业务状态作为权威事实
- 任务投影可存 accepted/rejected/pending batch count 等可重建辅助计数，但它们不是最终数据可用性主口径
- 任务投影不存 task name / description / arm_mode / is_active 等主数据；这些仍从 `task_types` join
- 比率字段（final_qualified_rate / manual_pass_rate 等）不物理存储，API 读取时现算；分母为 0 返回 `null`
- 全局 summary 不单独建全局表，继续直接由批次投影求和生成，不改成从 task 投影汇总
- 若页面需要展示 `failure_rate`，沿用既有批次判定口径，不在资产投影层另起一套新语义

### 刷新与一致性规则

- 事实更新后通过 PostgreSQL 持久化 job 表 `batch_asset_recompute_jobs` 标记 batch dirty
- worker 按 batch 粒度整批重算，不做分散的 `+1/-1` 增量修补
- batch rollup 成功后，标记父 task dirty，并 upsert `task_asset_recompute_jobs`
- batch 改挂 task 时，必须同时 dirty 旧 task 与新 task；global summary 保持不变
- task 重算默认整任务重算；若目标 task 下仍有 pending/running 的 batch job，应延迟/重试，避免半更新汇总
- 周期性对账任务用于发现漏标记、漏重算和统计漂移
- 投影层失效只影响展示新鲜度，不改变业务事实源
- 数据资产聚合正式走独立 `/api/data-assets/*` 路径；`/api/database` 不再承接长期聚合职责

### 任务级资产画像规则

- `数据总库` 正式三视角：Episode 明细、Batch 资产、Task 资产
- 最终可用性主口径固定为 `final_dataset_status`：
  - available = `QUALIFIED`
  - unavailable = `UNQUALIFIED`
  - pending = `PENDING`
- 人工质检辅口径固定为 `manual_qc_status`，必须独立展示，不得冒充最终可用资产
- `not_reviewed_count` 与 `pending_dataset_count` 必须拆开，不得合并为模糊字段
- 正式比率：
  - `final_qualified_rate = QUALIFIED / (QUALIFIED + UNQUALIFIED)`
  - `manual_pass_rate = MANUAL_PASS / (MANUAL_PASS + MANUAL_FAIL)`
  - 分母为 0 时返回 `null`，禁止返回误导性 0
- 正式 API：
  - `GET /api/data-assets/tasks`
  - `GET /api/data-assets/tasks/{task_type_id}`
  - 扩展 `POST /api/data-assets/rebuild` 支持 batch/task/all
- 钻取链路固定：Task → Batch（`taskTypeId` 过滤）→ Episode
- `task_type:unclassified` / `待分类` 必须始终可展示；默认列表优先 active task，但待分类不得被隐藏
- `task_types.total_batches` / `total_episodes` 进入废弃流程，不再作为长期资产计数权威源
- 不使用 `/api/dataset/tasks/*` 作为数据总库任务资产画像主路径；该路径继续服务训练数据消费语义

### 相关既有业务约束（本次继续沿用，不因 Route C' 改变）

- 任务派发与人工质检必须职责分离：工作台承接 batch 级任务生成与批量派发，`manual-qc` 页面只负责 claim/release/提交质检结果，不再承担派发入口
- 系统必须按角色提供不同视图：`admin`/`qc_manager` 看到完整运营视图；`reviewer` 只开放个人任务看板、我的任务列表、人工质检流水线三个界面；`viewer` 只读访问工作台概览
- reviewer 的工作模式是流水线式：从个人看板进入质检 → 提交 → 自动跳转下一条待质检任务，直到全部完成；提交后不应停留在原地或需要手动返回列表选择下一条
- reviewer 完成全部待质检任务后触发庆祝动画（礼花彩条 + 音效），作为正向激励闭环
- `task_types` 是人工维护的业务目录，由 `admin/qc_manager` 管理；扫描器不再负责自动创建正式任务类型，未分类或新增批次统一进入 `待分类`
- bucket discovery 采用 `recursive=False` 按层探索 + 结构特征识别 List；确认 List 后按 prefix 分片扫描，不再继续递归进入其 Episode/逐帧对象内部
- Episode 生命周期采用 ingestable / processable / qc_ready 三层模型
- 扫描器只负责把 MinIO 数据同步到 PostgreSQL，并保持已人工分类 batch 的任务类型不被自动覆盖
- 批次与任务类型关系是可人工改挂的业务关系，而不是扫描器不可变的自动归类结果
- 删除任务类型默认执行“回收到 `待分类`”语义，不直接破坏已有 batch/episode/QC 历史数据
- MinIO 凭据通过环境变量注入，不写入仓库代码

## 训练数据消费与批次驳回 — 业务规则

### 目标

将平台从"只记录质检结果的 QC 系统"升级为"能够按任务统计训练可用数据、执行批次驳回策略、生成可溯源最终状态并导出合格 episode 清单的数据资产供给系统"。

### 失败率计算公式（关键修正）

失败率 = 人工失败数 / 抽检数（NOT 批次总数）

\[
R_{fail} = \frac{N_{fail}^{manual}}{N_{sampled}}
\]

修正理由：以批次总数做分母会严重稀释失败率信号。例如抽检 25 条发现 12 条不合格，按批次总数 100 算只有 12%，但实际上抽检的 25 条中近一半不合格，说明这批数据质量很差。改用抽检数做分母后 12/25=48%，能更敏感地触发驳回。

### 批次判定规则

设驳回阈值 \(\theta\)（默认 0.10，可在设置页"通用"tab 中调整）：

\[
BatchDecision =
\begin{cases}
Rejected, & R_{fail} > \theta \\
Accepted, & R_{fail} \le \theta
\end{cases}
\]

注意：\(R_{fail} = \theta\) 时不驳回（"超过阈值"才驳回）。

### 三层状态模型

- **ManualQcStatus**: NOT_REVIEWED / MANUAL_PASS / MANUAL_FAIL
- **BatchDecision**: PENDING / ACCEPTED / REJECTED  
- **FinalDatasetStatus**: PENDING / QUALIFIED / UNQUALIFIED

批次驳回时所有 episode 最终不可用；批次通过时人工失败的不可用，未抽检和人工通过的可用。

### Episode 最终判定表

| 批次判定 | 人工状态 | 最终状态 | 来源 |
|---------|---------|---------|------|
| REJECTED | MANUAL_FAIL | UNQUALIFIED | MANUAL_FAIL |
| REJECTED | MANUAL_PASS | UNQUALIFIED | BATCH_REJECT_OVERRIDE_MANUAL_PASS |
| REJECTED | NOT_REVIEWED | UNQUALIFIED | BATCH_REJECT_PROPAGATED_FAIL |
| ACCEPTED | MANUAL_FAIL | UNQUALIFIED | MANUAL_FAIL |
| ACCEPTED | MANUAL_PASS | QUALIFIED | MANUAL_PASS |
| ACCEPTED | NOT_REVIEWED | QUALIFIED | BATCH_ACCEPT_INFERRED_PASS |

### 判定触发时机

- 质检员提交 QC 结果后自动触发所属批次的判定检查
- 管理员可手动触发重新判定
- 判定条件：`sampled_episode_count > 0 AND reviewed_episode_count >= sampled_episode_count`
- 判定幂等：重复执行不产生不一致状态

### 设置页新增"通用"标签

在现有 `settings.vue` 的 tab 结构中新增"通用"tab，包含：
- 批次驳回阈值 \(\theta\)（默认 0.10，即抽检失败率 > 10% 触发驳回）

### 相关文档

- 完整设计文档：`software/dataset_consumption_batch_rejection_agent_guide.tex`

## QC 任务池 / 历史任务池 / admin 重新质检 — 业务规则（2026-07-10 已确认）

### 目标

在现有人工质检体系上补齐 reviewer 当前任务池、reviewer 历史任务池、admin 直接接管已完成任务重新质检、以及 claim 权限收口规则，避免已完成任务被普通 reviewer 反复重做，同时保留 admin 的最高权限干预能力。

### 核心语义

- `QcTask.is_active` 表示**当前有效任务尝试 / 当前有效派发版本**，**不表示**“是否已完成”。
- `QcTask.status` 表示当前任务尝试的处理进度，现阶段继续使用：`new / assigned / in_review / done`。
- reviewer 的“当前任务池 / 历史任务池”是**业务视图**，由查询规则区分，不直接等价于数据库某一个字段。
- admin 认领 `done` 任务不是“临时查看”，而是**直接 reopen 这条任务并接管所有权**。

### 当前任务池与历史任务池定义

#### reviewer 当前任务池

必须同时满足：

- `QcTask.is_active = 1`
- `QcTask.assignee = 当前 reviewer`
- `QcTask.status in ('assigned', 'in_review')`

业务语义：

- 这里只显示 reviewer 现在还能继续处理的任务。
- 这里**绝不能出现 `done`**。
- admin 接管后，任务必须立刻从原 reviewer 当前池消失。

#### reviewer 历史任务池

业务语义上应表示：

- “该 reviewer 曾经完成过的人工质检记录”
- 支持查看历史结果，并可对历史结果发起重新处理入口（reviewer 侧是申请重新质检；admin 侧可直接接管）

实现口径建议：

- 展示层以 `QcReviewRevision` / 完成记录为主，而不是简单依赖“当前 `QcTask.status='done'` 这一行还归属谁”。
- 原因：若 admin 接管并 reopen 了原 `done` task，旧 reviewer 的历史记录不能因此消失。

### 角色行为规则

#### reviewer

- `new`：不可认领（任务尚未正式进入其任务池）
- `assigned`：仅当 `assignee == 当前 reviewer` 时可认领
- `in_review`：仅锁持有人本人可继续提交或释放
- `done`：不可认领；只能在历史任务池中查看历史，并按产品入口申请重新质检

#### admin

- `new`：可认领
- `assigned`：可认领，即直接接管任务所有权
- `in_review`：若他人有效锁仍在，则不可接管；若锁过期，可接管
- `done`：可认领；认领动作的语义是 **reopen + ownership transfer**

#### qc_manager

当前先按非 admin 收口处理：

- 不享有“直接接管 done 任务”的最高权限语义
- 若后续业务决定与 admin 完全等权，再单独放开

### admin 认领 done 的 reopen 语义

当 admin 对 `done` 状态任务执行认领时，后端必须在同一事务中完成：

1. 校验任务 `is_active = 1`
2. 校验不存在他人的有效锁
3. 将任务所有权切换给 admin
4. 将 `QcTask.status: done -> in_review`
5. 设置新的 lock owner / expires_at
6. `QcTask.version += 1`
7. 将 `Episode.reviewer` 改为 admin
8. 将 `Episode.qc_status: done -> in_review`
9. 将 `Episode.qc_result: pass/fail -> pending`
10. 将 `Episode.reason_code` 重置为 `-`
11. 将 `Episode.manual_qc_status` 重置为 `NOT_REVIEWED`
12. 保留旧 `QcReviewRevision` 不删除，等待本次重新提交后追加新的 revision
13. 写入审计日志，明确记录这是“admin reopen done task”

禁止出现的脏状态：

- `QcTask.status = in_review` 但 `Episode.qc_status = done`
- admin 已接管，但旧 reviewer 当前任务池里仍能查到此任务
- 旧历史 revision 被覆盖或删除

### claim 接口业务约束

#### reviewer claim

必须同时满足：

- `QcTask.is_active = 1`
- `QcTask.status = 'assigned'`
- `QcTask.assignee = 当前 reviewer`
- 没有他人的有效锁

禁止：

- 认领 `new`
- 认领 `done`
- 认领派发给别人的任务
- 认领 inactive 旧任务

#### admin claim

允许：

- `is_active = 1`
- `status in ('new', 'assigned', 'done')`
- 若 `status = 'in_review'`，仅在锁过期后才能接管

业务结果：

- claim 成功后，任务所有权立即转移给 admin
- 原 reviewer 当前任务池必须刷新后消失该任务
- 若是 `done`，同时触发 reopen 语义

### submit / release 约束

#### submit

只允许对满足以下条件的任务提交：

- 当前 active task
- `status = 'in_review'`
- lock owner 是当前用户
- version 原子匹配

禁止：

- 找不到 active task 时回退提交旧任务
- 无锁提交
- 对 `done` / `assigned` 直接提交

#### release

只允许：

- `status = 'in_review'`
- 当前用户是锁持有人，或 admin 明确执行强制释放

禁止：

- 对 `done` 执行 release 后把任务变回 `assigned/new`

### 前端页面改造点

#### reviewer /task-pool

改为双卡片：

1. **我的任务清单**
   - 数据源：reviewer 当前任务池
   - 独立分页
   - 操作：`进入质检`

2. **历史任务清单**
   - 数据源：reviewer 历史完成记录
   - 独立分页
   - 操作：`进入质检`（建议实际呈现为历史查看模式）、`申请重新质检`

#### admin /task-pool

- 仍保留全局 QC 任务明细视图
- `进入质检` 后允许对 `new/assigned/done` 执行 claim
- 若 claim 的是 `done`，UI 文案需明确是“接管并重新质检”

#### manual-qc 页面

需要根据后端返回的任务状态 / 权限标志控制按钮：

- reviewer 查看历史任务时：默认只读，不允许 claim/submit
- admin 打开可接管的 `done` 任务时：允许 claim，claim 后进入重新质检状态
- 页面需能正确处理“任务已被 admin 接管 / 版本已变更 / 锁已变化”的冲突提示

### 审计要求

admin 接管 reviewer 任务或 reopen done 任务时，审计必须记录：

- 原审核员
- 新审核员
- 原状态
- 是否从 `done` reopen
- task id / episode id / version
- 操作时间

### 现状漏洞（待实现时一并修复）

当前代码已确认存在以下问题：

- reviewer 任务池查询会混入 `done`
- reviewer 仍可认领 `未派发` 任务
- `done` 任务缺少 claim 阻断
- admin claim 会直接覆盖 assignee/reviewer，但没有清晰的 reopen 语义约束
- `release` 可错误作用于 `done`，造成 task/episode 状态矛盾
- `submit` 存在回退到非 active task 的风险

上述漏洞在实现本轮任务池/历史池改造时必须同步收口。

## Verification Status

- A: 已完成
- B1: 进行中（DROID 已完成，扩展到 19 数据集）
- B2: 进行中（DQAF + Consistency Matters + Forge 已完成）
- B3: 未开始
- C: 已完成（TeleDex 文档、schema、MinIO 实查均已完成）
- **F: 已闭环（可指导实现）**
- **D: ready（可按现有业务规则开始实现）**
- E: 待 D 完成后整合交付

## L3 V1 Execution Snapshot

- L3 的 V1 自动指标现已细化到实现级：P0 必做 6 项（LDLJ、Dead Actions、Action Saturation、Static Detection、Timestamp Regularity、Qpos-Action Tracking Error）+ P1 增强 2 项（Per-finger Gripper Chatter、Joint Effort）
- 统一输入源：仅 `processed/telemetry.npz`
- 统一子系统约束：arm_dims（弧度）与 hand_dims（0~255）分开计算；手部先归一化到 `[0,1]`
- Timeline 只由可定位的异常产出：`同步异常`、`跟踪误差`、`停滞`、`动作饱和`、`手指颤振`
- manual QC 自动指标区只承载 L3；L2/L4 继续人工审核

## Notes

- 当前已不再缺核心业务规则，剩余工作重心转向代码实现
- 唯一仍打开的问题是全量 list census，它属于规模与验收覆盖问题，不改变既定控制面设计
- 下一阶段产出应是 MinIO 控制面 migration、扫描器实现、manual QC MinIO 化改造
- `database` 页面后续若进入大规模远程使用，性能优化优先级应遵循：先后端分页/筛选，再前端短时缓存；`KeepAlive` 或单纯前端全量分页都不能作为长期主方案
- 任务派发后续正式形态应采用”批次级生成待派发任务池 + reviewer 批量分配”模式，而不是逐条 `episode` 手工指定审核员；若重新生成派发任务，系统必须切换到新的活跃派发版本并退役旧版本未开始任务，避免旧 full 任务继续污染当前 sampled 视图
- 角色视图分离后的页面路由规则：登录后 `reviewer` → `/reviewer`（个人看板）、`admin/qc_manager` → `/dashboard`（派发工作台）；`manual-qc` 是共用页面，但 reviewer 在流水线模式下提交后自动跳转下一条，admin 模式下不自动跳转
- L3 方案已正式收口到 V1 可执行级：L1 继续由 TeleDex 平台负责；L2（视觉质量）与 L4（任务完成度）保持人工审核；L3（遥操作轨迹质量）采用 Forge 主方案 + TeleDex/灵巧手专项自定义指标。V1 首版自动指标分档为 P0 必做 6 项（LDLJ、Dead Actions、Action Saturation、Static Detection、Timestamp Regularity、Qpos-Action Tracking Error）+ P1 增强 2 项（Per-finger Gripper Chatter、Joint Effort）；P2 的 SPARC / Action Entropy / State-Conditioned Variance / 跨-episode consistency 指标暂缓。manual QC 的自动指标区只承载 L3，不承担 L2/L4 自动判定

## RDDQF v1.2 平台增强 — 业务规则

### 目标

在 v1.0 批次驳回模块基础上增强四个方向：导出字段丰富化、管理员任务池管理能力、Episode 状态溯源、任务操作审计。

### 导出字段增强

当前导出仅含 11 个基本字段。v1.2 扩展到 ~25 字段，新增：
- 任务类型信息 (task_type_id, task_type_name)
- L3 v2 分数 (training_quality_score + 4 维度分数)
- MinIO 路径 (raw/processed prefix, telemetry/manifest/metadata path, video paths)
- 质检员信息 (reviewer_id, qc_result_id)
- 时间信息 (created_at, uploaded_at, qc_completed_at, final_decided_at)

新增 DatasetExportJob 表记录导出历史。

### 管理员任务池管理 (Reviewer Task Manager)

- 入口：工作台审核员工作量卡片 → "管理任务"按钮 → Drawer/Modal
- 操作：撤回/转派/释放 pending 任务，支持批量操作
- 状态限制：pending 可撤回/转派/释放；in_progress 默认不可操作（强制释放需记录原因）；completed 不可操作
- 所有操作写入 TaskOperationLog 审计表

### Episode 状态溯源面板

在 Episode 列表点击某条记录时展示完整判定链：
- 最终状态 + 来源
- 人工质检状态
- 所在批次状态 + 失败率
- 策略版本 + 判定时间 + 原因

### MQ-02 / DX-01 优化 (技术债，本版本可暂不实现)

- MQ-02: 当前仅检测 Arm Action 二阶差分，未检测 Hand Action
- DX-01: 当前 lag alignment 在 error 序列上平移而非 action-qpos 对齐
- 记入技术债，后续版本处理

### 相关文档

- v1.2 设计文档：`software/rddqf_v1_2_platform_enhancement_agent_guide.tex`
