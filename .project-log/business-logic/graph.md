# Business Logic Graph

## Main

```text
A -> B1 + B2 + B3 -> C -> F -> D -> E

A:  项目启动
B1: 报告01 公开数据集隐式QC
B2: 报告02 数据质量检测框架
B3: 报告03 数据筛选/策展框架（暂缓）
C:  TeleDex数据格式分析 + MinIO 实查
F:  MinIO 数据湖控制面方案设计（当前节点）
D:  基于 MinIO 数据湖架构的 QC 方案落地
E:  汇总交付
```

## Branches

```text
None yet.
```

## Notes

- **2026-06-23 结构变更**：新增节点 F（MinIO 数据湖控制面方案设计），原 C->D 直连改为 C->F->D
- 调研阶段（A->B->C）主要产出已完成；当前位于实施阶段的 Node D
- Node F 已完成实现前业务规则闭环：扫描器算法、episode 状态推进、object_role/qc_ready 清单、classification_rules 框架与真实 basename 首版 seed 盘点、manual QC 对象访问协议均已补齐
- D 不再直接从 C 承接，改为从 F 承接（即基于 MinIO 控制面而非基于纯文件系统的 QC 方案）
- Node D 已具备进入实现规划的前置约束：manual QC 预览类媒体走短时 presigned URL，结构化对象与显式下载保持后端受控访问
- Node F 当前新增一条关键约束：任务类型从”扫描器自动正式归类”收敛为”人工维护主数据”，扫描器只负责同步数据并把未确认 batch 放入 `待分类`
- Node D 后续实现除了 MinIO 控制面和 manual QC，还必须新增任务类型管理系统：任务类型主数据管理、批次从 `待分类` 加入/移出、删除任务类型后的回收语义、数据总库批次检索增强
- **2026-07-15 结构增强**：Node D 正式新增“数据总库资产画像升级”子路线。长期实现不再继续依赖 Episode 实时聚合主路径，而是采用 Route C'：`batches.list_id` + `batch_asset_rollups` + `batch_asset_recompute_jobs` + 周期性对账
- **2026-07-16 结构增强**：在 Route C' 之上，Node D 数据总库资产画像子路线正式扩展为三视角：Episode 明细 + Batch 资产 + Task 资产。任务层采用 Route T2：`task_asset_rollups` + `task_asset_recompute_jobs`，只从 `batch_asset_rollups` 汇总，不回扫 episodes
- **2026-07-17 扫描主干升级**：Node F->D 的扫描入库实现边界升级为 v3。v3 替代 v2，采用每日 smart/每周 full、任意深度 namespace discovery、List shard 持久队列、独立 coordinator/worker、Episode 指纹与选择性对象索引、二次确认软删除/恢复和一键操作
- **2026-06-25** Node D 正在实施角色视图分离：reviewer 个人看板 + task-pool reviewer 版 + manual QC 流水线模式 + 完成庆祝动画；这些均属于 D 节点前端体验子任务
