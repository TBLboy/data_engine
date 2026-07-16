# MinIO 分层并行扫描架构方案——技术评估

> 评估对象：GPT 输出的 `minio_layered_parallel_scanning_architecture.md`
> 评估人：Codex
> 日期：2026-07-16
> 项目路径：`/home/tbl/Project/data_collect/software/`

---

## 一、当前现实基线

在做任何判断之前，先确认当前的实际情况：

| 指标 | 实际数值 |
|------|----------|
| MinIO 桶 | 1 个（`yaocao`） |
| 批次（Batch） | 52 |
| Episode 总量 | 5,217 |
| 含 processed manifest 的 Episode | 4,525 |
| 纯 raw（待后处理）Episode | 692 |
| 估算 MinIO 对象总数 | ~10 万 |
| 平均每个 Batch 的 Episode 数 | ~100 |
| 平均每个 Batch 的对象数 | ~2,000 |
| 当前扫描代码行数 | 835 行 |
| 当前触发方式 | 手动 + 每日 00:00 cron |
| 当前执行模型 | FastAPI 进程内 daemon 线程 |
| 当前瓶颈 | `list_objects(recursive=True)` 挂死 |

---

## 二、方案总体评价

GPT 方案是一个**从第一性原理设计的长期架构**，设计思想本身是正确和完整的。但方案整体定位是一个"终极形态"的最大化版本，需要在落地时**根据当前实际规模和痛点做显著裁剪**。

核心判断：

> **方案的核心架构方向（子进程替代线程、Prefix 分片、流式不存全量、持久化队列、分片级重试）必须采纳。方案中的多个表和层级在当前规模下属于过度工程化，不应在当前阶段实现。**

下面对每个关键模块做逐项分析。

---

## 三、逐项分析

### 3.1 子进程模型 — 必须采纳（最高优先级）

```text
提案：每个 ScanShard 启动独立子进程，父进程负责超时终止
```

当前用 `threading.Thread`（daemon=True）执行扫描，线程一旦在 `list_objects` 的 HTTP 请求上挂住，Python 无法在同一进程内安全终止它。`_cleanup_stale_jobs()` 只能更新数据库状态，停不了活线程。

子进程模型是**唯一能可靠终止卡死扫描的方法**——`Process.terminate()` 由操作系统直接 SIGTERM，宽限期后 `kill()` 发 SIGKILL。Python 线程做不到这一点。

**判断：必须实现，且这是整个改造中优先级最高的一项。**

### 3.2 Prefix 分片 — 必须采纳

```text
提案：一个 Batch/List Prefix = 一个 ScanShard，分配给不同 Worker 并行扫描
```

与当前数据结构天然匹配。现有的 `ListRecord.list_prefix` 边界就是分片单元。实际收益：

- 一个批次扫描失败不影响其他 51 个批次
- 可以按分片显示进度（而不是「scanning...」）  
- 分片级重试粒度合理：重扫一个批次而不是整个桶
- 批次完成即可触发对应 `batch_asset_recompute_job`

**判断：方向正确，现有数据模型已经支撑这个划分，实现成本可控。**

### 3.3 流式 + 批量写入 — 必须采纳

```text
禁止：list(service.list_objects(...))
推荐：for obj in list_objects(...): buffer.append(obj); if len(buffer) >= 200: flush
```

当前全桶 ~10 万对象全部 `list()` 打进内存再构建 prefix tree，内存占用随对象数线性增长。流式分批解决两个问题：内存上限固定，以及 MinIO 响应的部分超时可以只损失一个批次而不是整个扫描。

**判断：思路正确，实现简单，必须采纳。**

### 3.4 PostgreSQL 持久化队列 — 部分采纳

```text
提案：scan_jobs + scan_shards 两张表，Worker 通过 FOR UPDATE SKIP LOCKED 领取
```

`FOR UPDATE SKIP LOCKED` 是 PostgreSQL 的成熟并发控制原语，多个 Worker 安全并行领取任务的正确方式。`batch_asset_recompute_jobs` 和 `task_asset_recompute_jobs` 已经在用相同的模式，有先例可循。

