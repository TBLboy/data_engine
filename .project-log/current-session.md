# Current Session

## Last Updated

- 2026-07-16 12:45 CST（Route T2 全量落地完成检查 + 实现提交准备）

## Current Objective

- 固化并落地“任务级数据资产画像” Route T2：业务逻辑、投影层、API、前端三视角

## Current Status

- Route T2 业务逻辑已正式固化到 `.project-log/business-logic/*`
- 代码实现已全量落地并通过检查：
  - 模型/迁移：`task_asset_rollups`、`task_asset_recompute_jobs`
  - 服务层：task enqueue / recompute / rebuild / list / detail；batch 成功后联动父 task
  - Worker：batch job 优先，再处理 task job；子 batch pending 时 task 等待
  - API：`GET /api/data-assets/tasks`、`GET /api/data-assets/tasks/{task_type_id}`，`POST /api/data-assets/rebuild` 支持 batch|task|all
  - 前端：数据总库 Task 资产视角 + 任务抽屉 + Task→Batch 钻取 + 重建资产画像
- 验证：
  - `tests/test_data_assets.py` 10/10 OK
  - backend import smoke OK
  - frontend `vue-tsc --noEmit` OK
- 正式口径保持不变：
  - 最终可用：`final_dataset_status`
  - 人工质检：`manual_qc_status`
  - 未质检与待裁定拆开
  - 比率分母为 0 返回 `null`
  - task 投影只从 `batch_asset_rollups` 汇总

## Problems And Resolutions

- GPT 原文方案偏重，部分字段/dirty 设计与现有 Route C' 风格不完全一致
  - 处理：保留 Route T2 主方向，实现风格收敛为现有 batch 投影模式
- SQLite `autoflush=False` 下 task/batch job enqueue 可能重复插入，触发 UNIQUE 冲突
  - 处理：enqueue/rollup 改为 session identity + flush 安全查找；batch rollup 写后 flush，保证同事务 task 聚合可见
- worker 同时处理 batch + task job 后，旧测试仍期望 processed==1
  - 处理：测试改为 `>=1`，并断言父 task job 也被处理完成

## Next Steps

- 真实环境执行 Alembic `20260716_0024` 迁移 + `/api/data-assets/rebuild` 全量重算冒烟
- 确认无调用依赖后，推进 `task_types.total_*` 废弃清理
