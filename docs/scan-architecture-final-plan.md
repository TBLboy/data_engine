# MinIO 扫描入库架构升级——最终实施方案

> 前提：按数据已大规模（500+ 批次、50,000+ Episode）设计，一步到位，不做过渡补丁。
> 日期：2026-07-16

---

## 一、最终决策：GPT 方案的 12 个模块，采纳 8 个，替代 2 个，废弃 2 个

在"以大规模为前提"的约束下重新逐项评估：

| # | GPT 提案模块 | 最终决策 | 理由 |
|---|-------------|----------|------|
| 1 | 子进程替代线程 | **采纳，必须** | 大规模下分片多、扫描时间长，挂一个 shard 卡整个扫描不可接受 |
| 2 | MinIO 超时参数 | **采纳，必须** | 基础可靠性，任何规模都需要 |
| 3 | Prefix 分片 (Batch=Shard) | **采纳，必须** | 分片是并行、重试、进度展示的前提 |
| 4 | 流式 + 批量写入 | **采纳，必须** | 防止百万对象撑爆内存 |
| 5 | scan_jobs + scan_shards + SKIP LOCKED | **采纳，必须** | 持久化队列是 Worker 动态领取的基础设施 |
| 6 | Heartbeat + Lease | **采纳，必须** | Worker 崩溃后 shard 能被其他 Worker 接管 |
| 7 | 分片级重试 | **采纳，必须** | 大规模下不能因一个 shard 失败重扫全桶 |
| 8 | 前端进度展示 | **采纳** | 操作可见性的基本要求 |
| 9 | `object_inventory` 对象索引表 | **替代方案** | 不新增表，扩展现有 `episode_objects` + `episode_inventory` 承担同角色，避免维护两套对象元数据 |
| 10 | `scan_prefix_states` 冷热调度 | **简化采纳** | 保留 prefix 状态表，但先不实现 HOT/WARM/COLD 四级调度。用 `last_successful_scan_at` + `change_detected` 布尔值决定是否跳过某 prefix，逻辑简单有效 |
| 11 | 超大 Batch 拆分 (Level 2) | **保留接口，暂不实现** | 分片模型预留 `parent_shard_id`，当单个 Batch > 10,000 Episode 时再触发 |
| 12 | Historical Reconcile (Level 3) | **废弃独立层级** | Reconcile 作为 scan_job 的一种 `scan_mode`，不用独立表或独立 Worker 类型 |

---

## 二、最终架构图（裁剪版）

```text
MinIO 对象湖 (192.168.21.95:9190)
        │
        ▼
┌──────────────────────────────┐
│  Prefix Discovery            │
│  非递归枚举 batch/ 根前缀     │
│  产出 scan_shards 列表       │
└──────────────┬───────────────┘
               │
               ▼
┌──────────────────────────────┐
│  PostgreSQL 持久化队列       │
│  scan_jobs + scan_shards     │
│  FOR UPDATE SKIP LOCKED      │
└──────────────┬───────────────┘
               │
     ┌─────────┼─────────┐
     ▼         ▼         ▼
┌─────────┐┌─────────┐┌─────────┐
│Worker 1 ││Worker 2 ││Worker N │  子进程，独立 session
│ lease   ││ lease   ││ lease   │  独立 MinIO client
│ heartbeat││ heartbeat││ heartbeat│
└────┬────┘└────┬────┘└────┬────┘
     │          │          │
     └──────────┼──────────┘
                ▼
┌──────────────────────────────┐
│  业务解析器 (现有逻辑复用)   │
│  EpisodeInventory            │
│  EpisodeObject (含 etag/size │
│    /last_modified 变更检测)   │
│  Episode / Batch 写回        │
└──────────────┬───────────────┘
               ▼
┌──────────────────────────────┐
│  资产投影联动 (现有)         │
│  enqueue batch_asset_recompute│
│  → enqueue task_asset_recompute│
└──────────────────────────────┘
```

---

## 三、数据库新增/变更

### 3.1 新增 `scan_jobs`（替代当前 `scan_jobs`，扩展版）

```sql
CREATE TABLE scan_jobs (
    id              BIGSERIAL PRIMARY KEY,
    bucket          VARCHAR(128) NOT NULL,
    scan_mode       VARCHAR(32) NOT NULL DEFAULT 'full',
        -- 'full' | 'incremental' | 'prefix_list' | 'manual_prefix'
    status          VARCHAR(32) NOT NULL DEFAULT 'pending',
        -- 'pending' | 'running' | 'cancelling' | 'cancelled'
        -- | 'succeeded' | 'partially_failed' | 'failed'
    priority        INTEGER NOT NULL DEFAULT 50,

    total_shards    INTEGER NOT NULL DEFAULT 0,
    succeeded_shards INTEGER NOT NULL DEFAULT 0,
    failed_shards   INTEGER NOT NULL DEFAULT 0,
    running_shards  INTEGER NOT NULL DEFAULT 0,

    triggered_by    VARCHAR(64),
    trigger_source  VARCHAR(32) NOT NULL DEFAULT 'manual',
        -- 'manual' | 'cron' | 'api'

    heartbeat_at    TIMESTAMPTZ,
    started_at      TIMESTAMPTZ,
    finished_at     TIMESTAMPTZ,
    cancel_requested_at TIMESTAMPTZ,

    error_summary   TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_scan_jobs_status ON scan_jobs(status);
CREATE INDEX idx_scan_jobs_bucket ON scan_jobs(bucket);
```

