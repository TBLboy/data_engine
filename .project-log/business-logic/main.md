# Main Business Logic

## Status

- Research phase: Complete（公开数据集调研 + TeleDex 格式分析 + MinIO 数据湖实查均已完成）
- Current phase: 训练数据消费与批次驳回模块进入业务逻辑设计阶段（LaTeX 设计文档已产出，关键业务规则：失败率分母=抽检数 已确认）

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
| `dataset_consumption_batch_rejection_agent_guide.tex` | D2 | 已产出（批次驳回 + 数据集管理 + 导出，v1.0） |
| MinIO → PostgreSQL ingestion / manual QC 改造方案 | D | 待实现 |
| 训练数据消费与批次驳回模块 | D2 | 待实现（代码未开始，业务规则已确认） |

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
- 任务派发与人工质检必须职责分离：工作台承接 batch 级任务生成与批量派发，`manual-qc` 页面只负责 claim/release/提交质检结果，不再承担派发入口
- 系统必须按角色提供不同视图：`admin`/`qc_manager` 看到完整运营视图；`reviewer` 只开放个人任务看板、我的任务列表、人工质检流水线三个界面；`viewer` 只读访问工作台概览
- reviewer 的工作模式是流水线式：从个人看板进入质检 → 提交 → 自动跳转下一条待质检任务，直到全部完成；提交后不应停留在原地或需要手动返回列表选择下一条
- reviewer 完成全部待质检任务后触发庆祝动画（礼花彩条 + 音效），作为正向激励闭环
- `task_types` 是人工维护的业务目录，由 `admin/qc_manager` 管理；扫描器不再负责自动创建正式任务类型，未分类或新增批次统一进入 `待分类`
- bucket 全量扫描采用全层级递归发现 + 结构特征识别 list
- Episode 生命周期采用 ingestable / processable / qc_ready 三层模型
- 扫描器只负责把 MinIO 数据同步到 PostgreSQL，并保持已人工分类 batch 的任务类型不被自动覆盖
- 批次与任务类型关系是可人工改挂的业务关系，而不是扫描器不可变的自动归类结果
- 删除任务类型默认执行“回收到 `待分类`”语义，不直接破坏已有 batch/episode/QC 历史数据
- MinIO 凭据通过环境变量注入，不写入仓库代码

## 训练数据消费与批次驳回 — 业务规则

### 目标

将平台从"只记录质检结果的 QC 系统"升级为"能够按任务统计训练可用数据、执行批次驳回策略、生成可溯源最终状态并导出合格 episode 清单的数据资产供给系统"。

### 失败率计算公式（关键修正）

失败率 = 人工失败数 / 抽检数（NOT 批次总数）

\[
R_{fail} = \frac{N_{fail}^{manual}}{N_{sampled}}
\]

修正理由：以批次总数做分母会严重稀释失败率信号。例如抽检 25 条发现 12 条不合格，按批次总数 100 算只有 12%，但实际上抽检的 25 条中近一半不合格，说明这批数据质量很差。改用抽检数做分母后 12/25=48%，能更敏感地触发驳回。

### 批次判定规则

设驳回阈值 \(\theta\)（默认 0.10，可在设置页"通用"tab 中调整）：

\[
BatchDecision =
\begin{cases}
Rejected, & R_{fail} > \theta \\
Accepted, & R_{fail} \le \theta
\end{cases}
\]

注意：\(R_{fail} = \theta\) 时不驳回（"超过阈值"才驳回）。

### 三层状态模型

- **ManualQcStatus**: NOT_REVIEWED / MANUAL_PASS / MANUAL_FAIL
- **BatchDecision**: PENDING / ACCEPTED / REJECTED  
- **FinalDatasetStatus**: PENDING / QUALIFIED / UNQUALIFIED

批次驳回时所有 episode 最终不可用；批次通过时人工失败的不可用，未抽检和人工通过的可用。

### Episode 最终判定表

