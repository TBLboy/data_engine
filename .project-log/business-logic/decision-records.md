### 2026-07-16 — 任务级数据资产画像长期路线：Route T2（收敛实现）

- Decision: 在已落地的 Route C' 之上，数据总库正式新增 **任务级资产画像**。长期路线采用 **Route T2：新增 `task_asset_rollups` 任务级派生投影 + `task_asset_recompute_jobs` 持久化 dirty/recompute 队列**；任务投影只从 `batch_asset_rollups` 汇总，不回扫 `episodes`，也不让前端按批次临时求和。
- Context: 数据总库当前已有 Episode 明细视角与 Batch 资产画像视角；产品需要第三个 Task 视角，直接回答“某个任务下有多少 batch/episode、多少可用/不可用、多少未完成、合格率多少、总时长/总帧数多少”。现有 `task_types.total_batches/total_episodes` 与 `/api/dataset/tasks/*` 的 task summary 都不足以承担长期资产画像职责：前者只是粗计数且刷新不可靠，后者偏训练消费语义且走 Python 实时聚合。
- Alternatives considered:
  - 方案 T0：请求时对 `episodes` 做 `GROUP BY task_type`
  - 方案 T1：请求时对 `batch_asset_rollups` 实时聚合，不建任务投影表
  - 方案 T2：新增 `task_asset_rollups` + 任务级 dirty/recompute
  - 方案 T3：把更多统计字段继续堆进 `task_types`
  - 方案 T4：直接上 Kafka / ClickHouse / 外部 OLAP
- Reason:
  - T0 会重复 Route C' 已否决的实时扫明细主路径，后续规模增长后必然退化
  - T1 短期可用，但 task 视图后续必然需要按可用率/时长/帧数排序筛选，并独立表达 freshness；继续只靠读时 group by 会重新把压力推回查询层
  - T3 会把业务主数据与分析状态混在 `task_types`，与 Route C' 已拒绝“把统计堆进业务表”的原则冲突
  - T4 对当前规模过重
  - T2 最符合现有 Route C' 结构：batch 投影继续做权威聚合基座，task 投影只做其上的二级读模型
- Implementation detail:
  - 正式数据对象：
    - `task_asset_rollups`：任务级可重建统计投影，`task_type_id` 作为主键/唯一键
    - `task_asset_recompute_jobs`：按 `task_type_id` 粒度持久化 dirty/recompute 请求；同一 task 的 pending/running 请求合并，不无限堆积
  - 正式聚合链路固定为：
    ```text
    episodes
      -> batch_asset_rollups
      -> task_asset_rollups
      -> GET /api/data-assets/tasks
    ```
  - 全局 summary 继续由 `batch_asset_rollups` 求和生成，不改成从 task rollup 汇总，避免多一层 stale 传播
  - 统一统计作用域继续固定为 `active_list_active_batch_indexed_episodes`；task / batch / global 三层不得使用不同 active scope
  - 最终可用性主口径固定为 `final_dataset_status`：
    - available = `QUALIFIED`
    - unavailable = `UNQUALIFIED`
    - pending = `PENDING`
  - 人工质检辅口径固定为 `manual_qc_status`：
    - reviewed = `MANUAL_PASS + MANUAL_FAIL`
    - not_reviewed = `NOT_REVIEWED`
    - manual_pass / manual_fail 分开计数
  - 比率口径：
    - `final_qualified_rate = QUALIFIED / (QUALIFIED + UNQUALIFIED)`；分母为 0 时返回 `null`
    - `manual_pass_rate = MANUAL_PASS / (MANUAL_PASS + MANUAL_FAIL)`；分母为 0 时返回 `null`
    - 比率不物理存储，由 API 读取计数字段后计算
  - `not_reviewed_count` 与 `pending_dataset_count` 必须拆开，不得合并成模糊字段
  - 时长/帧数严格从子 batch rollup 求和，并继续暴露 covered/missing episode count；纯 raw 无 processed manifest 的 0 值是合法缺失，不得伪造
  - 投影层可存：batch_count、episode_count、reviewed/not_reviewed、manual pass/fail、qualified/unqualified/pending、duration/frame 及其 covered/missing、sampled_episode_count、accepted/rejected/pending batch count、source watermark、calculation_version、refreshed_at
  - 投影层不存：task name/description/arm_mode/is_active 等主数据；这些仍从 `task_types` join
  - dirty 触发：
    - episode/batch 事实变化先走既有 batch recompute
    - batch rollup 成功后 mark 父 task dirty
    - batch 改挂 task 时，必须同时 dirty 旧 task 与新 task
    - list active/inactive、batch active 变化、手动 rebuild 也触发相关 task dirty
  - 任务重算以“整任务重算”为默认策略；若目标 task 下仍有 pending/running 的 batch job，应延迟/重试，避免汇总半更新状态
  - 正式 API 边界：
    - `GET /api/data-assets/tasks`
    - `GET /api/data-assets/tasks/{task_type_id}`
    - 扩展既有 `POST /api/data-assets/rebuild` 支持 batch/task/all 范围
  - 前端 `数据总库` 正式三视角：
    1. Episode 明细
    2. Batch 资产
    3. Task 资产
  - 钻取链路固定为：Task → Batch（带 taskTypeId 过滤）→ Episode
  - `task_type:unclassified` / `待分类` 必须始终可展示；默认列表优先 active task，但待分类不得被隐藏
  - `task_types.total_batches` / `total_episodes` 进入废弃流程：停止新增依赖 → 资产接口切换到 task rollup → 兼容观察 → 再删列
  - 实现风格对齐现有 Route C'：优先 `task_type_id` 主键、字符串 calculation_version、job 表承载 dirty/recompute，不另起更重的工作流引擎
