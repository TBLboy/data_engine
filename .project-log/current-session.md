# Current Session

## Last Updated

- 2026-07-17 CST（扫描入库 v3 正式固化完成）

## Current Objective

- 扫描入库架构升级：可靠增量同步 v3 已成为正式主干，等待实施 Step 0

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

#### 扫描入库架构 v3 决策固化

- 基于真实生产库重新评估：58 active List、5,987 Inventory、约 2,909,780 条 `episode_objects`；旧“约 10 万对象”评估作废
- v3 正式方案已写入 `docs/scan-architecture-final-plan-v3.md`，v2 标记为被替代
- 正式能力：每日 smart、每周 full、manual_prefix；任意深度 namespace discovery；持久 shard 队列；独立 coordinator/worker；可终止子进程；Episode 指纹与选择性对象索引；二次确认软删除/自动恢复；一键扫描
- 原四个扫描开放问题 Q-004/008/009/010 已全部关闭
- 关键修正：现有 `scan_jobs` 原地演进，不重建 BIGINT 主键；逐帧 PNG/PLY 不再逐行写 `episode_objects`
- 五项验收已固化：每日定时、速度/扩展、故障鲁棒性、删除同步、一键操作

### 遗留约束

- `frontend` Docker 构建走 COPY dist 模式，要求本地 `npm run build` 后 Docker build 才会拿到新代码
- 前端 JS 哈希每次构建变化，用户浏览器需要 Ctrl+Shift+R 硬刷新

## Problems And Resolutions

1. Docker compose `--build` 因 buildx 未安装静默失败，导致 frontend 容器仍运行旧镜像
   - 处理：改为 `docker compose build --no-cache frontend` + `docker compose up -d frontend` 两步操作
2. `task_type_counts_map` 中引用了在后文定义的 `_task_type_batch_query` / `_active_batch_query`
   - Python 函数体在调用时才解析，运行正常（非 def-time 解析）

## Next Steps

- 按 v3 启动 Step 0：只读 MinIO census + 当前扫描耗时/内存/数据库行为基线
- 当前扫描器仍是旧 daemon thread，全量扫描卡死问题在 v3 实施完成前仍存在
