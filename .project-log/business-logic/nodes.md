# Business Logic Nodes

## Node Template

```yaml
id: <node-id>
name: <node-name>
status: draft | stable | deprecated
state:
  - <what has become true at this node>
inputs:
  - <required input data or signal>
outputs:
  - <available output data or signal>
data_format:
  - <data type, message type, file type, coordinate frame, etc.>
related_hardware:
  - <hardware if any>
related_interfaces:
  - <API, SDK, protocol, etc.>
verification:
  - <how to confirm this state is reached>
```

## Nodes

```yaml
id: ingest-manager
name: IngestManager
status: draft
state:
  - 新入库 batch/episode 已建档
  - raw/processed 可用性已判定
  - QC 任务已创建或进入待创建队列
inputs:
  - collection_data 根目录路径
  - raw / processed 目录事件或周期扫描结果
outputs:
  - task_type / batch / episode 建档记录
  - ingest 状态
  - needs_convert / qc_queue_ready 标记
related_interfaces:
  - POST /api/ingest/scan
  - GET /api/ingest/jobs
```

```yaml
id: deploy-host
name: DeployHost
status: draft
state:
  - 平台已部署在公司本地中心主机
  - 前端/后端/数据库/存储已集中运行
inputs:
  - 主机硬件资源
  - 本地数据目录
outputs:
  - Web 访问入口
  - 本地存储服务
  - 数据库服务
related_hardware:
  - 公司空余台式机
related_interfaces:
  - Browser Access over LAN
```

```yaml
id: auth-rbac
name: Auth & RBAC
status: draft
state:
  - 用户账号已建立
  - 角色权限已生效
inputs:
  - user
  - role
outputs:
  - 登录会话
  - 权限判定结果
related_interfaces:
  - POST /api/auth/login
  - POST /api/auth/logout
  - GET /api/me
```

```yaml
id: qc-task-queue
name: QCTaskQueue
status: draft
state:
  - QC 任务已生成
  - 任务已派发/认领/关闭
inputs:
  - batch / episode
  - reviewer_id
outputs:
  - reviewer 待办任务
  - 任务状态流转记录
related_interfaces:
  - GET /api/qc/tasks
  - POST /api/qc/tasks/{id}/assign
  - POST /api/qc/tasks/{id}/claim
  - POST /api/qc/tasks/{id}/close
```

```yaml
id: audit-log
name: AuditLog
status: draft
state:
  - 关键操作已留痕
  - revision / assignment / status change 可追溯
inputs:
  - operator action
  - qc payload
  - status transition
outputs:
  - audit_event
  - assignment_history
  - revision trace
related_interfaces:
  - GET /api/audit
  - GET /api/tasks/{id}/history
```

### Backend

```yaml
id: scanner
name: Scanner
status: draft
state:
  - 已扫描并索引所有 task 和 episode
  - 已解析 device_info / recording_info / manifest
inputs:
  - collection_data 根目录路径
outputs:
  - task 列表
  - episode 列表（含元信息）
  - raw/processed 状态标记
data_format:
  - device_info.json
  - recording_info.json
  - manifest.json
related_interfaces:
  - GET /api/tasks
  - GET /api/tasks/{id}/episodes
```

```yaml
id: converter
name: Converter
status: draft
state:
  - raw 数据已转换为 processed 数据
inputs:
  - raw episode 目录
outputs:
  - telemetry.npz
  - manifest.json
  - metadata.json
  - camera_info.json
  - cameras/*.mp4 / *.png / *.npy
data_format:
  - raw_0.mcap → processed
related_hardware:
  - 无
```

```yaml
id: sampler
name: Sampler
status: draft
state:
  - 已生成待检 episode 列表
inputs:
  - episode 列表
  - 抽样策略参数
outputs:
  - 待检 episode 列表
related_interfaces:
  - POST /api/sample
```

```yaml
id: data-reader
name: DataReader
status: draft
state:
  - 已按帧返回图像 + telemetry 切片
  - 可返回 RGB / Depth 预览 / 原始深度引用
inputs:
  - episode_id
  - frame_index
outputs:
  - RGB 图像帧 (JPEG)
  - 深度预览帧 (JPEG/PNG, 来自 colormap)
  - 原始深度图引用 (uint16 PNG 或 frame path)
  - telemetry 数据片段 (JSON)
data_format:
  - MP4 → JPEG
  - depth_colormap.mp4 → JPEG/PNG
  - depth PNG(uint16, mm) → 原始诊断读取
  - telemetry.npz → JSON
related_interfaces:
  - GET /api/episodes/{id}/frames
  - GET /api/episodes/{id}/depth-preview
  - GET /api/episodes/{id}/depth-raw
```

