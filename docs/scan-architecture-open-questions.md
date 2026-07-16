# 扫描入库架构升级——待确认问题

> 随附文档：
> - `scan-pipeline-optimization-brief.md`（问题背景，已发）
> - `scan-architecture-final-plan.md`（实施方案，已发）
>
> 以下问题是在最终方案中尚未完全确定的关键决策点，请逐个给出明确判断和理由。

---

## Q1：`object_inventory` 到底需不需要建？

**GPT 原始方案**坚持要新建一张 `object_inventory` 表，作为 MinIO 所有对象的平铺元数据镜像（object_key / etag / size / last_modified 等），扫描器只写到这一层，业务解析器再据此生成 Episode。

**Codex 的替代方案**是不新建表，直接复用现有的 `episode_objects` 表（已含 object_key / etag / size_bytes / content_hash / last_modified / last_seen_scan_id）。变化检测时对比这四元组判断对象是否变更。

两个方案在百万对象规模下都能工作。`object_inventory` 的好处是解耦"对象存在性"和"对象业务含义"，坏处是多一层需要维护一致性的表。

**请回答**：
1. 在大规模场景下，独立的 `object_inventory` 是否比复用 `episode_objects` 有实质优势？
2. 如果有，优势具体体现在哪些查询/操作上？
3. 如果建，`object_inventory` 和 `episode_objects` 的同步策略怎么设计？谁写谁？

---

## Q2：`scan_prefix_states` 的冷热调度应做到什么程度？

**GPT 原始方案**设计了 HOT / WARM / COLD / ARCHIVED 四级调度，每级有独立扫描频率和升降级规则。

**Codex 的简化方案**把四级压缩为一个布尔值 `skip_until_next_change` + 整数 `consecutive_unchanged`。规则：连续 3 次无变化 → skip=TRUE；检测到变化 → skip=FALSE。增量扫描跳过 skip=TRUE 的 prefix，全量扫描不跳过。

简化方案的本质是用二分法替代多级分级，好处是实现简单，坏处是无法对不同活跃度的 prefix 做差异化扫描频率。

**请回答**：
1. 在大规模场景下（500+ 批次），二分法（扫/不扫）是否足够？还是多级频率（每 30 分钟 / 每天 / 每周 / 每月）有真实的业务需求？
2. COLD/ARCHIVED 级别的独立调度是否为后续数据归档/生命周期管理所必需？
3. 能否接受先做二分法，日后需要时再加多级？接口设计上如何不给自己留坑？

---

## Q3：现有 `scan_jobs` 表怎么处理？

当前系统中 `scan_jobs` 表主键是 SHA1 字符串（`scan_{sha1[:16]}`），GPT 方案的新 `scan_jobs` 用 BIGSERIAL。两套 schema 差异较大。

Codex 建议：Alembic 重命名旧表为 `scan_jobs_legacy`，数据迁移后删除。

**请回答**：
1. 这个迁移策略是否合理？有没有更平滑的方式？
2. 旧 `scan_jobs` 的历史数据需要保留吗？前端目前没有展示扫描历史的页面。
3. 新 `scan_jobs` 的主键方案（BIGSERIAL vs UUID vs 自定义字符串）长期哪个更好？

---

## Q4：Worker 是独立进程还是 FastAPI 子进程？

**GPT 方案**要求扫描 Worker 是独立进程，不由 FastAPI 启动。

**Codex 的方案**建议 Worker 主进程由 `start.sh` 或 supervisord 启动，与 FastAPI 平级运行。子进程由 Worker 主进程 fork。

**请回答**：
1. 独立进程 vs FastAPI 内嵌子进程，在容器化部署（Docker Compose）场景下哪个更合适？
2. 如果独立进程，启动/停止/监控的具体方案推荐什么（supervisord / systemd / Docker 多容器 / 其他）？
3. Worker 进程如果崩溃，自动重启机制怎么设计？

---

## Q5：增量扫描的策略是否靠谱？

GPT 方案和 Codex 方案都依赖同一个核心假设：**在 MinIO 服务器不可控、无法配置 Bucket Notification 的前提下，通过对每个 prefix 做 `list_objects` + 对象指纹对比（etag/size/last_modified）来实现增量检测。**

**请回答**：
1. 这个假设在大规模下是否成立？`list_objects` 单个 prefix 的开销会随该 prefix 内对象数增长，是否有隐蔽的性能陷阱？
2. 是否存在"某个 prefix 内新增/修改了对象，但通过纯 etag/size/last_modified 对比无法检测到"的场景？
3. 是否有已知的开源工具或 S3 标准特性（如 S3 Inventory / ListObjectsV2 with start-after）可以进一步优化这个方案？

---

## Q6：实施顺序是否有更好的编排？

Codex 的 8 步实施顺序是自底向上的（表 → 基础设施 → 扫描逻辑 → 业务解析 → 前端 → 增量 → 并行）。

**请回答**：
1. 这个顺序是否合理？有没有某一步应该提前或延后？
2. 每步完成后能否独立验证和部署？灰度策略怎么设计？
3. 整个改造预计的总工时/代码量大概是多少？有没有可以进一步合并的步骤？

---

## Q7：并发 Worker 数量

Codex 建议初始 2 个 Worker，GPT 建议初始 1 Discovery + 3 Scan Worker。

**请回答**：
1. 两个数字哪个更合理？判断依据是什么？
2. Worker 数量动态调整的触发条件（pending shard 数 / MinIO P95 延迟 / 超时率）哪些是最有效的信号？
3. 是否需要一个最小 Worker 数的硬性保证（即至少 1 个 Worker 始终运行）？

---

## Q8：是否需要 `batch_asset_recompute_jobs` 去重机制

当前方案中，每个 shard 完成后会 enqueue 对应 Batch 的重算 job。但一个 Batch 可能被多个 Episode shard 覆盖（未来超大 Batch 拆分场景），或者同一 Batch 在短时间内被多次触发。

**请回答**：
1. 是否需要在 shard 完成回调中做去重（同一 batch 一个扫描周期内只产生一个 job）？
2. 当前 `batch_asset_recompute_jobs` 的 `on_conflict_do_update`（upsert）是否已经自动解决了这个问题？
3. 如果多个 shard 并发完成时同时 enqueue 同一 Batch，PostgreSQL 的锁机制能否正确处理？
