#!/usr/bin/env bash
#
# Starts/stops/restarts every backend service plus the frontend using a plain
# `python3 -m venv` virtual environment — no uv, no conda required.
#
# Usage:
#   ./start_services_plain.sh [start|stop|restart|status]
#
# Prerequisites:
#   - A system `python3` in the 3.9-3.13 range (faiss-cpu has no wheels for
#     3.14+ yet). Override which interpreter to use with PYTHON_BIN, e.g.:
#       PYTHON_BIN=python3.12 ./start_services_plain.sh start
#   - node/npm for the frontend.
#   - GOOGLE_APPLICATION_CREDENTIALS pointing at a valid Vertex AI
#     service-account key (export it before running this script).

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RUNTIME_DIR="$ROOT_DIR/.runtime"
LOG_DIR="$RUNTIME_DIR/logs"
PID_FILE="$RUNTIME_DIR/pids.env"
VENV_DIR="${VENV_DIR:-$ROOT_DIR/.venv-plain}"

PYTHON_BIN="${PYTHON_BIN:-python3}"

# Must point at your own Vertex AI service-account JSON key (not committed
# anywhere in this repo). Export it before running this script, e.g.:
#   export GOOGLE_APPLICATION_CREDENTIALS="/path/to/your-service-account.json"
GOOGLE_APPLICATION_CREDENTIALS="${GOOGLE_APPLICATION_CREDENTIALS:-}"

# Vertex AI project/location — override per environment. Defaults match the
# local-dev project used by the committed .env files; on a server with its
# own service account (e.g. via Application Default Credentials), export
# these to point at that server's actual GCP project instead, e.g.:
#   export VERTEX_PROJECT_ID="steadfast-slate-513507-i5"
VERTEX_PROJECT_ID="${VERTEX_PROJECT_ID:-}"
VERTEX_LOCATION="${VERTEX_LOCATION:-}"

mkdir -p "$LOG_DIR"

is_running() {
  local pid="$1"
  [[ -n "${pid}" ]] && kill -0 "$pid" >/dev/null 2>&1
}

check_python_version() {
  if ! command -v "$PYTHON_BIN" >/dev/null 2>&1; then
    echo "'$PYTHON_BIN' not found on PATH. Install Python 3.9-3.13, or set PYTHON_BIN." >&2
    exit 1
  fi

  local version major minor
  version="$("$PYTHON_BIN" -c 'import sys; print(f"{sys.version_info[0]}.{sys.version_info[1]}")')"
  major="${version%%.*}"
  minor="${version##*.}"

  if [[ "$major" -ne 3 || "$minor" -lt 9 || "$minor" -gt 13 ]]; then
    echo "Warning: $PYTHON_BIN is $version. faiss-cpu (and this app) needs Python 3.9-3.13." >&2
    echo "If dependency install fails below, point PYTHON_BIN at a 3.9-3.13 interpreter, e.g.:" >&2
    echo "  PYTHON_BIN=python3.12 ./start_services_plain.sh start" >&2
  fi
}

ensure_venv() {
  if [[ ! -f "$VENV_DIR/bin/activate" ]]; then
    echo "Creating virtual environment at: $VENV_DIR (using $PYTHON_BIN)"
    "$PYTHON_BIN" -m venv "$VENV_DIR"
    # shellcheck disable=SC1090
    source "$VENV_DIR/bin/activate"
    pip install --upgrade pip -q
    pip install -r "$ROOT_DIR/requirements.txt"
    deactivate
  else
    echo "Using existing virtual environment: $VENV_DIR"
  fi
}

ensure_frontend_dependencies() {
  local frontend_dir="$ROOT_DIR/frontend"
  if [[ ! -d "$frontend_dir/node_modules" ]]; then
    if ! command -v npm >/dev/null 2>&1; then
      echo "npm not found on PATH. Install Node.js/npm first." >&2
      exit 1
    fi
    echo "Frontend dependencies not found. Running npm install..."
    (cd "$frontend_dir" && npm install)
  fi
}