**与当前 `scan_jobs` 的区别：**
- 主键从 SHA1 字符串改为 BIGSERIAL（Alembic 管理更方便）
- 新增 `scan_mode` / `priority` / `trigger_source`
- 新增总/成/败/运行分片计数
- 新增 `heartbeat_at` / `cancel_requested_at`
- 删除当前混杂在 error_detail 里的进度字符串

### 3.2 新增 `scan_shards`

```sql
CREATE TABLE scan_shards (
    id              BIGSERIAL PRIMARY KEY,
    scan_job_id     BIGINT NOT NULL REFERENCES scan_jobs(id) ON DELETE CASCADE,
    bucket          VARCHAR(128) NOT NULL,
    prefix          VARCHAR(1024) NOT NULL,
    shard_type      VARCHAR(32) NOT NULL DEFAULT 'prefix_scan',
        -- 'discovery' | 'prefix_scan' | 'episode_scan'

    parent_shard_id BIGINT REFERENCES scan_shards(id),
        -- 预留：超大 Batch 拆分时指向父 shard

    status          VARCHAR(32) NOT NULL DEFAULT 'pending',
        -- 'pending' | 'running' | 'succeeded' | 'failed'
        -- | 'retry_wait' | 'cancelled'

    priority        INTEGER NOT NULL DEFAULT 50,
    attempt_count   INTEGER NOT NULL DEFAULT 0,
    max_attempts    INTEGER NOT NULL DEFAULT 3,

    lease_owner     VARCHAR(64),
    lease_expires_at TIMESTAMPTZ,
    heartbeat_at    TIMESTAMPTZ,

    objects_seen    INTEGER NOT NULL DEFAULT 0,
    objects_changed  INTEGER NOT NULL DEFAULT 0,
    episodes_seen   INTEGER NOT NULL DEFAULT 0,
    episodes_changed INTEGER NOT NULL DEFAULT 0,

    next_retry_at   TIMESTAMPTZ,
    started_at      TIMESTAMPTZ,
    finished_at     TIMESTAMPTZ,

    error_detail    TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    UNIQUE(scan_job_id, prefix)
);

CREATE INDEX idx_scan_shards_status ON scan_shards(status, next_retry_at)
    WHERE status IN ('pending', 'retry_wait');
CREATE INDEX idx_scan_shards_job ON scan_shards(scan_job_id);
```

**说明：**
- 不引入 `estimated_weight`、`historical_object_count`、`historical_duration_ms` 等字段。Worker 排序领取时按 `priority DESC, objects_seen DESC` 即可实现"大分片优先"，不需要额外权重表。
- `parent_shard_id` 保留为 NULL，为未来超大 Batch 二次拆分留接口。

### 3.3 扩展现有表（不变结构，只扩展字段语义）

**`episode_objects`** — 已承担对象索引角色，无需新增 `object_inventory` 表。扫描时对比 `(object_key, etag, size_bytes, last_modified)` 判断对象是否变化。字段 `last_seen_scan_id` 继续用来跟踪对象是否在最近一次扫描中被发现。

**`episode_inventory`** — 新增 `last_seen_scan_job_id` 字段（或复用现有 `last_seen_scan_id`）用于标记对象是否在本次扫描中出现。

### 3.4 新增 `scan_prefix_states`（裁剪版）

```sql
CREATE TABLE scan_prefix_states (
    id              BIGSERIAL PRIMARY KEY,
    bucket          VARCHAR(128) NOT NULL,
    prefix          VARCHAR(1024) NOT NULL,

    last_successful_scan_at  TIMESTAMPTZ,
    last_change_detected_at  TIMESTAMPTZ,
    consecutive_unchanged    INTEGER NOT NULL DEFAULT 0,

    -- 以下为可选：简单的跳过策略用的布尔值
    skip_until_next_change   BOOLEAN NOT NULL DEFAULT FALSE,

    created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    UNIQUE(bucket, prefix)
);
```

**为什么不用 HOT/WARM/COLD/ARCHIVED 四级分级？**

