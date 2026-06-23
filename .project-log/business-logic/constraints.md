# Business Logic Constraints

## System Constraints

- Unknown

## Hardware Constraints

- Unknown

## Software Constraints

- **前后端代码分离**：前端 (Vue) 和后端 (FastAPI) 代码在不同目录，独立开发和构建
- **部署仅前端**：最终部署产物为前端静态文件，后端作为独立服务运行
- 前端通过 HTTP API 与后端通信

## Real-Time / Threading Constraints

- Unknown

## Safety Constraints

- Unknown

## SDK / API Constraints

- Unknown

## Configuration Constraints

- Unknown

## Open Questions

### V1.0 已决策（不再视为 open）
- 允许 `pass` 但挂次原因码，表示数据可用但存在轻微瑕疵 ✅
- `qc_confidence` 保留为正式字段但非必填 ✅
- `reviewed_segments` 作为正式持久化字段保留 ✅
- `primary_reason_code` 不允许在 pass 下填写 ✅
- `secondary_reason_codes` 数量上限固定为 3 ✅
- 来自 batch 队列提交后自动跳转下一条 episode ✅
- `batch_qc_summary` 采用提交后同步刷新 ✅
- 默认派发模式为按批次百分比抽检，`qc_manager` / `admin` 可改为全量派发 ✅
- 未被抽中的 episode 保持在候选池，不直接生成 `qc_task`，直到后续补充派发或切换为全量派发 ✅
- 抽检比例、派发模式、补派动作必须进入审计日志，保证后续可追溯为什么这批数据只检了部分 ✅
- 批次完成率默认以“已抽中并生成任务的样本集”为分母，同时单独展示抽检覆盖率 ✅
- 重新质检需要 `qc_manager` / `admin` 权限，普通 reviewer 不可发起 ✅
- depth 在 Manual QC 中默认收起，reviewer 主动切换时显示 ✅
- V1.0 不做 RGB/depth 分屏对照，只做单路切换 ✅

### 待到 V2 再决策
- 自动 QC 误判是否需要单独记录 `auto_error_type`（V2 定）
- `auto_done` 复查时是否强制填写覆写自动结果的备注（V2 定）
- `override_auto_result` 是否强制要求至少填写一个 `reviewed_segments` 区间（V2 定）
- `manifest.json` V2 是否正式索引 depth 预览文件（当前发现文件存在但未被索引）
- depth colormap 色带、裁剪范围、坏值映射规则是否需要固定（V1 先用上游默认）

### 仍待决策
- 是否要求操作员必须看完所有红色异常段后才能提交
- `fail` 后是直接隔离，还是进入待二次复核池
- 软锁默认超时时间（10 分钟 / 20 分钟 / 更长）
- 一条 episode 是否允许多轮复核以及多位 reviewer 版本共存

