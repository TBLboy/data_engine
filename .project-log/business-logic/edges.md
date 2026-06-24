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
  - 确定全量扫描采用全层级递归发现 + 结构特征识别
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
  - 基于既定 6 表控制面实现 MinIO 扫描与对象映射
  - 改造现有本地 ingestion 为 MinIO 对象读取
  - 改造 manual QC 上下文加载为 MinIO 对象访问
  - 实现 media presign refresh 与受控下载接口
inputs:
  - MinIO 控制面方案（Node F 已产出）
  - 现有 QC 代码（local file 基线）
  - 现有 manual QC 页面实现
outputs:
  - MinIO 兼容的 ingestion 链路（待实现）
  - Object 访问协议实现（待实现）
  - `ManualQcContext.media[]` 合同落地（待实现）
verification:
  - 业务规则已齐备；实现前仅剩 `yaocao` 全量 list census 可作为规模校验补充，不阻塞编码
notes:
  - 现有 manual QC（telemetry 指标、timeline、review lock）保持不动
  - 主要改造点在"对象从哪里读"和"对象映射怎么查"
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
