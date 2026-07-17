# MinIO 扫描入库架构升级 - 最终实施方案 v3

> Status: 正式主干，替代 `scan-architecture-final-plan-v2.md`
> Date: 2026-07-17
> Basis: 当前代码审计 + 生产 PostgreSQL 基线 + v2 决策复核

## 1. 目标

在不依赖 MinIO Bucket Notification、S3 Inventory 或上传端改造的前提下，建立一套：

- 每日自动运行；
- 前端一键触发；
- 可分片、可并行、可取消、可超时、可重试；
- 对新增、修改、删除和恢复均可最终对齐；
- 当前规模显著提速，并能随 List 数量横向扩展；
- 扫描失败不会无限卡死，也不会用不完整结果误判删除；
- 不破坏 Batch、Episode、QC、导出和审计历史；
- 与 `batch_asset_rollups -> task_asset_rollups` 资产投影链路可靠联动；

的 MinIO -> PostgreSQL 扫描入库系统。

## 2. 真实环境基线

2026-07-17 生产 PostgreSQL 快照：

| 指标 | 数值 |
|---|---:|
| Active List | 58 |
| 一级 List | 49 |
| 二级 List | 9 |
| raw-only List | 6 |
| processed-only List | 0 |
| raw + processed List | 52 |
| Episode Inventory | 5,987 |
| Active-scope Episode | 5,986 |
| `episode_objects` | 2,909,780 |

最近两次旧扫描停留在 `classifying`，进度约为 24,051 prefixes / 23 lists / 2,526 episodes。由此确认当前瓶颈同时包括：

- 全桶 `recursive=True`；
- `list(...)` 把全部对象放入内存；
- 数百万对象逐行 ORM 查询/upsert；
- 扫描过程中部分提交，失败后留下不完整代次；
- FastAPI 进程内 daemon 线程无法可靠终止；
- 单任务混合 discovery、业务解析、入库和删除判断。

旧文档中的“约 10 万对象”估算作废。v3 以当前约 291 万对象为基线。

## 3. 正式架构

```text
Frontend / Scheduler
  -> POST smart scan / scheduled smart scan
  -> scan-coordinator (single active coordinator via PostgreSQL lock)
       -> namespace discovery
       -> create scan_job + scan_shards
       -> aggregate progress / cancel / retry / finalize
  -> PostgreSQL persistent queue
       -> scan_jobs
       -> scan_shards
       -> scan_prefix_states
  -> scan-worker replicas (initially 2)
       -> FOR UPDATE SKIP LOCKED
       -> lease + heartbeat
       -> killable child process per shard
       -> streaming MinIO enumeration
       -> episode-level fingerprint + selective object index
       -> atomic shard publish
  -> business_resolver
       -> List / Batch / EpisodeInventory / Episode
       -> source presence / current readiness / recovery
  -> persistent asset recompute queue
       -> batch_asset_rollups
       -> task_asset_rollups
```

Docker Compose 正式增加：

- `scan-coordinator`: 1 个实例，负责定时触发、discovery、任务聚合、过期 lease 回收；
- `scan-worker`: 初始 2 个实例，负责 shard 执行；
- FastAPI 只负责 API 和权限，不执行长时间扫描；
- PostgreSQL 是队列和状态事实源，进程重启不丢任务。

## 4. 四种扫描职责

### 4.1 `smart`

前端主按钮和每日定时任务的默认模式。用户无需选择技术参数。

执行链：

1. 运行 namespace discovery；
2. 新 List、`suspect_missing` List、失败待重试 List 立即创建高优先级 shard；
3. 对 `next_scan_at <= now()` 的已知 List 创建 shard；
4. 若最近 7 天没有成功 `full`，自动升级为 `full`；
5. 返回 job id，后端继续执行，前端只展示总进度和结果。

同一 bucket 同时只允许一个 active `smart/full` job。重复点击返回现有任务，不重复创建。

### 4.2 `incremental`

只扫描新发现、需确认缺失、失败重试和已到 `next_scan_at` 的 List。它仍会完整流式枚举被选中的 List；“增量”表示缩小 List 范围并只解析变化 Episode，不表示 MinIO 支持变更日志。

### 4.3 `full`

完整 discovery 后为所有已知 List 建 shard，忽略 `next_scan_at`。`full` 仍按 List 分片和流式执行，禁止恢复为全桶 `list(...)`。

### 4.4 `manual_prefix`

管理员定向重扫一个或多个 List。用于故障排查、上传完成后的立即同步和缺失确认。

## 5. 调度规则

