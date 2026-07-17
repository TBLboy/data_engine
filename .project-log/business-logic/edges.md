# Business Logic Edges

## Edge A->B: 执行公开数据集QC调研

```yaml
edge_id: A->B
from: A
to: B
path: main
status: stable（主要产出已完成）
method: 调研公开机器人数据集的质检流程
execution_chain:
  - 阅读DROID论文和数据集文档
  - 分析DROID数据集（droid_100样本）
  - 阅读RH20T、DQAF、Consistency Matters论文
  - 调研 Forge、RINSE、异常检测前沿
  - 扩展到 19 数据集/生态覆盖
  - 提取可迁移QC规则（27条）
inputs:
  - DROID论文：https://arxiv.org/html/2403.12945v2
  - RH20T文档：https://rh20t.github.io/
  - DQAF论文：https://arxiv.org/abs/2605.26349
  - Consistency Matters论文：https://arxiv.org/html/2412.14309v2
  - Forge + RINSE + 异常检测
outputs:
  - 报告 01：公开数据集隐式QC（19数据集覆盖）
  - 报告 02：数据质量检测框架（DQAF + L3深度）
  - 报告 03：数据策展框架（暂缓）
verification:
  - 内容与原始论文交叉核对一致
notes:
  - 主要产出已在 2026-06-16 完成
  - 如时间允许可继续深入 B3，但不阻塞后续节点
```

## Edge B->C: 深度分析 Linker TeleDex + MinIO 实查

```yaml
edge_id: B->C
from: B
to: C
path: main
status: stable（已完成）
method: 深度理解 Linker TeleDex 数据格式 + 实地验证 MinIO 对象存储
execution_chain:
  - 阅读Linker Open TeleDex数据说明文档PDF
  - 理解telemetry.npz字段结构（timestamps、qpos、qvel、actions等）
  - 使用 boto3 直连 MinIO，验证连通性
  - 枚举 bucket 并确认 `yaocao` 为主业务 bucket
  - 实查对象布局：list 多层分布、raw/processed 双层结构、episode 组织方式
  - 读取样例元数据（manifest.json、metadata.json、recording_info.json）
  - 确认 manual QC 真实依赖 processed 层对象
  - 确认 V1 默认 scope = 单 bucket yaocao
inputs:
  - Linker Open TeleDex数据说明文档PDF
  - MinIO 凭据（endpoint, access_key, secret_key）
outputs:
  - Linker TeleDex数据格式理解文档
  - MinIO 对象布局记录
  - 三条基础业务规则（list定义、episode状态、task_type归类）
verification:
  - PDF已阅读，核心结构已理解
  - MinIO 连接成功：list_buckets, list_objects, get_object 均验证通过
  - 样例元数据已读取，确认了 processed 层的 QC 依赖
notes:
  - C 节点同时覆盖了"文档分析"和"MinIO 实查"两部分
  - MinIO 实查结果直接驱动了后续 Node F 的规则设计
```

## Edge C->F: MinIO 数据湖控制面规则确定

```yaml
edge_id: C->F
from: C
to: F
path: main
status: stable（三条基础规则已确定）
method: 基于 MinIO 实查数据，确定数据湖接入的业务基础规则
execution_chain:
  - 基于实查对象结构定义 list = bucket + list_prefix
  - 确定扫描采用任意深度按层 namespace discovery + 结构特征识别 + 已知 List prefix 分片
  - 定义 episode 三层生命周期状态（ingestable/processable/qc_ready）
  - 确定 task_type 不再由扫描器 authoritative 自动落定，而由 `admin/qc_manager` 通过任务类型管理系统维护
  - 确定 `待分类` 作为保底任务类型，承接新扫描 batch、移出任务的 batch、删除任务类型后回收的 batch
  - 确定错分 batch 的标准纠正流程：先在数据总库确认当前归属，再从原任务类型移出回到 `待分类`，最后加入正确任务类型
inputs:
  - MinIO 实查结果（Node C 产出）
  - 用户关于"一个任务可能拆散到多个list"、"多次少量写入"的输入
outputs:
  - 三条基础业务规则
  - PostgreSQL 控制面模型决策
  - 全量扫描策略原则
verification:
  - 规则与 MinIO 真实对象结构对照一致
  - 规则已记录到 decision-records.md、progress.md、current-session.md
notes:
  - 这是从"调研"到"方案设计"的转折边
  - 三条规则是后续 Node F 字段设计的前置约束
```

