# MinIO 扫描入库管线优化——背景与技术咨询文档

> 用途：提供给 GPT 用于分析扫描入库管线当前问题与改进方案
> 版本：2026-07-16

---

## 一、背景

Robot QC 平台通过**MinIO 扫描入库管线**将远程 MinIO 服务器（192.168.21.95:9190）上的遥操作数据规范化入库。扫描器是全系统的数据入口：所有原始数据必须先通过扫描器发现、分类并写入数据库，后续质检、统计和导出功能才能正常工作。

当前扫描器在生产环境中运行不稳定：部分扫描任务耗时约 15 分钟成功完成，但多次出现**扫描任务卡死数天至数十天**的现象。用户观察后台始终显示 "scanning" 或 "classifying" 状态的僵尸任务。

---

## 二、当前架构

### 2.1 触发方式

- **手动触发**：管理员在浏览器数据总库页点击「扫描全部」，调用 `POST /api/database/scan`
- **定时触发**：APScheduler 后台调度器每日 00:00（CST）自动触发一次全量扫描

### 2.2 执行流程

```
触发请求
  ↓
POST /api/database/scan
  ├── 清理超过 30 分钟的僵尸 job（仅更新 DB 状态）
  ├── 检查是否存在正在运行的 job → 有则返回现有 job 防止重复
  └── 创建 ScanJob 记录（status='scanning'）
      ↓
  enqueue_scan_job()
      └── threading.Thread(target=process_scan_job)  # Python 线程
          ↓
      process_scan_job()
          ├── 创建独立 DB session
          ├── resume_minio_scan() → _execute_minio_scan()
          │    ↓
          │  _execute_minio_scan()
          │    ┌─────────────────────────────────────────────┐
          │    │ 1. list(service.list_objects(bucket,        │  ← 关键瓶颈
          │    │              recursive=True))                │
          │    │    全桶递归列对象，无超时、无分页限制       │
          │    ├─────────────────────────────────────────────┤
          │    │ 2. 内存构建 prefix_tree                      │
          │    │    按 prefix 归类 raw/processed 层级关系     │
          │    ├─────────────────────────────────────────────┤
          │    │ 3. 推断 list 候选                            │
          │    │    确定哪些 prefix 构成独立批次              │
          │    ├─────────────────────────────────────────────┤
          │    │ 4. 逐 list 处理                             │
          │    │    - upsert ListRecord                       │
          │    │    - upsert Batch                            │
          │    │    - 逐 episode 处理                        │
          │    │      · upsert EpisodeInventory               │
          │    │      · upsert EpisodeObject                  │
          │    │      · 读取 manifest.json                    │
          │    │      · upsert Episode                        │
          │    ├─────────────────────────────────────────────┤
          │    │ 5. 标记不活跃的 list 为 is_active=false      │
          │    │ 6. ScanJob → done                            │
          │    └─────────────────────────────────────────────┘
          ├── 完成 → 记录审计日志
          └── 异常 → ScanJob → failed
```

### 2.3 关键代码路径

| 组件 | 文件 | 职责 |
|------|------|------|
| `_execute_minio_scan()` | `backend/app/services/scanner.py` | 扫描主逻辑，~500 行 |
| `MinioService.list_objects()` | `backend/app/services/minio_client.py` | 对 `minio-py.list_objects` 的薄封装 |
| `scan_queue.py` | `backend/app/services/scan_queue.py` | 线程池封装，daemon 线程执行 |
| `scan_scheduler.py` | `backend/app/services/scan_scheduler.py` | APScheduler 调度器 |
| `GET /api/database/scan` | `backend/app/api/routes/qc.py` | 触发入口 |

### 2.4 数据模型

```sql
-- ScanJob：每个扫描任务一条记录
ScanJob {
    id           : String(64) PK,  -- scan_{sha1[:16]}
    bucket       : String(128),    -- 默认为 yaocao
    scope        : String(32),     -- full
    status       : String(32),     -- scanning / classifying / done / failed
    total_prefixes : Integer,
    confirmed_lists : Integer,
    total_episodes  : Integer,
    new_episodes    : Integer,
    triggered_by    : String(64),
    started_at      : DateTime,
    finished_at     : DateTime?,
}
```

### 2.5 数据规模

| 指标 | 数值 |
|------|------|
| MinIO 桶名 | `yaocao` |
| 已知批次 | 52 |
| 已知任务类型 | 20 |
| Episode 总量 | 5,217 |
| 含有效 manifest 的 Episode | 4,525 |
| 纯 raw（无 processed）Episode | 692 |
| 扫描成功耗时 | ~15 分钟 |
| 卡死最长记录 | >10 天 |

---

## 三、当前问题

### 3.1 根因：`list_objects()` 全桶递归无防护

```python
# minio_client.py
class MinioService:
    def list_objects(self, bucket, prefix='', *, recursive=True):
        return self._client.list_objects(bucket, prefix=prefix, recursive=recursive)

# scanner.py - 调用点
list(service.list_objects(normalized_bucket, recursive=True))
```

