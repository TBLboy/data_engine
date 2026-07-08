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
┌─────────────────────────┐      ┌──────────────────────────┐
│  Robot QC 服务器         │      │  AI 模型服务器             │
│                         │      │                          │
│  backend (Docker)       │ HTTP │  Ollama (systemd 服务)    │
│  └─ llm_client.py ──────┼─────▶│  └─ qwen3-vl-thinking:32b│
│     http://<host>:11434 │ LAN  │     :11434                │
│                         │      │                          │
│  健康检查:               │      │  systemd 开机自启          │
│  GET /ai-assistant/health│     │  模型常驻 GPU 不卸载        │
└─────────────────────────┘      └──────────────────────────┘
```

模型服务器和平台服务器可部署在同一台或不同机器，仅需局域网互通。
模型通过 systemd 服务常驻运行，开机自启、崩溃自动重启、模型保持加载不卸载。

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

### 配置 systemd 服务（推荐）

将 Ollama 注册为系统服务，实现开机自启、崩溃自动重启、模型常驻 GPU。

```bash
sudo tee /etc/systemd/system/ollama.service << 'EOF'
[Unit]
Description=Ollama Model Server
After=network.target

[Service]
Type=simple
User=<你的用户名>
Environment="OLLAMA_MODELS=/home/<用户>/Project/models/qwen2.5"
Environment="OLLAMA_HOST=0.0.0.0:11434"
Environment="OLLAMA_KEEP_ALIVE=8760h"
Environment="OLLAMA_NUM_PARALLEL=1"
Environment="OLLAMA_CONTEXT_LENGTH=4096"
ExecStart=/home/<用户>/.local/bin/ollama serve
ExecStartPost=/bin/bash -c 'sleep 5 && /home/<用户>/.local/bin/ollama run <模型名> "" 2>/dev/null; echo "model warmed"'
Restart=on-failure
RestartSec=5
LimitNOFILE=65536

[Install]
WantedBy=default.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable ollama
sudo systemctl start ollama
sudo systemctl status ollama
```

关键环境变量：

| 变量 | 作用 | 默认值 | 推荐值 |
|------|------|--------|--------|
| OLLAMA_MODELS | 模型文件存储目录 | ~/.ollama/models | /home/xxx/Project/models/qwen2.5 |
| OLLAMA_HOST | 监听地址和端口 | 127.0.0.1:11434 | 0.0.0.0:11434 |
| OLLAMA_KEEP_ALIVE | 模型驻留时间 | 5m | 8760h（1年，即常驻）|
| OLLAMA_NUM_PARALLEL | 并发请求数 | 1 | 1（节省显存）|
| OLLAMA_CONTEXT_LENGTH | 上下文长度 | 2048 | 4096（32B 模型 24G 显存下安全值）|

> `OLLAMA_KEEP_ALIVE=8760h` 确保模型不卸载。首次推理后模型常驻 GPU，后续请求秒级响应。
> `ExecStartPost` 在服务启动后自动预热模型，避免用户第一次对话等太久。

### 下载模型

```bash
# 从 HuggingFace 下载 GGUF 量化模型（推荐，需要代理）
OLLAMA_MODELS=/path/to/models HTTPS_PROXY=http://127.0.0.1:10808 \
  ~/.local/bin/ollama pull hf.co/unsloth/Qwen3-VL-32B-Thinking-GGUF:Q4_K_M

# 或从 Ollama 官方库下载
OLLAMA_MODELS=/path/to/models ~/.local/bin/ollama pull qwen2.5:7b
```

**HuggingFace 下载失败的应急方案：**

如果 HF 签名验证超时（模型数据已下载但注册失败），可用 Modelfile 手动注册：

```bash
# 找到已下载的 blob hash
ls -lh $OLLAMA_MODELS/blobs/

# 创建 Modelfile 指向 blob
cat > /tmp/Modelfile << 'EOF'
FROM /path/to/models/blobs/sha256-<模型文件的hash>
EOF

