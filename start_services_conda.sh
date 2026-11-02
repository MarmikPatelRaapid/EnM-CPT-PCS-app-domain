#!/usr/bin/env bash
#
# Starts/stops/restarts every backend service plus the frontend using the
# project's conda environment (eandm_cpt_pcs, Python 3.11 — required because
# faiss-cpu has no wheels for newer Pythons). Unlike start_services.sh (which
# uses uv/.venv and predates the Prompts/Batch Processing services), this
# script covers the full current stack: prompts_api.py and batch_api.py too.
#
# Usage:
#   ./start_services_conda.sh [start|stop|restart|status]
#
# Prerequisites:
#   - conda env "eandm_cpt_pcs" already created with backend deps installed
#     (see requirements.txt). Create it once with:
#       conda create -y -n eandm_cpt_pcs python=3.11
#       conda activate eandm_cpt_pcs
#       pip install -r requirements.txt
#   - frontend/node_modules already installed (npm install), or this script
#     will run `npm install` automatically on first start.
#   - GOOGLE_APPLICATION_CREDENTIALS pointing at a valid service-account key
#     (set below, or export it before running this script to override).

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RUNTIME_DIR="$ROOT_DIR/.runtime"
LOG_DIR="$RUNTIME_DIR/logs"
PID_FILE="$RUNTIME_DIR/pids.env"

CONDA_ENV_NAME="${CONDA_ENV_NAME:-eandm_cpt_pcs}"
# Must point at your own Vertex AI service-account JSON key (not committed
# anywhere in this repo). Export it before running this script, e.g.:
#   export GOOGLE_APPLICATION_CREDENTIALS="/path/to/your-service-account.json"
GOOGLE_APPLICATION_CREDENTIALS="${GOOGLE_APPLICATION_CREDENTIALS:-}"

mkdir -p "$LOG_DIR"

is_running() {
  local pid="$1"
  [[ -n "${pid}" ]] && kill -0 "$pid" >/dev/null 2>&1
}

resolve_conda_python() {
  # `conda` is usually a shell function (from `conda init`), not a binary on
  # PATH, so it isn't reliably available to a plain script. Instead, look
  # directly for the env's interpreter under common conda install locations.
  local candidate_bases=(
    "${CONDA_BASE:-}"
    "$HOME/anaconda3"
    "$HOME/miniconda3"
    "$HOME/miniforge3"
    "/opt/anaconda3"
    "/opt/miniconda3"
  )
  local base env_python
  for base in "${candidate_bases[@]}"; do
    [[ -z "$base" ]] && continue
    env_python="$base/envs/$CONDA_ENV_NAME/bin/python"
    if [[ -x "$env_python" ]]; then
      echo "$env_python"
      return 0
    fi
  done

  echo "Could not find conda env '$CONDA_ENV_NAME' under any of: ${candidate_bases[*]}" >&2
  echo "If conda is installed elsewhere, set CONDA_BASE, e.g.:" >&2
  echo "  CONDA_BASE=/path/to/conda ./start_services_conda.sh start" >&2
  echo "Or create the env first:" >&2
  echo "  conda create -y -n $CONDA_ENV_NAME python=3.11" >&2
  echo "  conda activate $CONDA_ENV_NAME && pip install -r requirements.txt" >&2
  exit 1
}

ensure_frontend_dependencies() {
  local frontend_dir="$ROOT_DIR/frontend"
  if [[ ! -d "$frontend_dir/node_modules" ]]; then
    echo "Frontend dependencies not found. Running npm install..."
    (cd "$frontend_dir" && npm install)
  fi
}

start_one() {
  local name="$1"
  local workdir="$2"
  local cmd="$3"
  local logfile="$LOG_DIR/${name}.log"
  nohup bash -lc "export GOOGLE_APPLICATION_CREDENTIALS='$GOOGLE_APPLICATION_CREDENTIALS'; cd \"$workdir\" && exec $cmd" >"$logfile" 2>&1 &
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
    echo "GOOGLE_APPLICATION_CREDENTIALS is not set." >&2
    echo "Export it first, e.g.:" >&2
    echo "  export GOOGLE_APPLICATION_CREDENTIALS=\"/path/to/your-service-account.json\"" >&2
    exit 1
  fi

  if [[ "$(id -u)" -ne 0 ]]; then
    echo "Note: the frontend listens on port 80 by default, which usually needs root." >&2
    echo "Run this script with sudo, or use an unprivileged port instead, e.g.:" >&2
    echo "  VITE_PORT=5173 $0 start" >&2
  fi

  local PYBIN
  PYBIN="$(resolve_conda_python)"
  ensure_frontend_dependencies

  echo "Using Python: $PYBIN"
  echo "Using credentials: $GOOGLE_APPLICATION_CREDENTIALS"

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