因为四级分级需要定义各级的扫描频率、降级阈值、升级条件等一套规则引擎。当前用一个简单的布尔值 `skip_until_next_change` 配合 `consecutive_unchanged` 计数同样能实现"不频繁扫描无变化 prefix"的效果，但实现复杂度是后者的 1/4。

规则：
- 连续 3 次扫描无变化 → `skip_until_next_change = TRUE`（但全量 reconcile 时仍会扫）
- 任何时候检测到变化 → `skip_until_next_change = FALSE`，`consecutive_unchanged = 0`
- 增量扫描时跳过 `skip_until_next_change = TRUE` 的 prefix
- 全量扫描时不跳过任何 prefix（reconcile 职责）

---

## 四、增量扫描策略（核心新能力）

当前只能全量扫描。新增增量模式：

### 4.1 增量扫描触发

```http
POST /api/database/scan
{
  "mode": "incremental"    // 新增
}
```

默认模式：`incremental`（日常 cron 使用）。
手动触发可选 `full`（前端按钮）。

### 4.2 增量扫描逻辑

```
1. Prefix Discovery（always）
   - 非递归枚举顶层 prefix
   - 识别新出现的 prefix，立即创建高优先级 shard
   - 与 scan_prefix_states 对比，检测消失的 prefix

2. 对每个已知 prefix：
   - 取 scan_prefix_states.skip_until_next_change
   - 若 TRUE 且 mode=incremental → 跳过
   - 否则创建 shard 入队

3. Worker 领取 shard：
   - 流式 list_objects(prefix=shard.prefix, recursive=True)
   - 每个对象：查询 episode_objects 对比 (key, etag, size, last_modified)
   - 未变化：只更新 last_seen_scan_id
   - 已变化或新增：更新 episode_objects + 标记 changed

4. Shard 完成后：
   - 若 objects_changed > 0：更新 scan_prefix_states (last_change_detected_at, skip=FALSE)
   - 若 objects_changed == 0：consecutive_unchanged += 1
   - 触发受影响 Batch 的 batch_asset_recompute_jobs

5. 全部 shard 完成后：
   - 标记未在本次扫描中出现的对象为 inactive
   - 标记未出现的 prefix 为 inactive
```

### 4.3 变化检测

不再依靠 MinIO 事件通知（用户明确说 MinIO 服务器不可控），而是用对象指纹对比：

```python
def object_changed(existing: EpisodeObject, incoming: dict) -> bool:
    return (
        existing.content_hash != incoming['etag']
        or existing.size_bytes != incoming['size_bytes']
        or existing.last_modified != incoming['last_modified']
    )
```

---

## 五、Worker 进程模型

### 5.1 主 Worker 进程

```
scan_worker_main.py  (独立进程，不由 FastAPI 启动)
  │
  ├── 从 scan_shards 领取 (SKIP LOCKED)
  ├── 对每个 shard 启动子进程
  ├── 监控子进程 wall-clock 时间
  ├── 超时 → terminate(5s) → kill(2s)
  ├── 更新 heartbeat 和 lease
  └── 处理子进程退出码和结果
```

### 5.2 子进程

```
scan_shard_worker.py  (短期子进程)
  │
  ├── 独立 MinioService 实例
  ├── 独立 SQLAlchemy Session
  ├── 流式扫描一个 prefix
  ├── 对比 + 批量写入
  └── 正常退出，返回统计
```

### 5.3 启动方式

当前扫描由 FastAPI 进程内 daemon 线程执行，新方案改为：

- **独立 Worker 进程**：由 `supervisord` 或在 `start.sh` 中启动，与 FastAPI 进程平级
- Worker 数量通过环境变量 `SCAN_WORKER_COUNT` 控制，默认 2
- Discovery 不在独立 Worker，而在**任何一个空闲 Worker 取不到 shard 时触发**，或者由 cron scheduler 在扫描开始前触发

简化方案：cron scheduler 仍然是触发入口，它创建一个 `scan_job` + discovery → 生成 shards → Worker 消费。这样不需要独立的 Discovery Worker，减少一个进程类型。

### 5.4 超时参数

```python
MINIO_CONNECT_TIMEOUT = 5       # 秒
MINIO_READ_TIMEOUT = 60         # 秒
MINIO_MAX_RETRIES = 3
SHARD_LEASE_SECONDS = 90        # Worker 必须每 90s 内续约
SHARD_HEARTBEAT_INTERVAL = 10   # 每 10s 续约一次
SHARD_TIMEOUT_SECONDS = 600     # 单个 shard 总超时 10 分钟
WORKER_GRACE_PERIOD = 5         # terminate 后等待 5s
WORKER_KILL_PERIOD = 2          # 宽限后再 kill
```

---

## 六、分片级重试

