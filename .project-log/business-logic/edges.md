# Business Logic Edges

## Edge Template

```yaml
edge_id: <edge-id>
from: <start-node-id>
to: <target-node-id>
path: main | branch | archived
status: draft | stable | testing | validated | archived
method: <method summary>
execution_chain:
  - <step 1>
  - <step 2>
inputs:
  - <input>
outputs:
  - <output>
parameters:
  - name: <parameter-name>
    type: <data-type>
    default: <default-value>
    source: <config/code/user/hardware>
error_handling:
  - <failure condition and response>
verification:
  - <verification method>
```

## Edges

```yaml
edge_id: ingest-to-qc-queue
from: ingest-manager
to: qc-task-queue
path: main
status: draft
method: 新入库数据先进入 QC 候选池，再按抽检比例或全量策略生成 QC 任务并进入派发队列
execution_chain:
  - Scanner / IngestManager 识别新 batch / episode
  - 系统创建或更新 task_type / batch / episode 记录
  - 判断 processed 是否存在
  - processed 就绪则标记 processed_ready，进入待抽检候选池
  - `qc_manager` / `admin` 为 batch 选择派发模式：默认按比例抽检，可切换为全量派发
  - 系统按派发计划筛选 sample episode，并为 sample 集生成 QC 任务进入 pending_assign
  - 未抽中的 episode 保持候选状态，等待后续补派或全量展开
inputs:
  - raw / processed episode
  - dispatch mode
  - sampling ratio
outputs:
  - sampled qc_task
  - pending_assign 状态
  - sampling audit trail
verification:
  - 新入库 episode 可先在候选池中被主管看到，抽检后样本任务进入任务池
```

```yaml
edge_id: manager-assign-reviewer
from: qc-task-queue
to: auth-rbac
path: main
status: draft
method: 主管把 QC 任务派发给 reviewer 账号
execution_chain:
  - qc_manager 打开任务池
  - 选择 reviewer
  - 系统写入任务责任人和分配历史
  - reviewer 待办列表更新
inputs:
  - task_id
  - reviewer_id
outputs:
  - assigned task
  - assignment_history
verification:
  - reviewer 登录后可在我的待办看到任务
```

```yaml
edge_id: reviewer-submit-with-audit
from: manual-qc-ui
to: audit-log
path: main
status: draft
method: reviewer 提交 QC 结果后同步写审计事件和 revision 历史
execution_chain:
  - reviewer 打开任务并完成检查
  - 提交 POST /api/qc/manual/{episode_id}
  - ResultStore 写当前结果与 revision
  - AuditLog 写入 action / payload snapshot / status change
inputs:
  - reviewer_id
  - qc payload
outputs:
  - qc_result
  - qc_review_revision
  - audit_event
verification:
  - 可回溯谁在何时对哪条 episode 做了什么提交
```

```yaml
edge_id: lan-browser-access
from: deploy-host
to: dashboard
path: main
status: draft
method: 员工通过局域网浏览器访问中心主机上的 QC 平台
execution_chain:
  - 中心主机运行前后端和数据库
  - 员工电脑通过浏览器打开平台地址
  - 登录后进入各自权限范围内页面
inputs:
  - LAN URL
  - user session
outputs:
  - dashboard 页面
verification:
  - 不同电脑可访问同一套数据与 QC 结果
```

```yaml
edge_id: dashboard-to-batch-detail
from: dashboard
to: batch-detail
path: main
status: draft
method: 点击批次进入批次详情页
execution_chain:
  - 在主界面选中任务种类
  - 点击某个批次
  - 打开该批次详情页
inputs:
  - batch_id
outputs:
  - batch-detail 页面
verification:
  - 可从主界面进入批次详情
```

```yaml
edge_id: database-to-qc-reason-codes
from: database-view
to: qc-reason-codes
path: main
status: draft
method: 手动QC/复查时选择原因码
execution_chain:
  - 在数据库页面选中 episode
  - 打开 QC 面板
  - 选择原因码并提交
inputs:
  - episode_id
  - qc_result
outputs:
  - reason_code
  - note
verification:
  - 结果可回写到 QC 记录
```

```yaml
edge_id: manual-qc-end-to-end
from: dashboard
to: result-store
path: main
status: draft
method: 手动QC页面完成 episode 级裁决并写回结果
execution_chain:
  - 在 Dashboard 选择 batch 或 episode
  - 后端校验 processed 数据存在性
  - 创建 review_lock 并将 episode 状态切换为 in_review
  - 进入 Manual QC 页面查看视频、时间轴、指标摘要和异常段
  - 操作员完成核查并选择 qc_result / reason code / note
  - 前端校验通过后提交 POST /api/qc/manual/{episode_id}
  - ResultStore 写入 qc_review_revision 与当前 qc_result
  - episode 状态切换为 done
  - batch_qc_summary 刷新
inputs:
  - episode_id
  - frame data
  - episode summary metrics
  - segment violations
  - reason_code / note
outputs:
  - QC 结果记录
  - batch qc_status 更新
verification:
  - 页面提交后可在 Report 中看到结果与统计变化
```
