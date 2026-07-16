# Known Issues

## 2026-07-10 — QC 任务池 / 认领状态机存在权限与状态矛盾风险 (RESOLVED)

- Resolution date: 2026-07-10 17:30 CST
- Resolution: 全部 6 条 required fix rules 已在代码中落地，前后端 build 通过。
  - backend `_ensure_task_claimable` / `_claim_task` 已按 reviewer/admin 角色 + status 约束收口
  - backend `release_manual_qc` 已加 `task.status != 'in_review'` 阻断
  - backend `submit_manual_qc` 已移除 fallback 到旧 task 的逻辑
  - reviewer 任务池通过 `/reviewer/tasks/current` 只返回 `assigned/in_review`
  - reviewer 历史池通过 `/reviewer/tasks/history` 返回 revision 历史
  - 待部署验收确认后关闭本条目。

## 2026-07-10 — QC 任务池 / 认领状态机存在权限与状态矛盾风险 (HISTORICAL)

- Symptom:
  - reviewer 当前任务池会混入 `done` 任务，已完成数据仍可继续进入人工质检页面。
  - reviewer 当前可认领 `assignee='未派发'` 的任务，不符合“必须先派发到本人任务池才能认领”的业务规则。
  - `done` 任务缺少明确的 claim/release 阻断，存在被错误 reopen 或形成 task/episode 状态不一致的风险。
  - admin 接管 reviewer 任务时会直接覆盖 `task.assignee` 与 `episode.reviewer`，但旧业务逻辑未正式定义该动作的 reopen/ownership transfer 语义。

- Reproduction condition:
  - 打开 reviewer 视角 `task-pool`，当前 `/task-pool` 查询只按 `is_active=1 + assignee=当前用户` 过滤，不排除 `done`。
  - 调用 manual claim/release/submit 路由时，旧后端规则未完整收口 `done` / inactive / 非本人 assigned 任务。

- Root cause:
  - 现有状态机把 `is_active`、`status`、任务池视图概念混在一起，缺少“当前任务池 / 历史任务池 / reopen done”三套明确语义。
  - reviewer 当前任务池与历史任务池尚未在查询层分离。
  - admin 最高权限接管逻辑在代码中部分存在，但未被正式定义为“ownership transfer + reopen”业务规则。

- Required fix rules:
  1. reviewer 当前任务池只允许 `assigned/in_review`，不得出现 `done`
  2. reviewer 历史任务池单独展示已完成历史记录
  3. reviewer claim 仅允许：active + assigned + assignee=本人 + 无他人有效锁
  4. admin claim `done` 时，必须作为 `done -> in_review` 的正式 reopen 流程处理，并同步重置 episode 当前结果为 pending
  5. `release` 禁止对 `done` 生效
  6. `submit` 只能针对 active + in_review + 当前锁持有人 + version 匹配的任务

- Verification target after implementation:
  - reviewer 当前任务池中不再出现 `done`
  - admin 接管 `assigned` 或 `done` 任务后，该任务从原 reviewer 当前任务池彻底消失
  - admin 接管 `done` 任务后，旧历史 revision 保留，新提交生成新的 revision
  - `release(done)` 和 `submit(non-active)` 被后端拒绝
