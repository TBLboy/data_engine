# Requirements

## Project Summary

- Goal: 基于已有的数据采集系统，搭建一套数据质检（QC）软件
- Users / Operators: 数据采集操作员、质检审核员
- Current stage: 调研阶段，定义业务逻辑

## 上游数据采集系统

系统名称：Linker Open TeleDex 数据采集系统
基于 ROS2，以 MCAP 格式录制原始数据，前端触发转换后写入 processed 目录。

### 硬件配置

- 机器人平台：Linkerbot
- 机械臂：Linker Arm A7 Lite（左右各 7 自由度，弧度单位 rad）
- 灵巧手：Linker Hand O6 / L6 / L20 / L20 Lite / L25（0-255 范围值）
- 遥操作手臂：Linker TA
- 遥操作手套：Linker TG（柔性）/ FFG（力反馈）/ MCG（惯性动捕）
- 相机：Orbbec Gemini 335L（头部）+ Gemini 2×2（左右腕部）
  - RGB 分辨率：640×480
  - 深度分辨率：640×400

### 采集的 ROS2 话题

相机话题（每个相机最多 7 个）：
- `/{camera_name}/color/image_raw` — RGB 图像 (sensor_msgs/Image)
- `/{camera_name}/color/camera_info` — RGB 内参 (sensor_msgs/CameraInfo)
- `/{camera_name}/depth/image_raw` — 深度图像 (sensor_msgs/Image, 16UC1, mm)
- `/{camera_name}/depth/camera_info` — 深度内参
- `/{camera_name}/gyro_accel/sample` — 相机 IMU (sensor_msgs/Imu)
- `/{camera_name}/accel/imu_info` — 加速度计标定
- `/{camera_name}/gyro/imu_info` — 陀螺仪标定

其中 camera_name 为：top / left_wrist / right_wrist

机械臂话题：
- `/left_arm_joint_state`、`/left_arm_joint_control`
- `/right_arm_joint_state`、`/right_arm_joint_control`

灵巧手话题：
- `/cb_left_hand_state`、`/cb_left_hand_control_cmd`
- `/cb_right_hand_state`、`/cb_right_hand_control_cmd`

可选触觉话题：
- `/cb_left_hand_matrix_touch`、`/cb_right_hand_matrix_touch`
- `/cb_left_hand_matrix_touch_mass`、`/cb_right_hand_matrix_touch_mass`

### 任务目录结构

```text
collection_data/
└── double_linkerhand_grasp_YYYY-MM-DD_HH-mm-ss/
    ├── raw/
    │   └── episode_XXXXXX/
    │       ├── device_info.json       # 硬件配置信息
    │       ├── recording_info.json    # 录制概要（话题、时长、消息数）
    │       └── raw/
    │           ├── metadata.yaml      # rosbag2 元数据
    │           └── raw_0.mcap         # 原始 ROS 消息（唯一数据源）
    └── processed/
        └── episode_XXXXXX/
            ├── telemetry.npz          # 核心遥测数据
            ├── camera_info.json       # 相机内参 + IMU 标定
            ├── manifest.json          # 文件索引 + 时长/帧数/帧率
            ├── metadata.json          # 对齐策略 + 同步误差 + 设备信息
            ├── cameras/
            │   ├── cam_top.mp4, cam_left_wrist.mp4, cam_right_wrist.mp4
            │   ├── cam_top.timestamps.npy, ...
            │   ├── cam_top_depth/*.png (uint16, mm)
            │   ├── cam_top_depth.timestamps.npy, ...
            │   └── cam_top_depth_colormap.mp4 (预览)
            └── cameras/ (彩色点云转换额外包含)
                └── *_pointcloud/*.ply
```

### telemetry.npz 字段详解

| 字段名 | shape | dtype | 说明 |
|--------|-------|-------|------|
| timestamps | (N,) | float64 | Unix epoch 秒，对齐后统一时间轴 |
| qpos | (N, D) | float32 | 关节位置（混合单位） |
| qvel | (N, D) | float32 | 关节速度（混合单位） |
| effort | (N, D) | float32 | 力矩/力信息 |
| actions | (N, D) | float32 | 遥操控制指令 |
| ee_poses_qpos_left/right | (N, 7) | float32/64 | 基于 qpos 正运动学的末端位姿 [x,y,z,qx,qy,qz,qw] |
| ee_poses_actions_left/right | (N, 7) | float32/64 | 基于 actions 正运动学的末端位姿 |
| imu_cam_top/left_wrist/right_wrist | (N, 6) | float32 | [ax,ay,az,gx,gy,gz] |
| sync_validation_is_valid | (N,) | bool | 每帧同步校验标志 |
| sync_validation_max_diff | (N,) | float64 | 每帧最大跨传感器时间差 (ms) |
| tactile_*_matrix | (N, 12, 6) | float32 | 触觉矩阵（可选） |
| tactile_*_mass | (N,) | float32 | 各指合力值 g（可选） |

维度说明：N 为帧数，D = left_arm_dof + right_arm_dof + left_hand_dof + right_hand_dof。
以双臂 7+7、双手 6+6 为例，D=26，索引切片：
- 0:7 → 左臂
- 7:14 → 右臂
- 14:20 → 左手
- 20:26 → 右手

单位说明：
- 机械臂 qpos/qvel：弧度 rad / rad/s
- 机械臂 effort：牛米 N·m
- 灵巧手 qpos/actions：0-255 范围值

### 三种转换模式

1. **基础转换**：telemetry + RGB 视频 + 深度 PNG + 时间戳
2. **D2C 转换**：基础 + 深度对齐到彩色相机坐标系
3. **彩色点云转换**：D2C + 逐帧彩色点云 PLY

