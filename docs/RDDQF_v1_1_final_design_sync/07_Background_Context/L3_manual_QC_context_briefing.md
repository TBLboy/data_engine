# L3 人工质检界面 — 项目背景与技术上下文简报

> 用途：与 GPT/其他 AI 讨论 L3 阶段优化时，直接提供此文档即可获得完整上下文。

---

## 1. 项目概览

项目名：灵机启物机器人数采质检平台
技术栈：Python FastAPI + PostgreSQL + Vue 3 (Element Plus) + MinIO + Docker Compose
目标：对 Linker Open TeleDex 平台的机器人遥操作采集数据进行多层质检（L1-L4），其中 L3 为程序自动计算的轨迹质量评分

四层质检体系：
- L1：硬性门控（TeleDex 平台上游负责）
- L2：视觉质量（模糊/过曝/遮挡/深度异常）— 人工判断
- L3：遥操作轨迹质量 — 程序自动计算（本简报重点）
- L4：任务完成度 — 人工判断


## 2. 数据源结构与存储架构

### 2.1 存储架构

MinIO (对象存储) <-> PostgreSQL (元数据 + 业务索引) <-> FastAPI 后端 <-> Vue 前端

- MinIO (yaocao bucket): 存储 raw 和 processed 原始文件
- PostgreSQL: 存储 episode 元数据、批次、任务、QC 结果、审计日志，是唯一业务事实源
- 前端: 只调后端 API，不直连 MinIO（媒体预览通过 presigned URL）

### 2.2 MinIO 对象目录结构

yaocao/<list_prefix>/raw/episode_NNN/    -- 原始 .mcap ROS2 bag 文件
yaocao/<list_prefix>/processed/episode_NNN/   -- 后处理数据

processed/episode_NNN/ 目录下的关键文件:
  manifest.json      -- 元数据 (fps, frame_count, duration_sec)
  metadata.json      -- 对齐信息 (alignment method)
  telemetry.npz      -- 核心遥操作数据 (见下文详细说明)
  cameras/
    cam_top.mp4           -- 顶部 RGB 视频
    cam_left_wrist.mp4    -- 左手腕 RGB 视频
    cam_right_wrist.mp4   -- 右手腕 RGB 视频
    depth_colormap_*.mp4  -- 深度伪彩色视频 (可选)
  camera_info.json
  timestamp_*.npy    -- 时间戳对齐文件
  depth_*.png        -- 逐帧深度图

raw vs processed 关键区别:
- raw/: TeleDex 采集的原始 .mcap 文件 (ROS2 bag)，未做后处理
- processed/: 经过 TeleDex 同步对齐、视频编码、遥操作数据提取后的产物
- L3 质检只使用 processed/ 下的数据


### 2.3 telemetry.npz 数据结构（L3 核心输入）

文件: processed/<episode>/telemetry.npz
来源: TeleDex 平台从 raw .mcap 提取 + 同步对齐后生成

实测数据形状 (以 episode_000000 为例，双机械臂 + 单手任务):
  数组              形状           dtype       说明
  timestamps        (394,)         float64     绝对时间戳（秒）
  qpos              (394, 26)      float32     实际关节位置
  qvel              (394, 26)      float32     关节速度
  actions           (394, 26)      float32     目标/命令关节位置
  effort            (394, 26)      float32     关节力矩
  sync_validation_is_valid  (394,)  bool       同步校验逐帧通过标记
  sync_validation_max_diff  (394,)  float64    同步逐帧最大偏差(ms)
  imu_cam_top       (394, 6)       float32     IMU 数据
  imu_cam_left_wrist (394, 6)      float32
  imu_cam_right_wrist (394, 6)     float32
  ee_poses_qpos_left  (394, 7)     float32     末端执行器位姿
  ee_poses_qpos_right (394, 7)     float32
  ee_poses_actions_left  (394, 7)  float32
  ee_poses_actions_right (394, 7)  float32

