# 项目级日志系统

## 设计决策

### 2026-07-01 — 三层日志架构：数据库审计 + 文件日志 + Docker 轮转

- Decision: 日志分为三层。Tier 1 数据库 audit_events 结构化存储业务操作审计（可查可导出），Tier 2 文件日志纯文本按天轮转（开发者 tail -f grep 排查），Tier 3 Docker json-file 限制大小轮转（运维 docker logs）
- Context: 现有审计系统仅有 16 处手动创建点，缺中间件自动捕获，无 Python logging 配置，无 Docker 日志轮转。用户需要覆盖远程网页操作和本机部署操作两类场景的专业项目级日志
- Reason: 数据库做结构化查询和前端展示，文件日志做运维兜底（数据库挂了还能看文件），Docker 层做容器级隔离。不做 ELK 因为单容器项目过度设计
- Impacted nodes: D
- Status: design

## 三层架构

| 层 | 存储位置 | 格式 | 用途 | 轮转策略 |
|---|---|---|---|---|
| Tier 1 数据库审计 | PostgreSQL audit_events 表 | 结构化字段 | 前端可查可导出，合规审计 | 无限制（定期清理策略待定） |
| Tier 2 应用文件日志 | 容器内 /app/logs/app.log | 纯文本行 | 开发者 tail -f grep 排查 | TimedRotatingFileHandler 按天，保留30天 |
| Tier 3 Docker 容器日志 | Docker json-file | JSON行（Docker默认） | 运维 docker logs | max-size=50m, max-file=5 |

## Tier 1 — 数据库审计日志

### 模型增强

在现有 audit_events 表基础上新增字段：

| 字段 | 类型 | 说明 |
|---|---|---|
| event_type | String(32) | api_request / business_action / system_action / auth_event |
| severity | String(16) | info / warning / error |
| operator_id | String(64) | FK 指向 users 表 |
| ip_address | String(45) | 请求来源 IP |
| user_agent | String(256) | 浏览器 User-Agent |
| duration_ms | Integer | 请求耗时（仅 api_request 类型） |

### 中间件自动捕获

新建 app/middleware/audit_middleware.py，注册为 FastAPI 中间件：
- 自动捕获所有 API 请求：method, path, status_code, duration_ms, user, ip, ua
- event_type = api_request
- 排除 /api/health 健康检查（避免噪音）
- 异步写入 AuditEvent，不阻塞请求响应

### 补齐缺失审计点

| 模块 | 操作 | event_type |
|---|---|---|
| auth routes | login 成功/失败, logout | auth_event |
| ReviewerTaskManager | revoke, reassign, release | business_action |
| batch_adjudication | 批次判定结果 | business_action |
| dataset_service | 导出操作 | business_action |

## Tier 2 — 应用文件日志

### 配置

- 位置：容器内 /app/logs/app.log
- 格式：2026-07-01 00:00:01 [INFO] app.services.scanner: 扫描完成 job_id=xxx episodes=4097
- Handler：logging.handlers.TimedRotatingFileHandler，按天轮转，保留 30 天
- 级别：INFO（全量），生产环境可通过环境变量调整为 WARNING
- 新建 app/core/logging_config.py，在 FastAPI startup 事件中调用 setup_logging()

### 替换 print() 为 logger

| 文件 | 现有方式 | 改为 |
|---|---|---|
| scan_scheduler.py | print() | logger.info() |
| scan_queue.py | print() | logger.info() |

## Tier 3 — Docker 容器日志

### docker-compose.yml 配置

```yaml
services:
  backend:
    logging:
      driver: json-file
      options:
        max-size: 50m
        max-file: 5
```

- json-file 驱动是 Docker 默认驱动，docker logs 命令兼容
- 单文件上限 50MB，最多保留 5 个历史文件（共 250MB）

## 前端日志查看器增强

qc-history.vue 改进项：

1. 筛选面板：event_type 下拉、severity 下拉、日期范围选择器（el-date-picker）、操作人搜索
2. 表格新增列：event_type、severity、ip_address
3. 导出按钮：当前筛选结果导出 JSON/CSV
4. 详情弹窗：点击行查看完整 detail 和 user_agent

## 实施顺序

1. Tier 1 核心：增强 AuditEvent 模型 (migration) + 中间件自动捕获 → 立即获得全量 API 请求日志
2. Tier 1 补齐：补缺失审计点 (auth/services)
3. Tier 2：Python logging 配置 + 替换 print
4. Tier 3：Docker 日志轮转配置
5. 前端增强：日志查看器筛选导出

## 不做

- ELK/Loki/Grafana 日志聚合栈（单容器项目过度设计）
- 实时日志流 WebSocket 推送
- 日志告警与通知
- 机器学习异常检测