关键问题：

1. **无超时控制**：`minio-py` 的 `list_objects` 返回的是生成器，底层使用 HTTP 请求。如果 MinIO 服务端响应慢或网络抖动，调用可能无限挂起。
2. **全桶递归**：`recursive=True` 且 `prefix=''` 时会枚举桶中所有对象，对对象数量大的桶尤其耗时。
3. **无分页限制**：不设置 `max_keys`，MinIO 服务端可能返回大量结果导致内存压力。
4. **同步阻塞**：`list(...)` 将生成器转换为列表的瞬间阻塞线程，若 MinIO 服务端流式响应缓慢则整个线程挂死。

### 3.2 线程级灾难恢复缺失

扫描任务运行在 Python `threading.Thread`（daemon=True）中：

```python
# scan_queue.py
worker = threading.Thread(target=process_scan_job, args=(...), daemon=True)
```

- 线程挂死后没有恢复机制：没有线程监控、没有看门狗、没有超时终止
- `ScanJob` 的 `status` 留在 `scanning`/`classifying`，永不变为 `failed`
- `_cleanup_stale_jobs()` 只在**下一次扫描触发前**清理僵尸 job 的 DB 状态，但无法终止实际挂死的线程。且清理条件是 >30 分钟，而实际扫描可能正常耗时近 15 分钟，安全边际不够。

### 3.3 全量扫描模型不符合增量需求

当前设计总是**全桶扫描**，无法增量检测新增/修改/删除的对象。随着数据增长：
- 扫描时间线性增长
- 重复处理已入库且未变化的数据
- 无法快速发现新数据

### 3.4 无部分扫描/断点续扫能力

- 只支持 `scope='full'`，没有按 prefix 范围扫描
- 扫描中途失败后从头重来，没有 checkpoint

### 3.5 无进度反馈

- `ScanJob.error_detail` 做进度字段用，但只记录粗略计数
- 前端无法感知扫描进度，用户只能等待

### 3.6 容器内外部依赖

```
Backend (容器内)
  └→ MinIO 服务器 (192.168.21.95:9190, 外部物理服务器)
```

网络环境不稳定时（隔墙、跨网段），`list_objects` 的 TCP 连接可能长时间无响应。

---

## 四、我们希望 GPT 分析的方向

### 4.1 增量扫描方案

- 如何避免全桶递归？是否可以利用 MinIO 的事件通知（bucket notification / S3 Event）？
- 如果不用事件通知，能否基于对象 `last_modified` 做增量检测？
- 能否以 prefix（批次级）为单位做局部扫描，而不是全桶？

### 4.2 扫描超时与重试策略

- `list_objects` 的最佳超时配置？`minio-py` 是否支持 `timeout` 参数？
- 长扫描（15min+）的分片策略：能否按 prefix 分批次扫描？
- 失败重试策略：指数退避 / 断路器？

### 4.3 扫描任务可靠性

- 如何可靠终止挂死的扫描任务？
- 是否应改用子进程替代线程（可控超时 kill）？
- 是否需要异步 worker 架构（Celery / ARQ / RQ 等）？

### 4.4 扫描性能优化

- `list_objects` 分页控制：`max_keys` 应该设多大？
- 并行扫描：能否同时对不同 prefix 并发扫描？
- 内存使用优化：当前将全量对象列表加载到内存，能否流式处理？

### 4.5 扫描架构展望

- 短期：在现有线程模型上如何以最小改动解决卡死问题？
- 中期：是否迁移到独立的后台 worker（独立进程或容器）？
- 长期：是否接入 MinIO Bucket Notification（SQS/Webhook）实现实时增量检测？

---

## 五、约束条件

1. **MinIO 服务器不可控**：`192.168.21.95:9190` 是远程服务器，无法安装插件或修改配置，只能通过 S3 兼容 API 操作。
2. **扫描器必须幂等**：重新扫描不应产生重复数据或数据损坏。
3. **当前表结构已稳定**：`batch_asset_rollups` + `task_asset_rollups` 已上线，扫描结果必须正确驱动资产投影重算。
4. **优先最小改动**：在确保稳定性的前提下尽量不改动现有架构，避免大规模重构。
5. **无需额外基础设施**：当前无 Kafka/RabbitMQ/Redis，持 Postgresql 和 Python 标准库。
6. **生产环境正在运行**：改动必须可灰度、可回滚。

---

## 六、我们关心的具体问题

1. `minio-py` 的 `list_objects` 能否设置网络超时（connect/read timeout）？
2. 当前线程模型卡死后如何检测和自动恢复？
3. 如果不使用 MinIO 事件通知，纯 S3 API 能否实现增量扫描？
4. Python `threading.Thread` 挂死后能否在同一进程内可靠终止？
5. 长期来看是否有推荐的开源扫描同步工具适用此场景？
6. 对于 50+ 批次、5000+ episode 规模下，合理的全量扫描时间预期是多少？