- Impacted nodes: D, D2
- Status: confirmed

### 2026-07-15 — 数据总库长期架构升级路线：Route C'

- Decision: 数据总库的“总体资产统计 + 批次级资产画像”正式采用 **Route C'：显式 Batch–List 关系 + 批次级派生投影 + PostgreSQL 持久化重算队列 + 周期性对账**。这条路线作为后续代码改造的正式业务逻辑边界，不再继续把资产画像能力塞进现有 Episode 明细接口，也不把越来越多的统计字段直接堆进 `batches`。
- Context: 当前平台已经形成三层稳定结构：1）MinIO 控制面事实层（`lists / episode_inventory / episode_objects`）；2）业务实体层（`batches / episodes`）；3）QC 与训练消费层（`qc_tasks / qc_review_revisions / batch_decision_log`）。在这个基础上，数据总库新增的总量卡片和批次画像本质上属于读模型/统计投影，不再适合继续依赖实时 Episode 聚合或继续扩张 `batches` 表语义。
- Alternatives considered:
  - 方案 A：继续基于 `episodes` 实时 `GROUP BY` 聚合，按请求即时计算 summary 和 batch 画像
  - 方案 B：把总时长、总帧数、覆盖率等画像字段直接冗余到 `batches`
  - 方案 C：事实表 + 显式关系 + 独立统计投影 + dirty 重算机制
- Reason:
  - 方案 A 在当前数千 Episode 规模下也许可用，但随着后续增加时长/帧数/模态覆盖/标注覆盖/L3 分布等维度，会反复扫描大量明细，且 summary 与 batch 列表容易出现统计口径漂移
  - 方案 B 虽然查询便宜，但会把 `batches` 变成混合了业务状态与分析状态的膨胀实体，不利于后续扩展和对账修复
  - 方案 C' 最符合当前代码形态：保留现有控制面/业务面/消费面事实源，新增可重建的派生投影层，既保证页面读性能，又不破坏原始业务事实