# 注册模型
OLLAMA_MODELS=/path/to/models ~/.local/bin/ollama create <模型名> -f /tmp/Modelfile
```

常用模型：

| 模型 | 大小 | 显存 | 说明 |
|------|------|------|------|
| qwen2.5:7b | 4.7GB | ~6GB | 轻量，中文好，响应快 |
| qwen2.5:14b | 8.9GB | ~12GB | 更强的推理能力 |
| qwen3-vl-thinking:32b | 19GB | ~23GB | 最强，多模态+思维链，需 RTX 4090 24G |

### 模型管理

```bash
~/.local/bin/ollama list          # 查看已下载的模型
~/.local/bin/ollama rm <模型名>    # 删除模型
sudo systemctl restart ollama     # 重启服务
sudo systemctl status ollama      # 查看运行状态
journalctl -u ollama -f           # 查看实时日志
```

### 验证模型推理

```bash
# 检查模型是否已加载到 GPU
curl http://127.0.0.1:11434/api/ps

# 直接测试推理
curl http://127.0.0.1:11434/api/chat -d '{
  "model": "qwen3-vl-thinking:32b",
  "messages": [{"role": "user", "content": "你好"}],
  "stream": false
}'

# 查看 GPU 显存占用
nvidia-smi
```

### 平台配置

1. 进入设置页 → 通用 tab → "AI 模型服务器"
2. 配置三要素：
   - **服务器 IP 地址**：模型服务器的局域网 IP
   - **端口**：Ollama 端口（默认 11434）
   - **模型名称**：如 `qwen3-vl-thinking:32b` 或 `qwen2.5:7b`
3. 保存，立即生效，无需重启

环境变量（在 docker-compose.yml 中配置）：

```env
AI_EXPLAIN_ENABLED=true         # 是否启用 LLM 调用
AI_EXPLAIN_TIMEOUT_SECONDS=120  # 调用超时（大模型建议 120s+）
```

模型名称通过设置页面配置，存入 GeneralConfig，不再通过环境变量硬编码。

### 健康检查

平台提供快速健康检查端点，前端发送消息前自动检测模型服务是否可达：

```bash
# 3 秒超时，快速判断 Ollama 是否在线
curl http://<平台IP>:58080/api/ai-assistant/health
# → {"ok": true, "models": 2}
```

### 调用链

```
前端点击发送
  → GET /api/ai-assistant/health（3s 超时，检测 Ollama 连通性）
  → POST /api/ai-assistant/chat/stream（SSE 流式）
    → GeneralConfig 读取 host:port:model
    → httpx.stream(http://<host>:<port>/api/chat)
      → llama-server 推理（GPU 加速）
      → 逐 token 返回 SSE
    → validator 校验
    → 消息持久化到 ai_messages
  → 前端逐字渲染
```

### 故障排查

**Q: 前端提示"无法连接 AI 模型服务"？**
1. 检查 Ollama 是否运行：`sudo systemctl status ollama`
2. 检查端口是否监听：`curl http://<IP>:11434/api/tags`
3. 检查 Docker 容器能否访问宿主机：确保设置页 IP 配置为宿主机局域网 IP（非 127.0.0.1）

**Q: 每次对话都要等很久？**
检查 `OLLAMA_KEEP_ALIVE` 是否配置为足够长的时间。如果 Ollama 是手动 `serve &` 启动的，重启后模型会被卸载。

**Q: 推理直接报错或返回模板解释？**
1. 检查显存：`nvidia-smi`，如果接近 24GB 上限，降低 `OLLAMA_CONTEXT_LENGTH`
2. 检查后端日志：`docker compose -f deploy/docker-compose.yml logs backend | grep -i ollama`
3. 确认 `AI_EXPLAIN_TIMEOUT_SECONDS` 足够（推荐 120s）

**Q: 模型下载完成后 Ollama 不识别？**
HuggingFace 下载可能因签名验证失败而注册失败。使用 `OLLAMA_MODELS=... ollama list` 检查，如不存在则使用 Modelfile 手动注册。
