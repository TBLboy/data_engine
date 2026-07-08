# Current Session

## Last Updated

- 2026-07-08 (QC Agent Phase 1 落地：持久化聊天 + conversation API + 流式 SSE + pageState 上下文，qwen3-vl:32b 模型下载中)
- 2026-07-08 (AI 助手对话体验修复：prompt 重写为文本摘要+对话式指令+对话历史，qwen2.5:7b 不再千篇一律回复，已部署)
- 2026-07-08 (manual QC 遥操作曲线图坐标轴对齐修复：固定 y 轴宽度 + 双图光标解耦 + 拖拽优化，已 push main)
- 2026-07-08 (lerobot-doctor 全部 11 条对标审查完成：5 改造 + 4 不适用 + 2 已有覆盖，DI-01~04 体系完整闭环)
- 2026-07-07 (DI-03 维度健康 + DX-02 扩展：zero-variance、MAD outliers、effort/qvel NaN/Inf 全覆盖)
- 2026-07-07 (arm_mode 生产部署修复：前端重建 + 数据库 migration 补跑 + backend 重启，全站接口恢复)
- 2026-07-07 (BUG提交增强：多图粘贴+暂存草稿，bug-management 适配多图展示)
- 2026-07-07 (BUG提交/管理需求确认：顶部新增 BUG提交按钮，admin 右上角下拉菜单新增 BUG管理入口)
- 2026-07-07 (清除所有启发式猜测逻辑：DOF路径修复 + 删除_detect_dims + manifest替代硬编码匹配 + payloads/scanner清理)
- 2026-07-07 (遥操作曲线视图重构：双面板拆分 + 异常段背景叠加 + 维度显示修正 + DOF检测改为metadata)
- 2026-06-30 (DI-01 改用深度相机真实时间戳替代合成轴：cam_top_depth.timestamps.npy → depth_dt → 仅评分不输出timeline段)
- 2026-06-30 (批量修复：导出UTF-8编码/QC筛选字段/批次checkbox选择/checkbox边框)
- 2026-06-30 (每日凌晨自动扫描入库：APScheduler cron 00:00 UTC 触发 run_minio_scan)
- 2026-06-30 (修复派发重生成数量不稳定 + 旧 QC 痕迹残留：重生成前彻底归零所有 episode QC 状态，3 次 15% 抽样稳定在 10 条)
- 2026-06-30 (修复 manual_qc_status 历史未回填 + 批次判定抽检过滤 + 数据库页面显示：3 个批次成功重判、数据库页面补回 QC 结果列、PENDING_NOT_ADJUDICATED 映射)
- 2026-06-29 (RDDQF v1.2 平台增强完整落地：导出字段扩展14项、导出历史、管理员任务池管理撤回/释放、任务操作日志、审核员卡片管理任务抽屉)
- 2026-06-28 (L3 v2 全部 9 指标 + Score Fusion 重构完成：MQ-01/02/03 + LQ-01/02/03 + DI-01/02 + DX-01，生产部署就绪)
- 2026-06-28 (MQ-01 + MQ-02 算法修正：二阶差分→三阶 jerk；action 一阶→二阶差分；消除稳定加速/匀速快速误报；DROID 数据集结构分析)
- 2026-06-27 (RDDQF L3 v2 MVP 迁移：新四层架构替换旧 L3 v1 指标引擎，前端质量画像 UI，死代码清理)
- 2026-06-27 (修复 settings 页面未部署、遥操作曲线切换、历史审计分页)
- 2026-06-25 (L3 指标计算引擎落地：新建 l3_metrics.py 含 8 项 P0+P1 指标、arm/hand 自动检测、timeline 段生成，替换 payloads.py 手写 6 项指标为 L3MetricsEngine 统一入口)
- 2026-06-25 (L2/L3 质检指标补全启动：L2 视觉指南 + L3 指标计算重构)
- 2026-06-25 (锁机制重构与任务池标签动态扫描)
- 2026-06-25 (双视角深度体验审计 + 10 项正确性修复 + 7 项体验优化，整体复检通过)
- 2026-06-25 (QcTask updated_at, pipeline auto-advance fix, reviewer dashboard bugfix)

