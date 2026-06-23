# Current Session

## Last Updated

- 2026-06-23

## Current Objective

- 完善 MinIO 数据湖控制面业务逻辑：扫描器算法、对象映射、episode 状态推进、QC 就绪检查与分类规则
- 将成熟的 MinIO 业务规则落地到 software 目录，转入代码实现阶段

## Current Business Logic Position

- Main path: A → B1 + B2 + B3 → C → F → D → E
- Current node: F（业务规则已闭环，可交接 Node D）
- Current edge: F → D（基于控制面方案的 QC 改造）
- Node F 完成项：6 表控制面 schema、全层级递归扫描算法、episode 三层状态推进、object_role/qc_ready 清单、classification_rules 种子策略与真实 basename 首版盘点、manual QC 对象访问混合协议、Node D API 合同收口

## Completed This Session

- 将 root `.project-log/business-logic/` 中已成熟的 MinIO control-plane 业务逻辑整体迁移到 `software/.project-log/business-logic/`
- migrated: `control-plane-schema-v1.md`, `decision-records.md`, `main.md`, `edges.md`, `nodes.md`, `graph.md`, `open-questions.md`, `constraints.md`
- 修复 graph.md 中 `node.md` 为 `nodes.md` 的 typo
- 验证所有 8 个迁移文件与 root 源文件完全一致
- 确认无旧逻辑残留

## Current State

- 7 个核心业务逻辑文件 + 1 个 constraints 文件已在 software 目录完整落地
- `yaocao` bucket 业务规则闭环：扫描/分类/状态推进/object_role/seed 盘点/对象访问协议全部可用
- 唯一开放项：Q-20260623-004（全量 list census，非阻塞）
- 下一步进入代码实现：MinIO 控制面 migration、扫描器实现、manual QC MinIO 化改造

## Next Steps

- Git push
- 开始代码实现：控制面 6 表迁移、扫描器、分类规则种子、manual QC 媒体访问改造
