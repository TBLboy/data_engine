# Main Business Logic

## Status

- Research phase: Complete（公开数据集调研 + TeleDex 格式分析 + MinIO 数据湖实查均已完成）
- Current phase: Node F 业务规则已闭环，进入 Node D 实现准备阶段

## Main Path

```text
A → B1 + B2 + B3 → C → F → D → E
```

## Path Summary

- **A**: 项目启动，调研目标确定
- **B1**: 报告 01 — 公开数据集隐式 QC 策略（DROID/RH20T/LeRobot/RoboMimic/OXE/RoboCasa）
- **B2**: 报告 02 — 数据质量检测框架（DQAF/score_lerobot/Consistency/Green-VLA/PSD）
- **B3**: 报告 03 — 数据筛选/策展框架（Data Quality in IL/DemInf/QoQ/SCIZOR/S2I）
- **C**: Linker TeleDex 数据格式深度分析 + MinIO 对象存储实地验证
- **F**: MinIO 数据湖控制面方案设计（业务规则已闭环）
- **D**: 基于 MinIO 数据湖架构的 QC 方案落地
- **E**: 完整项目交付

## Deliverables

| 文件 | 节点 | 状态 |
|------|------|------|
| `doc/reports/01_public_dataset_implicit_qc.md` | B1 | 进行中（DROID 已完成，扩展到 19 数据集） |
| `doc/reports/02_data_quality_assessment_frameworks.md` | B2 | 进行中（DQAF + Consistency Matters + Forge 已完成） |
| `doc/reports/03_data_curation_frameworks.md` | B3 | 未开始 |
| `doc/reports/04_teledex_qc_summary.md` | E | 基线章节完成（v0.1）；§6–§9 待补充 |
| `control-plane-schema-v1.md` | F | 已产出（schema v0.2 + 扫描/分类/对象访问规则） |
| MinIO → PostgreSQL ingestion / manual QC 改造方案 | D | 待实现 |

## Transition Phase — F Closed, D Ready

当前业务逻辑主线已经从“定义 MinIO 控制面规则”推进到“按既定规则实施 Node D 改造”。Node F 已完成的实现前规则包括：

- `yaocao` bucket 对象布局实查确认：`<bucket>/<list_prefix>/{raw|processed}/episode_xxxxxx/...`
- list 定义、deepest-match 排重、全量递归扫描策略
- `ingestable / processable / qc_ready` 三层 episode 状态模型
- `scan_jobs / discovered_prefixes / lists / episode_inventory / episode_objects / classification_rules` 六张控制面表设计
- `task_types` / `lists` / `qc_tasks` 三类实体区分，以及 bind / unbind / retire 语义
- manual QC 的 MinIO 对象访问协议：媒体预览走短时 presigned URL，结构化对象与显式下载走后端受控接口
- Node D manual QC API 合同：`qc-context` embedded `media[]`、按 `objectId` 定向 refresh、下载走独立 endpoint
- `database` 页面长期性能方向已明确：不能继续依赖“全量 episodes 拉到前端后本地过滤”，后续正式方案应切换为“服务端分页 + 服务端筛选 + 前端短时缓存”

仍保留但不阻塞实现的开放项：

- `Q-20260623-004`：`yaocao` bucket 的全量 list census（raw_only / processed_only / both 分布）尚未完成；这影响规模评估和验收覆盖，不影响当前实现方向

## Stable Assumptions

- 数据采集平台已确定使用 Linker Open TeleDex，数据格式不改动
- MinIO 在 V1 中仅作为原始对象存储层，不承担业务查询职责
- PostgreSQL 是唯一业务查询入口和系统事实源
- 前端继续只调后端 API，不直接耦合 MinIO 路径
- `database` 页面不能长期依赖全量 episodes 前端本地过滤；随着数据规模和多用户远程访问增长，正式形态应由后端负责分页、筛选与总数统计，前端只渲染当前页
- `task_types` 是人工维护的业务目录，由 `admin/qc_manager` 管理；扫描器不再负责自动创建正式任务类型，未分类或新增批次统一进入 `待分类`
- bucket 全量扫描采用全层级递归发现 + 结构特征识别 list
- Episode 生命周期采用 ingestable / processable / qc_ready 三层模型
- 扫描器只负责把 MinIO 数据同步到 PostgreSQL，并保持已人工分类 batch 的任务类型不被自动覆盖
- 批次与任务类型关系是可人工改挂的业务关系，而不是扫描器不可变的自动归类结果
- 删除任务类型默认执行“回收到 `待分类`”语义，不直接破坏已有 batch/episode/QC 历史数据
- MinIO 凭据通过环境变量注入，不写入仓库代码

## Verification Status

- A: 已完成
- B1: 进行中（DROID 已完成，扩展到 19 数据集）
- B2: 进行中（DQAF + Consistency Matters + Forge 已完成）
- B3: 未开始
- C: 已完成（TeleDex 文档、schema、MinIO 实查均已完成）
- **F: 已闭环（可指导实现）**
- **D: ready（可按现有业务规则开始实现）**
- E: 待 D 完成后整合交付

## Notes

- 当前已不再缺核心业务规则，剩余工作重心转向代码实现
- 唯一仍打开的问题是全量 list census，它属于规模与验收覆盖问题，不改变既定控制面设计
- 下一阶段产出应是 MinIO 控制面 migration、扫描器实现、manual QC MinIO 化改造
- `database` 页面后续若进入大规模远程使用，性能优化优先级应遵循：先后端分页/筛选，再前端短时缓存；`KeepAlive` 或单纯前端全量分页都不能作为长期主方案