start_one() {
  local name="$1"
  local workdir="$2"
  local cmd="$3"
  local logfile="$LOG_DIR/${name}.log"

  # Only forward these if actually set — exporting an *empty* override would
  # stop each service's own .env-driven fallback from ever loading its
  # (non-empty) default, since those loaders skip keys already in os.environ.
  local env_prefix="export GOOGLE_APPLICATION_CREDENTIALS='$GOOGLE_APPLICATION_CREDENTIALS';"
  if [[ -n "$VERTEX_PROJECT_ID" ]]; then
    env_prefix="$env_prefix export VERTEX_PROJECT_ID='$VERTEX_PROJECT_ID';"
  fi
  if [[ -n "$VERTEX_LOCATION" ]]; then
    env_prefix="$env_prefix export VERTEX_LOCATION='$VERTEX_LOCATION';"
  fi

  nohup bash -lc "$env_prefix cd \"$workdir\" && exec $cmd" >"$logfile" 2>&1 &
  echo "$!"
}

stop_all() {
  if [[ ! -f "$PID_FILE" ]]; then
    echo "No PID file found; nothing to stop."
    return 0
  fi
  # shellcheck disable=SC1090
  source "$PID_FILE"
  local stopped_any=0
  for pid_var in SYNTHETIC_PID CPT_SYNTHETIC_PID EVIDENCE_PID RESOLVER_PID PCS_PID \
                 CPT_RETRIEVAL_PID CPT_PIPELINE_PID PROMPTS_PID BATCH_PID FRONTEND_PID; do
    local pid="${!pid_var:-}"
    if is_running "$pid"; then
      kill "$pid" >/dev/null 2>&1 || true
      stopped_any=1
      echo "Stopped $pid_var (PID: $pid)"
    fi
  done
  rm -f "$PID_FILE"
  if [[ "$stopped_any" -eq 0 ]]; then
    echo "No active service processes were running."
  fi
}

status_all() {
  if [[ ! -f "$PID_FILE" ]]; then
    echo "Status: no PID file found. Services are not managed by this script right now."
    return 0
  fi
  # shellcheck disable=SC1090
  source "$PID_FILE"
  for pid_var in SYNTHETIC_PID CPT_SYNTHETIC_PID EVIDENCE_PID RESOLVER_PID PCS_PID \
                 CPT_RETRIEVAL_PID CPT_PIPELINE_PID PROMPTS_PID BATCH_PID FRONTEND_PID; do
    local pid="${!pid_var:-}"
    if is_running "$pid"; then
      echo "$pid_var -> RUNNING (PID: $pid)"
    else
      echo "$pid_var -> NOT RUNNING"
    fi
  done
}

