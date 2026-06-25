# Current Session

## Last Updated

- 2026-06-25 (QcTask updated_at, pipeline auto-advance fix, reviewer dashboard bugfix)

## Current Objective

- 以公司内网可直接投入使用为标准推进 Robot QC V1
- 推进存储架构从“本地 processed 目录 + PostgreSQL”升级为“MinIO 原始对象存储 + PostgreSQL 元数据/QC 湖仓协同”

## Current Status

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
- 本地历史 SQLite 库已补齐 `users.is_active`、`users.password_changed_at`、`episodes` 入库字段与 `ingest_jobs` 表，旧库可以继续用于当前阶段联调
- 已在隔离 `.conda-env` 中成功执行真实样例扫描：`/home/tbl/Project/data_collect/data/raw/process` 导入 1 条 episode，入库任务状态为 `indexed`
- 已落地 review lock 状态机：manual QC 支持 claim / release / lock expiry / optimistic version 并发保护，后端冲突已按 403/409 语义返回
- 已补齐账号生命周期能力：管理员可创建账号、重置密码、启停账号；停用账号会被拒绝登录，且当前登录管理员不可自停用
- 已完成账号生命周期后端联调验证：管理员/主管账号列表访问、reviewer 禁止访问、创建/重置密码/启停/停用后拒绝登录均已确认
- 前端开发态已改为保持浏览器同源 `/api` 请求，并通过 `VITE_PROXY_API_TARGET` 对齐当前 backend，避免跨域预检导致的 session bootstrap 失败
- 前端请求头逻辑已修正：仅在存在 JSON body 时附加 `Content-Type: application/json`，`/auth/session` 等 GET 不再强制带 JSON 头
- 已重新跑通隔离 Playwright golden path：`login → dashboard → task-pool → manual-qc → qc-history → logout`，最新结果为 `1 passed (3.2s)`
- manual QC 浏览器验证已兼容 `认领任务/重新认领` 两种锁状态文案，并修正 Element Plus `Fail` 单选交互脚本
- `qc-history` 已补齐批次报告与 JSON 导出能力：后端提供 `/api/qc-history/report`、`/api/qc-history/export`，前端历史页已接入批次切换、报告总览与按范围导出
- 已在新鲜隔离运行时验证 `qc-history` 报告/导出接口与浏览器交互：`scope=report|episodes|audits` 均返回正确 payload，专用 Playwright 用例已通过 `1 passed (2.5s)`
- 已引入正式 Alembic migration 基线：新库通过 `upgrade head` 建表，已有业务表但无版本表的旧库会先执行 SQLite 兼容补齐，再 `stamp head` 纳入版本管理
- 已补齐账号页非管理员浏览器与 API 复核：`qc_manager` 可见 `/accounts` 但仅只读，`reviewer`/`viewer` 不显示账号菜单且直达 `/accounts` 会被路由重定向回 `/dashboard`
- 已通过专用 Playwright 用例验证 task-pool 多批次选择稳定性：空批次、全量批次、可操作批次切换后均能保持正确渲染，刷新后仍保留有效批次选择，结果 `1 passed (2.8s)`
- 已完成真实 Docker/PostgreSQL 发布链路验收：启动 compose Postgres、运行 Alembic `upgrade head`、执行显式管理员初始化、重启 production backend/frontend，并验证 `/api/auth/login` 登录成功
- 已修复 backend 容器内 `app/core/config.py` 的路径推导缺陷，避免 `/app` 场景下 `PROJECT_ROOT = BASE_DIR.parents[1]` 触发 `IndexError`
- 已补上 `/api/health` 健康检查接口，使部署文档中的健康探针地址与当前运行时保持一致
- 已完成 MinIO 数据湖化第一轮业务分析：当前系统仍以本地 `source_path/storage_path` 和本地文件读取为主，尚未具备对象存储对象清单、bucket/prefix 关联、presigned/代理访问等能力
- 已明确后续业务方向：MinIO 仅存原始对象数据，PostgreSQL 负责 episode 元数据、批次、账号、任务、QC 结果、审计与对象映射；前端继续只调后端 API，不直接耦合 MinIO 路径
- 已完成 MinIO 连通性与对象布局实查：凭据可正常列出 bucket，当前主要业务数据集中在 `yaocao` bucket；样例结构已确认是“任务前缀/processed/episode_xxx”与“任务前缀/raw/episode_xxx”两层并存，其中 manual QC 真正依赖的是 `processed` 前缀下的 `manifest.json`、`metadata.json`、`telemetry.npz`、多路 `mp4` 与时间戳/深度对象
- 生产部署已收口到真实本机环境：`software/deploy/.env` 已写入私有 `SECRET_KEY`、`POSTGRES_PASSWORD`、MinIO endpoint/credentials 与默认 bucket `yaocao`，compose 生产栈现在可直接在本机启动并连接真实 MinIO 数据
- `software/deploy/README.txt` 已扩展为迁移部署手册，覆盖 secret 生成、`.env` 结构、首次 bootstrap、已有 PostgreSQL 卷改密、真实 MinIO 验证与跨机器迁移步骤
- 已完成真实 MinIO 生产栈现场验收：数据库页面可读取真实 episode/批次/最近扫描任务；并确认扫描触发接口是 `POST /api/database/scan`，`GET /api/database/scan` 不提供状态读取
- 当前完整浏览器自动验收仍受本机 Firefox/Playwright headless 启动异常阻塞，错误包含 `RenderCompositorSWGL failed mapping default framebuffer`；因此本轮 database 页面验证以真实部署、API 观测、源码复核和用户现场浏览为主
- 已收口 `database` 页面重复扫描入口：顶部 `扫描入库` 已删除，仅保留扫描卡片内的单一主入口，并统一文案为 `扫描入库`
- 已修复 production 扫描任务鲁棒性缺陷：`/api/database/scan` 不再依赖 request-bound `BackgroundTasks` 执行长扫描，而是改为在服务进程内独立线程启动扫描 worker；页面刷新、关闭或请求返回后，扫描都会继续推进，不会因为 HTTP 生命周期结束而卡死在 `scanning`
- 已修复扫描任务时间展示错误：后端现在按 `APP_TIMEZONE`（默认 `Asia/Shanghai`）把 UTC 数据库时间转换后再返回前端，`startedAt/finishedAt` 与本地实际观察时间已对齐
- 已在生产库中手动失效两条历史卡死任务：`queued_1782269665_user_admin`、`queued_1782270935_user_admin`，并保留失败原因说明，避免它们持续阻塞同 bucket 的新扫描
- 已补上 database 页面按角色隐藏扫描入口：`admin/qc_manager` 可见扫描卡片，`reviewer/viewer` 只保留只读检索与历史任务视图
- 已修复 `raw_data` 被误识别成独立批次的问题：扫描器现在会把 `raw_data` / `processed_data` / `data` 这类技术包装目录折叠回上一层业务 list，不再把它们当业务批次名或分类基准
- 已落地任务类型管理首版：新增独立一级页面 `任务类型管理`，仅对 `admin/qc_manager` 显示；支持任务类型列表、详情、创建、重命名、删除，以及从 `待分类` 加入批次、从任务类型移出批次回到 `待分类`
- 已新增任务类型管理后端 API：`GET/POST/PATCH/DELETE /api/task-types`、`GET /api/task-types/{id}/batches`、`GET /api/batches?task_type_id=...`、`POST /api/task-types/{id}/batches:attach`、`POST /api/task-types/{id}/batches/{batchId}:detach`
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

## Current Risks

- 当前真实入库和业务模型中仍残留旧本地字段：`episodes.source_path`、`batches.storage_path`、`ingest_jobs.source_path` 及旧 `app/services/ingestion.py` 尚未从仓库彻底移除，后续还需补 migration 与模型清理，避免“代码已不走、结构仍滞留”
- MinIO manual QC 当前已切到对象读取，但 media descriptor / presigned preview URL / refresh/download 接口仍未落地，视频区仍是占位 UI，Node D 合同还有后续实现工作
- 当前 scanner 已能生成 batch/episode 业务行，但 task type 仍主要依赖 basename 规则 seed，后续还需要补 task-type 管理接口、人工确认入口与浏览器端到端验证
- 当前虽已明确 bucket 全量扫描必须做递归结构识别，但 `raw_only`、`processed_only`、父子 prefix 同时命中的边界判定和重扫幂等策略还未落成正式字段设计
- 当前仍未确认是否存在“显式任务字段”可直接从单个 episode 元数据稳定提取；因此任务类型设计必须允许规则推断和人工回写，而不能把 MinIO 路径字符串直接当最终业务分类键
