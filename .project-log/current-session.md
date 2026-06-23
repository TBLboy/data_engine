# Current Session

## Last Updated

- 2026-06-22

## Current Objective

- 已完成抽检派发业务逻辑修订，下一步进入后端服务实现，并按新派发模型同步前端语义。

## Current Business Logic Position

- Main path: V1.0 Manual QC Platform
- Current node: Dispatch strategy finalized
- Current edge: Business logic → Backend implementation
- Active branch: 默认百分比抽检，可选全量派发

## Completed This Session

- 将任务派发策略定稿为”默认百分比抽检，可选全量派发”
- 更新 `.project-log/requirements.md`
- 更新 `.project-log/business-logic/constraints.md`
- 更新 `.project-log/business-logic/edges.md`
- 更新 `.project-log/business-logic/main.md`
- 补齐 dispatch-plan / dispatch-preview 接口、候选池/任务池分离、样本统计口径、V1.0 最小交付标准
- 完成前端抽检派发语义对齐：
  - `types/qc.ts` 新增 `DispatchMode`、`DispatchPreview`，扩展 `BatchSummary`/`QcTask` 字段
  - `api/mock.ts` 按新字段重构所有批次和任务数据
  - `pages/dashboard.vue` 重写为候选总量/已抽中样本/样本完成率/抽检覆盖率口径
  - `pages/task-pool.vue` 新增派发计划区（模式切换 + 比例输入 + 候选池预览）
  - `npm run build` 通过

## Current State

- 前端 UI 已完整（老板演示级），抽检派发语义已对齐
- 数据层目前使用 mock 数据
- V1.0 派发规则已收口为 sampled default / full optional
- 后端尚未实现

## Next Steps

- 开始后端服务实现（FastAPI + PostgreSQL + Docker Compose）
- 优先落地 batch 候选池、dispatch-plan / dispatch-preview、qc_task 生成与指派接口
- 前端切到真实 API 数据源
