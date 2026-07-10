#!/bin/bash
# Ollama 后端服务启动脚本
# 用法: ./scripts/start_ollama.sh [start|stop|restart|status]

set -e

# 配置
OLLAMA_BIN="/home/tbl/.local/bin/ollama"
MODEL_DIR="/home/tbl/Project/models/qwen2.5"
MODEL_NAME="qwen3-vl-thinking:32b"
OLLAMA_HOST="0.0.0.0:11434"
OLLAMA_KEEP_ALIVE="8760h"
OLLAMA_CONTEXT_LENGTH=4096
OLLAMA_NUM_PARALLEL=1

log_info()  { echo "[INFO]  $1"; }
log_warn()  { echo "[WARN]  $1"; }
log_error() { echo "[ERROR] $1"; }

check_installation() {
    if [ ! -f "$OLLAMA_BIN" ]; then
        log_error "Ollama 未找到: $OLLAMA_BIN"
        exit 1
    fi
    log_info "Ollama 已安装: $($OLLAMA_BIN --version)"
}

check_status() {
    if ! systemctl is-active --quiet ollama 2>/dev/null; then
        log_warn "Ollama systemd 服务未运行"
        return 1
    fi

    log_info "Ollama systemd 服务正在运行"

    local ps_output
    ps_output=$(curl -s --max-time 5 http://127.0.0.1:11434/api/ps 2>/dev/null || echo "")

    if [ -z "$ps_output" ]; then
        log_warn "无法连接到 Ollama API"
        return 1
    fi

    # 用 python3 解析 JSON，输出模型状态
    echo "$ps_output" | python3 -c "
import sys, json
d = json.load(sys.stdin)
models = d.get('models', [])
if not models:
    print('  无模型加载到 GPU')
    sys.exit(0)
for m in models:
    name = m.get('name', '?')
    vram = m.get('size_vram', 0)
    vram_mb = vram / 1024 / 1024
    expires = m.get('expires_at', '?')
    if vram > 0:
        print(f'  [{name}] 已加载 VRAM={vram_mb:.0f}MB, 过期={expires}')
    else:
        print(f'  [{name}] 未加载到 GPU (已卸载)')
"
    return 0
}

start_service() {
    log_info "启动 Ollama 服务..."
    log_info "配置: 模型=$MODEL_NAME 目录=$MODEL_DIR 端口=$OLLAMA_HOST 常驻=$OLLAMA_KEEP_ALIVE"

    if pgrep -f "ollama serve" > /dev/null 2>&1; then
        log_warn "Ollama 进程已在运行 (PID: $(pgrep -f 'ollama serve' | head -1))"
        log_warn "如需重启请使用: $0 restart"
        return 1
    fi

    export OLLAMA_MODELS="$MODEL_DIR"
    export OLLAMA_HOST="$OLLAMA_HOST"
    export OLLAMA_KEEP_ALIVE="$OLLAMA_KEEP_ALIVE"
    export OLLAMA_NUM_PARALLEL="$OLLAMA_NUM_PARALLEL"
    export OLLAMA_CONTEXT_LENGTH="$OLLAMA_CONTEXT_LENGTH"

    nohup "$OLLAMA_BIN" serve > /tmp/ollama.log 2>&1 &
    local pid=$!
    log_info "ollama serve 已启动 (PID: $pid)"

    local retries=0
    while [ $retries -lt 30 ]; do
        if curl -s --max-time 2 http://127.0.0.1:11434/api/tags > /dev/null 2>&1; then
            log_info "Ollama 服务已就绪"
            break
        fi
        sleep 1
        retries=$((retries + 1))
    done

    if [ $retries -eq 30 ]; then
        log_error "Ollama 服务启动超时，请检查日志: /tmp/ollama.log"
        return 1
    fi

    log_info "预热模型 $MODEL_NAME ..."
    "$OLLAMA_BIN" run "$MODEL_NAME" "" 2>/dev/null || true
    log_info "模型预热完成，服务启动成功"
    return 0
}

stop_service() {
    log_info "停止 Ollama 服务..."

    if systemctl is-active --quiet ollama 2>/dev/null; then
        echo '821778' | sudo -S systemctl stop ollama
        log_info "已通过 systemd 停止"
        return 0
    fi

    local pid
    pid=$(pgrep -f "ollama serve" | head -1)
    if [ -n "$pid" ]; then
        kill "$pid" 2>/dev/null || true
        sleep 2
        kill -0 "$pid" 2>/dev/null && kill -9 "$pid" 2>/dev/null || true
        log_info "已停止进程 $pid"
    else
        log_warn "未找到运行中的 Ollama 进程"
    fi
    return 0
}

restart_service() {
    stop_service
    sleep 2
    start_service
}

show_help() {
    echo "用法: $0 [命令]"
    echo ""
    echo "命令:"
    echo "  start     启动 Ollama 服务"
    echo "  stop      停止 Ollama 服务"
    echo "  restart   重启 Ollama 服务"
    echo "  status    查看服务状态"
    echo "  help      显示帮助"
}

case "${1:-status}" in
    start)   check_installation; check_status && { log_warn "服务已在运行"; exit 0; } || start_service ;;
    stop)    stop_service ;;
    restart) check_installation; restart_service ;;
    status)  check_installation; check_status ;;
    help|--help|-h) show_help ;;
    *) log_error "未知命令: $1"; show_help; exit 1 ;;
esac
