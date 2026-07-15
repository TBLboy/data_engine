# Business Logic Nodes

## Node A: 项目启动，调研目标确定

```yaml
id: A
name: 项目启动，调研目标确定
status: stable
state:
  - 调研目标已明确：研究公开数据集QC方法
  - 数据平台已确定：Linker Open TeleDex
  - 调研范围已确定：公开数据集 + 数据格式分析 + QC方案建议
inputs:
  - 用户需求：调研机器人数据集质检与清洗方法
outputs:
  - 调研计划
  - requirements.md已创建
data_format:
  - 文档（Markdown）
related_hardware:
  - None（纯调研启动）
verification:
  - requirements.md已创建并确认调研目标
notes:
  - 这是调研项目的启动节点
```

## Node B: 公开数据集QC调研

```yaml
id: B
name: 公开数据集QC调研
status: stable（大部分完成）
state:
  - DROID数据集QC调研已完成
  - RH20T数据集QC调研已完成
  - DQAF、Consistency Matters、Forge 调研已完成
  - 报告扩展到 19 数据集/生态覆盖
  - B3（数据策展框架）暂缓，待评估是否需要深入
inputs:
  - DROID、RH20T等公开数据集文档
  - 数据质量评估论文（DQAF、Consistency Matters等）
  - TeleDex平台内置QC能力理解
outputs:
  - 报告 01：公开数据集隐式QC策略（19数据集覆盖，已完成）
  - 报告 02：数据质量检测框架（DQAF + L3深度调研，已完成）
  - 报告 03：数据策展框架（暂缓）
data_format:
  - 文档（Markdown）
  - 数据分析脚本（Python）
related_hardware:
  - None
notes:
  - B 节点已经完成主要产出，剩余 B3 可根据时间决定是否继续深入
```

## Node C: Linker TeleDex 数据格式深度分析 + MinIO 实查

```yaml
id: C
name: Linker TeleDex 数据格式深度分析 + MinIO 实查
status: stable（已完成）
state:
  - TeleDex官方数据说明文档V3.0已完整阅读（19页）
  - telemetry.npz完整schema已记录（含ee_poses_*, imu_*, tactile_*, sync_validation_*）
  - 目录结构、三种转换方式、对齐参数已理解
  - 平台内置QC能力已识别（同步校验、结尾裁剪、sync_error统计）
  - MinIO 对象存储连通性已验证：凭据可正常列出 bucket
  - `yaocao` bucket 对象布局实查完成：list 多层分布、raw/processed 结构、episode 数量范围
  - `manifest.json`、`metadata.json`、`recording_info.json` 样例元数据已读取
  - manual QC 真实依赖（processed 层关键对象）已确认
inputs:
  - doc/Linker Open TeleDex数据采集系统-数据说明文档.pdf
  - MinIO 凭据与环境
outputs:
  - api/teledex-data-format.md（工程记忆摘要，已完成）
  - MinIO 对象布局与元数据分析记录（已完成）
  - 三条基础业务规则：list定义、episode三层状态、task_type归类（已完成）
data_format:
  - raw: MCAP + device_info.json + recording_info.json + metadata.yaml
  - processed: telemetry.npz + camera_info.json + manifest.json + metadata.json + cameras/
  - MinIO: bucket/list_prefix/{raw|processed}/episode_xxxxxx/...
related_hardware:
  - None
notes:
  - C 节点产出已全部完成，可以作为下一阶段的基线
  - MinIO 实查确认原本的"推测性架构分析"推进成了"可落地约束"
```

## Node F: MinIO 数据湖控制面方案设计（当前节点）