## Current Objective

- 以公司内网可直接投入使用为标准推进 Robot QC V1
- 完成 RDDQF L3 v2 MVP 迁移，将 L3 从单层指标引擎升级为四层训练数据质量评估引擎
- 收口任务类型 arm_mode 单/双臂配置，把单臂任务从 L3 统计口径中正确剥离无关手臂维度

## Current Status

- 2026-07-07: 已完成任务类型 arm_mode 第一轮代码落地：TaskType 新增 `both_arms / left_arm / right_arm`，后端 task-types API 与前端任务类型管理页已打通配置入口
- 2026-07-07: L3 真实计算链路已改为从 `episode -> batch -> task_type` 读取 `arm_mode`，并在 `TelemetryParser / L3V2Engine` 中按 arm_mode 过滤 arm/hand 维度；manual QC 展示层按当前决策保持不变
- 2026-07-07: backend `python -m compileall backend/app` 已通过，frontend `npm --prefix frontend run build` 已通过

- 前端页面已从 mock 迁移到后端 API
- 手动 QC 页面已接入真实上下文和提交接口
- 已补齐真实账号鉴权：PBKDF2 密码哈希、HttpOnly cookie session、前端登录态与路由守卫
- 已在隔离 backend 上验证 login / session / protected routes / manual QC submit / logout
- 已通过隔离 Playwright runner 完成浏览器 golden path：login → dashboard → task-pool → manual-qc → qc-history → logout
- 已完成 Docker 容器验收：nginx `/api` 反向代理、login/session/task-pool 联通均已验证
- `episode_000099` 已接入真实样例 metrics / timeline 读取链路
- 后端默认启动已移除 `create_all + seed_demo_data`，不再自动建表或灌入 demo 数据
- 新增显式初始化入口 `python -m app.services.bootstrap --admin-username ... --admin-password ...`，用于建库并创建首个管理员
- 后端已补 `APP_ENV` / `FRONTEND_ORIGIN` / `EXTRA_FRONTEND_ORIGINS` / `SESSION_COOKIE_SECURE` 配置，并在 production 下拒绝默认 `SECRET_KEY` 与 SQLite 部署
- 登录页已移除默认管理员与初始密码展示，避免继续传递 demo 假设
- compose 与部署说明已切到 PostgreSQL 基线，并要求显式初始化后再启动业务服务
- 已落地真实扫描入库链路：`/api/database/scan`、`ingest_jobs` 持久化、source fingerprint 幂等跳过、批次来源路径与 task type 自动归类
- `database` 页面已接入真实扫描请求与入库任务列表展示，错误提示已改为读取后端返回的 `detail`

## Current Risks

