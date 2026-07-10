# Current Session

## Last Updated

- 2026-07-10 15:00 CST (通知红点、BUG管理权限收口、部署文档更新、修复提交)

## Current Objective

- 以公司内网可直接投入使用为标准推进 Robot QC V1
- 当前任务：re-review 全链路浏览器端到端验收

## Current Status

- audit_events 两列溢出修复完成：
  - `detail`: VARCHAR(64) → 500（已通过直接 ALTER TABLE 修复）
  - `id`: VARCHAR(64) → 128（模型 + baseline migration + migration 0022 + DB 全部同步）
  - baseline migration `20260623_0001` 已同步修正
- `format_time()` helper 已补充
- `Dockerfile` 改为 `start.sh` 启动，自动 `alembic upgrade head`
- 重新质检审批入口已从侧边栏移至头像下拉菜单（admin + qc_manager 可见）
- BUG管理前后端均收口为 admin 独占
- 通知红点系统上线：
  - `GET /api/notifications` 返回 bugCount + rereviewCount
  - 头像红点仅在 admin/qc_manager 显示
  - 下拉菜单各入口独立红点（BUG管理、重新质检审批）
  - 30 秒自动轮询
- 部署文档已更新（auto-migration 说明）

## Problems And Resolutions

- audit_events.detail VARCHAR(64) 溢出 → 直接 DB ALTER TABLE 绕过 Alembic/Docker 缓存
- audit_events.id VARCHAR(64) 溢出 → 模型修正 + baseline 修正 + migration 0022 + DB ALTER TABLE
- reviewer 头像消失 → v-if 改为 v-if/v-else 结构，非管理员保留纯头像
- 重新质检审批侧边栏入口不合理 → 移至头像下拉菜单

## Verification

- Python `py_compile`：全部通过
- `npm run build`：全部通过
- Docker compose ps：所有服务 healthy

## Files Changed

- `backend/app/api/routes/qc.py` — +format_time, +GET /notifications, 三处 rereview audit detail 恢复原始格式
- `backend/app/models/audit.py` — id String(64) → String(128)
- `backend/Dockerfile` — CMD 改为 start.sh
- `backend/start.sh` — 新增
- `backend/migrations/versions/20260623_0001_baseline_schema.py` — id 列 64 → 128
- `backend/migrations/versions/20260710_0022_expand_audit_events_id_column.py` — 新增
- `frontend/src/components/AppLayout.vue` — 菜单重组 + 通知红点 + BUG管理权限收口
- `frontend/src/api/client.ts` — +fetchNotifications
- `frontend/src/style.css` — +.menu-badge, +.avatar-badge
- `deploy/README.txt` — auto-migration 说明

## Next Steps

- 继续浏览器端到端验收 reviewer 双卡片 + 申请重检 + admin 审批 + admin 认领 done
- Push 到 origin/main
