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