## Edge F->D: 基于控制面方案的 QC 改造

```yaml
edge_id: F->D
from: F
to: D
path: main
status: ready（Node F 已闭环，可进入实现）
method: 将 QC 方案迁移到 MinIO 数据湖控制面之上
execution_chain:
  - 按 v3 实现任意深度 namespace discovery，并为已知 List 生成持久化 shard
  - 每日 smart / 每周 full / manual_prefix 统一进入 PostgreSQL 队列；普通前端保持一键操作
  - 独立 scan-coordinator/scan-worker 使用 lease、heartbeat、timeout、terminate/kill 和分片重试
  - 每个 List shard 流式扫描，使用 Episode 指纹、选择性关键对象索引和 bulk upsert；禁止逐对象 ORM 查询
  - 只有成功完整 shard 可产生缺失证据；两次成功未见后软失活，重现自动恢复
  - 扫描结果原子发布后触发 batch/task asset recompute，running 重算通过 rerun_requested 保证不漏更新
  - 改造现有本地 ingestion 为 MinIO 对象读取
  - 改造 manual QC 上下文加载为 MinIO 对象访问
  - 实现 media presign refresh 与受控下载接口
  - 为 `database` 页面建立长期正式的数据资产读模型：`batches.list_id`、`batch_asset_rollups`、`batch_asset_recompute_jobs`、独立数据资产 API 与周期性对账
  - 在 Route C' 之上扩展任务级资产画像 Route T2：`task_asset_rollups`、`task_asset_recompute_jobs`、`GET /api/data-assets/tasks*`，并保持 batch rollup 为唯一聚合基座
inputs:
  - MinIO 控制面方案（Node F 已产出）
  - 现有 QC 代码（local file 基线）
  - 现有 manual QC 页面实现
outputs:
  - MinIO 兼容的 ingestion 链路（待实现）
  - Object 访问协议实现（待实现）
  - `ManualQcContext.media[]` 合同落地（待实现）
  - 任务级资产投影与 API（业务逻辑已确认，代码待实现）
verification:
  - 业务规则已由 v3 闭环；Step 0 必须重新执行只读 MinIO census，并以当前 DB 58 active List / 5,987 Inventory / 约 291 万对象索引作为对比基线
  - 必须分别验收每日定时、性能/扩展、故障注入、删除/恢复和前端一键操作，详见 v3 第 13 节
notes:
  - 现有 manual QC（telemetry 指标、timeline、review lock）保持不动
- 主要改造点在"对象从哪里读"和"对象映射怎么查"
- 自 2026-07-15 起，`数据总库` 的长期正式方案已从“Episode 实时聚合增强”收敛为 Route C' 读模型升级路线；`/api/database` 保持 Episode 明细路径，资产聚合走独立 `/api/data-assets/*`
- 自 2026-07-16 起，数据总库正式三视角固定为 Episode / Batch / Task；任务层采用 Route T2，只从 `batch_asset_rollups` 汇总
- 自 2026-07-17 起，扫描实现只允许遵循 `docs/scan-architecture-final-plan-v3.md`；v2 保留追溯但不得作为编码依据
```

## Edge D->E: 整合交付

```yaml
edge_id: D->E
from: D
to: E
path: main
status: draft（未开始）
method: 整合所有调研与实现成果
execution_chain:
  - 整合公开数据集QC调研文档
  - 整合Linker TeleDex数据格式分析
  - MinIO 数据湖方案说明
  - QC 方案与实现说明
  - 撰写完整交付文档
inputs:
  - 公开数据集QC调研文档
  - Linker TeleDex数据格式分析
  - MinIO 数据湖方案
  - QC 方案与实现
outputs:
  - 完整交付文档
  - 可交付给领导的文档
verification:
  - 未开始
notes:
  - 交付范围需结合 MinIO 数据湖方案和用户实际使用场景决定
  - 交付对象可能同时包含"调研成果"和"系统实现"
```