- Implementation detail:
  - `batches.list_id` 作为正式的 Batch–List 显式关系字段落到业务模型中，但第一阶段采用 **可空字段 + 历史回填验证 + 兼容观察 + 再决定是否收紧为非空**，不直接假设历史数据全部可唯一映射
  - 批次级派生统计投影的正式实体固定为 `batch_asset_rollups`，仅保存可确定性重建的聚合结果，例如：`episode_count`、`total_duration_sec`、`duration_covered_episode_count`、`duration_missing_episode_count`、`total_frame_count`、`frame_covered_episode_count`、`frame_missing_episode_count`、`sampled_episode_count`、`reviewed_count`、`manual_pass_count`、`manual_fail_count`、`qualified_count`、`unqualified_count`、`pending_dataset_count`、`last_episode_updated_at`、`source_watermark`、`calculation_version`、`refreshed_at`
  - 第一版**不复制**这些业务状态字段进投影表：`task_type_id`、`batch_name`、`qc_status`、`batch_decision`、`reject_threshold`、`failure_rate`；这些字段仍以 `batches` 或关联维表为准，投影层不生成新的权威口径
  - 顶部总览不单独建全局总表；第一版直接对 `batch_asset_rollups` 求和，确保 summary 与 batch 列表使用完全一致的作用域
  - 统计作用域正式固定为：**active list + active batch + indexed business episodes**，内部统一标识为 `active_list_active_batch_indexed_episodes`。不允许顶部卡片与 batch 列表采用不同过滤口径
  - `duration_sec` 与 `frame_count` 的权威来源固定为扫描阶段持久化到 PostgreSQL 的 manifest 派生字段；其中 `frame_count` 定义为 manifest 声明的 episode 级帧数，不做多相机视频帧总和。覆盖规则固定为：`duration_sec > 0` 视为有效时长，`frame_count > 0` 视为有效帧数
  - PostgreSQL 持久化 dirty/recompute 队列的正式实体固定为 `batch_asset_recompute_jobs`；同一 batch 的重算请求按 `batch_id` 合并，worker 以 batch 粒度执行**整批重算**，而不是做分散的 `+1/-1` 增量计数
  - dirty 触发的核心事实变化包括：Episode 新增/移出作用域、`duration_sec`/`frame_count` 修改、`batch_id` 变更、人工 QC 结果变更、最终数据集状态变更、Batch–List 关系变更、List active/inactive 状态变更、管理员手动重建
  - 周期性对账任务作为低频兜底链路，负责发现漏标记、漏重算和统计漂移；投影层可以重建，但不能反向替代业务事实源
  - 数据资产读路径正式拆分为独立 API：`/api/data-assets/summary`、`/api/data-assets/batches`，并保留管理员手动全量重建入口；现有 `/api/database` 继续维持 Episode 明细浏览语义，不再作为长期聚合主路径
  - 迁移顺序固定为：阶段 0 冻结统计口径与实时基线 SQL → 阶段 1 新增 `batches.list_id` 并回填 → 阶段 2 建立 `batch_asset_rollups` 与全量重建能力 → 阶段 3 引入 `batch_asset_recompute_jobs` 与自动重算链路 → 阶段 4 新增独立 API → 阶段 5 前端接入 → 阶段 6 切换与验收 → 阶段 7 清理兼容逻辑
  - 统计能力正式上线前，必须先确认 manifest 派生字段在扫描链路中可稳定写库，避免时长/帧数基线不可信
- Impacted nodes: D, D2
- Status: confirmed

### 2026-07-10 — QC 任务池拆分 + admin 可直接接管 done 任务

- Decision: reviewer 的人工质检入口正式拆分为“我的任务清单（当前可处理任务）”与“历史任务清单（已完成历史记录）”；同时允许 admin 直接认领 `done` 状态任务，认领动作语义定义为 **reopen + ownership transfer**，而不是新增独立 admin 审批入口
- Context: 当前 reviewer 任务池把 `done` 任务也混在当前列表中，导致已完成数据仍可重新进入质检；同时产品希望避免为 admin 增加额外按钮和独立流程，保持最高权限角色可直接处理异常任务
- Alternatives considered:
  - 方案 A：所有角色统一走“申请重新质检 → 审批 → 新建复检任务”
  - 方案 B：admin 直接接管 `done` 任务；reviewer 通过历史池入口申请重新质检
- Reason:
  - 方案 A 审计更严谨，但对 admin 来说链路过长、交互复杂
  - 方案 B 更符合“admin 最高权限”的产品直觉，同时仍可通过严格后端状态机避免双重归属和历史污染
