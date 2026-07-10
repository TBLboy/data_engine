# Current Session

## Last Updated

- 2026-07-10 17:45 CST (QC 任务池/历史池/admin reopen/复检申请审批 全链路已部署上线，DB migration 已执行)
- 2026-07-10 17:30 CST (QC 任务池/历史池/admin reopen/复检申请审批 全链路代码落地完成，前后端 build 通过)
- 2026-07-10 15:10 CST (QC 任务池 / 历史任务池 / admin 接管 done 任务业务规则已正式收口并写入 project-log)

## Current Objective

- 以公司内网可直接投入使用为标准推进 Robot QC V1
- 当前任务：QC 任务池/历史池/admin reopen/复检申请审批 全链路代码落地已完成，进入部署验收阶段

## Current Status

- 全链路代码已落地并通过 build：
  - 后端状态机收口：claim/release/submit 按角色+任务状态约束
  - reviewer 双任务池分页接口：GET `/reviewer/tasks/current` + `/reviewer/tasks/history`
  - 复检申请接口：POST `/qc/episodes/{id}/rereview-request`
  - 复检审批接口：GET `/admin/rereview-requests` + POST approve/reject
  - 审批通过后：same task reopen（assignee 改回申请人，episode reset to pending，revision 保留）
  - manual-qc context：新增 viewMode/canClaim/canSubmit/taskStatus 权限标志
  - 前端 `task-pool.vue`：reviewer 双卡片独立分页，历史卡 `申请重新质检` 已启用
  - 前端 `rereview-approvals.vue`：admin/qc_manager 审批页
  - 前端 `manual-qc.vue`：claim/submit 按钮受后端权限标志控制，历史模式加提示
  - router + 侧边栏菜单已接入审批页面
- 新增 `QcRereviewRequest` 模型 + migration `20260710_0019`

## Problems And Resolutions

- 全部已解决。本轮无遗留问题。
- build 首次失败（`rereview-approvals.vue` 未使用的 `computed` import）→ 移除后通过。

## Verification

- Python `py_compile`：全部通过
- `npm run build`：全部通过，产出 `rereview-approvals-CwwoPixG.js`、`task-pool-CzSt90lE.js` 等新 chunk
- 未验证项：需要在生产/测试环境 `alembic upgrade head` + 浏览器端到端验收

## Files Changed

- `backend/app/api/routes/qc.py`
- `backend/app/models/qc.py`
- `backend/app/models/__init__.py`
- `backend/app/schemas/qc.py`
- `backend/app/services/payloads.py`
- `backend/migrations/versions/20260710_0019_qc_rereview_requests.py`
- `frontend/src/api/client.ts`
- `frontend/src/components/AppLayout.vue`
- `frontend/src/pages/manual-qc.vue`
- `frontend/src/pages/rereview-approvals.vue`
- `frontend/src/pages/task-pool.vue`
- `frontend/src/router/index.ts`
- `.project-log/business-logic/main.md`
- `.project-log/business-logic/decision-records.md`
- `.project-log/debugging/known-issues.md`
- `.project-log/progress.md`
- `.project-log/current-session.md`

## Current State

- 全链路代码落地完成，前后端 build 通过，无编译错误。
- Docker 容器已重建并启动：backend (healthy)、frontend (running)。
- DB migration `20260710_0019` 已执行，`qc_rereview_requests` 表已创建。
- 待浏览器端到端验收。

## Next Steps

- 浏览器验收 reviewer 双卡片 + 申请重检 + admin 审批 + admin 认领 done 完整路径