- 每日 `00:00 Asia/Shanghai` 自动创建 `smart` job；时间继续由 `SCAN_CRON_HOUR/MINUTE` 配置覆盖；
- 每周日 `02:00 Asia/Shanghai` 自动创建 `full` job；若已有 active job，则合并/延后，不并发启动第二个全局任务；
- coordinator 每 10 秒执行任务聚合、lease 回收和 retry 到期检查；
- 定时任务通过 PostgreSQL advisory lock + active-job 幂等约束防止多实例重复创建；
- Docker/主机重启后，pending/retry_wait shard 继续执行，过期 running shard 被回收重试。

自适应 List 扫描频率：

```text
检测到变化       -> next_scan_at = now + 30min
连续 1 次无变化  -> now + 2h
连续 2 次无变化  -> now + 12h
连续 3 次无变化  -> now + 1day
连续 4 次及以上  -> now + 7days
```

支持 `adaptive / realtime / daily / weekly / manual` 覆盖策略。任何 `adaptive` List 最长 7 天必须扫描一次；每周 `full` 是最终一致性兜底。

## 6. Namespace Discovery 与上传规范

### 6.1 Discovery

1. 从 bucket 根开始，用 `recursive=False` 按层遍历 prefix；
2. prefix 的直接子级出现 `raw/` 或 `processed/`，且其下存在 `episode_*` 时确认为 List；
3. 确认 List 后停止进入其 Episode/相机/逐帧对象内部；
4. 未知结构分支继续向下探索；
5. 父子同时命中时使用 deepest-match；父级有不属于子 List 的直接 Episode 时父级保留；
6. discovery 失败只使 discovery shard 失败，不允许据此失活任何 List。

### 6.2 上传规范

推荐新数据使用 `<bucket>/<list>/`，但扫描正确性不能依赖固定深度。允许 `<bucket>/<group>/<list>/` 等历史和业务分组层级。

硬约束：

- `raw/`、`processed/` 是 List 的直接子级；
- Episode 目录名符合 `episode_*`；
- 同一 List 的 raw/processed 位于同一 canonical list prefix；
- List 身份为 `(bucket, canonical_list_prefix)`；
- 路径移动或重命名视为“旧 List 缺失 + 新 List 出现”，不自动迁移 QC 历史；
- 如需业务迁移，必须通过独立管理员迁移操作并写审计记录。

因此不强制“bucket 下一层必须直接是 List”。

## 7. 分片、流式处理与扩展能力

### 7.1 默认分片

默认一个 List prefix 对应一个 shard。Worker 流式遍历，不把对象全集放入内存。

### 7.2 超大 List

`scan_shards.parent_shard_id` 和 `shard_type` 必须从第一版保留。满足任一条件时，后续扫描自动使用 Episode-group 子分片：

- Episode 数 > 10,000；
- 上次对象数 > 1,000,000；
- 连续两次扫描耗时 > 600 秒。

父 discovery shard 只非递归枚举 `raw/processed` 下的 Episode prefix，再按确定性 Episode 范围生成子 shard。删除判断限定在成功完成的子 shard 范围内。

### 7.3 数据库写入

- 禁止每个对象一次 ORM 查询；
- 每个 shard 批量加载已有 Episode 摘要和关键对象索引；
- 使用 PostgreSQL bulk upsert；
- MinIO 枚举完成前不发布缺失结果；
- 一个 shard 的业务结果在单一数据库事务中原子发布；
- shard 失败时事务回滚，旧成功快照继续可用。

## 8. Episode 指纹与选择性对象索引

`episode_objects` 不再保存所有逐帧 PNG/PLY。只保存业务可寻址对象：

- manifest / metadata / telemetry / camera_info；
- RGB/深度预览视频；
- timestamp NPY；
- raw MCAP / recording_info / device_info / raw metadata；
- API 明确允许预览或下载的其他对象。

以下 bulk 对象不逐行持久化：

- depth PNG 帧；
- pointcloud PLY 帧；
- 其他数量随帧数线性增长、没有单对象业务访问需求的文件。

扫描仍流式经过所有对象，并在 `episode_inventory` 保存：

```text
raw_object_count
processed_object_count
raw_total_size_bytes
processed_total_size_bytes
raw_content_fingerprint
processed_content_fingerprint
latest_object_modified_at
```

fingerprint 对排序稳定的 `(object_key, etag, size, last_modified)` 做确定性滚动哈希。任意 bulk 对象新增、修改或删除都会改变 Episode 指纹；只有变化 Episode 才重新读取 manifest 和更新业务模型。

旧 bulk 行清理必须在新扫描器 Shadow 验证后单独执行，不允许在首次迁移中直接删除 291 万历史行。

## 9. 删除、缺失与恢复

### 9.1 统一来源状态

List、EpisodeInventory 和关键 EpisodeObject 使用：