```yaml
id: metrics
name: Metrics
status: draft
state:
  - 已计算三层粒度的数据指标
  - 段级违规已标记到时间轴
  - L3 核心指标已按 TeleDex v1 规范收口
inputs:
  - telemetry.npz 数据
  - camera_info.json
  - manifest.json
  - metadata.json
  - joint limits / robot config
outputs:
  - episode 级：Q_motion + 10项 L3 指标摘要
  - segment 级：异常段列表 + 红黄级别违规标记
  - frame 级：sync_validation 引用量
  - 给 Manual QC / Auto QC / Report 复用的统一结构化输出
data_format:
  - float32 arrays → dict
  - 段违规标记映射到视频时间轴 (黄色 V^N / 红色 V^E)
L3_v1_core_metrics:
  - ldlj_smoothness
  - action_saturation_rate
  - static_fraction
  - finger_chatter_max
  - path_efficiency
  - tracking_error
  - joint_limit_risk
  - effort_abnormality
  - timestamp_jitter
  - sync_bad_ratio
computation_strategy:
  主工具: Forge
  辅助校验: monalysa (仅内部验证)
  自定义指标:
    - finger_chatter_max
    - path_efficiency
    - tracking_error
    - joint_limit_risk
    - effort_abnormality
    - sync_bad_ratio
  粒度:
    - episode 级: 排序 / 汇总 / 报告
    - segment 级: 2.5s/段, 服务人工 QC 和自动 QC
    - frame 级: 仅保留 sync_validation 引用量
  灵巧手适配:
    - hand qpos/actions 先归一化到 [0,1]
    - chatter 按 per-finger 计算, episode 取 finger-max
    - arm 与 hand 分子系统计算, 不混合阈值
  聚合方式:
    - 分组聚合后得到 Q_motion
    - 非简单平均
```

```yaml
id: auto-qc
name: AutoQC
status: draft
state:
  - VLM + CV 检查已执行
  - L2-L4 判定已生成
inputs:
  - 采样帧图像
  - telemetry 数据
outputs:
  - L2 视觉判定
  - L3 数据质量判定
  - L4 任务完成判定
related_interfaces:
  - VLM API
  - POST /api/qc/auto/{episode_id}
```

```yaml
id: result-store
name: ResultStore
status: draft
state:
  - QC 结果已持久化
  - 当前生效结论与历史 revision 已分离保存
  - batch 汇总已刷新或进入异步重算
inputs:
  - episode_id + 判定结果
  - review_mode
  - reviewer_id
outputs:
  - qc_result 当前生效记录
  - qc_review_revision 历史记录
  - batch_qc_summary 聚合结果
related_interfaces:
  - POST /api/qc/manual/{episode_id}
  - GET /api/episodes/{id}/qc-history
  - GET /api/report
persistence_model:
  episode:
    role: 保存当前 QC 状态与当前结论引用
    key_fields:
      - episode_id
      - qc_status
      - current_qc_result_id
      - current_assignee_reviewer_id
  qc_result:
    role: 保存当前生效 QC 结论
    key_fields:
      - qc_result_id
      - episode_id
      - qc_result
      - primary_reason_code
      - review_mode
      - is_active
  qc_review_revision:
    role: 保存每次提交的历史快照
    key_fields:
      - revision_id
      - episode_id
      - revision_no
      - payload_json
      - operator_id
  batch_qc_summary:
    role: 保存批次聚合统计
    key_fields:
      - batch_id
      - pass_rate
      - top_primary_reason_codes_json
```

### Frontend