- 任务类型 arm_mode 已完成代码落地，但尚未对真实单臂任务样本做一轮人工比对验证，当前还未确认动作密度/停滞类指标在业务样本上的变化幅度
- arm_mode migration `20260707_0017_task_type_arm_mode.py` 已新增，但尚未说明当前运行环境是否已实际执行到库
- manual QC 展示层本轮按业务决策保持不变，因此质检员界面不会额外提示当前任务的 arm_mode；这不是缺陷，而是当前明确的范围收口
- 已把 `task_type:unclassified` 固化为系统保底任务类型：禁止编辑、禁止删除；删除普通任务类型时，其关联批次会自动回收到 `待分类`，不会破坏 batch / episode / QC 历史
- 已完成任务派发主流程第一轮重构：工作台 `dashboard` 已承接 batch 级任务生成与批量派发工作区，`task-pool` 已降级为任务明细中心；`manual-qc` 继续只保留 claim/release/提交质检结果链路
- 已落地派发版本语义与批量分配能力：新增 `Batch.active_dispatch_generation`、`QcTask.dispatch_generation/is_active/assignment_mode`，`dispatch-plan` 现在会退役旧版本未开始任务并切换活跃派发版本；新增 `dispatch-assign` 批量派发接口，支持平均派发和自定义每人条数
- 已完成运行态验证：production compose 中已成功升级 Alembic `20260624_0005_dispatch_generation`，`/api/dashboard` 与 `/api/task-pool` 都已返回新的 `dispatchPreviews/reviewerAccounts` 结构；对 `batch_871627c45789aecb` 走通了 sampled → full → sampled 重生成流程，当前版本最终稳定在 `activeDispatchGeneration=4` 且旧任务被累计退役 `264` 条，不再继续污染当前视图
- 已增强 `database` 页筛选交互：批次、QC 状态、QC 结果下拉框均支持键盘输入筛选，方便后期大量 batch 下快速定位
- 已在生产 API 层验证任务类型管理闭环：创建任务类型成功、`待分类` 批次池查询成功、attach/detach 往返成功、普通任务类型删除后批次成功回到 `待分类`、`待分类` 自身编辑/删除被拒绝
- 已明确 `yaocao` bucket 全量扫描原则：扫描器不能假设 list 固定在第一层或第二层，而应递归遍历所有层级 prefix，并用“直接子级命中 `raw/`、`processed/`，且其下存在 `episode_xxxxxx/`”的结构特征识别 list，确保 `yaocao/<list>/...` 与 `yaocao/K1/<list>/...` 都不会漏扫
- 已完成 `database` 页面长期性能方案首版落地：`/api/database` 现已支持 `page/page_size/keyword/batch_id/qc_status/qc_result` 服务端分页与服务端筛选，前端 `database-view.vue` 改为按页请求并接入 `el-pagination`，不再在浏览器内对全量 4000+ episode 做本地过滤与整表渲染
- 已修复 `task-pool` 派发名单来源错误：任务派发页面现改为读取启用中的 reviewer 账号目录，而不再错误复用 `reviewerWorkloads` 历史统计；新建的 `审核员01/02/03` 已在运行中 backend 的 `task_pool_payload()` 中确认出现在 `reviewerAccounts`
- 已收口 `task-pool` 四块统计卡片显示方式：待派发 / 已派发 / 审核锁激活 / 已完成 现在使用局部固定展示样式，不再在卡片体内出现无意义滚动条；相关 frontend/backend 镜像均已重建并在 production compose 中重新启动
- 已完成 UI 组件外观系统抽象：新建 `frontend/src/styles/components.css`，定义 `qc-card`、`qc-stat-card`、`qc-select`、`qc-table`、`qc-progress` 五个抽象外观类，将散落在 style.css 和各页面 scoped style 中的重复组件样式统一提取；所有页面已完成批量替换，style.css 清理 ~100 行冗余；后续同类组件自动保持外观一致
- 已将"任务明细中心"菜单和页面标题更名为"人工质检入口"
- 已修复人工质检入口批次下拉框边框不可见问题（白框在白底上消失），通过全局 `--el-input-border-color` 设为 `#c0c4cc` + 对该下拉框显式加蓝色边框
- 已删除工作台 `dashboard` 中重复的扫描任务面板，四个统计卡片改为固定高度无溢出
- 已给工作台批次派发总览表格补上选中行高亮（蓝底 + 左侧蓝色强调条）、滚动条常驻深灰色、进度条轨道灰色化、选中行内 tag 白框修复