- Implementation detail:
  - reviewer 当前任务池：`is_active=1 AND assignee=当前 reviewer AND status in ('assigned','in_review')`
  - reviewer 历史任务池：按 reviewer 的已完成历史记录 / revision 展示，不再让 `done` 混入当前任务池
  - reviewer claim 仅允许：active + assigned + assignee=本人 + 无他人有效锁
  - admin claim 允许：active + `status in ('new','assigned','done')`，但若他人 `in_review` 锁有效则禁止接管
  - admin 认领 `done` 时，必须原子执行：`task.done -> in_review`、切换 assignee/lock owner、`episode.done -> in_review`、`episode.qc_result -> pending`、`manual_qc_status -> NOT_REVIEWED`、保留旧 revision 并等待新提交追加 revision
  - `release` 禁止对 `done` 生效；`submit` 禁止回退提交非 active task
  - 新增 `QcRereviewRequest` 模型，reviewer 历史卡可提交申请，admin/qc_manager 通过 `rereview-approvals` 页面审批，审批通过后复用原 task reopen（不回退新建 task）
- Impacted nodes: D
- Status: implemented

### 2026-07-10 — D2 导出增强 + admin 任务管理补强（补充记录）

- Decision: 在已确认的批次驳回主流程之外，补齐训练数据导出的关键字段、管理员任务管理能力，以及前端状态原因展示所依赖的配套结构，作为 D2 的配套增强项纳入正式业务记录。

- Context: v1.0 批次驳回模块已落地。实际使用中发现导出字段不够丰富（缺少 MinIO 路径和 L3 分数）、管理员无法回收卡住的任务（质检员请假等场景）、前端缺少状态判定原因展示
- Reason: 下游训练团队需要 MinIO 路径信息来定位原始数据；管理员需要任务管理权限来处理异常情况（请假、负载不均、错误派发）；质检员需要看到"为什么这条 episode 不能用于训练"
- Implementation detail:
  - 导出新增字段：task_type_id/name, l3_training_quality_score, motion_quality_score, learnability_score, data_integrity_score, execution_diagnostic_score, minio_raw/processed_prefix, telemetry/metadata/manifest_path, video_paths, reviewer_id, qc_result_id, created_at, uploaded_at, qc_completed_at
  - 新增 DatasetExportJob 表
  - 新增 TaskOperationLog 表（revoke/reassign/release/force_release）
  - 新增 API: GET/POST admin 任务管理端点
  - MQ-02 Hand Action Continuity 和 DX-01 真正 Lag Alignment 标记为技术债，本版本暂不实现
- Impacted nodes: D2
- Status: active

### 2026-06-29 — 批次驳回失败率分母：抽检数 vs 批次总数

- Decision: 批次驳回判定中的失败率分母采用**抽检数**（\(N_{sampled}\)），而非批次总数（\(N_{batch}\)）
- Context: LaTeX 设计文档初版使用 \(R_{fail} = N_{fail}^{manual} / N_{batch}\)。用户指出这会在抽检比例较低时严重稀释失败率信号。例如批次 100 条、抽检 25 条、发现 12 条不合格：按总数算是 12%，不触发 10% 阈值；按抽检数算是 48%，明显应驳回
- Reason: 抽检本身就是对批次质量的统计推断。如果抽检 25 条就查出 12 条不合格，这批数据质量大概率很差，应驳回重采。用抽检数做分母使失败率对抽检结果更敏感，不会因为"分母很大而掩盖高密度的失败"
- Implementation detail:
  - 公式：\(R_{fail} = N_{fail}^{manual} / N_{sampled}\)
  - 驳回条件：\(R_{fail} > \theta\)（默认 \(\theta = 0.10\)，可在设置页"通用"tab 中调整）
  - 等于阈值时不驳回
  - 驳回阈值因为分母变小，默认值 0.10 可能在实践中偏严，后续需根据真实数据校准
- Impacted nodes: D2
- Status: active

### 2026-06-25 - L3 V1 指标公式、阈值语义与 timeline 触发规则正式细化