```yaml
id: F
name: MinIO 数据湖控制面方案设计
status: stable（control-plane 业务规则已闭环，可交接 Node D）
state:
  - PostgreSQL 控制面模型已确定：MinIO = raw storage only
  - list 定义与全量扫描规则已确定：全层级递归 + 结构特征识别
  - episode 状态模型已确定：ingestable / processable / qc_ready
  - task_type 控制面归类方案已细化：prefix 规范化 + 分层 seed 规则 + 人工确认
  - 控制面 schema v0.2 已产出：6 张新表 + 扫描器实现级规则 + object_role/qc_ready 清单
  - 扫描器状态机已细化：scanning → classifying → episode_inventory → done/failed
  - 幂等策略已细化：UNIQUE 约束 + UPSERT + no-DELETE + 单调状态推进
  - 父子 prefix 排重规则已细化：deepest-match + 父级独有 episode 保留
  - object_role 规范化字典已确定：required/optional/not-used/unknown 四类
  - classification_rules 结构已细化：candidate_label、match_scope、is_authoritative、冲突优先级、manual override 保留
  - episode → episodes/batches 下联 ingestion 链路已定义
  - 真实 `yaocao` basename 首版盘点已完成：36 个结构命中、35 个业务样式 basename、1 个 `raw_data` 技术子分支
  - authoritative seed 范围已收敛到单义单物料 token：`huanggua`、`huangguakuai`、`tudou`、`tudoutiao`、`luobo`
  - suggest-only / no-match 首版边界已明确，可直接产出 migration seed 草案
  - task_type 不再作为扫描器自动决定的正式归类结果，而是转为 `admin/qc_manager` 维护的业务主数据
  - 新批次默认进入 `待分类`，已人工分类 batch 的任务类型在后续 rescan 中保持不变
  - 任务类型管理业务流已补充：创建/重命名/删除任务类型、从 `待分类` 加入 batch、从任务移出 batch 回到 `待分类`、错分 batch 通过“移出再加入”纠正
  - 数据总库在这一业务流中承担“确认批次当前归属”的查询职责，后续需要补批次/QC状态/QC结果下拉框的键盘检索能力
inputs:
  - MinIO 实查结果（Node C 产出）
  - 三条基础业务规则
  - PostgreSQL 现有 schema（episodes/batches/ingest_jobs/task_types/qc_tasks）
  - 用户关于"多次少量写入"、"百分比派发"等实际使用场景输入
outputs:
  - control-plane-schema-v1.md（v0.2：6 表 + 扫描器实现级规则 + 状态推进 + object_role 字典 + classification_rules 首版真实 seed 盘点 + 对象访问协议，已产出）
  - classification_rules 首版 seed 清单（authoritative / suggest-only / no-match 边界已定义）
  - manual QC 对象访问协议业务规则（已产出）
data_format:
  - 文档（Markdown）
  - Schema 设计（SQLAlchemy-ready 字段定义）
related_interfaces:
  - boto3 (MinIO S3 SDK)
  - PostgreSQL (Alembic migration)
  - Backend API (FastAPI)
verification:
  - 现有 schema（episode/batch/ingest/task_type/qc）已复核，新表无冲突
  - 扫描、状态、清单、归类四块规则已补齐到可直接指导实现级别
  - 真实 `yaocao` basename 样本已盘点并形成首版 seed review table
  - manual QC 对象访问协议已结合现有 backend/frontend 合同完成约束分析
notes:
  - Node F 的控制面业务规则已闭环，下一阶段进入 Node D，把 seed 规则落成 migration，并将 manual QC 与 media access 改造成 MinIO 版本
  - 代码实现仍未开始，继续遵循先完善业务逻辑再落代码
```

## Node D: 基于 MinIO 数据湖架构的 QC 方案落地