- 已明确 manual QC 的 MinIO 对象访问协议：预览/播放类 MP4 采用后端签发的短时 presigned URL，`manifest.json`/`metadata.json`/`telemetry.npz` 等结构化对象继续由后端读取解析，显式下载/导出保持后端受控接口
- 已落地 manual QC 同步播放器首版：底部 frame 控制栏成为唯一播放控制权，三路视频去掉独立 controls，统一按共享 `currentFrame/currentTimeSec/playing` 同步播放、暂停、逐帧和拖动 seek，并开始使用后端返回的真实 `fps/durationSec/frameCount` 驱动时间轴显示
- Node F 控制面业务规则已闭环：扫描、状态推进、object_role、classification_rules 与 manual QC 对象访问协议均已落定，下一步进入 Node D 实现规划与 API/前端合同改造
- 已在 scan API 切换后继续收口下游链路：`database/dashboard` 扫描任务视图已全部改为 bucket/scope 语义，`BatchSummary` 已切到 `bucket + storagePrefix`，frontend mock 已同步为 MinIO 字段
- manual QC 真实上下文已从本地 processed 目录读取切换为基于控制面 `episode_inventory + episode_objects + lists` 的 MinIO 对象读取；后端直接从 MinIO 拉取 `manifest.json` / `metadata.json` / `telemetry.npz` 生成 metrics 与 timeline，不再参与旧本地扫描目录逻辑
- 已继续推进旧本地字段清理：新增 `app/services/authz.py` 承接权限校验，旧 `app/services/ingestion.py` 与 `models/ingest.py` 已从运行路径删除；同时新增 Alembic revision `20260623_0003` 用于删除 `ingest_jobs`、`batches.storage_path`、`episodes.source_path/source_hash/ingest_status`
- 已完成真实浏览器媒体验收：Playwright 直接打开生产态 manual QC 页面，观察到 `videos=3`、`refreshVisible=true`、`downloadButtons=3`，说明真实视频元素已经在浏览器侧渲染成功
- 生产 HTTP 扫描入口已进一步稳定：最新 job `queued_1782241730_user_admin` 已在生产环境从 `scanning -> classifying -> done` 完整走完，最终结果为 `confirmed_lists=42`、`total_episodes=4097`、`new_episodes=69`，说明公网/内网入口 + 后台 worker + PostgreSQL/MinIO 联动链已能在真实环境闭环完成
- 生产扫描过程的可观测性已补齐：`scan_jobs.error_detail` 现在会在 running/classifying 阶段暴露 `prefixes=...` / `lists=... episodes=... new=...` 进度信息，前端 `ingestJobs` 也能看到非 0 进度，避免“后台在跑但前台永远 0/0/0”
- 已完成管理员/质检员双视角真实浏览器（chromium）深度体验审计，产出调研报告 `audit-report-draft.md`，按正确性（坏了吗）+ 可用性（反人类吗）两个维度记录发现；并把方法论沉淀为可复用 skill `~/.claude/skills/multi-role-ux-audit`
- 已修复派发抽检% 静默重置（HIGH）：dashboard 派发工作区百分比输入框由 `v-if` 改 `v-show` 保住值，生成前加二次确认显式展示模式/比例，杜绝 `full→sampled` 切换后静默按 100% 过量派发整批
- 已修复任务状态机 `assigned+fail` 黑洞（HIGH）：`apply_dispatch_plan` 重派发时跳过已 `done` 的 episode（不再拉回 new/assigned 却残留旧 `qc_result`）；migration `20260625_0007` 订正存量矛盾态，生产库矛盾态已归零，`episode_000020` 由 `assigned+fail` 订正为 `assigned+pending`
- 已修复根路径 `/` 白屏崩溃（HIGH）：router 根路由由自我重定向 `redirect:'/'` 改为 `redirect:'/login'`，消除无限重定向栈溢出；chromium 实测 `/`→`/login` 无 pageerror、`#app` 正常渲染
- 已修复 `/api/task-pool` 对 reviewer 越权（MEDIUM）：`task_pool_payload` 按角色裁剪，reviewer 仅返回自己的任务/批次、`reviewerAccounts/Workloads` 清空；admin 仍全量；API 实测 reviewer 拿 3 批次/41 任务、accounts/workloads=0
- 已修复任务类型“删除”文案撒谎（MEDIUM）：保持软停用语义（保护审计/历史引用），前后端文案统一为“停用”
- 已修复跨页计数不一致 / 幻影批次（MEDIUM）：统一以“有 active ListRecord 的批次”为唯一业务口径，`_refresh_task_type_stats`/`history_payload`/`build_history_report_payload` 全部对齐（新增 `task_type_active_counts`）；migration `20260625_0008` 重算存量计数，待分类由 5/304 订正为 4/303（与 database 总库一致，排除 `raw_data` 残留批次）
- 已修复审核锁未释放（MEDIUM）：manual-qc 改用 `onBeforeRouteLeave` 可靠释放自己的锁；后端 `release_manual_qc` 允许 `admin/qc_manager` 强制释放他人锁，前端补“强制释放”入口
- 已补派发可发现性（MEDIUM）：派发工作区醒目显示“待派发”与“未纳入派发 N 集”，避免任务停留 new 导致 reviewer 无活可干
- 已修复质量评分环（MEDIUM）：固定展示综合 `Q_motion`，不再随严重度排序变化
- 已加任务类型名输入校验（MEDIUM）：非空 + ≤50 字符 + 禁尖括号，覆盖创建/重命名
- 已完成体验优化一组（LOW）：登录错误只渲染 `detail` + 空值客户端校验、工作台默认选“有批次”的任务类型、manual-qc 返回按钮按角色对齐标签与去向、对象下载按 `mimeType` 给扩展名、无媒体（0 帧）集禁用播放控件、全局中文 Element Plus locale（确认框 OK/Cancel 等中文化）
- 已完成整体复检：重建 backend/frontend 镜像、`alembic upgrade head`（0007/0008）、生产栈重启 Healthy；db/API 实测矛盾态=0、待分类 4/303、reviewer 越权已堵、admin 全量对照正常；chromium 实测根路径不白屏、admin dashboard 派发工作区正常渲染
- 已明确 L2/L3/L4 四层质检体系的人机分工：L1 硬性门控 = 上游 TeleDex 平台负责；L2 视觉质量（模糊/过曝/遮挡/抖动）与 L4 任务完成度 = 质检员人工判断；L3 遥操作轨迹质量 = 程序自动计算（当前仅手写 6 个 numpy 指标，业务文档调研了 Forge 8+3 指标体系但未落定选型与阈值）
- 已规划 L2/L3 补全工作：任务 1 = 编写质检员视觉检查指南文档（L2 指标人工判读清单）；任务 2 = L3 指标计算方案从概念级扩充到可执行级（技术选型 Forge、细颗粒度业务逻辑含公式+阈值+灵巧手适配、代码落地替代手写 numpy、独立指标说明文档供审查）
- 已确认当前 manual QC 指标计算的 raw/processed 数据依赖关系：取 processed 前缀下的 telemetry.npz（474-489 行），无 processed 时 fallback 已从 demo 假数据改为空数组（诚实返回无指标）
- 已完成 L2 视觉质检指南（任务 1）：编写《数采人员操作规范.md》，含数采人员 3 条采集规范 + 质检员 6 项 L2 视觉检查项（模糊/过曝/遮挡/抖动/深度图异常/动作流程完整性），每项有判定标准（正常/警告/不合格）和重点关注说明
- 已完成原因码汉化：QcReasonPicker 的 20 个中英文原因码映射（L2 视觉类 6 项 / L3 轨迹类 6 项 / L4 任务类 4 项 / 系统类 4 项），后端存储不变，纯前端显示层
- 已完成异常段标签汉化：timeline 的 sync_bad→同步异常、tracking_error→跟踪误差、high_velocity→高速运动
- 已完成视频安全加固：移除所有视频面板的"下载对象"按钮（downloadMedia 函数 + downloadingObjectId + downloadManualQcObject import 全部清除），video 元素加 `disablePictureInPicture` 禁用浏览器小窗播放
- 已完成 L3 指标计算引擎落地：新建 `backend/app/services/l3_metrics.py` 独立模块，含 8 项 P0+P1 指标（平滑度/无效动作/动作饱和/停滞/时间戳抖动/跟踪误差/手指颤振/执行力度）及 Q_motion 加权合成，支持 arm/hand 维度自动检测（基于 qpos 值域判断 rad vs 0-255），timeline 段逐帧生成+merged；`payloads.py` 中 `_build_real_manual_qc_context` 已切换为 L3MetricsEngine 统一入口，旧手写 6 项指标逻辑已移除
- 已验证真实 MinIO telemetry 数据的 arm/hand 维度结构：单臂 7+6 或双臂 14+12，含零值维度过滤；L3 指标在 batch_3585f01e8960f236_episode_000026 上产出 9 条指标卡片 + 7 个 timeline 段
- 已完成 L3 超参数配置页面：新增 `l3_config` 表 + migration `20260625_0009`，后端 `GET/PUT /api/admin/l3-params` 仅限 admin，前端 `/settings` 页面含 10 组 32 项参数输入，修改即时生效
- 已完成遥操作曲线联动视图：新增 `GET /api/episodes/{id}/telemetry-curve` 返回 arm/hand 分维 qpos+actions 时序数据（>500 帧自动降采样），前端 manual-qc.vue 集成 Chart.js 多系列折线图，实线=qpos 实际位置、虚线=actions 目标位置，支持 arm/hand 切换
- 已完成 L3 优化第一轮：修复 sync 阈值硬编码→使用 `sync_bad_threshold_ms`、修正 `_sliding_window_mask` 卷积实现替代错误的 cumsum、LDLJ `max_val`→`ldlj_max_val` 可配置、dead/static timeline 标签区分（动作消失 vs 运动停滞）、简化 `_merge_segments` 双 pass→单 pass、移除未使用 import
- 已完成多角色审查与修复：
  - [HIGH] PermissionError 返回 HTTP 500→修复为 403（新增全局 exception handler）
  - [LOW] 清理 payloads.py 中已废弃的 `_metric_level`/`_window_to_segment`/`_merge_segments`（~70行）
  - API 级验证：reviewer 越权返回 403、admin 全端点 200、L3 params 31 键完整、Q_motion weights 和=1.00、telemetry curve 数据结构正确
  - [MEDIUM] telemetry curve 加错误状态（替代永久 loading）、lock panel 加 z-index 防侧边栏遮挡
  - Reviewer 浏览器审计 8 项发现已处理；Admin 浏览器审计 10 项发现中 settings 页面已验证可用、账号创建标签已确认存在