26 关节维度拆分 (自动检测，非硬编码):
  - dims 0-13: 机械臂关节 (弧度制, 范围约 [-pi, pi])
    - dims 0-6: 左臂 (7 DOF)
    - dims 7-13: 右臂 (7 DOF)
  - dims 14-19: 全零维度 (可能是未接入手部 DOF)
  - dims 20-25: 灵巧手关节 (0-255, 需归一化到 [0,1])

自动检测逻辑: qpos 每维 max(abs) <= 3.5 视为 arm (rad), > 3.5 视为 hand (0-255)
零值维度 (range < 1e-8) 在 L3 计算前自动排除

### 2.4 数据集规模

- Bucket: yaocao (192.168.21.95:9190)
- 总 list 数: ~52
- 总 episode 数: ~5200 (分布在约 50 个批次中)
- 每条 episode: 60-600 帧不等，典型 10-30 秒
- 数据来源: 青岛采集现场，经内网同步到 MinIO


## 3. L3 指标计算引擎

### 3.1 架构

后端模块: backend/app/services/l3_metrics.py
入口函数: payloads.py 中 _build_real_manual_qc_context() -> L3MetricsEngine(telemetry).compute_all()
超参数管理: backend/app/models/l3_config.py (l3_config 表, JSON 存储)
前端配置页: /settings (仅 admin 可见)

### 3.2 当前 L3 指标列表 (8项 P0+P1 + 1 综合分)

P0 必做 6 项:
  1. LDLJ 平滑度         -- dimensionless jerk, qpos_arm 二阶差分 RMS, 归一化到 0-10
  2. 无效动作占比 (Dead)  -- |actions| < eps_arm/hand 的帧比例, arm/hand 分别算取 max
  3. 动作饱和率 (Sat)     -- action 值接近关节边界的比例, 手部用 0-255 硬阈值
  4. 停滞占比 (Static)    -- 滑动窗口内速度和动作同时低于阈值
  5. 时间戳抖动 (Jitter)  -- std(dt)/mean(dt), CV 衡量采样均匀性
  6. 跟踪误差 (Tracking)  -- |actions - qpos| 的 P95, arm/hand 加权 (0.7/0.3)

P1 增强 2 项:
  7. 手指颤振 (Chatter)   -- 手部维度方向翻转频率 (transitions/sec)
  8. 执行力度 (Effort)    -- effort 的 P95

综合分:
  Q_motion (0-10)          -- 8 项加权合成 (权重和=1.0)

### 3.3 超参数 (存储在 l3_config 表, 可通过 /settings 页面修改)

关键超参数及默认值:
  eps_arm=0.01, eps_hand=0.02           (Dead Actions 检测下限)
  dead_good=0.10, dead_warn=0.25        (Dead 阈值)
  sat_hand_low=10, sat_hand_high=245    (手部饱和边界, 0-255)
  sat_good=0.03, sat_warn=0.08
  static_window_s=0.5                   (停滞滑动窗口)
  tracking_arm_weight=0.7, tracking_hand_weight=0.3
  tracking_good=0.12, tracking_warn=0.20
  ldlj_good=7.0, ldlj_warn=5.0
  sync_bad_threshold_ms=700             (同步异常判定阈值)

### 3.4 Timeline 时间窗异常段

仅由能定位时间窗口的指标产出:
  - 同步异常 (sync_diff > 700ms)         -- 级别: bad
  - 跟踪误差 (weighted error > warn)     -- 级别: warn
  - 运动停滞 (滑动窗口持续低速)          -- 级别: warn
  - 动作饱和 (action 近边界)             -- 级别: warn
  - 动作消失 (actions 全低于 eps)        -- 级别: warn
  - 手指颤振 (高 chatter 帧)             -- 级别: warn

生成规则: 逐帧命中 -> 连续段 >= 0.5s -> gap <= 0.3s 合并 -> 中文标签输出

### 3.5 已知问题与待优化方向