```
第 1 次失败 → 等待 30s → retry
第 2 次失败 → 等待 2min → retry
第 3 次失败 → 等待 10min → retry
第 4 次失败 → shard = failed, job = partially_failed
```

添加随机抖动 ±20%，max_attempts=3（可配置）。

---

## 七、实施顺序（重新编排）

### 第 1 步：数据库 + 模型

- Alembic migration: 重命名现有 `scan_jobs` → `scan_jobs_legacy`（数据迁移后删除）
- 新建 `scan_jobs`（v2）、`scan_shards`、`scan_prefix_states`
- 模型代码同步更新

### 第 2 步：MinioService 超时 + 子进程基础设施

- `MinioService.__init__` 增加 `timeout` 参数传给 `minio-py`
- 新增 `app/services/scan_worker_main.py`（主 Worker 进程入口）
- 新增 `app/services/scan_shard_worker.py`（子进程入口）
- 子进程管理、超时、terminate/kill、heartbeat、lease 全部在这一步落地

### 第 3 步：Prefix Discovery + 分片生成

- 用非递归 `list_objects(recursive=False)` 逐层发现 prefix
- 生成 `scan_shards` 行
- 区分新 prefix（高优先级）和已知 prefix（正常优先级）

### 第 4 步：流式扫描 + 变化检测

- 每个 shard 子进程流式遍历对象
- 对比 `episode_objects` 判断变化
- 批量写入
- 更新 `scan_prefix_states`

### 第 5 步：业务解析器 + 资产投影

- 复用现有 `_execute_minio_scan` 中的业务解析逻辑（ListRecord / Batch / EpisodeInventory / Episode / EpisodeObject 的 upsert）
- 每个 shard 完成 → 收集 affected_batch_ids → enqueue batch_asset_recompute_jobs
- 需注意：一个 Batch 被多个 Episode shard 覆盖时，等全部相关 shard 完成后再触发一次（通过 shard 完成后的回调去重）

### 第 6 步：前端

- 进度展示（总分片/成功/失败/运行中/等待）
- 支持取消扫描
- 支持重试失败分片
- 支持手动重扫某个 prefix

### 第 7 步：增量模式 + skip 策略

- 实现增量扫描逻辑（见第四章）
- `scan_prefix_states.skip_until_next_change` 机制
- cron 默认使用增量模式

### 第 8 步：多 Worker 并行

- 启动多个 Worker 主进程（默认 2）
- 监控并发效果
- 根据 pending shard 数量动态调整

---

## 八、与现有代码的兼容

| 现有组件 | 处理方式 |
|----------|----------|
| `scan_jobs` (旧表) | Alembic 重命名为 `scan_jobs_legacy`，数据迁移到新表后 drop |
| `scanner.py::_execute_minio_scan()` | 业务解析逻辑（List/Batch/Episode upsert）抽取为 `business_resolver.py`，扫描流程本身废弃 |
| `scanner.py::run_minio_scan()` | 改为创建 `scan_jobs` v2 + 生成 shards，不再直接执行扫描 |
| `scan_queue.py` | 废弃（不再用线程），由 `scan_worker_main.py` 替代 |
| `scan_scheduler.py` | 保留，触发逻辑改为创建 scan_job + discovery |
| `qc.py::scan_database` | 接口签名不变，内部改为新流程 |
| `minio_client.py` | 新增 `timeout` 参数 |
| `EpisodeObject` / `EpisodeInventory` | 不变，扫描时对比 (etag, size, last_modified) 做变化检测 |
| `batch_asset_rollups` / `task_asset_rollups` | 不变，shard 完成后入队重算 |

---

## 九、不做的和原因

| 不做的 | 原因 |
|--------|------|
| `object_inventory` 新表 | `episode_objects`（含 etag/size/last_modified）已具备同等能力。新增表意味着维护两套对象元数据一致性，ROI 为负 |
| HOT/WARM/COLD/ARCHIVED 四级调度 | `skip_until_next_change` 布尔值 + `consecutive_unchanged` 计数已满足"跳过无变化 prefix"的目标，四级调度的管理复杂度远超收益 |
| 超大 Batch 自动二次拆分 (Level 2) | 当前无单 Batch > 10K episodes，保留 `parent_shard_id` 接口，需要时再加 |
| Historical Reconcile 独立层级 | 作为 `scan_mode='full'` 的一个模式足够，不需要独立表、独立 Worker |
| weighted 负载均衡 | `priority DESC, objects_seen DESC` 排序已实现"大分片优先"，不需要权重计算引擎 |

---

## 十、最终架构一句话

> **Prefix 分片 + PostgreSQL 持久化队列 + 子进程 Worker 动态领取 + 流式对象指纹对比增量检测 + 现有业务解析器复用 + 分片级重试 + 前端可观测进度。不引入 object_inventory，不引入冷热四级调度。**
