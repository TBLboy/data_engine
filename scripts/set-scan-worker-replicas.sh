#!/usr/bin/env bash
set -euo pipefail

# 从数据库读取 scan_worker_replicas 配置并应用
# 用法: scripts/set-scan-worker-replicas.sh [副本数]
#   不传参数时自动从 GeneralConfig 读取
#   传参数时直接设置指定副本数并保存到数据库

CDIR="$(cd "$(dirname "$0")/.." && pwd)"
COMPOSE_FILE="$CDIR/deploy/docker-compose.yml"
ENV_FILE="$CDIR/deploy/.env"

# 加载环境变量
if [ -f "$ENV_FILE" ]; then
  set -a
  source "$ENV_FILE"
  set +a
fi

DB_URL="${DATABASE_URL:-postgresql://robot_qc:${POSTGRES_PASSWORD}@localhost:5432/robot_qc}"
COMPOSE="${COMPOSE:-docker compose -f $COMPOSE_FILE}"

if [ $# -ge 1 ]; then
  REPLICAS="$1"
  echo "使用命令行指定副本数: $REPLICAS"
else
  # 从数据库读取配置
  REPLICAS=$(psql "$DB_URL" -t -A -c "
    SELECT params_json::json->>'scan_worker_replicas'
    FROM general_config
    WHERE id = 1
  " 2>/dev/null || echo "")

  if [ -z "$REPLICAS" ] || [ "$REPLICAS" = "null" ]; then
    REPLICAS=1
  fi
  echo "从 GeneralConfig 读取副本数: $REPLICAS"
fi

echo "执行: $COMPOSE up -d --scale scan-worker=$REPLICAS scan-worker"
eval "$COMPOSE up -d --scale scan-worker=$REPLICAS scan-worker"

echo "完成。当前 scan-worker 状态:"
eval "$COMPOSE ps scan-worker"
