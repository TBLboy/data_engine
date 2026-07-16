# Current Session

## Last Updated

- 2026-07-16 11:55 CST（任务级资产画像 Route T2 业务逻辑已固化）

## Current Objective

- 把“任务级数据资产画像”正式业务逻辑固化到 `.project-log`，暂不改代码

## Current Status

- Route C' 已落地并验证：`batches.list_id`、`batch_asset_rollups`、`batch_asset_recompute_jobs`、`/api/data-assets/summary|batches|rebuild`
- 任务级资产画像长期路线已确认并写入 project-log：Route T2
- 正式对象：`task_asset_rollups`、`task_asset_recompute_jobs`
- 正式 API：`GET /api/data-assets/tasks`、`GET /api/data-assets/tasks/{task_type_id}`，扩展 rebuild 支持 batch/task/all
- 正式口径：最终可用看 `final_dataset_status`；人工质检看 `manual_qc_status`；未质检与待裁定必须拆开
- 当前尚未开始任务级代码实现

## Problems And Resolutions

- GPT 原文方案偏重，部分字段/dirty 设计与现有 Route C' 风格不完全一致
  - 处理：保留 Route T2 主方向，但实现风格收敛为现有 batch 投影模式
- `task_types.total_*` 与 `/api/dataset/tasks/*` 容易被误当作任务资产画像来源
  - 处理：明确废弃 `task_types.total_*`，任务资产接口固定走 `/api/data-assets/tasks*`

## Next Steps

- 等用户确认后开始实现 Route T2
- 实现顺序：迁移建表 → task recompute 服务 → 接入 batch 成功链路 → 全量初始化与对账 → API → 前端 Task 视角
- 实现细节仍待确认：task calculation_version 策略、inactive task 是否允许持有 active-scope batch
