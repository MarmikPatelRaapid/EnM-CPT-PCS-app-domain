#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RUNTIME_DIR="$ROOT_DIR/.runtime"
LOG_DIR="$RUNTIME_DIR/logs"
PID_FILE="$RUNTIME_DIR/pids.env"
VENV_DIR="${VENV_DIR:-$ROOT_DIR/.venv}"
VENV_ACTIVATE="$VENV_DIR/bin/activate"

mkdir -p "$LOG_DIR"

is_running() {
  local pid="$1"
  if [[ -z "${pid}" ]]; then
    return 1
  fi
  kill -0 "$pid" >/dev/null 2>&1
}

collect_descendants() {
  local pid="$1"
  local child
  local children

  children="$(pgrep -P "$pid" || true)"
  for child in $children; do
    collect_descendants "$child"
    echo "$child"
  done
}

stop_process_tree() {
  local pid="$1"
  local label="$2"
  local descendants
  local target_pid
  local still_running=0

  if ! is_running "$pid"; then
    return 1
  fi

  descendants="$(collect_descendants "$pid")"
  kill "$pid" >/dev/null 2>&1 || true
  for target_pid in $descendants; do
    kill "$target_pid" >/dev/null 2>&1 || true
  done

  sleep 1

  if is_running "$pid"; then
    kill -9 "$pid" >/dev/null 2>&1 || true
  fi

  for target_pid in $descendants; do
    if is_running "$target_pid"; then
      kill -9 "$target_pid" >/dev/null 2>&1 || true
    fi
  done

  if is_running "$pid"; then
    still_running=1
  fi
  for target_pid in $descendants; do
    if is_running "$target_pid"; then
      still_running=1
      break
    fi
  done

  if [[ "$still_running" -eq 0 ]]; then
    echo "Stopped $label (PID: $pid)"
    return 0
  fi

  echo "Failed to fully stop $label (PID: $pid)"
  return 1
}

start_one() {
  local name="$1"
  local workdir="$2"
  local cmd="$3"
  local logfile="$LOG_DIR/${name}.log"

  nohup bash -lc "cd \"$workdir\" && exec $cmd" >"$logfile" 2>&1 &
  echo "$!"
}

activate_backend_venv() {
  if [[ ! -f "$VENV_ACTIVATE" ]]; then
    if ! command -v uv >/dev/null 2>&1; then
      echo "uv is not installed or not on PATH."
      echo "Install uv first, then re-run this script."
      exit 1
    fi

    if [[ ! -f "$ROOT_DIR/requirements.txt" ]]; then
      echo "Missing requirements file: $ROOT_DIR/requirements.txt"
      exit 1
    fi

    echo "Virtual environment not found at: $VENV_ACTIVATE"
    echo "Creating venv and installing backend dependencies with uv..."
    uv venv "$VENV_DIR"

    # shellcheck disable=SC1090
    source "$VENV_ACTIVATE"
    uv pip install -r "$ROOT_DIR/requirements.txt"
    echo "Backend virtual environment created: $VENV_DIR"
    return 0
  fi

  # shellcheck disable=SC1090
  source "$VENV_ACTIVATE"
  echo "Activated backend virtual environment: $VENV_DIR"
}

run_with_optional_sudo() {
  if command -v sudo >/dev/null 2>&1; then
    sudo "$@"
  else
    "$@"
  fi
}

install_npm_if_missing() {
  if command -v npm >/dev/null 2>&1; then
    return 0
  fi

  echo "npm is not installed. Attempting to install Node.js/npm..."
  if command -v apt-get >/dev/null 2>&1; then
    run_with_optional_sudo apt-get update
    run_with_optional_sudo apt-get install -y nodejs npm
  elif command -v dnf >/dev/null 2>&1; then
    run_with_optional_sudo dnf install -y nodejs npm
  elif command -v yum >/dev/null 2>&1; then
    run_with_optional_sudo yum install -y nodejs npm
  elif command -v pacman >/dev/null 2>&1; then
    run_with_optional_sudo pacman -Sy --noconfirm nodejs npm
  elif command -v brew >/dev/null 2>&1; then
    brew install node
  else
    echo "No supported package manager found to auto-install npm."
    echo "Please install Node.js/npm manually, then rerun this script."
    exit 1
  fi

  if ! command -v npm >/dev/null 2>&1; then
    echo "npm installation did not complete successfully."
    echo "Please install Node.js/npm manually, then rerun this script."
    exit 1
  fi
}

ensure_frontend_dependencies() {
  local frontend_dir="$ROOT_DIR/frontend"
  if [[ ! -d "$frontend_dir" ]]; then
    echo "Missing frontend directory: $frontend_dir"
    exit 1
  fi
  if [[ ! -f "$frontend_dir/package.json" ]]; then
    echo "Missing frontend package.json: $frontend_dir/package.json"
    exit 1
  fi

  install_npm_if_missing

  if [[ ! -d "$frontend_dir/node_modules" ]]; then
    echo "Frontend dependencies not found. Running npm install..."
    (cd "$frontend_dir" && npm install)
  else
    echo "Frontend dependencies already installed."
  fi
}

