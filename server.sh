#!/usr/bin/env bash
# ──────────────────────────────────────────────────────────────
#  server.sh — MotionWeaver 服务管理脚本
#
#  用法: ./server.sh <service> <action>
#    service:  frontend | backend | all
#    action:   start | stop | status | restart
#
#  示例:
#    ./server.sh all start       # 启动全部服务
#    ./server.sh backend restart # 重启后端 (含 Celery)
#    ./server.sh frontend stop   # 停止前端
#    ./server.sh all status      # 查看所有服务状态
# ──────────────────────────────────────────────────────────────
set -euo pipefail

# ── 路径配置 ──────────────────────────────────────────────
ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"
BACKEND_DIR="$ROOT_DIR/backend"
FRONTEND_DIR="$ROOT_DIR/frontend"
VENV="$BACKEND_DIR/venv/bin"
LOG_DIR="$ROOT_DIR/.logs"
mkdir -p "$LOG_DIR"

# ── 端口配置 ──────────────────────────────────────────────
FRONTEND_PORT=9000
BACKEND_PORT=9001

# ── 颜色 ─────────────────────────────────────────────────
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color
BOLD='\033[1m'

log_info()  { echo -e "${CYAN}[INFO]${NC}  $*"; }
log_ok()    { echo -e "${GREEN}[OK]${NC}    $*"; }
log_warn()  { echo -e "${YELLOW}[WARN]${NC}  $*"; }
log_err()   { echo -e "${RED}[ERR]${NC}   $*"; }

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  端口清理 — 杀掉占用指定端口的所有进程
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
kill_port() {
  local port=$1
  local pids
  pids=$(lsof -ti :"$port" 2>/dev/null || true)
  if [[ -n "$pids" ]]; then
    log_warn "清理端口 $port 上的进程: $pids"
    echo "$pids" | xargs kill -9 2>/dev/null || true
    sleep 1
  fi
}

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  进程清理 — 按名称模式杀掉进程
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
kill_by_pattern() {
  local pattern=$1
  local pids
  pids=$(pgrep -f "$pattern" 2>/dev/null || true)
  if [[ -n "$pids" ]]; then
    log_warn "终止匹配进程 [$pattern]: $pids"
    echo "$pids" | xargs kill -9 2>/dev/null || true
    sleep 1
  fi
}

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  检查进程是否存活
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
check_port() {
  local port=$1
  lsof -ti :"$port" &>/dev/null
}

check_pattern() {
  local pattern=$1
  pgrep -f "$pattern" &>/dev/null
}

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  BACKEND (uvicorn + celery)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
backend_start() {
  if check_port "$BACKEND_PORT"; then
    log_warn "Backend 已在端口 $BACKEND_PORT 运行"
    return 0
  fi

  log_info "启动 Backend (uvicorn :$BACKEND_PORT) ..."
  cd "$BACKEND_DIR"
  nohup "$VENV/python" -m uvicorn app.main:app \
    --host 0.0.0.0 --port "$BACKEND_PORT" --reload \
    > "$LOG_DIR/backend.log" 2>&1 &
  log_ok "Backend 已启动 (PID: $!, log: $LOG_DIR/backend.log)"

  log_info "启动 Celery Worker ..."
  nohup "$VENV/celery" -A app.tasks worker \
    --loglevel=info --concurrency=2 \
    > "$LOG_DIR/celery.log" 2>&1 &
  log_ok "Celery 已启动 (PID: $!, log: $LOG_DIR/celery.log)"
}

backend_stop() {
  log_info "停止 Backend ..."

  # Kill celery first
  kill_by_pattern "celery.*app.tasks.*worker"

  # Kill uvicorn
  kill_by_pattern "uvicorn app.main:app"

  # Force-clear port
  kill_port "$BACKEND_PORT"

  log_ok "Backend 已停止"
}