但方案中的 `scan_jobs` 字段过多（status / phase / cancel_requested_at / 各种统计计数器），在 52 个批次规模下不需要这么复杂的 job 状态机。同样，`scan_shards` 中的 `estimated_weight`、`historical_object_count`、`historical_duration_ms` 等字段在当前阶段属于过早优化。

**判断：采纳核心的 `scan_jobs` + `scan_shards` 模型和 `SKIP LOCKED` 分配机制。砍掉不必要的统计计数和历史权重字段，保留到需要时再加。**

### 3.5 `object_inventory` 对象索引层 — 不建议新增

```text
提案：新增 object_inventory 表，作为 MinIO → DB 的通用对象镜像层
```

当前已有以下三层做同样的事：

| 现有表 | 粒度 | 内容 |
|--------|------|------|
| `EpisodeObject` | 单个 MinIO 对象 | object_key / etag / size / last_modified / role |
| `EpisodeInventory` | 单个 Episode | manifest_hash / metadata_hash / state / duration / frame_count |
| `DiscoveredPrefix` | MinIO prefix | has_raw_child / has_processed_child / has_episode_grandchild |

在当前架构中，`EpisodeObject` 已经在承担对象索引的角色。业务解析器现在已经直接从扫描结果写入这些表，**不需要在中间再插一层**。

在什么情况下 `object_inventory` 才需要？当以下任一条件成立：
- 需要记录大量不属于 Episode 的对象（日志、中间文件、配置等）
- 需要支持纯对象级 API 查询而不经过 Episode 业务层
- 需要在 MinIO 层面做跨 Batch / Episode 的对象级对比

当前场景不满足上述任何条件。数据湖中所有对象都属于某个 Episode，Episode 就是天然的对象容器。

**判断：不新增 `object_inventory`。现有 `EpisodeObject` + `EpisodeInventory` 已经承担了这个角色。**

### 3.6 `scan_prefix_states` 冷热调度 — 不建议引入

```text
提案：HOT / WARM / COLD / ARCHIVED 四级调度策略，动态调整扫描频率
```

这是为**数百个以上 prefix、历史数据不断积累**的场景设计的。

当前 52 个批次，绝大部分是活跃数据，且新数据通过每日扫描一次即可发现。在 52 批次的规模下：
- 所有批次都是"热"的
- 每日全量扫描 52 个分片（每个 ~2,000 对象）完全可行
- 冷热调度的管理成本（状态维护、规则调整、bug 排查）高于收益

**判断：当前阶段不需要。等批次量 > 500 且单次全量扫描超过 2 小时再引入。**

### 3.7 超大 Batch 自动二次拆分 — 不需要

```text
提案：单 Batch 对象数 > 100,000 或扫描时长 > 10 分钟时，按 Episode 拆分子分片
```

当前最大 Batch 大约 2,000 个对象，离阈值差两个数量级。

**判断：当前不需要。当单个 Batch 超过 10,000 Episode 时再实现。**

### 3.8 并发建议 — 当前阶段太高

```text
提案：初始 1 Discovery + 3 Scan Worker，后续扩展到 4-8 个
```

当前瓶颈不在并发能力而在稳定性。MinIO 是外部单机服务器，3 个以上并发 `list_objects` 可能反而导致 MinIO 端连接数压力增大甚至触发限流。此外当前数据库写入已经是单事务提交模型，多个 Worker 同时写可能引入新的锁竞争。

**判断：初始 1 个 Discovery Worker + 1-2 个 Scan Worker。优先保证稳定完成，再根据实际吞吐测量决定是否扩容。**

### 3.9 实施顺序 — 可以合并

```text
提案：10 步，步步推进
```

在当前规模下，可以把相关步骤合并，简化为三个阶段的实施：

**判断：建议压缩为 3 个阶段而不是 10 步。**

---

## 四、推荐的实施路径：3 阶段裁剪版

### 阶段 A：治本（解决卡死问题）— 预期改动量小

1. **`MinioService.list_objects` 增加超时**
   - `minio-py` 底层 HTTP 连接设置 `timeout` 参数
   - 单次 `list_objects` 请求超时后触发重试

2. **扫描器从线程改为子进程**
   - 在 `scan_queue.py` 中用 `multiprocessing.Process` 替代 `threading.Thread`
   - 父进程监控子进程超时（设置合理的 wall-clock deadline）
   - 超时后 `terminate()` → 等 N 秒 → `kill()`
   - 重试 2-3 次后标记失败