```text
present -> suspect_missing -> missing
                         \-> present (recovered)
```

- 第一次成功完整扫描未发现：`suspect_missing`，安排 10 分钟后确认扫描；
- 第二个独立且成功完整扫描仍未发现：`missing`；
- 后续重新发现：自动恢复 `present`；
- skipped / failed / cancelled / timeout shard 不增加 missing streak，也不做删除判断。

### 9.2 List

- `missing` 后 `ListRecord.is_active=false`；
- 不删除 Batch、Episode、QC 或审计历史；
- 恢复后 `is_active=true` 并执行一次完整 List shard；
- 人工 task_type 归属不因缺失或恢复被覆盖。

### 9.3 Episode

- EpisodeInventory 保存 `source_status`；
- raw/processed 根均确认 missing 后，业务 `Episode.is_active=false`；
- 重现后恢复为 true；
- 数据资产、数据集导出和新 QC 派发只使用 active Episode；
- 历史 QC task/revision/decision log 永久保留。

### 9.4 关键对象与 Bulk 对象

- 关键对象逐行标记 suspect/missing/recovered；missing 对象禁止签发预览或下载 URL；
- bulk 对象通过 Episode count/size/fingerprint 对齐，不在本地伪造不存在的逐对象记录；
- manifest/telemetry/video 等必需对象缺失会使 Episode 当前 readiness 降级。

### 9.5 Readiness 状态

现有 `ingestable -> processable -> qc_ready` 不再作为只能升级的当前状态：

- `state`: 当前 readiness，可升级也可因对象缺失而降级；
- `max_observed_state`: 历史最高 readiness，只升不降。

例如历史曾 `qc_ready`、当前 telemetry missing：当前 `state=processable`，`max_observed_state=qc_ready`。

### 9.6 物理清理

扫描器永不自动物理删除 List、Batch、Episode、Inventory、QC 和审计数据。未来 purge 必须是独立管理员流程，显式确认依赖和影响范围并写审计。

## 10. 数据库演进

### 10.1 `scan_jobs`

现有 `scan_jobs` 原地扩展，保留 `String(64)` 主键。新任务 ID 使用 UUID/ULID 字符串。禁止 v2 的“重命名旧表并新建 BIGINT scan_jobs”方案，因为现有多张控制面表通过字符串外键引用该表。

新增字段包括：

```text
scan_mode, priority, trigger_source
total/succeeded/failed/running/skipped_shards
heartbeat_at, cancel_requested_at
error_summary, created_at, updated_at
```

旧字段在兼容期保留，前端切换后再单独清理。

### 10.2 `scan_shards`

使用 BIGINT IDENTITY 主键，`scan_job_id` 为 String(64) 外键。状态：

```text
pending / running / retry_wait / succeeded / skipped
failed / cancelling / cancelled / timeout
```

保留 priority、attempt、lease、heartbeat、timeout、进度、错误、parent shard 和 retry 时间。

### 10.3 `scan_prefix_states`

保存 `(bucket, prefix)` 唯一键、最后成功/变化时间、连续无变化次数、`next_scan_at` 和 scan policy。

### 10.4 来源状态字段

List、Inventory、关键 Object 增加 source status、missing streak、first/last missing、last confirmed present 等字段；Episode 增加 `is_active`；Inventory 增加 `max_observed_state` 和 Episode 聚合指纹字段。

### 10.5 Asset recompute

`batch_asset_recompute_jobs` 和 `task_asset_recompute_jobs` 增加 `rerun_requested`。running 时再次 enqueue 不重置为 pending，而是请求完成后再运行一次。

## 11. 可靠性状态机

### 11.1 Worker

- Worker 用 `FOR UPDATE SKIP LOCKED` 领取；
- 每个 shard 在可终止子进程执行；
- MinIO connect timeout 5 秒、read timeout 60 秒；
- shard 默认 wall-clock timeout 600 秒；
- 父进程先 terminate，5 秒后仍未退出则 kill；
- heartbeat 每 10 秒，lease 90 秒；
- 失败重试采用 30 秒 -> 2 分钟 -> 10 分钟，最多 3 次并带抖动；
- lease 过期由 coordinator 自动回收；
- 进程/容器重启后任务从 PostgreSQL 恢复。

### 11.2 Job

Job 终态：

```text
succeeded
partially_failed
failed
cancelled
```

存在重试耗尽 shard 时必须结束为 `partially_failed/failed`，不能永久显示 running。前端明确显示失败 shard、错误摘要和“重试失败项”。

### 11.3 删除安全

只有完整成功枚举且原子发布的 shard 可以产生“未发现”证据。任何失败路径都只能影响新鲜度，不得把现有数据误标 missing。