### 对齐参数

- 对齐方法：depth_anchored_fixed_fps
- 参考源：synthetic_fixed_fps
- max_time_diff_ms：22ms
- skip_initial_frames：0，skip_final_frames：30
- 支持 sensor_offsets_ms 固定时延补偿
- metadata.json 记录 global_valid_start/end 与 trimmed_valid_start/end

### raw 话题 → telemetry 字段映射

| telemetry 字段 | 来源话题 | 读取字段 |
|----------------|----------|----------|
| timestamps | 参考相机时间轴 | 相机消息头时间戳 |
| qpos | /left_arm_joint_state + /right_arm_joint_state + /cb_left_hand_state + /cb_right_hand_state | position |
| qvel | 同上 | velocity |
| effort | 同上 | effort |
| actions | /left_arm_joint_control + /right_arm_joint_control + /cb_left_hand_control_cmd + /cb_right_hand_control_cmd | position |
| ee_poses_* | 转换阶段正运动学计算 | — |
| imu_cam_* | /camera_name/gyro_accel/sample | linear_acceleration + angular_velocity |
| sync_validation_* | 转换阶段生成 | — |

### 数据采集系统已内置的 QC（L1 硬性门控）

采集软件在转换阶段已自动完成：
- 时间戳对齐与同步校验（sync_validation_is_valid / max_diff）
- 跨传感器最大时间差阈值 (22ms)
- 起止帧裁剪 (skip_final_frames=30)
- 末端位姿正运动学计算 (ee_poses)
- IMU 对齐

### Task Scope (V1.0)

- In scope: 基于 **processed 数据**（telemetry.npz + 视频 + 元数据）做 L2-L4 人工质检，两种方式（手动质检 / 质检后管理），多人协作，支持按比例抽检派发或全量派发，审计留痕，批次统计
- In scope: raw→processed 转换适配，用于上游未转换时的数据标准化
- Out of scope: L1 硬性门控（已在采集系统的转换阶段完成）
- Out of scope: AutoQC / VLM / 自动检测（规划在 V2）

### V1.0 内置 BUG 反馈与管理

为支持局域网内真实使用过程中的问题闭环，系统新增内置 BUG 提交/管理能力。

#### 用户侧提交流程

- 所有已登录用户都可以在顶部栏使用 `BUG提交` 按钮
- 按钮位于 `LAN 内网访问` 与 `任务派发` 之间
- 点击后弹出浮窗，支持：
  - 填写问题描述
  - 直接粘贴截图（首版单图即可）
  - 预览图片后提交
- 提交成功后，信息写入服务器统一存储，供管理员后续处理

#### 管理侧入口与能力

- `BUG管理` 仅对 `admin` 可见
- 入口放在右上角管理员头像/用户名下拉菜单中，不占用顶部高频操作区
- 管理页面需要支持：
  - 查看所有 BUG 提交记录
  - 查看提交时间、提交人、描述、截图、当前状态
  - 将 BUG 状态更新为 `已修复`
  - 删除无效/已清理记录

#### 状态模型

首版状态先保持最小闭环：
- `open` — 新提交、待处理
- `fixed` — 已修复

#### 存储与实现约束

- BUG 记录需持久化到数据库，不能只存在前端或内存中
- 截图文件首版可由后端受控存放在服务器本地目录
- 前端通过后端 API 访问截图，不直接暴露任意文件系统路径
- 该能力属于项目内建反馈系统，不依赖外部工单平台


上游数据采集软件将 raw 数据转换为 processed 数据的完整流程，QC 软件需实现相同功能作为适配层。

**阶段 1：MCAP 解析**

从 `raw_0.mcap` 读取所有 ROS2 消息，按话题分组：
- 3 相机 × 7 话题（color image/camera_info + depth image/camera_info + gyro_accel + accel_imu_info + gyro_imu_info）
- 4 个 joint_state（左右臂、左右手）
- 4 个 joint_control（左右臂遥操、左右手遥操）
- 可选触觉话题

**阶段 2：时间对齐**

- 基于所有深度帧时间戳生成合成固定帧率时间轴（synthetic_fixed_fps）
- 深度帧作为锚点（depth_anchored），在 max_time_diff_ms=22ms 窗口内匹配 RGB 帧
- 关节状态/控制通过插值对齐，补偿固定传感器时延：
  - 机械臂话题：+30ms
  - 灵巧手话题：+20ms
- IMU 通过插值对齐
- 裁剪尾帧：skip_final_frames=30
- 输出：统一时间轴 timestamps (N,)，所有数据对齐到同一帧索引

**阶段 3：正向运动学**

- 基于 qpos 计算末端位姿 → `ee_poses_qpos_left/right` (N,7)
- 基于 actions 计算末端位姿 → `ee_poses_actions_left/right` (N,7)
- 后端：linkerbot-python-sdk ArmKinetix，URDF 模型 (a7_lite)
- 格式：[x, y, z, qx, qy, qz, qw]

**阶段 4：视频/图像编码**

- RGB：sensor_msgs/Image → H.264 MP4，CRF=18，yuv420p，CFR
- 深度：sensor_msgs/Image (16UC1, mm) → uint16 PNG 序列
- 深度预览：深度图 color-map → 预览 MP4
- 时间戳：写入 float64 npy（与统一时间轴一致）

**阶段 5：元数据输出**

- `telemetry.npz`：所有对齐后的数值数据
- `manifest.json`：episode 元信息、文件索引、sync_error 统计
- `metadata.json`：对齐参数、设备信息、录制话题摘要
- `camera_info.json`：3 相机 RGB/Depth 内参 K/D + IMU 标定参数

### Open Questions

- 待讨论确认