start_all() {
  if [[ -f "$PID_FILE" ]]; then
    # shellcheck disable=SC1090
    source "$PID_FILE"
    for pid_var in SYNTHETIC_PID CPT_SYNTHETIC_PID EVIDENCE_PID RESOLVER_PID PCS_PID \
                   CPT_RETRIEVAL_PID CPT_PIPELINE_PID PROMPTS_PID BATCH_PID FRONTEND_PID; do
      if is_running "${!pid_var:-}"; then
        echo "Some services already appear to be running. Use: $0 stop (then start again)."
        exit 1
      fi
    done
  fi

  if [[ -z "$GOOGLE_APPLICATION_CREDENTIALS" ]]; then
    echo "Note: GOOGLE_APPLICATION_CREDENTIALS is not set." >&2
    echo "That's fine on a host with its own attached service account (Application" >&2
    echo "Default Credentials, e.g. a GCE/Cloud Run service account) — Vertex AI calls" >&2
    echo "will use that automatically. Otherwise, export a key file first, e.g.:" >&2
    echo "  export GOOGLE_APPLICATION_CREDENTIALS=\"/path/to/your-service-account.json\"" >&2
  fi

  if [[ "$(id -u)" -ne 0 ]]; then
    echo "Note: the frontend listens on port 80 by default, which usually needs root." >&2
    echo "Run this script with sudo, or use an unprivileged port instead, e.g.:" >&2
    echo "  VITE_PORT=5173 $0 start" >&2
  fi

  check_python_version
  ensure_venv
  ensure_frontend_dependencies

  local PYBIN="$VENV_DIR/bin/python"
  echo "Using Python: $PYBIN ($($PYBIN --version))"
  echo "Using credentials: ${GOOGLE_APPLICATION_CREDENTIALS:-<none, relying on Application Default Credentials>}"
  echo "Using Vertex project: ${VERTEX_PROJECT_ID:-<default: raapid-genai>}"
  echo "Using Vertex location: ${VERTEX_LOCATION:-<default: global>}"

  SYNTHETIC_PID="$(start_one "synthetic_api" "$ROOT_DIR/E&M_backend/E&M_Synthetic_data_generation" "'$PYBIN' main.py")"
  CPT_SYNTHETIC_PID="$(start_one "cpt_synthetic_api" "$ROOT_DIR/CPT_backend/CPT_Synthetic_data_generation" "'$PYBIN' main.py")"
  EVIDENCE_PID="$(start_one "evidence_api" "$ROOT_DIR/E&M_backend/E&M_evidence_predictions" "'$PYBIN' api_server.py")"
  RESOLVER_PID="$(start_one "resolver_api" "$ROOT_DIR/E&M_backend/E&M" "'$PYBIN' json_em_code_service.py")"
  PCS_PID="$(start_one "pcs_api" "$ROOT_DIR/PCS_backend" "'$PYBIN' pcs_pipeline_api.py")"
  CPT_RETRIEVAL_PID="$(start_one "cpt_retrieval_api" "$ROOT_DIR/CPT_backend/CPT_text_retrieval/text_retrieval" "env TOKENIZERS_PARALLELISM=false OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 '$PYBIN' -m uvicorn text_retrieval_api:app --host 127.0.0.1 --port 8083 --workers 1 --log-level debug")"
  CPT_PIPELINE_PID="$(start_one "cpt_pipeline_api" "$ROOT_DIR/CPT_backend/CPT_pipeline" "'$PYBIN' cpt_pipeline_api.py")"
  PROMPTS_PID="$(start_one "prompts_api" "$ROOT_DIR" "'$PYBIN' prompts_api.py")"
  BATCH_PID="$(start_one "batch_api" "$ROOT_DIR" "'$PYBIN' batch_api.py")"
  FRONTEND_PID="$(start_one "frontend_app" "$ROOT_DIR/frontend" "npm run dev")"

  cat >"$PID_FILE" <<EOF
SYNTHETIC_PID=$SYNTHETIC_PID
CPT_SYNTHETIC_PID=$CPT_SYNTHETIC_PID
EVIDENCE_PID=$EVIDENCE_PID
RESOLVER_PID=$RESOLVER_PID
PCS_PID=$PCS_PID
CPT_RETRIEVAL_PID=$CPT_RETRIEVAL_PID
CPT_PIPELINE_PID=$CPT_PIPELINE_PID
PROMPTS_PID=$PROMPTS_PID
BATCH_PID=$BATCH_PID
FRONTEND_PID=$FRONTEND_PID
EOF

  cat <<EOF

Services started.

Synthetic API (E&M): http://localhost:8082  (log: $LOG_DIR/synthetic_api.log)
Synthetic API (CPT): http://localhost:8086  (log: $LOG_DIR/cpt_synthetic_api.log)
Evidence API       : http://localhost:8000  (log: $LOG_DIR/evidence_api.log)
Resolver API       : http://localhost:8081  (log: $LOG_DIR/resolver_api.log)
PCS API            : http://localhost:8085  (log: $LOG_DIR/pcs_api.log)
CPT Retrieval      : http://localhost:8083  (log: $LOG_DIR/cpt_retrieval_api.log)
CPT Pipeline       : http://localhost:8084  (log: $LOG_DIR/cpt_pipeline_api.log)
Prompts/Schemas API: http://localhost:8087  (log: $LOG_DIR/prompts_api.log)
Batch Processing   : http://localhost:8088  (log: $LOG_DIR/batch_api.log)
Frontend           : http://localhost  (log: $LOG_DIR/frontend_app.log)

PIDs saved in: $PID_FILE
To stop all:  $0 stop
To check:     $0 status
EOF
}

case "${1:-start}" in
  start)
    start_all
    ;;
  stop)
    stop_all
    ;;
  restart)
    stop_all
    sleep 1
    start_all
    ;;
  status)
    status_all
    ;;
  *)
    echo "Usage: $0 [start|stop|restart|status]"
    exit 1
    ;;
esac