这是最小改动解决核心可靠性问题的路径。甚至在子进程模型就绪之前，仅给 `list_objects` 加超时就能杜绝无限挂死的现象。

### 阶段 B：分片化（解决效率和可观测性）— 预期改动量中

3. **新增 `scan_shards` 表（裁剪版）**
   ```sql
   scan_shards
   -----------
   id
   scan_job_id → scan_jobs.id
   bucket
   prefix
   status        -- pending / running / succeeded / failed / cancelled
   attempt_count
   last_error
   lease_owner
   lease_expires_at
   started_at
   finished_at
   ```

   只保留核心字段，不引入 weight / historical_duration 等过早优化。

4. **Prefix Discovery 阶段生成分片**
   - 先非递归枚举已知 `lists.list_prefix` 生成 shard 列表
   - 不再 `list_objects(recursive=True)` 遍历全桶

5. **流式扫描每个 shard**
   - `for obj in list_objects(prefix=shard_prefix, recursive=True)` 流式处理
   - 每 200 条批量 flush DB

6. **前端展示分片进度**

### 阶段 C：并行化（规模增长时再触发）— 预期改动量小

7. **启动 2 个 Worker 子进程**
   - 各自从 `scan_shards` 用 `SKIP LOCKED` 领取
   - 每个 Worker 独立子进程执行一个 shard

8. **分片级重试（指数退避）**

阶段 C 在当前 52 批次规模下不一定需要；等数据量到达 200+ 批次时再评估。

---

## 五、各模块采纳/拒绝清单

| 模块 | 提案内容 | 评估结果 |
|------|----------|----------|
| 子进程模型 | 独立子进程 + 超时终止 | **采纳，阶段 A** |
| MinIO timeout | connect/read timeout | **采纳，阶段 A** |
| Prefix 分片 | Batch = 一个 shard | **采纳，阶段 B** |
| 流式 + 批量写入 | for + buffer + flush | **采纳，阶段 B** |
| scan_shards 表 | 持久化分片，裁剪版 | **采纳，阶段 B** |
| SKIP LOCKED 队列 | PostgreSQL 领取机制 | **采纳，阶段 C** |
| Heartbeat + Lease | 定期续约 | **采纳，阶段 B** |
| 分片级重试 | 只重试失败 shard | **采纳，阶段 B** |
| 前端进度展示 | 分片计数展示 | **采纳，阶段 B** |
| 多 Worker 并行 | 多个独立扫描进程 | **延后到阶段 C** |
| object_inventory 表 | MinIO 通用对象索引 | **不引入，已有 EpisodeObject** |
| scan_prefix_states | HOT/WARM/COLD 调度 | **不引入，当前规模不需要** |
| 历史权重/负载均衡 | estimated_weight | **不引入，当前所有 shard 大小相近** |
| 超大 Batch 二次拆分 | Episode 级子分片 | **不引入，当前无单 Batch > 10K episodes** |
| scan_generation 安全删除 | 代次标记 | **延后，当前 is_active 已满足** |
| Reconcile 独立层级 | 低频全量校准 | **延后** |
| 取消流程 | cancelling → terminate → kill | **采纳，阶段 A 子进程模型自带** |
| 优先级分级 | 人工优先/新数据优先 | **延后，当前无抢资源场景** |
| 10 步实施 | 逐步推进 | **压缩为 3 阶段** |

---

## 六、最终判断

**GPT 方案在架构思想和主要方向上均为正确，适合作为长期演进目标。但需要分阶段裁剪落地，而不是一次性实施全部。**

优先级排序：

```
阶段 A（治本）  >  阶段 B（分片化）  >  阶段 C（并行化）
解决卡死/稳定性    解决效率/可观测性    解决规模扩展

object_inventory / scan_prefix_states / 冷热调度 / 超大拆分 → 暂不做
```

如果只做一件事：**给 `MinioService.list_objects` 加超时参数，并把扫描器从线程改为子进程。** 这两项改动量小（~100-200 行），直接解决当前最痛的问题。

如果要开始实施，建议从阶段 A 做起，一个 commit 一个能力，验证稳定后再进入下一阶段。
