# Task List — 生产落地验收与剩余缺口

## Last Updated

- 2026-07-20 11:10 CST

## 目标

确保当前已确认业务逻辑在代码与运行环境中完整落地：
QC → 标注 → 统一 QUALIFIED 导出（含标注增强与 JSONL 包）→ 真实 PostgreSQL/Compose 验收。

## 已完成

| 能力 | 状态 | 证据 |
|---|---|---|
| Annotation V1 源码 | done | `6c47362` |
| 统一 QUALIFIED 导出 + item 快照 | done | `11b33bb` |
| JSONL 数据包导出 | done | `14b3130` |
| Compose 重建 + migration head | done | alembic `20260720_0028` |
| 真实 HTTP 导出验收 | done | admin 登录导出 luobo 169 条 JSONL，items=169 |
| Ollama qwen 真实验收 | done | `/api/ai/explain` source=llm model=`qwen3-vl-thinking:32b` |
| 前端新文案上线 | done | 质检合格/完成标注、JSONL 包、是否完成标注 |

## 仍开放缺口

| 缺口 | 优先级 | 说明 |
|---|---|---|
| Schema 管理 / 批量 ensure / 分配 workload 运营面 | done | 生产 Schema/ensure/分配/reviewer 完成/JSONL snapshot 已真实验收 |
| VLM annotation-worker 持久化队列 | P2 | 业务已定，代码未完整落地 |
| 标注任务在生产数据中仍为 0 | P1 | 需运营面批量 ensure 或夜间流水线 |
| Docker 内默认 `OLLAMA_BASE_URL=localhost` | P2 | 运行时 GeneralConfig 已指向可用 host；默认 env 仍误导 |
| 导出 history 的 filters 含全量 snapshot | P2 | items 表已是权威；filters 可能膨胀 |
| 标注资格失效未接入变更流水线 | P1 | `invalidate_ineligible_tasks` 已有实现但尚未在 QC/扫描状态变化后触发 |
| 标注统计未使用持久化 rollup | P2 | 当前 statistics 是 task 查询；正式 `task_annotation_rollups` 仍未落地 |

---

## 任务表

| ID | 任务 | 优先级 | 状态 | 验收标准 |
|---|---|---|---|---|
| T11 | Compose 重建 + PostgreSQL migration + 真实导出验收 | P0 | done | head=`20260720_0028`；真实导出/历史/items 可查 |
| T11a | 重建 backend 并升级 migration | P0 | done | `20260717_0026 → 20260720_0028` |
| T11b | 重建 frontend / worker / coordinator | P0 | done | 服务 healthy；前端含新导出 UI |
| T11c | 真实 HTTP 验收 annotation + export API | P0 | done | statistics/summary/export/history/items |
| T11d | Ollama qwen32b 真实验收 | P0 | done | explain source=llm，非 fallback |
| T12 | Schema 管理 / 批量 ensure / 分配 workload 运营面 | P1 | done | 管理 UI + 路由修复；真实 ensure 4 条、reviewer 完成 1 条、JSONL/immutable item snapshot 验收完成 |
| T13 | VLM annotation-worker 持久化队列落地 | P2 | todo | 对齐 final-decisions worker 规则 |
| T14 | 修正 Docker 默认 Ollama 可达地址/文档 | P2 | todo | 容器默认可达 host Ollama 或文档明确依赖 GeneralConfig |
| T15 | 导出 history 瘦身：filters 仅条件，明细只看 items | P2 | todo | 大任务导出历史 API 不返回上万 snapshot |
| T16 | 标注资格失效/恢复接入 + annotation rollup | P1 | todo | QC/扫描改变资格时失效或恢复 task；首页统计使用持久化 task annotation rollup |

## 当前焦点

1. **T16** 标注资格失效/恢复与统计投影，补齐已确认生命周期规则
2. 其后 T13/T14/T15

## 本轮进行中（2026-07-20）

- 修复 `GET /api/annotations/eligible?task_type_id=...` 与 `POST /api/annotations/tasks/ensure` 的重复 `Batch` join；PostgreSQL 不再报 `DuplicateAlias`。
- 增加 manager 运营面：TaskType 资格/积压/完成率、补漏 ensure、Schema draft/publish、reviewer workload、分配与公共领取控制。
- 生产真实闭环：`task_type:luobo` 169 个可标注 Episode；ensure 创建 4 条任务；`reviewer01` 完成 1 条，JSONL manifest 显示 `annotationCompletedCount=1`，导出 item 固定指向 revision 1；重编辑后 revision 2 不影响历史 item。

## 本轮验收证据摘要

```text
alembic current: 20260720_0028 (head)
OpenAPI: /api/annotations/* + /api/dataset/tasks/{id}/exports
真实导出: task_type:luobo 169 QUALIFIED -> zip(manifest/episodes/schemas), items=169
annotationCompletedCount=0 (尚无生产 annotation tasks)
AI explain: source=llm model=qwen3-vl-thinking:32b fallbackUsed=false
```

## 规则

- 完成一批后重新核对代码与业务逻辑缺口
- 先改 task-list，再改代码
- 每完成一项更新 progress / current-session