backend_status() {
  echo -e "${BOLD}── Backend ──${NC}"

  if check_port "$BACKEND_PORT"; then
    local pid
    pid=$(lsof -ti :"$BACKEND_PORT" | head -1)
    echo -e "  Uvicorn:  ${GREEN}RUNNING${NC}  (port $BACKEND_PORT, PID $pid)"
  else
    echo -e "  Uvicorn:  ${RED}STOPPED${NC}"
  fi

  if check_pattern "celery.*app.tasks.*worker"; then
    local cpid
    cpid=$(pgrep -f "celery.*app.tasks.*worker" | head -1)
    echo -e "  Celery:   ${GREEN}RUNNING${NC}  (PID $cpid)"
  else
    echo -e "  Celery:   ${RED}STOPPED${NC}"
  fi
}

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  FRONTEND (next dev)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
frontend_start() {
  if check_port "$FRONTEND_PORT"; then
    log_warn "Frontend 已在端口 $FRONTEND_PORT 运行"
    return 0
  fi

  log_info "启动 Frontend (next dev :$FRONTEND_PORT) ..."
  cd "$FRONTEND_DIR"
  nohup npx next dev --port "$FRONTEND_PORT" \
    > "$LOG_DIR/frontend.log" 2>&1 &
  log_ok "Frontend 已启动 (PID: $!, log: $LOG_DIR/frontend.log)"
}

frontend_stop() {
  log_info "停止 Frontend ..."

  # Kill next dev processes
  kill_by_pattern "next dev"
  kill_by_pattern "next-server"

  # Force-clear port
  kill_port "$FRONTEND_PORT"

  log_ok "Frontend 已停止"
}

frontend_status() {
  echo -e "${BOLD}── Frontend ──${NC}"

  if check_port "$FRONTEND_PORT"; then
    local pid
    pid=$(lsof -ti :"$FRONTEND_PORT" | head -1)
    echo -e "  Next.js:  ${GREEN}RUNNING${NC}  (port $FRONTEND_PORT, PID $pid)"
  else
    echo -e "  Next.js:  ${RED}STOPPED${NC}"
  fi
}

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  路由
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
do_start() {
  case "$1" in
    frontend) frontend_start ;;
    backend)  backend_start ;;
    all)      backend_start; frontend_start ;;
  esac
}

do_stop() {
  case "$1" in
    frontend) frontend_stop ;;
    backend)  backend_stop ;;
    all)      frontend_stop; backend_stop ;;
  esac
}

do_status() {
  echo ""
  case "$1" in
    frontend) frontend_status ;;
    backend)  backend_status ;;
    all)      backend_status; echo ""; frontend_status ;;
  esac
  echo ""
}

do_restart() {
  do_stop "$1"
  sleep 1
  do_start "$1"
}

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  主入口
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
usage() {
  echo ""
  echo -e "${BOLD}MotionWeaver 服务管理${NC}"
  echo ""
  echo "  用法: $0 <service> <action>"
  echo ""
  echo "  service:  frontend | backend | all"
  echo "  action:   start | stop | status | restart"
  echo ""
  echo "  示例:"
  echo "    $0 all start        # 启动全部"
  echo "    $0 backend restart  # 重启后端"
  echo "    $0 all status       # 查看状态"
  echo ""
  exit 1
}

SERVICE="${1:-}"
ACTION="${2:-}"

if [[ -z "$SERVICE" || -z "$ACTION" ]]; then
  usage
fi

if [[ "$SERVICE" != "frontend" && "$SERVICE" != "backend" && "$SERVICE" != "all" ]]; then
  log_err "未知 service: $SERVICE (可选: frontend | backend | all)"
  exit 1
fi

case "$ACTION" in
  start)   do_start "$SERVICE" ;;
  stop)    do_stop "$SERVICE" ;;
  status)  do_status "$SERVICE" ;;
  restart) do_restart "$SERVICE" ;;
  *)       log_err "未知 action: $ACTION (可选: start | stop | status | restart)"; exit 1 ;;
esac
