# Robot QC 部署提示词

将以下内容粘贴给 AI 助手（Claude Code），即可在新机器上完成一键部署。

---

## 部署提示词

```
你需要在当前机器上部署 Robot QC 数据质检平台。请严格按照以下步骤操作，每步完成后向我确认。

## 前置条件检查

1. 确认 Docker 和 Docker Compose 已安装：
   docker --version && docker compose version

2. 确认当前目录是 git 仓库根目录（software/）：
   ls deploy/docker-compose.yml && echo "OK"

## 第一步：准备密钥

1. 检查 deploy/.env 是否存在：
   cat deploy/.env 2>/dev/null || echo ".env 不存在，需要创建"

2. 如果 .env 不存在，生成密钥并创建：
   SECRET_KEY=$(openssl rand -hex 32)
   POSTGRES_PASSWORD=$(openssl rand -hex 16)
   然后创建 deploy/.env 文件，内容如下（替换 MINIO 信息为真实值）：
   ```
   APP_ENV=production
   SECRET_KEY=<上面生成的SECRET_KEY>
   POSTGRES_PASSWORD=<上面生成的POSTGRES_PASSWORD>
   MINIO_ENDPOINT=<公司内网 MinIO 地址:端口>
   MINIO_ACCESS_KEY=<MinIO Access Key>
   MINIO_SECRET_KEY=<MinIO Secret Key>
   MINIO_DEFAULT_BUCKET=yaocao
   FRONTEND_ORIGIN=http://localhost:8080
   SESSION_COOKIE_SECURE=false
   ```
   设置权限: chmod 600 deploy/.env

## 第二步：构建前端

npm run build --prefix frontend

## 第三步：启动数据库

docker compose -f deploy/docker-compose.yml up --build -d db

等待数据库健康检查通过（通常 10-30 秒）。

## 第四步：初始化数据库和管理员

1. 先确保数据库 schema 已创建：
   docker compose -f deploy/docker-compose.yml run --rm -e APP_ENV=development backend alembic upgrade head

2. 创建管理员账号（修改密码为你自己的）：
   docker compose -f deploy/docker-compose.yml run --rm \
     -e APP_ENV=development \
     backend python -m app.services.bootstrap \
     --admin-username admin \
     --admin-password '你的密码' \
     --admin-name '系统管理员' \
     --admin-role admin

## 第五步：启动全部服务

docker compose -f deploy/docker-compose.yml up --build -d backend frontend

## 第六步：验证部署

1. 健康检查：
   curl http://127.0.0.1:8080/api/health

2. 浏览器打开 http://127.0.0.1:8080 使用管理员账号登录

3. 确认以下页面可访问：
   - 工作台: /dashboard
   - 数据总库: /database
   - 任务类型管理: /task-types
   - 训练数据集管理: /dataset-management
   - 设置: /settings（左侧菜单底部齿轮图标）

4. 进入设置页 → 通用 tab，检查"批次驳回阈值"是否为 0.10

## 注意事项

- 如果部署到其他机器，把 http://127.0.0.1:8080 替换为那台机器的 IP
- 如果已有 PostgreSQL 数据卷且想改密码，先在容器内 ALTER ROLE 再重启
- 前端页面通过 Vue Router 加载，刷新非根路径页面时 nginx 会返回 index.html
- MinIO 凭据不对会导致扫描和视频播放失败，但登录和页面浏览不受影响
- 数据库 migration 支持增量升级，重复执行 alembic upgrade head 是安全的
```

---

## 快速恢复 / 重新部署

```
# 停止所有服务（保留数据库数据卷）
docker compose -f deploy/docker-compose.yml down

# 重新构建并启动
docker compose -f deploy/docker-compose.yml up --build -d

# 如果数据库 schema 有更新
docker compose -f deploy/docker-compose.yml exec backend alembic upgrade head
```

## 完全重置

```
# 停止并删除数据库数据卷
docker compose -f deploy/docker-compose.yml down -v

# 然后从第三步重新开始
```