```yaml
id: dashboard
name: Dashboard / 主界面
status: draft
state:
  - 下拉搜索已选择任务种类
  - 批次列表已展示，含质检状态颜色标识
  - 可发起手动QC或进入数据库
  - 可进入该任务种类的完整数据库
  - reviewer 可看到我的待办角标
inputs:
  - GET /api/task-types (任务种类列表)
  - GET /api/task-types/{type}/batches (选中种类的批次汇总)
  - GET /api/qc/tasks?mine=true (我的待办)
outputs:
  - 选中批次 + 点击手动质检 → 跳转 manual-qc-ui
  - 选中批次 + 点击进入数据库 → 跳转 database-view
  - reviewer 看到待办入口
  - qc_manager 看到任务派发入口
data_format:
  任务种类: Scanner 动态扫描，下拉搜索选择，支持增删
  批次定义: 一次入库事件 = 一个批次
  入库最小条数: 可配置，默认50条
  批次列表每行: batch_name, episode_count, qc_status, pass_rate
qc_status 二态与颜色:
  未质检 (new): 灰色/默认 — 新入库数据
  已完成 (done): 绿色 — 手动QC完成或复查完成
  按钮联动:
    未质检 → [手动质检] 跳转
    已完成 → [手动质检] 可重新检
  (V1.0 不做自动质检与复查按钮)
related_interfaces:
  - GET /api/task-types
  - GET /api/task-types/{type}/batches
  - GET /api/qc/tasks?mine=true
```

```yaml
id: task-pool
name: Task Pool / 任务派发页
status: draft
state:
  - 主管可查看待派发任务池
  - 可按 batch/reviewer 筛选任务
  - 支持按 batch 批量派发
inputs:
  - GET /api/qc/tasks
  - POST /api/qc/tasks/{id}/assign
  - POST /api/qc/tasks/{id}/close
outputs:
  - 任务已派发，reviewer 待办列表更新
  - assignment_history 已写入
related_interfaces:
  - GET /api/qc/tasks
  - POST /api/qc/tasks/{id}/assign
  - POST /api/qc/tasks/{id}/close
```

```yaml
id: login
name: Login / 登录页
status: draft
state:
  - 用户已登录，session 已建立
inputs:
  - POST /api/auth/login
outputs:
  - 用户跳转到 dashboard
related_interfaces:
  - POST /api/auth/login
  - POST /api/auth/logout
```

```yaml
id: qc-history
name: QC History / 历史与审计页
status: draft
state:
  - 操作员可查看 episode 维度的 QC 历史
  - 管理员可查看系统审计事件列表
inputs:
  - GET /api/episodes/{id}/qc-history
  - GET /api/audit
outputs:
  - 历史 revision 列表
  - 审计事件列表
related_interfaces:
  - GET /api/episodes/{id}/qc-history
  - GET /api/audit
```

```yaml
id: database-view
name: Database View / 数据库页面
status: draft
state:
  - 展示该任务种类下所有批次的所有 episode 明细
  - 可按批次筛选、排序、搜索
  - 可查看批次统计和单条 episode 详情
  - 可对选中 episode 进入质检
inputs:
  - GET /api/task-types/{type}/episodes (全量 episode 列表)
outputs:
  - 选中 episode 进入 Manual QC
  - 跳转至 manual-qc-ui
  - 跳转至 qc-history
  - 打开原因码面板
data_format:
  episode 列表每行: episode_id, batch_name, frame_count, duration, qc_status, pass/fail, reason_code
related_interfaces:
  - GET /api/task-types/{type}/episodes
  - GET /api/episodes/{id}/frames
  - GET /api/batches/{id}
```

```yaml
id: manual-qc-ui
name: Manual QC UI
status: draft
state:
  - 三相机视频同步播放
  - 支持逐帧前进/后退
  - 支持时间轴拖动与点击跳转
  - 时间轴上已标注段级违规区间 (黄色 V^N / 红色 V^E)
  - 遥测曲线叠加阈值线并高亮违规段
  - 右侧面板显示 episode 级摘要 + 关键问题列表
  - 深度信息作为辅助证据可按需展开
  - 操作员已提交判定 + reason_code
inputs:
  - /api/episodes/{id}/frames
  - /api/metrics/{id}  (预计算完成的三层指标)
outputs:
  - L2/L4 手动判定结果
  - reason_code + free_text_note
layout:
  参考: 最终调研报告 §4.5 DQAF 反馈生成模板
  视频区 (60%):
    - 三相机同步播放
    - 默认显示 RGB
    - depth 作为可切换辅助视图，不默认常驻占位
    - 支持单相机 RGB / Depth colormap 切换，必要时支持分屏对照
    - 时间轴标注段级违规 (黄/红区间)
    - 支持逐帧/拖动/点击跳转
  指标摘要面板 (25%):
    - episode 总分 q(τ) (0-10)
    - 子任务完成状态 ([✓][✗])
    - 关键问题列表 (红色标记超标项)
    - 各维度子分: Q_sync, Q_visual, Q_motion, Q_task
  遥测曲线面板 (15%, 可展开):
    - qpos/actions/effort 曲线联动视频帧
    - 阈值线叠加
    - 违规段高亮
  深度使用策略:
    - 用于遮挡、接触距离、物体丢失、RGB证据不足时的辅助核查
    - 默认读取 *_depth_colormap.mp4 作为人工可视化源
    - 原始 uint16 depth 仅用于后端诊断/算法，不直接给人工主视图
  操作员职责:
    - 在自动标注引导下核查视觉质量 (L2)
    - 判断任务完成度 (L4)
    - 必要时调用 depth 辅助核查空间关系
    - 选择 reason_code + 填写备注
    - 提交 pass/fail 判定
related_interfaces:
  - GET /api/episodes/{id}/qc-context
  - GET /api/episodes/{id}/frames
  - GET /api/episodes/{id}/metrics
  - POST /api/episodes/{id}/review-lock
  - DELETE /api/episodes/{id}/review-lock
  - POST /api/qc/manual/{episode_id}
```