## 12. 一键操作合同

前端保留一个主按钮：`开始扫描`。

点击后：

1. 调用 `POST /api/database/scan`，默认 `mode=smart`；
2. 若已有 active job，直接返回该任务；
3. 后端自动完成 discovery、模式升级、分片、并行、重试、缺失确认和资产重算；
4. 前端显示整体百分比、成功/运行/等待/失败数和最终摘要；
5. 用户关闭页面不影响任务；重新打开可继续查看；
6. 普通操作不要求用户选择 Worker 数、prefix、timeout 或重试参数。

高级操作收在二级入口，仅 admin/qc_manager 可用：全量扫描、定向扫描、取消、重试失败项。

## 13. 五项能力评估与验收

### 13.1 每天定时扫库入库

结论：支持。

验收：连续 7 天每天按配置时区产生一个且仅一个 scheduled smart job；服务重启不重复、不漏任务；新 List 在下一次 daily smart 后进入 PostgreSQL。

### 13.2 速度和扩展性

结论：对当前环境预计大幅提速，且增长主要表现为新增 List 时可横向扩展。

提速来源：避免全桶对象树、固定内存流式处理、选择性对象索引、Episode 指纹短路、bulk upsert、List 分片、双 Worker、自适应频率。全量对账仍是 O(MinIO 对象数)，这是无事件通知时不可消除的下界。

验收：Shadow 基线中峰值内存不随 bucket 总对象数线性增长；无变化 Episode 不重复读 manifest；数据库不再产生逐对象 SELECT；当前全量扫描耗时显著低于旧成功基线；增加 Worker 时吞吐可测量提升且错误率不恶化。

扩展边界：若增长来自新增 List，可增加 Worker 横向扩展；若单 List 超过阈值，自动使用 Episode-group 子分片。若未来达到数亿对象且要求分钟级发现，必须取得 Bucket Notification/S3 Inventory/上传完成事件之一，纯 ListObjects 轮询无法无限扩展。

### 13.3 鲁棒性

结论：支持。

验收：注入 MinIO read hang、Worker kill、容器重启、数据库暂时不可用和单 shard 数据异常；任务必须超时/重试/恢复或明确失败，不能永久 running；失败 shard 不影响成功 shard，也不能触发误删除。

### 13.4 删除同步

结论：支持最终一致的软删除和自动恢复。

验收：删除 List、完整 Episode、manifest、telemetry、视频和 bulk frame 后，分别验证第一次扫描进入 suspect、第二次成功确认进入 missing、active scope/预览/QC/导出正确排除，历史记录保留；对象恢复后状态和资产投影自动恢复。

### 13.5 傻瓜式操作

结论：支持。

验收：用户只点击一次 `开始扫描` 即获得 job；无需保持页面；后台自动完成所有技术步骤；最终页面给出成功、部分失败或失败的明确结论；重复点击不创建重复全局任务。

## 14. 实施顺序

1. 只读 census + 当前性能基线；
2. schema migration：原地扩展 scan_jobs、新增 shard/prefix state/source state/fingerprint/rerun；
3. 抽离 `business_resolver.py`；
4. namespace discovery；
5. scan-coordinator + 独立 scan-worker + 子进程超时/lease/retry；
6. 流式 List shard + Episode 指纹 + 选择性对象索引 + bulk upsert；
7. missing 二次确认、readiness 降级和恢复；
8. asset recompute `rerun_requested`；
9. API + 一键前端 + 进度/取消/失败重试；
10. Shadow 对比 -> 少量 prefix 写入 -> 全 prefix 单 Worker -> 双 Worker；
11. 切换每日 smart / 每周 full 调度；
12. 稳定观察后停止旧 bulk 行写入，再独立评估历史 bulk 行清理。

## 15. 不做清单

- 不新增 `object_inventory`；
- 不依赖固定一级目录；
- 不依赖 MinIO 事件通知；
- 不把全桶对象装入内存；
- 不逐对象 ORM 查询；
- 不在失败/跳过 shard 上做删除判断；
- 不自动物理删除业务和审计历史；
- 不重建 `scan_jobs` 主键体系；
- 不让 FastAPI 进程执行长时间扫描；
- 不要求普通用户理解扫描模式和 Worker 参数。

## 16. 最终定义

> v3 = 任意深度 namespace discovery + 已知 List 分片 + PostgreSQL 持久队列 + 独立 coordinator/Worker + 可终止子进程 + 流式 Episode 指纹 + 选择性对象索引 + 原子 shard 发布 + 二次确认软删除/自动恢复 + 幂等资产重算 + 每日 smart/每周 full + 前端一键操作。
