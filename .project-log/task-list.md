# Task List — 统一质检合格数据导出落地

## Last Updated

- 2026-07-20 10:01 CST

## 进度总览（对照业务逻辑 vs 代码）

### 已完成（主路径可用）

| 能力 | 状态 | 证据 |
|---|---|---|
| Annotation V1 模型 / migration / API / 工作台 | done | commit `6c47362`，`20260718_0027` |
| 标注资格 = QUALIFIED + active scope | done | `annotation.py` |
| 完成校验 + immutable revision | done | `complete_task` |
| 标注统计 API | done | `GET /api/annotations/statistics` |
| 业务逻辑：统一导出收口 | done | `.project-log/business-logic/*`（2026-07-20） |

### 部分完成 / 错误方向（不可提交为正式版本）

| 能力 | 状态 | 问题 |
|---|---|---|
| dataset summary 标注计数 | partial | 已有 `annotationCompletedEpisodeCount` / `annotationPendingEpisodeCount`，但卡片未改成「质检合格 / 完成标注」 |
| 导出门禁 | **wrong** | 当前 WIP 把导出收紧为“必须 completed annotation”，违反统一导出语义 |
| 导出附带 revision 字段 | partial | 仅对 completed 行导出，且缺少 `annotation_completed` / `training_default_included` 等统一字段 |
| 导出历史 filters 快照 | partial | 只写入 `filters_json`，无 `dataset_export_items` |
| 前端导出提示 | wrong | 仍提示“必须先完成标注” |

### 未开始

| 能力 | 状态 |
|---|---|
| `dataset_export_items` 表 / ORM / migration | todo |
| 统一导出行模型（全部 QUALIFIED + 可选标注增强） | todo |
| JSONL 数据包（manifest / episodes / schemas） | todo |
| Episode 列表标注状态列 | todo |
| 卡片「质检合格 / 完成标注」 | todo |
| 历史导出不可变回归测试 | todo |
| Compose / PostgreSQL / MinIO 真实导出验收 | todo |
| Schema 管理 UI、批量 ensure、分配 workload 运营面 | todo（导出主链路之后） |

---

## 任务表

状态：`todo` | `in_progress` | `done` | `blocked` | `cancelled`

| ID | 任务 | 优先级 | 状态 | 依赖 | 验收标准 |
|---|---|---|---|---|---|
| T00 | 创建 task-list 并对齐业务逻辑与代码进度 | P0 | done | — | 本文档已写清完成/错误/未完成项 |
| T01 | commit 备份：业务逻辑收口 + task-list + 当前 WIP 现场 | P0 | done | T00 | 有明确 commit；不把错误门禁标为完成 |
| T02 | 重构导出服务为统一 QUALIFIED 范围 | P0 | todo | T01 | 全部 active-scope QUALIFIED 可导出；未标注不阻断 |
| T03 | 导出行增加标注增强字段 | P0 | todo | T02 | 含 `annotation_completed`、`annotation_status`、`training_default_included`、revision/Schema/payload 或 null |
| T04 | 扩展 `DatasetExportJob` + 新增 `dataset_export_items` | P0 | todo | T02 | migration + ORM；创建 job 时事务内冻结 item 快照 |
| T05 | 导出产物：CSV 审计 + JSONL 数据包 | P1 | todo | T03,T04 | CSV 可审计；JSONL 含 manifest/episodes/schemas 语义（V1 可先同步返回再异步化） |
| T06 | 路由/权限/错误语义对齐统一导出 | P0 | todo | T02 | 无“必须完成标注才导出”的 422；历史接口兼容 |
| T07 | 前端卡片与表格：质检合格/完成标注 + 是否完成标注列 | P0 | todo | T03,T06 | 卡片双计数；表格有标注列；去掉错误门禁 alert |
| T08 | 回归测试覆盖统一导出与快照不可变 | P0 | todo | T03,T04,T05 | 无标注/草稿/完成/failed/uncertain/新 revision 后历史不变 |
| T09 | 后端 compile + 测试 + 前端 build 验收本批 | P0 | todo | T08 | 相关测试与 build 通过 |
| T10 | commit 正式版本：统一导出落地 | P0 | todo | T09 | 干净 diff、明确 commit message |
| T11 | Compose 重建 + PostgreSQL migration + 真实导出验收 | P1 | todo | T10 | 运行容器 head 迁移；真实导出下载与历史可查 |
| T12 | Schema 管理 / 批量 ensure / 分配 workload 运营面 | P2 | todo | T10 | 生产运营可独立完成标注闭环（导出主链路后） |

---

## 当前焦点

1. **T01** commit 备份  
2. 然后 **T02** 重构错误导出门禁  

## 规则

- 一次只推进一个 task 到完成态（可在同批内连做，但状态要逐项更新）。
- 任务范围变化：先改本表，再改代码。
- 每完成一项：更新本表状态 + `progress.md` / `current-session.md`。
- 错误 WIP 不得标为 done，必须经 T02 重构后才算统一导出完成。