- 已修复 settings 页面未部署问题：Dockerfile 仅复制预编译 dist/，settings.vue 含 TS 编译错误（未使用 computed/getLabel）导致 npm run build 失败，dist 中缺少 settings-*.js。修复 TS 错误后重新 build + deploy，页面正常可用
- 已修复遥操作曲线 arm/hand 切换无响应：根因是 Chart.js 不允许同一 canvas 创建第二个实例，切换模式时 renderChart() 未先销毁旧 Chart。修复为 watch(curveMode) 中先 destroyChart() 再 renderChart()
- 已完成历史审计页面分页改造：Revision 时间线（每页20条，共26条）和系统审计事件（每页50条，共198条）从一次全量返回改为服务端分页，后端 history_payload 新增 revision_page/size 和 audit_page/size 参数，前端加入 el-pagination 控件

## Current Risks

- 当前真实入库和业务模型中仍残留旧本地字段：`episodes.source_path`、`batches.storage_path`、`ingest_jobs.source_path` 及旧 `app/services/ingestion.py` 尚未从仓库彻底移除，后续还需补 migration 与模型清理，避免“代码已不走、结构仍滞留”
- MinIO manual QC 当前已切到对象读取，但 media descriptor / presigned preview URL / refresh/download 接口仍未落地，视频区仍是占位 UI，Node D 合同还有后续实现工作
- 当前 scanner 已能生成 batch/episode 业务行，但 task type 仍主要依赖 basename 规则 seed，后续还需要补 task-type 管理接口、人工确认入口与浏览器端到端验证
- 当前虽已明确 bucket 全量扫描必须做递归结构识别，但 `raw_only`、`processed_only`、父子 prefix 同时命中的边界判定和重扫幂等策略还未落成正式字段设计
- 当前仍未确认是否存在“显式任务字段”可直接从单个 episode 元数据稳定提取；因此任务类型设计必须允许规则推断和人工回写，而不能把 MinIO 路径字符串直接当最终业务分类键
