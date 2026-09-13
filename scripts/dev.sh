#!/usr/bin/env bash
# 一站式 dev 启动脚本 — 同时拉起后端 API + 前端 Vite dev server
#
# 用法：
#   bash scripts/dev.sh               # 后端走 ScriptedReasoner（无 DEEPSEEK_API_KEY）
#   DEEPSEEK_API_KEY=sk-... bash scripts/dev.sh   # 后端走真实 DeepSeek
#   bash scripts/dev.sh --backend-only
#   bash scripts/dev.sh --frontend-only
#
# 端口：
#   - 后端 FastAPI: http://127.0.0.1:8000  (改 PROOFPATH_PORT)
#   - 前端 Vite  : http://127.0.0.1:5173  (改 vite.config.ts)
#   - 前端已配 proxy：/api/* → 127.0.0.1:8000

set -eo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

backend_only=0
frontend_only=0
for arg in "$@"; do
  case "$arg" in
    --backend-only)  backend_only=1 ;;
    --frontend-only) frontend_only=1 ;;
    -h|--help)
      sed -n '2,12p' "$0"; exit 0 ;;
  esac
done

# 颜色
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; BLUE='\033[0;34m'; NC='\033[0m'
log()  { printf "${BLUE}[dev]${NC} %s\n" "$*"; }
warn() { printf "${YELLOW}[dev]${NC} %s\n" "$*" >&2; }
err()  { printf "${RED}[dev]${NC} %s\n" "$*" >&2; }

# 1. 检查 Python venv
if [ ! -x ".venv/bin/python" ]; then
  err ".venv/bin/python 不存在。先：uv venv && uv pip install -e '.[dev,server,frontend]'"
  exit 1
fi

# 2. 决定后端 reasoner
if [ -n "${DEEPSEEK_API_KEY:-}" ]; then
  log "检测到 DEEPSEEK_API_KEY → 使用真实 DeepSeekReasoner"
else
  warn "未设置 DEEPSEEK_API_KEY → 后端走 ScriptedReasoner (D-014 demo 模式)"
  warn "  这是预期行为：API 端到端可跑，证据核验照样工作，只是分析结果是预埋剧本"
fi

# 3. 启动后端（如未禁用）
BACKEND_PID=""
if [ "$frontend_only" -eq 0 ]; then
  log "启动后端 FastAPI（端口 ${PROOFPATH_PORT:-8000}）…"
  PYTHONPATH=src PROOFPATH_HOST=127.0.0.1 PROOFPATH_PORT="${PROOFPATH_PORT:-8000}" \
    .venv/bin/python -m uvicorn proofpath.api:app --host 127.0.0.1 --port "${PROOFPATH_PORT:-8000}" \
      --log-level info > /tmp/proofpath-backend.log 2>&1 &
  BACKEND_PID=$!
  log "后端 PID: $BACKEND_PID（日志：/tmp/proofpath-backend.log）"

  # 等 /docs 就绪
  for i in 1 2 3 4 5 6 7 8 9 10; do
    if curl -sS -o /dev/null --max-time 1 "http://127.0.0.1:${PROOFPATH_PORT:-8000}/docs"; then
      log "后端就绪 (http://127.0.0.1:${PROOFPATH_PORT:-8000}/docs)"
      break
    fi
    sleep 1
  done
fi

# 4. 启动前端（如未禁用）
FRONTEND_PID=""
if [ "$backend_only" -eq 0 ]; then
  if [ ! -d "frontend/node_modules" ]; then
    log "frontend/node_modules 缺失，先装依赖…"
    (cd frontend && pnpm install --prefer-offline 2>&1 | tail -3)
  fi
  log "启动前端 Vite dev server（端口 5173）…"
  (cd frontend && pnpm dev --host 127.0.0.1 --port 5173) > /tmp/proofpath-frontend.log 2>&1 &
  FRONTEND_PID=$!
  log "前端 PID: $FRONTEND_PID（日志：/tmp/proofpath-frontend.log）"

  # 等前端就绪
  for i in 1 2 3 4 5 6 7 8 9 10; do
    if curl -sS -o /dev/null --max-time 1 "http://127.0.0.1:5173"; then
      log "前端就绪 (http://127.0.0.1:5173)"
      break
    fi
    sleep 1
  done
fi

echo
log "==================== 测试入口 ===================="
log "前端 UI          : http://127.0.0.1:5173"
log "后端 Swagger     : http://127.0.0.1:${PROOFPATH_PORT:-8000}/docs"
log "后端 OpenAPI JSON: http://127.0.0.1:${PROOFPATH_PORT:-8000}/openapi.json"
log "CLI 演示         : PYTHONPATH=src .venv/bin/python -m proofpath demo --audit run.jsonl"
log "=================================================="
echo
log "按 Ctrl-C 停止两端。"

# 5. 等待并清理
cleanup() {
  echo
  log "正在关闭…"
  if [ -n "${BACKEND_PID:-}" ];  then kill "$BACKEND_PID"  2>/dev/null || true; fi
  if [ -n "${FRONTEND_PID:-}" ]; then kill "$FRONTEND_PID" 2>/dev/null || true; fi
  exit 0
}
trap cleanup INT TERM

# 阻塞直到任一进程退出
while true; do
  if [ -n "${BACKEND_PID:-}" ]  && ! kill -0 "$BACKEND_PID"  2>/dev/null; then
    err "后端进程已退出，查看日志：tail -50 /tmp/proofpath-backend.log"
    cleanup
  fi
  if [ -n "${FRONTEND_PID:-}" ] && ! kill -0 "$FRONTEND_PID" 2>/dev/null; then
    err "前端进程已退出，查看日志：tail -50 /tmp/proofpath-frontend.log"
    cleanup
  fi
  sleep 2
done
