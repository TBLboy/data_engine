# Task List — 生产落地验收与剩余缺口

## Last Updated

- 2026-07-20 17:55 CST

## 目标

确保当前已确认业务逻辑在代码与运行环境中完整落地：
QC → 标注 → 统一 QUALIFIED 导出（含标注增强与 JSONL 包）→ 真实 PostgreSQL/Compose 验收。

## 已完成

| 能力 | 状态 | 证据 |
|---|---|---|
| Annotation V1 源码 | done | `6c47362` |
| 统一 QUALIFIED 导出 + item 快照 | done | `11b33bb` + job 58: 169 items |
| JSONL 数据包导出 | done | `14b3130` |
| 标注运营面 | done | `17cb76e` + 生产 ensure/完成/导出验收 |
| Compose 重建 + migration head | done | alembic `20260720_0033` |
| 真实 HTTP/服务端导出验收 | done | `task_type:luobo` JSONL ZIP 169；completed=1 pending=168 |
| Ollama qwen 真实验收 | done | generation worker 2-pass vision+JSON |
| 标注资格失效/恢复 | done | QC 裁决 + scan-v3 接入 |
| 标注运营 rollup 投影 | done | migrations `0029`–`0032` |
| VLM 持久化队列 + 真实 invoke | done | queue+worker+coordinator+API |
| 前端 VLM 任务运营面 | done | `/annotations` list/enqueue/cancel/retry |
| Schema occurrence 粗对齐 | done | T18a |
| MinIO 媒体抽帧 | done | T18b media_image_count=5 |
| Ollama 视觉 + 2-pass JSON | done | T18c draft instr+2 occurrences |
| 夜间窗口/每日上限部署配置 | done | T19：00:00–06:00 Asia/Shanghai，daily=100；白天 discover=0 |

## 仍开放缺口

| 缺口 | 优先级 | 说明 |
|---|---|---|
| T13–T19 代码未提交 | P1 | 待用户明确 commit（非业务逻辑缺口） |
| occurrence 时间对齐可再校准 | P3 | 粗对齐已可验证；可选非 thinking 模型对比 |

---

## 任务表

| ID | 任务 | 优先级 | 状态 | 验收标准 |
|---|---|---|---|---|
| T11–T12 | Compose/导出/运营面 | P0–P1 | done | 真实 PG/HTTP |
| T13 | VLM 持久化队列 | P2 | done | enqueue→claim→Ollama→draft |
| T14 | Docker Ollama 可达 | P2 | done | bridge gateway |
| T15 | 导出 history/items | P2 | done | filters 瘦身 + items |
| T16a/b | 资格/rollup | P1 | done | 失效 cancel + 统计一致 |
| T17 | 前端 generation 运营面 | P2 | done | npm build + UI |
| T18a | occurrence normalize/publish | P2 | done | blank-only / PG lock |
| T18b | MinIO 抽帧 | P2 | done | media_image_count>0 |
| T18c | 视觉 mmproj + JSON 落地 | P1 | done | draft instruction+occurrences |
| T19 | 夜间窗口/每日上限 | P3 | done | 白天 skip；窗口内+quota 单元测试 |

## 当前焦点

1. 用户明确要求后 commit T13–T19
2. 可选：occurrence 质量再校准

## 本轮验收证据摘要（2026-07-20 17:55）

```text
offline: test_annotations 16/16 OK (含 night window/daily limit)
coordinator log: auto discovery skipped: outside configured window
settings: enabled=true tz=Asia/Shanghai 00:00-06:00 daily=100
export task_type:luobo: 169 QUALIFIED, status_counts pending=168 completed=1
record_export job=58 items=169 unannotated_included=True
T18c draft still present: Collect one radish. + 2 occurrences
```

## 规则

- 完成一批后重新核对代码与业务逻辑缺口
- 先改 task-list，再改代码
- 每完成一项更新 progress / current-session
