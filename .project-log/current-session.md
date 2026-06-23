# Current Session

## Last Updated

- 2026-06-23 (MinIO control-plane schema/models first implementation block landed and validated)

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
- 已完成 MinIO 基础规则沉淀：`list` 暂按 `bucket + list_prefix` 视作一次采集/上传来源批次，不等于最终业务任务；episode 需区分“可接纳 / 可处理 / QC 就绪”三层状态，只有 processed 且关键对象齐全时才进入 manual QC
- 已明确 `yaocao` bucket 全量扫描原则：扫描器不能假设 list 固定在第一层或第二层，而应递归遍历所有层级 prefix，并用“直接子级命中 `raw/`、`processed/`，且其下存在 `episode_xxxxxx/`”的结构特征识别 list，确保 `yaocao/<list>/...` 与 `yaocao/K1/<list>/...` 都不会漏扫
- 已明确任务类型归类原则：当前对象元数据尚未看到可直接充当稳定业务任务主键的单字段，V1 应由 prefix 命名、episode 元数据与后续人工确认共同生成 `candidate_task_type/final_task_type`，最终以 PostgreSQL 落库结果为准

- 已明确 manual QC 的 MinIO 对象访问协议：预览/播放类 MP4 采用后端签发的短时 presigned URL，`manifest.json`/`metadata.json`/`telemetry.npz` 等结构化对象继续由后端读取解析，显式下载/导出保持后端受控接口
- 已进一步收口 Node D manual QC API 合同：`/api/episodes/{episode_id}/qc-context` 直接返回 embedded `media[]` descriptors；预览 URL 刷新走 `POST /api/episodes/{episode_id}/media/refresh` 按 `objectId` 定向更新；显式下载走独立 `GET /api/episodes/{episode_id}/objects/{object_id}/download`
- Node F 控制面业务规则已闭环：扫描、状态推进、object_role、classification_rules 与 manual QC 对象访问协议均已落定，下一步进入 Node D 实现规划与 API/前端合同改造
- 已在 scan API 切换后继续收口下游链路：`database/dashboard` 扫描任务视图已全部改为 bucket/scope 语义，`BatchSummary` 已切到 `bucket + storagePrefix`，frontend mock 已同步为 MinIO 字段
- manual QC 真实上下文已从本地 processed 目录读取切换为基于控制面 `episode_inventory + episode_objects + lists` 的 MinIO 对象读取；后端直接从 MinIO 拉取 `manifest.json` / `metadata.json` / `telemetry.npz` 生成 metrics 与 timeline，不再参与旧本地扫描目录逻辑
- 已继续推进旧本地字段清理：新增 `app/services/authz.py` 承接权限校验，旧 `app/services/ingestion.py` 与 `models/ingest.py` 已从运行路径删除；同时新增 Alembic revision `20260623_0003` 用于删除 `ingest_jobs`、`batches.storage_path`、`episodes.source_path/source_hash/ingest_status`
- 已完成真实浏览器媒体验收：Playwright 直接打开生产态 manual QC 页面，观察到 `videos=3`、`refreshVisible=true`、`downloadButtons=3`，说明真实视频元素已经在浏览器侧渲染成功
- 生产 HTTP 扫描入口已从 504 改为异步返回 queued job，且至少有多条 queued job 在生产 PostgreSQL 中真实跑到 `done`（如 `queued_1782227875_user_admin`、`queued_1782230632_user_admin`）；当前剩余问题收敛为 queued worker 存在不稳定性，并非业务链完全不可用
- 已完成真实对象级验证：manual QC payload 针对真实 MinIO episode 已返回 3 路媒体 descriptors，并带有有效 `previewUrl`；当前由于临时验证库尚未生成 `qc_task`，`refreshable=false` 属于预期结果，后续需在完整派发链路下验证 refresh 行为

## Current Risks

- 当前真实入库和业务模型中仍残留旧本地字段：`episodes.source_path`、`batches.storage_path`、`ingest_jobs.source_path` 及旧 `app/services/ingestion.py` 尚未从仓库彻底移除，后续还需补 migration 与模型清理，避免“代码已不走、结构仍滞留”
- MinIO manual QC 当前已切到对象读取，但 media descriptor / presigned preview URL / refresh/download 接口仍未落地，视频区仍是占位 UI，Node D 合同还有后续实现工作
- 当前 scanner 已能生成 batch/episode 业务行，但 task type 仍主要依赖 basename 规则 seed，后续还需要补 task-type 管理接口、人工确认入口与浏览器端到端验证
- 当前虽已明确 bucket 全量扫描必须做递归结构识别，但 `raw_only`、`processed_only`、父子 prefix 同时命中的边界判定和重扫幂等策略还未落成正式字段设计
- 当前仍未确认是否存在“显式任务字段”可直接从单个 episode 元数据稳定提取；因此任务类型设计必须允许规则推断和人工回写，而不能把 MinIO 路径字符串直接当最终业务分类键
