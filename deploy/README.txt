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

---

## AI 质检助手模块

平台支持通过本地大模型（Ollama）对 L3 自动质检结果进行中文解读，
降低质检员判读门槛。

### 架构

```
┌─────────────────────────┐      ┌─────────────────────┐
│  Robot QC 服务器         │      │  AI 模型服务器        │
│                         │      │                     │
│  backend (Docker)       │ HTTP │  Ollama serve       │
│  └─ llm_client.py ──────┼─────▶│  └─ qwen2.5:7b     │
│     OLLAMA_BASE_URL=    │ LAN  │     :11434          │
│     http://192.168.x.x  │      │                     │
│                         │      │  RTX 4090 24GB      │
└─────────────────────────┘      └─────────────────────┘
```

模型服务器和平台服务器可部署在同一台或不同机器，仅需局域网互通。

### 安装 Ollama

```bash
# 1. 下载 Ollama（Linux）
curl -fsSL https://github.com/ollama/ollama/releases/latest/download/ollama-linux-amd64.tar.zst \
  -o /tmp/ollama.tar.zst
zstd -d /tmp/ollama.tar.zst -o /tmp/ollama.tar
mkdir -p ~/.local
tar -xf /tmp/ollama.tar -C ~/.local/
chmod +x ~/.local/bin/ollama
```

### 启动 Ollama

```bash
# 模型存储目录 + 监听所有网卡（允许其他机器访问）
OLLAMA_MODELS=/path/to/models OLLAMA_HOST=0.0.0.0:11434 ~/.local/bin/ollama serve &

# 仅本机访问（默认行为）
OLLAMA_MODELS=/path/to/models ~/.local/bin/ollama serve &
```

关键环境变量：

| 变量 | 作用 | 默认值 |
|------|------|--------|
| OLLAMA_MODELS | 模型文件存储目录 | ~/.ollama/models |
| OLLAMA_HOST | 监听地址和端口 | 127.0.0.1:11434 |

### 下载模型

```bash
OLLAMA_MODELS=/path/to/models ~/.local/bin/ollama pull qwen2.5:7b
```

常用模型：

| 模型 | 大小 | 说明 |
|------|------|------|
| qwen2.5:7b | 4.7GB | 推荐，7.6B 参数，Q4_K_M 量化，中文优秀 |
| qwen2.5:14b | 8.9GB | 更强推理，需更多显存 |
| qwen2.5:32b | 19GB | 最强，需 RTX 4090 24G 几乎满载 |

### 模型管理

```bash
~/.local/bin/ollama list          # 查看已下载的模型
~/.local/bin/ollama rm qwen2.5:7b # 删除模型
pkill ollama                       # 停止服务
```

### 外部访问模型 API

启动后直接 HTTP 请求 11434 端口：

```bash
# 查看模型列表
curl http://<ip>:11434/api/tags

# 问答
curl http://<ip>:11434/api/chat -d '{
  "model": "qwen2.5:7b",
  "messages": [{"role": "user", "content": "你好"}],
  "stream": false
}'
```

### 平台配置

1. 进入设置页 → 通用 tab → "AI 模型服务器"
2. 填入模型服务器的 IP 和端口（默认 11434）
3. 保存，立即生效，无需重启

环境变量（在 docker-compose.yml 中配置）：

```env
AI_EXPLAIN_ENABLED=true         # 是否启用 LLM 调用
OLLAMA_MODEL=qwen2.5:7b         # 模型名称
AI_EXPLAIN_TIMEOUT_SECONDS=30   # 调用超时
```

默认 `AI_EXPLAIN_ENABLED=false`，显式设为 `true` 后才调用 LLM。
LLM 不可用时自动回退到规则模板解释。

### 调用链

```
前端点击 AI 按钮
  → POST /api/ai/explain
    → GeneralConfig 读取 host:port
    → httpx.post(http://<host>:<port>/api/chat)
      → qwen2.5:7b 返回解释
    → 前端展示
```

### 常见问题

**Q: Ollama 启动后其他机器访问不通？**
确保 OLLAMA_HOST=0.0.0.0:11434，防火墙放行 11434 端口。

**Q: 模型下载慢？**
使用代理：
```bash
HTTPS_PROXY=http://127.0.0.1:10808 ~/.local/bin/ollama pull qwen2.5:7b
```

**Q: 显存不够？**
换更小的量化版本：
```bash
~/.local/bin/ollama pull qwen2.5:3b
```

**Q: 如何验证 GPU 推理生效？**
查看 Ollama 启动日志，应出现：
```
msg="inference compute" library=CUDA compute=8.9 name="NVIDIA GeForce RTX 4090"
```