1. 阈值非标定: 全部经验值，未按任务类型做统计标定 (计划积累 200+ approved sample 后升级)
2. Dead/Static 重叠: 两者都检测"不动"但口径不同, 标签已区分但评分有冗余
3. Hand saturation 误报: 手部值 0/255 在部分任务中是"完全张开/闭合"的正常状态
4. LDLJ 仅用 arm 维度: 手部 jerk 未纳入平滑度评估
5. 没有 episode 间对比: P2 指标 (SPARC, Entropy, cross-episode consistency) 已规划但未实现
6. Timeline 段质量: 单帧检测 + min_dur 产生 0-duration 段 (已部分修复)
7. 无任务类型感知: 不同任务 (倾倒/抓取/放置) 应有不同阈值标准


## 4. 人工 QC 工作台界面 (manual-qc.vue)

### 4.1 页面布局

页面路径: /manual-qc/:episodeId
文件: frontend/src/pages/manual-qc.vue (~600 行)

两栏布局 (Grid):
  左侧主区 (manual-main):
    - 顶部状态条: Episode 信息 (批次名/任务名/episode编号) + 审核锁状态 + 认领/释放按钮
    - 视频播放区: RGB 三路视频 (cam_top/left_wrist/right_wrist) + Depth 深度伪彩色切换
    - 播放控制条: Frame 滑块 + 播放/暂停 + 逐帧/+-1s 步进
    - 遥操作曲线联动视图: Chart.js 折线图, arm/hand 切换, 实线=qpos 虚线=actions
    - 异常段核查清单: timeline 段标签列表

  右侧边栏 (manual-side sticky):
    - Episode 质量评分环: Q_motion 综合分 (0-10)
    - 子指标卡片列表: 按严重度排序 (bad > warn > good)
    - 质检结论提交区: Pass/Fail + 主原因码 + 备注 + 提交按钮
    - Revision 历史: 该 episode 的历次 QC 记录

### 4.2 L3 相关 UI 组件详细说明

质量评分环:
  - 固定展示 Q_motion 综合分 (不受排序影响)
  - 展示形式: 大数字 + 标签

子指标卡片 (sortedMetricCards):
  - 按 severity 排序: bad 在前, warn 次之, good 在后
  - 每张卡片: 指标名称 + Tooltip 说明 + 数值 + 颜色级别 (红/黄/绿)
  - 当前 9 张卡片: Q_motion, LDLJ, Dead, Sat, Static, Jitter, Tracking, Chatter, Effort

遥操作曲线联动视图:
  - Chart.js 折线图, 多系列叠加
  - x 轴: 相对时间 (秒)
  - y 轴: 位置值 (arm=rad, hand=0-255)
  - 实线 = 实际关节位置 (qpos)
  - 虚线 = 目标关节位置 (actions)
  - 不同颜色 = 不同关节维度
  - Arm/Hand 切换按钮 (仅在 data 存在时显示)
  - API: GET /api/episodes/{id}/telemetry-curve (返回降采样后的时序数据)

Timeline 异常段:
  - 在播放进度条下方以标签形式展示
  - 每个 segment: 起止时间 + 中文标签 + 级别颜色
  - 异常段核查清单: el-check-tag 列表

### 4.3 当前 L3 数据流

1. 用户打开 /manual-qc/:id
2. 前端调用 GET /api/episodes/{id}/qc-context
3. 后端 payloads.py 从 MinIO 读取 telemetry.npz
4. L3MetricsEngine 计算全部指标
5. 返回 JSON: { metrics: [...], timelineSegments: [...] }
6. 前端渲染评分环 + 指标卡片 + timeline

同时异步加载遥操作曲线数据:
7. 前端调用 GET /api/episodes/{id}/telemetry-curve
8. 返回降采样后的 qpos/actions 时序数据
9. Chart.js 渲染折线图


## 5. 当前 L3 已知问题和待优化点

### 5.1 算法层面

