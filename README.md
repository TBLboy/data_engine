# Robot QC V1

灵机启物机器人数采质检平台 — 训练数据消费与数据资产供给系统。

## 功能范围

- MinIO 数据湖全量扫描入库
- 批次管理与抽检任务派发
- 人工质检审核（认领/锁定/提交）
- L3 v2 四层自动指标评估（训练质量评分）
- 批次驳回判定（失败率 > 阈值 → 整批不可用于训练）
- 训练数据集管理与合格数据清单导出（CSV/JSON）
- QC 历史审计与报表
- 多角色权限（admin / qc_manager / reviewer / viewer）
- Docker + PostgreSQL 生产部署

## 目录结构

```
backend/        FastAPI + SQLAlchemy + Alembic
frontend/       Vue 3 + Element Plus + Chart.js
deploy/         Docker Compose 生产栈 + 部署说明
.project-log/   项目进度与业务逻辑文档
```

## 常用命令

在 `software/` 目录下执行。

### 服务管理

```bash
# 启动所有服务
docker compose -f deploy/docker-compose.yml up -d

# 停止所有服务
docker compose -f deploy/docker-compose.yml down

# 停止并删除数据库（彻底重置）
docker compose -f deploy/docker-compose.yml down -v

# 查看运行状态
docker compose -f deploy/docker-compose.yml ps

# 查看日志
docker compose -f deploy/docker-compose.yml logs -f --tail=50

# 重新构建并重启单个服务（如改完代码后）
docker compose -f deploy/docker-compose.yml up -d --build backend
docker compose -f deploy/docker-compose.yml up -d --build frontend
```

### 数据库

```bash
# 运行数据库迁移（增量升级，安全可重复执行）
docker compose -f deploy/docker-compose.yml exec backend alembic upgrade head

# 查看当前迁移版本
docker compose -f deploy/docker-compose.yml exec backend alembic current
```

### 开发调试

```bash
# 后端编译检查
cd backend && ./.conda-env/bin/python -m compileall -q app/

# 前端构建
cd frontend && npm run build

# 前端类型检查
cd frontend && npx vue-tsc --noEmit
```

### 快速部署（新机器）

```bash
# 1. 准备密钥
SECRET_KEY=$(openssl rand -hex 32)
POSTGRES_PASSWORD=$(openssl rand -hex 16)
# 编辑 deploy/.env 填入上述值和 MinIO 凭据

# 2. 构建前端
npm run build --prefix frontend

# 3. 启动数据库
docker compose -f deploy/docker-compose.yml up --build -d db

# 4. 初始化 schema + 创建管理员
docker compose -f deploy/docker-compose.yml run --rm -e APP_ENV=development backend alembic upgrade head
docker compose -f deploy/docker-compose.yml run --rm -e APP_ENV=development backend python -m app.services.bootstrap --admin-username admin --admin-password '你的密码' --admin-name '系统管理员' --admin-role admin

# 5. 启动全部
docker compose -f deploy/docker-compose.yml up --build -d backend frontend

# 6. 浏览器打开 http://<机器IP>:8080
```

详细部署说明见 `deploy/README.txt`。