```yaml
id: auto-qc-review
name: Auto QC Review UI
status: deferred (V2)
state:
  - VLM/CV 结果已展示
  - 操作员已逐项复核
inputs:
  - AutoQC 结果数据
outputs:
  - 最终判定
related_interfaces:
  - POST /api/qc/auto/{episode_id}
  - POST /api/qc/manual/{episode_id}
```

```yaml
id: qc-reason-codes
name: QC Reason Codes
status: draft
state:
  - 手动QC/复查时可选择标准化原因码
  - 原因码可用于统计和回溯
  - 支持主原因码 + 次原因码
inputs:
  - episode_id
  - qc_result
outputs:
  - primary_reason_code
  - secondary_reason_codes
  - free_text_note
  - review_decision
  - reviewed_segments
data_format:
  - primary_reason_code: enum (required when fail)
  - secondary_reason_codes: enum[] (optional)
  - free_text_note: string (optional)
  - review_decision: enum (optional, for auto_done review)
  - reviewed_segments: object[] (optional)
reason_code 体系:
  L2_视觉类:
    - blur (模糊)
    - exposure_over (过曝)
    - exposure_under (欠曝)
    - color_cast (偏色/白平衡异常)
    - occlusion_hand (手部遮挡)
    - occlusion_object (目标物遮挡)
    - hand_not_visible (手部不可见)
    - fingertip_not_visible (指尖接触区不可见)
    - object_not_visible (目标物不可见)
    - focus_bad (失焦)
    - depth_invalid (深度无效/大面积0值)
    - camera_missing (相机数据缺失)
  L3_轨迹类:
    - motion_abnormal (动作整体异常)
    - chatter (手指颤振)
    - stall (异常停滞)
    - saturation (动作饱和)
    - spike (尖峰/突变)
    - tracking_error (qpos-actions跟踪误差大)
    - joint_limit_risk (接近关节极限)
    - low_smoothness (平滑度差)
    - path_inefficient (路径效率低)
    - effort_abnormal (力矩/电流异常)
    - timestamp_jitter (时间戳抖动异常)
    - sync_bad (同步质量差)
    - tactile_abnormal (触觉异常)
  L4_任务类:
    - task_incomplete (任务未完成)
    - wrong_final_state (最终状态错误)
    - excessive_backtracking (回退/重试过多)
    - grasp_failed (抓取失败)
    - transfer_failed (转运失败)
    - placement_failed (放置失败)
    - subtask_order_wrong (子任务顺序错误)
  系统类:
    - conversion_issue (raw转processed异常)
    - metadata_missing (元数据缺失)
    - device_issue (设备异常)
    - modality_missing (模态缺失)
    - file_corrupted (文件损坏)
    - unsupported_format (格式不支持)
primary_reason_code 规则:
  - fail 时必选且只能选一个
  - pass 时默认可为空
  - 若允许 pass 但记录轻微问题，则只放到 secondary_reason_codes
secondary_reason_codes 规则:
  - 可多选
  - 用于描述伴随问题或轻微瑕疵
  - 不作为主统计口径，主统计以 primary_reason_code 为准
review_decision 枚举:
  - confirm_auto_pass
  - confirm_auto_fail
  - override_auto_result
reviewed_segments 示例:
  - start_sec: 12.4
    end_sec: 14.1
    tag: chatter
    note: right thumb repeated open-close
related_interfaces:
  - POST /api/qc/manual/{episode_id}
  - POST /api/qc/auto/{episode_id}
  - GET /api/report
```
