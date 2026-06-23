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
- 调研阶段（A->B->C）主要产出已完成；当前位于实施前期的方案设计阶段（F→D 交接）
- Node F 已完成实现前业务规则闭环：扫描器算法、episode 状态推进、object_role/qc_ready 清单、classification_rules 框架与真实 basename 首版 seed 盘点、manual QC 对象访问协议均已补齐
- D 不再直接从 C 承接，改为从 F 承接（即基于 MinIO 控制面而非基于纯文件系统的 QC 方案）
- Node D 已具备进入实现规划的前置约束：manual QC 预览类媒体走短时 presigned URL，结构化对象与显式下载保持后端受控访问
- Node D 的 manual QC API 合同已收口：`qc-context` 直接携带 embedded media descriptors，预览刷新按 `objectId` 定向更新，下载保持独立受控接口
- B3（报告 03）暂缓，不阻塞后续节点
- nodes.md、edges.md、decision-records.md 已同步更新
