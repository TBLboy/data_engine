# Business Logic Constraints

## System Constraints

- 不改动Linker TeleDex数据采集平台

## Hardware Constraints

- 数据采集硬件已确定：
  - 机械臂：Linker Arm LA7
  - 灵巧手：Linker Hand O6/L6/L20/L25
  - 相机：Orbbec Gemini 335L + Gemini 2
  - 遥操作：Linker TA + TG/FFG/MCG手套

## Software Constraints

- 数据采集软件：Linker Open TeleDex系统（ROS2 + MCAP）
- 数据格式：telemetry.npz、camera_info.json、manifest.json、metadata.json
- 不改动现有数据格式

## Real-Time / Threading Constraints

- None（调研阶段不涉及实时系统）

## Safety Constraints

- None（调研阶段不涉及硬件操作）

## SDK / API Constraints

- Linker TeleDex使用ROS2话题结构
- 相机话题：/{camera_name}/color/image_raw、/{camera_name}/depth/image_raw等
- 机械臂话题：/left_arm_joint_state、/right_arm_joint_control等
- 灵巧手话题：/cb_left_hand_state、/cb_right_hand_control_cmd等

## Configuration Constraints

- None（调研阶段不涉及配置实施）

## Data Lake Constraints

- V1 默认只连接 `yaocao` 这一个 bucket，不做多 bucket 路由
- MinIO bucket/prefix 扫描必须采用全层级递归发现策略，不能假设 list 固定出现在第一层或第二层
- list 的识别依据结构特征（直接子级命中 `raw/`、`processed/` 且其下存在 `episode_xxxxxx/`），而不是固定深度或命名正则
- MinIO 凭据（endpoint、access_key、secret_key）必须以环境变量注入，不能写入仓库代码或部署文档中的明文默认值
- 扫描结果（discovered_prefixes vs lists）采用两层 PostgreSQL 存储，分别跟踪原始发现与结构确认结果
- 不支持前端直接访问 MinIO，所有媒体对象通过后端 API（presigned URL 或代理流）暴露，不把 bucket/prefix/key 规则暴露给前端
- 对象存储与 PostgreSQL 之间的关联键由控制面字段定义，不直接使用 MinIO 路径字符串作为业务主键

## Task Type Management Constraints

- `task_type:unclassified` / `待分类` 是系统保底任务类型，必须永久存在，不能被删除
- 正式任务类型主数据只面向 `admin` 与 `qc_manager` 开放管理；`reviewer`、`viewer` 无权创建、删除、重命名或改挂批次
- 扫描器不自动创建正式任务类型，不自动把新 batch 归入正式任务类型；新 batch 默认进入 `待分类`
- 已经归入正式任务类型的 batch，不得作为“新增批次”候选再次出现在其他任务类型的加入列表里
- 删除任务类型时，关联 batch 必须回收到 `待分类`，不得联动删除 batch / episode / QC 历史数据
- 从任务类型中移除 batch，本质上等价于把该 batch 重新归入 `待分类`
- 批次改错分的标准操作流应保持可追溯：先从原任务类型移出回到 `待分类`，再从 `待分类` 加入正确任务类型
- 数据总库中的批次、QC 状态、QC 结果筛选必须支持键盘输入检索，以适应大规模 batch 数量下的快速定位需求

## Documentation Constraints

- 调研报告需使用Markdown格式
- 交付文档需适合领导阅读（简洁、有结构、有明确建议）