- Decision: L3 V1 在实现级别进一步细化为“episode-level 指标卡片 + segment-level 时间窗告警”双输出结构。每个指标必须同时定义：1）输入字段；2）预处理；3）公式口径；4）阈值语义；5）是否进入 timeline；6）中文展示名。所有阈值在 V1 中先采用**保守经验阈值 + 样本分布辅助**策略：明显异常优先抓出，宁可提示偏多，也不追求第一版就做出严格的统计学最优阈值
- Context: 前一版决策已经收口了 P0/P1/P2 指标分档，但还缺少真正能指导代码实现的细节：例如 Dead Actions 中的 ε 怎么设、Action Saturation 对 arm/hand 如何分边界、Tracking Error 用 mean/p95 还是全局 max、哪些指标要产出 timelineSegments 等。如果不把这些细节写死，代码落地时仍会回到“临时拍脑袋”
- Reason: manual QC 的核心诉求不是学术论文复现，而是“给质检员一个可信、可解释、可定位时间段的 L3 自动提示层”。因此指标定义要以“可解释 + 可调 + 能定位异常段”为先，而不是先追求最复杂公式
- Implementation detail:

  **统一输入预处理**
  1. 从 `processed/telemetry.npz` 读取：`timestamps`, `qpos`, `qvel`, `actions`, `effort`, `sync_validation_is_valid`, `sync_validation_max_diff`
  2. `timestamps` 转换为相对秒：`t_rel = timestamps - timestamps[0]`
  3. 维度拆分：
     - `arm_dims`: 机械臂关节维度（弧度制）
     - `hand_dims`: 灵巧手关节维度（0~255）
  4. 手部归一化：`actions_hand_norm = actions_hand / 255.0`，`qpos_hand_norm = qpos_hand / 255.0`
  5. 所有 arm/hand 相关指标优先分别计算，再根据“worst-case / mean”聚合为 episode 级卡片值

  **P0 必做 6 项细则**

  1. `LDLJ 平滑度`
     - 输入：`qpos[:, arm_dims]` 或 `actions[:, arm_dims]`，默认以 `qpos` 为主、`timestamps` 定义时长
     - 公式：沿 Forge/DQAF 口径，使用 dimensionless jerk / LDLJ 评分；输出归一到 0~10，分数越高越好
     - 阈值语义：
       - `good >= 7.0`
       - `warn 5.0 ~ 7.0`
       - `bad < 5.0`
     - timeline：**不直接产 segment**。LDLJ 作为整条轨迹平滑度总分，不直接定位到时间窗
     - 展示：`平滑度 LDLJ*`

  2. `Dead Actions / 无效动作占比`
     - 输入：`actions[:, arm_dims]` 与 `actions_hand_norm[:, hand_dims]`
     - 口径：
       - arm dead: `mean(all(|a_arm| < ε_arm))`
       - hand dead: `mean(all(|a_hand_norm| < ε_hand))`
       - episode 值取 `max(arm_dead, hand_dead)`，保证最差子系统能暴露出来
     - 初始阈值：
       - `ε_arm = 0.01 rad`
       - `ε_hand = 0.02`（归一化后）
     - 阈值语义：
       - `good < 10%`
       - `warn 10% ~ 25%`
       - `bad > 25%`
     - timeline：**是**。连续 `all(|a| < ε)` 的窗口段进入 `stall / 停滞` segment
     - 展示：`无效动作占比`

  3. `Action Saturation / 动作饱和率`
     - 输入：`actions[:, arm_dims]`, `actions[:, hand_dims]`
     - 口径：
       - arm saturation：动作值接近关节物理上下界的比例（首版按 qpos/actions 的观测分布估计上限，后续再替换成正式 joint limit 表）
       - hand saturation：手部值接近 `0` 或 `255` 的比例
       - episode 值取 `max(arm_sat, hand_sat)`
     - 首版手部阈值：`a_hand <= 3 or a_hand >= 252` 视为饱和
     - 首版机械臂阈值：先按该 episode 中 arm `qpos`/`actions` 的 1% / 99% 分位附近 + 固定 margin 检测近边界风险，后续若拿到正式 limit 表再替换
     - 阈值语义：
       - `good < 3%`
       - `warn 3% ~ 8%`
       - `bad > 8%`
     - timeline：**是**。连续 saturation 命中段进入 `动作饱和` segment
     - 展示：`动作饱和率`

  4. `Static Detection / 停滞占比`
     - 输入：`actions[:, arm_dims]`, `actions_hand_norm[:, hand_dims]`, 可选结合 `qvel`
     - 口径：与 Dead Actions 不同，停滞强调“持续时间窗”。以滑动窗口（建议 0.5s）统计窗口内平均动作幅值和速度幅值是否同时低于阈值
     - 初始阈值：
       - arm: `mean(|a_arm|) < 0.01` 且 `mean(|qvel_arm|) < 0.01`
       - hand: `mean(|a_hand_norm|) < 0.02`
     - 阈值语义：
       - `good < 8%`
       - `warn 8% ~ 20%`
       - `bad > 20%`
     - timeline：**是**。停滞窗口直接进入 `停滞` segment
     - 展示：`停滞占比`

  5. `Timestamp Regularity / 时间戳抖动`
     - 输入：`timestamps`
     - 公式：`dt = diff(t_rel)`，`jitter_ratio = std(dt) / mean(dt)`
     - 阈值语义：
       - `good < 0.02`
       - `warn 0.02 ~ 0.05`
       - `bad > 0.05`
     - timeline：**否**。这是整条序列采样时序稳定性指标，不产 segment
     - 展示：`时间戳抖动`

  6. `Qpos-Action Tracking Error / 跟踪误差`
     - 输入：`qpos`, `actions`（arm/hand 分开；hand 先归一化）
     - 口径：
       - 当前状态 vs 目标命令逐帧绝对差
       - episode 卡片值取 `p95`
       - arm 和 hand 分开算后取 weighted max（arm 权重大于 hand）
     - 初始权重：`arm 0.7`, `hand 0.3`
     - 阈值语义：
       - `good < 0.12`
       - `warn 0.12 ~ 0.20`
       - `bad > 0.20`
       - 若继续沿现有原值空间展示，则前端显示需要转换为“归一化误差”中文说明，避免不同量纲误导
     - timeline：**是**。逐帧误差超过 `warn_threshold` 的连续窗口进入 `跟踪误差` segment
     - 展示：`跟踪误差`

  **P1 增强 2 项细则**

  7. `Per-finger Gripper Chatter / 手指颤振`
     - 输入：`actions[:, hand_dims]`
     - 口径：每个手指维度先二值化或差分阈值化，再计算 transitions/sec；episode 值取 `finger_max`，辅助值可保留 `finger_mean`
     - 初始阈值：`> 2 transitions/sec` 视为高 chatter
     - 阈值语义：
       - `good < 1.0/s`
       - `warn 1.0 ~ 2.0/s`
       - `bad > 2.0/s`
     - timeline：**是**。chatter 高发窗口进入 `手指颤振` segment
     - 展示：`手指颤振`

  8. `Joint Effort / 执行力度`
     - 输入：`effort[:, arm_dims]`（如手部无 effort 则只对 arm）
     - 口径：首版卡片值用 `p95(abs(effort))`；后续若要更敏感可增加积分 `sum(abs(effort))*dt` 作为后台排序特征
     - 阈值语义：
       - `good < 0.9`
       - `warn 0.9 ~ 1.5`
       - `bad > 1.5`
     - timeline：可选。V1 首版**不强制进 timeline**，避免时间窗过多；若后续发现高 effort 与异常动作高度耦合，再加 `高负载` segment
     - 展示：`执行力度`

  **Timeline 统一规则**
  - 仅从能提供时间定位的指标生成：`跟踪误差`、`停滞`、`动作饱和`、`手指颤振`，以及平台已有 `sync_validation_max_diff` 导出的 `同步异常`
  - 生成规则：逐帧命中 → 最小持续时长 `>= 0.5s` → gap merge `<= 0.3s` → 中文标签输出
  - V1 segment 标签固定为：`同步异常`、`跟踪误差`、`停滞`、`动作饱和`、`手指颤振`
  - `高速运动` 不作为独立 L3 指标保留；它更像派生告警，可在后续用作辅助 timeline，不进入核心卡片体系

  **前端卡片展示规则**
  - 评分环只显示 `Q_motion` 这一总分
  - 下方子指标卡片按严重度排序（现有逻辑保留），但展示名称和描述全部使用中文业务语义
  - 首版建议卡片集合：`Q_motion`、`平滑度 LDLJ*`、`无效动作占比`、`动作饱和率`、`停滞占比`、`时间戳抖动`、`跟踪误差`、`执行力度`（P1 若启用则加入 `手指颤振`）

- Impacted nodes: D, E
- Status: active