stop_all() {
  if [[ ! -f "$PID_FILE" ]]; then
    echo "No running services found (missing PID file)."
    return 0
  fi

  # shellcheck disable=SC1090
  source "$PID_FILE"

  local stopped_any=0
  for pid_var in SYNTHETIC_PID CPT_SYNTHETIC_PID EVIDENCE_PID RESOLVER_PID PCS_PID CPT_RETRIEVAL_PID CPT_PIPELINE_PID FRONTEND_PID; do
    local pid="${!pid_var:-}"
    if [[ -n "$pid" ]]; then
      if stop_process_tree "$pid" "$pid_var"; then
        stopped_any=1
      fi
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
  for label in SYNTHETIC_PID CPT_SYNTHETIC_PID EVIDENCE_PID RESOLVER_PID PCS_PID CPT_RETRIEVAL_PID CPT_PIPELINE_PID FRONTEND_PID; do
    local pid="${!label:-}"
    if is_running "$pid"; then
      echo "$label -> RUNNING (PID: $pid)"
    else
      echo "$label -> NOT RUNNING"
    fi
  done
}

start_all() {
  if [[ -f "$PID_FILE" ]]; then
    # shellcheck disable=SC1090
    source "$PID_FILE"
    if is_running "${SYNTHETIC_PID:-}" || is_running "${CPT_SYNTHETIC_PID:-}" || is_running "${EVIDENCE_PID:-}" || is_running "${RESOLVER_PID:-}" || is_running "${PCS_PID:-}" || is_running "${CPT_RETRIEVAL_PID:-}" || is_running "${CPT_PIPELINE_PID:-}" || is_running "${FRONTEND_PID:-}"; then
      echo "Some services appear to be running already."
      echo "Use: ./start_services.sh stop"
      exit 1
    fi
  fi

  activate_backend_venv
  ensure_frontend_dependencies

  SYNTHETIC_PID="$(start_one "synthetic_api" "$ROOT_DIR/E&M_backend/E&M_Synthetic_data_generation" "python main.py")"
  CPT_SYNTHETIC_PID="$(start_one "cpt_synthetic_api" "$ROOT_DIR/CPT_backend/CPT_Synthetic_data_generation" "python main.py")"
  EVIDENCE_PID="$(start_one "evidence_api" "$ROOT_DIR/E&M_backend/E&M_evidence_predictions" "python api_server.py")"
  RESOLVER_PID="$(start_one "resolver_api" "$ROOT_DIR/E&M_backend/E&M" "python json_em_code_service.py")"
  PCS_PID="$(start_one "pcs_api" "$ROOT_DIR/PCS_backend" "python pcs_pipeline_api.py")"
  CPT_RETRIEVAL_PID="$(start_one "cpt_retrieval_api" "$ROOT_DIR/CPT_backend/CPT_text_retrieval/text_retrieval" "env TOKENIZERS_PARALLELISM=false OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 \"$VENV_DIR/bin/python\" -m uvicorn text_retrieval_api:app --host 127.0.0.1 --port 8083 --workers 1 --log-level debug")"
  CPT_PIPELINE_PID="$(start_one "cpt_pipeline_api" "$ROOT_DIR/CPT_backend/CPT_pipeline" "python cpt_pipeline_api.py")"
  FRONTEND_PID="$(start_one "frontend_app" "$ROOT_DIR/frontend" "npm run dev")"

  cat >"$PID_FILE" <<EOF
SYNTHETIC_PID=$SYNTHETIC_PID
CPT_SYNTHETIC_PID=$CPT_SYNTHETIC_PID
EVIDENCE_PID=$EVIDENCE_PID
RESOLVER_PID=$RESOLVER_PID
PCS_PID=$PCS_PID
CPT_RETRIEVAL_PID=$CPT_RETRIEVAL_PID
CPT_PIPELINE_PID=$CPT_PIPELINE_PID
FRONTEND_PID=$FRONTEND_PID
EOF

  cat <<EOF
Services started.

Synthetic API     (E&M): http://localhost:8082  (log: $LOG_DIR/synthetic_api.log)
Synthetic API     (CPT): http://localhost:8086  (log: $LOG_DIR/cpt_synthetic_api.log)
Evidence API : http://localhost:8000  (log: $LOG_DIR/evidence_api.log)
Resolver API : http://localhost:8081  (log: $LOG_DIR/resolver_api.log)
PCS API      : http://localhost:8085  (log: $LOG_DIR/pcs_api.log)
CPT Retrieval: http://localhost:8083  (log: $LOG_DIR/cpt_retrieval_api.log)
CPT Pipeline : http://localhost:8084  (log: $LOG_DIR/cpt_pipeline_api.log)
Frontend     : http://localhost:5173  (log: $LOG_DIR/frontend_app.log)

PIDs saved in: $PID_FILE
To stop all:  ./start_services.sh stop
To check:     ./start_services.sh status
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
    start_all
    ;;
  status)
    status_all
    ;;
  *)
    echo "Usage: ./start_services.sh [start|stop|restart|status]"
    exit 1
    ;;
esac