- 阈值全部是经验值，没有按任务类型做统计标定
- 不同采集任务（倾倒/抓取/放置/移动）的理想阈值应不同
- 手部 0/255 饱和误报：完全张开/闭合在正常操作中是合法状态
- 零值维度排除后 arm dims 仍可能包含"几乎不动"的关节（如 dims 0-4 范围仅 ~0.01 rad），导致 Dead/Static 指标虚高
- LDLJ 仅用 arm 维度计算，手部 jerk 未纳入
- 单帧 chatter 检测产出的 timeline 段质量差（0-1 秒的碎片段）
- 无 episode 间对比能力（如"这条 episode 相比同类任务的平均水平差多少"）

### 5.2 UI/UX 层面

- 指标卡片数值缺乏上下文基准线（用户不知道 0.121 的跟踪误差是好是坏）
- Timeline 段和视频播放器没有联动（点击异常段不能跳转到对应帧）
- 遥操作曲线图缺乏异常标注（看不出哪些时间点有异常）
- 评分环只有 Q_motion，用户无法直观理解各项子指标如何贡献到总分
- 没有"一键对比"同类 episode 的指标分布
- 指标卡片的描述文字过长，实际用户很少阅读
- 缺乏实时指标计算进度反馈（大 episode 计算较慢）

### 5.3 工程层面

- telemetry_curve API 和 qc-context API 是两次独立请求，都可以触及 MinIO
- 降采样策略固定（max 500 点），没有根据帧率自适应
- 超参数设置页面 (/settings) 目前只有 L3 标签页，未来需要更多设置分类
- L3 计算结果是 per-episode 的，但批次报告 (history report) 中未充分利用这些指标
- 没有指标计算的离线缓存机制，每次打开 manual QC 都重新计算


## 6. 关键代码文件清单

后端:
  backend/app/services/l3_metrics.py       -- L3 指标计算引擎 (420 行)
  backend/app/services/payloads.py          -- manual QC context 组装 (L3MetricsEngine 入口)
  backend/app/models/l3_config.py           -- L3 超参数持久化模型
  backend/app/api/routes/qc.py              -- API 路由 (/qc-context, /telemetry-curve, /admin/l3-params)
  backend/app/schemas/qc.py                 -- Pydantic response schema
  backend/migrations/versions/20260625_0009_l3_config.py  -- L3 配置表 migration

前端:
  frontend/src/pages/manual-qc.vue          -- 人工 QC 工作台主页面 (600 行)
  frontend/src/pages/settings.vue           -- 设置页面 (L3 参数标签页)
  frontend/src/api/client.ts                -- API 调用封装 (fetchL3Params, fetchTelemetryCurve 等)
  frontend/src/styles/components.css        -- 组件外观模板系统
  frontend/src/components/QcReasonPicker.vue -- 质检原因码选择器

业务逻辑文档:
  software/.project-log/business-logic/main.md             -- 主业务逻辑
  software/.project-log/business-logic/decision-records.md -- L3 决策记录 (公式/阈值/timeline 规则)
  software/.project-log/business-logic/open-questions.md   -- 开放问题列表

## 7. 讨论方向建议

与 GPT 讨论时可以重点探讨以下话题:

1. UI 优化: 如何让 L3 指标卡片更直观、信息密度更高？
   - 是否需要进度条/仪表盘式展示？
   - 如何给数值提供上下文基准线 (如"同类任务平均 0.08，当前 0.12")？
   - 评分环的设计是否有更好的替代方案？

2. Timeline 与视频联动: 如何让异常段和视频播放器互动？
   - 点击异常段跳转到对应帧？
   - 在播放进度条上标注异常区间？
   - 遥操作曲线图上叠加异常高亮？

3. 阈值标定: 如何从经验值过渡到数据驱动的阈值？
   - 需要多少标注样本？
   - percentile-based 还是 clustering-based？
   - 如何按任务类型差异化？

4. 指标体系完整性: 还缺哪些关键指标？
   - SPARC (spectral arc length) 是否需要？
   - 动作熵 / 状态条件方差？
   - Episode 间一致性？

5. 性能优化: 计算缓存、数据预取、API 合并？
