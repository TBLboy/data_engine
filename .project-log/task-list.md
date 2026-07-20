# Task List — 统一质检合格数据导出落地

## Last Updated

- 2026-07-20 10:11 CST

## 进度总览（对照业务逻辑 vs 代码）

### 已完成

| 能力 | 状态 | 证据 |
|---|---|---|
| Annotation V1 模型 / migration / API / 工作台 | done | commit `6c47362` |
| 统一导出业务逻辑文档 | done | `.project-log/business-logic/*` + commit `7c32a91` |
| task-list 建立与备份 commit | done | `7c32a91` |
| 统一 QUALIFIED 导出门禁（未标注不阻断） | done | `DatasetExportService` 重构 |
| 导出行标注增强字段 | done | `annotationCompleted` / status / revision / payload |
| 路由语义对齐统一导出 | done | `/dataset/tasks/{id}/exports` |
| 前端卡片「质检合格 / 完成标注」 | done | `dataset-management.vue` |
| 前端表格「是否完成标注」列 | done | Episode 列表 API + UI |
| `dataset_export_items` ORM + migration | done | `20260720_0028` + `DatasetExportItem` |
| 创建 export job 时写入 item 快照 | done | `record_export(..., rows=)` |

### 未完成

| 能力 | 状态 |
|---|---|
| JSONL 数据包（manifest / episodes / schemas） | partial（CSV/JSON 已有，zip JSONL 未做） |
| 历史导出不可变回归测试（新 revision 后旧 item 不变） | done |
| 前端 build / 全量测试验收本批 | done |
| 正式 commit 本批实现 | in_progress |
| Compose / PostgreSQL / MinIO 真实导出验收 | todo |
| Schema 管理 / 批量 ensure / 分配 workload 运营面 | todo |

---

## 任务表

状态：`todo` | `in_progress` | `done` | `blocked` | `cancelled` | `partial`

| ID | 任务 | 优先级 | 状态 | 依赖 | 验收标准 |
|---|---|---|---|---|---|
| T00 | 创建 task-list 并对齐业务逻辑与代码进度 | P0 | done | — | 本文档已写清完成/错误/未完成项 |
| T01 | commit 备份：业务逻辑收口 + task-list + 当前 WIP 现场 | P0 | done | T00 | commit `7c32a91` |
| T02 | 重构导出服务为统一 QUALIFIED 范围 | P0 | done | T01 | 全部 active-scope QUALIFIED 可导出；未标注不阻断 |
| T03 | 导出行增加标注增强字段 | P0 | done | T02 | 含 completed/status/training_default_included/revision/Schema/payload |
| T04 | 扩展 `DatasetExportJob` + 新增 `dataset_export_items` | P0 | done | T02 | migration + ORM；创建 job 时事务内冻结 item 快照 |
| T05 | 导出产物：CSV 审计 + JSONL 数据包 | P1 | partial | T03,T04 | CSV/JSON 已支持；独立 JSONL zip 数据包延后 |
| T06 | 路由/权限/错误语义对齐统一导出 | P0 | done | T02 | 无“必须完成标注才导出”的阻断语义 |
| T07 | 前端卡片与表格：质检合格/完成标注 + 是否完成标注列 | P0 | done | T03,T06 | 卡片双计数；表格有标注列；错误 alert 已移除 |
| T08 | 回归测试覆盖统一导出与快照不可变 | P0 | done | T03,T04 | 无标注/完成/新 revision 后历史 item 不变已覆盖 |
| T09 | 后端 compile + 测试 + 前端 build 验收本批 | P0 | done | T08 | annotation 6/6、data-assets 11/11、compile、frontend build 通过 |
| T10 | commit 正式版本：统一导出落地 | P0 | in_progress | T09 | 干净 diff、明确 commit message |
| T11 | Compose 重建 + PostgreSQL migration + 真实导出验收 | P1 | todo | T10 | 运行容器 head 迁移；真实导出下载与历史可查 |
| T12 | Schema 管理 / 批量 ensure / 分配 workload 运营面 | P2 | todo | T10 | 生产运营可独立完成标注闭环 |

---

## 当前焦点

1. **T10** 正式 commit 本批统一导出实现
2. 后续 **T05** 完整 JSONL 数据包
3. 后续 **T11** Compose / PostgreSQL 真实验收

## 规则

- 一次只推进一个 task 到完成态（可在同批内连做，但状态要逐项更新）。
- 任务范围变化：先改本表，再改代码。
- 每完成一项：更新本表状态 + `progress.md` / `current-session.md`。