| 批次判定 | 人工状态 | 最终状态 | 来源 |
|---------|---------|---------|------|
| REJECTED | MANUAL_FAIL | UNQUALIFIED | MANUAL_FAIL |
| REJECTED | MANUAL_PASS | UNQUALIFIED | BATCH_REJECT_OVERRIDE_MANUAL_PASS |
| REJECTED | NOT_REVIEWED | UNQUALIFIED | BATCH_REJECT_PROPAGATED_FAIL |
| ACCEPTED | MANUAL_FAIL | UNQUALIFIED | MANUAL_FAIL |
| ACCEPTED | MANUAL_PASS | QUALIFIED | MANUAL_PASS |
| ACCEPTED | NOT_REVIEWED | QUALIFIED | BATCH_ACCEPT_INFERRED_PASS |

### 判定触发时机

- 质检员提交 QC 结果后自动触发所属批次的判定检查
- 管理员可手动触发重新判定
- 判定条件：`sampled_episode_count > 0 AND reviewed_episode_count >= sampled_episode_count`
- 判定幂等：重复执行不产生不一致状态

### 设置页新增"通用"标签

在现有 `settings.vue` 的 tab 结构中新增"通用"tab，包含：
- 批次驳回阈值 \(\theta\)（默认 0.10，即抽检失败率 > 10% 触发驳回）

### 相关文档

- 完整设计文档：`software/dataset_consumption_batch_rejection_agent_guide.tex`

## Verification Status

- A: 已完成
- B1: 进行中（DROID 已完成，扩展到 19 数据集）
- B2: 进行中（DQAF + Consistency Matters + Forge 已完成）
- B3: 未开始
- C: 已完成（TeleDex 文档、schema、MinIO 实查均已完成）
- **F: 已闭环（可指导实现）**
- **D: ready（可按现有业务规则开始实现）**
- E: 待 D 完成后整合交付

## L3 V1 Execution Snapshot

- L3 的 V1 自动指标现已细化到实现级：P0 必做 6 项（LDLJ、Dead Actions、Action Saturation、Static Detection、Timestamp Regularity、Qpos-Action Tracking Error）+ P1 增强 2 项（Per-finger Gripper Chatter、Joint Effort）
- 统一输入源：仅 `processed/telemetry.npz`
- 统一子系统约束：arm_dims（弧度）与 hand_dims（0~255）分开计算；手部先归一化到 `[0,1]`
- Timeline 只由可定位的异常产出：`同步异常`、`跟踪误差`、`停滞`、`动作饱和`、`手指颤振`
- manual QC 自动指标区只承载 L3；L2/L4 继续人工审核

## Notes

- 当前已不再缺核心业务规则，剩余工作重心转向代码实现
- 唯一仍打开的问题是全量 list census，它属于规模与验收覆盖问题，不改变既定控制面设计
- 下一阶段产出应是 MinIO 控制面 migration、扫描器实现、manual QC MinIO 化改造
- `database` 页面后续若进入大规模远程使用，性能优化优先级应遵循：先后端分页/筛选，再前端短时缓存；`KeepAlive` 或单纯前端全量分页都不能作为长期主方案
- 任务派发后续正式形态应采用”批次级生成待派发任务池 + reviewer 批量分配”模式，而不是逐条 `episode` 手工指定审核员；若重新生成派发任务，系统必须切换到新的活跃派发版本并退役旧版本未开始任务，避免旧 full 任务继续污染当前 sampled 视图
- 角色视图分离后的页面路由规则：登录后 `reviewer` → `/reviewer`（个人看板）、`admin/qc_manager` → `/dashboard`（派发工作台）；`manual-qc` 是共用页面，但 reviewer 在流水线模式下提交后自动跳转下一条，admin 模式下不自动跳转
- L3 方案已正式收口到 V1 可执行级：L1 继续由 TeleDex 平台负责；L2（视觉质量）与 L4（任务完成度）保持人工审核；L3（遥操作轨迹质量）采用 Forge 主方案 + TeleDex/灵巧手专项自定义指标。V1 首版自动指标分档为 P0 必做 6 项（LDLJ、Dead Actions、Action Saturation、Static Detection、Timestamp Regularity、Qpos-Action Tracking Error）+ P1 增强 2 项（Per-finger Gripper Chatter、Joint Effort）；P2 的 SPARC / Action Entropy / State-Conditioned Variance / 跨-episode consistency 指标暂缓。manual QC 的自动指标区只承载 L3，不承担 L2/L4 自动判定