```yaml
id: D
name: 基于 MinIO 数据湖架构的 QC 方案落地
status: active（进行中）
state:
  - QC 指标体系已建立（27项，L1-L4）
  - manual QC 页面已接入真实 telemetry 指标
  - review lock/并发保护已实现
  - manual QC 媒体访问协议已确定：媒体预览走短时 presigned URL，结构化对象/下载走后端受控接口
  - 任务派发主流程已重构：工作台 dashboard 承接 batch 级生成与批量派发，task-pool 降级为明细中心
  - 派发版本语义已落地：active_dispatch_generation + is_active + supersede 旧任务
  - 统计卡片、滚动条、下拉框边框、进度条轨道等组件外观已统一抽象到 components.css
  - 子评分指标已支持按严重程度排序（红→黄→绿）并带滚动容器
  - 任务类型管理页已支持搜索过滤与滚动浏览
  - 当前正在实施：角色视图分离 + reviewer 流水线质检模式 + 完成庆祝动画
  - 数据总库资产画像升级路线已确认：采用 Route C'，后续以显式 Batch–List 关系、批次级派生投影、PostgreSQL 持久化 dirty 队列和周期性对账作为正式实现边界
  - 数据总库长期正式形态不再继续依赖 Episode 实时聚合主路径，也不再把新增画像字段持续堆入 `batches`
  - 数据总库资产 summary 与 batch profile 的统一统计作用域已冻结为 `active_list_active_batch_indexed_episodes`
inputs:
  - QC 指标体系（Node B 产出）
  - MinIO 控制面方案（Node F 产出）
  - 现有 manual QC / dashboard / task-pool 代码
  - 数据总库资产画像改造任务说明 + Route C' 架构决策
outputs:
  - reviewer 个人任务看板（新页面 `/reviewer`）← 待实现
  - task-pool reviewer 版（同路由按角色分支渲染）← 待实现
  - manual QC 流水线模式（提交后自动跳转下一条）← 待实现
  - 完成庆祝动画（canvas-confetti + Web Audio API）← 待实现
  - 角色路由守卫与菜单过滤 ← 待实现
  - 数据总库总体资产 summary API（正式接口边界：`GET /api/data-assets/summary`）
  - 数据总库批次级资产画像 API（正式接口边界：`GET /api/data-assets/batches`）
  - 数据总库资产画像手动全量重建入口（正式接口边界：`POST /api/data-assets/rebuild`）
  - `batches.list_id` 显式关系 + `batch_asset_rollups` 批次级统计投影 + `batch_asset_recompute_jobs` 持久化 dirty/recompute 队列 + 周期性对账
data_format:
  - 文档（Markdown）
  - 代码（Python/Vue）
notes:
  - D 节点将基于 Node F 的控制面设计来改造现有 QC 流程
  - 当前 manual QC 依赖本地文件系统，需迁移到 MinIO
  - 角色视图分离是 D 节点的前端体验子任务，不改变后端 QC 数据模型
  - 数据总库资产画像属于 D 节点内部的读模型升级子路线：事实源仍是现有控制面/业务面/QC 面表，新增的是可重建的批次级统计投影层
  - `/api/database` 继续承接 Episode 明细浏览；数据资产聚合不再以它作为长期主路径
```

## Node D2: 训练数据消费与批次驳回模块

```yaml
id: D2
name: 训练数据消费与批次驳回模块
status: design（业务规则已确认，代码未开始）
state:
  - LaTeX 设计文档已产出 (dataset_consumption_batch_rejection_agent_guide.tex)
  - 关键修正：失败率分母由"批次总数"改为"抽检数"
  - 三层状态模型已定义：ManualQcStatus → BatchDecision → FinalDatasetStatus
  - 设置页将新增"通用"tab，承载驳回阈值参数
  - 前端新增"训练数据集管理"页面 (/dataset-management)
  - 支持导出合格 episode 元数据清单 (CSV/JSON)
inputs:
  - 现有 Batch/Episode/QcTask 模型
  - QC 结果提交流程 (qc.py submit endpoint)
  - 设计文档 LaTeX 文件
outputs:
  - Batch 表新增字段 (batch_decision, reject_threshold, failure_rate, etc.)
  - Episode 表新增字段 (manual_qc_status, final_dataset_status, final_decision_source, is_exportable)
  - BatchDecisionLog 审计日志表
  - BatchAdjudicationService（幂等判定逻辑）
  - DatasetSummaryService / DatasetExportService
  - 后端 API：/api/dataset/* 路由组
  - 前端页面：训练数据集管理 (/dataset-management)
  - 设置页"通用"tab + 驳回阈值参数
data_format:
  - 文档（LaTeX + Markdown）
  - 代码（Python/Vue）
notes:
  - 失败率公式（核心修正）：R_fail = N_fail_manual / N_sampled（NOT N_batch）
  - 驳回阈值默认 0.10，首版上线后需根据真实数据校准
  - 判定幂等，可重复执行不产生不一致
  - 导出只含 QUALIFIED episode 的元数据，不直接导出 MinIO 大文件
```

## Node E: 完整项目交付

```yaml
id: E
name: 完整项目交付
status: draft（未开始）
state:
  - 完整调研报告基线章节已完成
  - MinIO 数据湖方案待整合
  - 最终交付物待确认
inputs:
  - 公开数据集QC调研文档
  - Linker TeleDex数据格式分析
  - MinIO 数据湖方案
  - QC 方案与实现
outputs:
  - 完整项目文档（Markdown格式）
  - 可交付给领导的文档
data_format:
  - 文档（Markdown）
notes:
  - 这是项目的最终交付节点
  - 交付范围需结合 MinIO 数据湖方案和用户实际使用场景决定
```
