# Current Session

## Last Updated

- 2026-07-16 14:30 CST（扫描架构升级决策固化完成）

## Current Objective

- 扫描入库架构升级：分层并行扫描 v2 方案正式确定，等待实施启动

## Current Status

### 已完成

#### `task_types.total_*` 废弃清理（commit `73f4c0c`）

- 删除 `task_types.total_batches` / `total_episodes` 列（迁移 `20260716_0025`）
- `serialize_task_type` 改为实时动态计数
  - 新增 `task_type_counts_map()` 批次查询，避免序列化时 N+1
  - 优先使用 Active-list / active-batch / indexed-episode 统计口径
  - `totalBatches` / `totalEpisodes` API 字段名称和含义不变
- 所有写入路径全部移除
  - `_refresh_task_type_stats` 函数及所有调用点（list / create / delete / attach / detach）
  - `scanner.py` 中的 `total_batches` / `total_episodes` 写入
  - `classification_seed.py` 构造器旧字段
- `cleanup_replaced_batch` 中移除已无用的 `legacy_task_type` 变量引用

#### 真实库线上迁移 + rebuild 冒烟

- Docker compose 重建 backend + frontend 镜像
- Alembic `20260716_0025` 迁移已执行，头正确
- `python -m app.services.data_assets_worker rebuild-all all` 成功：**52 batches / 20 tasks**
- `task_asset_rollups` 已填充实际数据

#### 前端构建修复（commit `845a5fb`）

- `database-view.vue` 中存在未使用的 `drillTaskToEpisodes` 函数，导致 `vue-tsc` 编译报错
- 移除该函数后构建成功

#### 前端卡片顺序修正（commit `a3b59b8`）

- 数据总库三个资产卡片顺序原为 Episode → 任务 → 批次
- 修正为 Episode → 批次 → 任务，与设计文档一致
- npm run build + frontend Docker 镜像重建 + 重启完成

#### 推送

- 4 commits 已全部推送至 `origin/main`

#### 扫描入库架构升级决策固化

- GPT 关键决策分析反馈已收到
- 采纳 10 项 GPT 建议，生成最终实施方案 v2（`docs/scan-architecture-final-plan-v2.md`）
- v2 方案正式决策已写入 `decision-records.md`
- 核心修改：
  - `skip_until_next_change` → `next_scan_at` 自适应退避
  - 删除检测收窄到 shard 范围
  - Asset Recompute 新增 `rerun_requested` 幂等字段
  - 独立 Docker Worker Service 替代 FastAPI 内嵌
  - 不建 `object_inventory`，复用 `episode_objects`
  - 不做四级冷热调度
- 实施计划：10 步，约 5,000-8,500 行代码，16-25 人日

### 遗留约束

- `frontend` Docker 构建走 COPY dist 模式，要求本地 `npm run build` 后 Docker build 才会拿到新代码
- 前端 JS 哈希每次构建变化，用户浏览器需要 Ctrl+Shift+R 硬刷新

## Problems And Resolutions

1. Docker compose `--build` 因 buildx 未安装静默失败，导致 frontend 容器仍运行旧镜像
   - 处理：改为 `docker compose build --no-cache frontend` + `docker compose up -d frontend` 两步操作
2. `task_type_counts_map` 中引用了在后文定义的 `_task_type_batch_query` / `_active_batch_query`
   - Python 函数体在调用时才解析，运行正常（非 def-time 解析）

## Next Steps

- 扫描架构升级 v2：等待用户确认后启动 Step 0（基线测试 + Feature Flag）
- 当前扫描器稳定性问题（后台扫描卡死）待 v2 升级解决
