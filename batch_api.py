"""Queue-based batch processing API.

Accepts a set of text files plus a workflow (em/cpt/pcs), enqueues each file as
a task on an internal queue, and a pool of background worker threads (count
adjustable at runtime) processes them against the existing downstream
pipeline services. Jobs and their per-file results are persisted to
prompts.db, so job history survives a server restart and previous outputs
can always be re-downloaded. Clients poll a job's status for progress and
download a zip of the JSON outputs once done.

Run with: python batch_api.py  (serves on port 8088)
"""
from __future__ import annotations

import io
import json
import queue
import sqlite3
import threading
import time
import uuid
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

import requests
from fastapi import FastAPI, File, Form, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

ROOT = Path(__file__).resolve().parent
DB_PATH = ROOT / "prompts.db"

EVIDENCE_URL = "http://localhost:8000"
EM_URL = "http://localhost:8081"
CPT_URL = "http://localhost:8084"
PCS_URL = "http://localhost:8085"

WORKFLOW_ZIP_PREFIX = {"em": "EnM", "cpt": "CPT", "pcs": "PCS"}

DEFAULT_CONCURRENCY = 4
MIN_CONCURRENCY = 1
MAX_CONCURRENCY = 16

app = FastAPI(title="Batch Processing API")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173", "http://localhost", "http://127.0.0.1"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

TASK_QUEUE: "queue.Queue[tuple[str, int]]" = queue.Queue()
DB_LOCK = threading.Lock()


# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------


def _get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn


def _init_db() -> None:
    with DB_LOCK, _get_connection() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS batch_jobs (
                job_id TEXT PRIMARY KEY,
                workflow TEXT NOT NULL,
                status TEXT NOT NULL,
                total INTEGER NOT NULL,
                completed INTEGER NOT NULL DEFAULT 0,
                failed INTEGER NOT NULL DEFAULT 0,
                model_name TEXT,
                thinking_budget INTEGER,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS batch_job_files (
                job_id TEXT NOT NULL,
                file_index INTEGER NOT NULL,
                name TEXT NOT NULL,
                text TEXT NOT NULL,
                status TEXT NOT NULL,
                output TEXT,
                summary TEXT NOT NULL DEFAULT '',
                error TEXT NOT NULL DEFAULT '',
                PRIMARY KEY (job_id, file_index)
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS app_settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        conn.commit()


def _get_setting(key: str, default: str) -> str:
    with DB_LOCK, _get_connection() as conn:
        row = conn.execute("SELECT value FROM app_settings WHERE key = ?", (key,)).fetchone()
        return row["value"] if row else default


def _set_setting(key: str, value: str) -> None:
    with DB_LOCK, _get_connection() as conn:
        conn.execute(
            """
            INSERT INTO app_settings (key, value, updated_at)
            VALUES (?, ?, ?)
            ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = excluded.updated_at
            """,
            (key, value, datetime.now(timezone.utc).isoformat()),
        )
        conn.commit()


def _create_job_record(
    job_id: str,
    workflow: str,
    model_name: Optional[str],
    thinking_budget: Optional[int],
    file_entries: list[dict[str, str]],
) -> None:
    now = datetime.now(timezone.utc).isoformat()
    with DB_LOCK, _get_connection() as conn:
        conn.execute(
            """
            INSERT INTO batch_jobs
                (job_id, workflow, status, total, completed, failed, model_name, thinking_budget, created_at, updated_at)
            VALUES (?, ?, 'running', ?, 0, 0, ?, ?, ?, ?)
            """,
            (job_id, workflow, len(file_entries), model_name, thinking_budget, now, now),
        )
        conn.executemany(
            """
            INSERT INTO batch_job_files (job_id, file_index, name, text, status, output, summary, error)
            VALUES (?, ?, ?, ?, 'queued', NULL, '', '')
            """,
            [
                (job_id, index, entry["name"], entry["text"])
                for index, entry in enumerate(file_entries)
            ],
        )
        conn.commit()


def _get_file_task_inputs(job_id: str, file_index: int) -> Optional[dict[str, Any]]:
    with DB_LOCK, _get_connection() as conn:
        job_row = conn.execute(
            "SELECT workflow, model_name, thinking_budget FROM batch_jobs WHERE job_id = ?",
            (job_id,),
        ).fetchone()
        if job_row is None:
            return None
        file_row = conn.execute(
            "SELECT text FROM batch_job_files WHERE job_id = ? AND file_index = ?",
            (job_id, file_index),
        ).fetchone()
        if file_row is None:
            return None
        conn.execute(
            "UPDATE batch_job_files SET status = 'running' WHERE job_id = ? AND file_index = ?",
            (job_id, file_index),
        )
        conn.commit()
        return {
            "workflow": job_row["workflow"],
            "model_name": job_row["model_name"],
            "thinking_budget": job_row["thinking_budget"],
            "text": file_row["text"],
        }


def _record_file_result(
    job_id: str,
    file_index: int,
    *,
    output: Optional[dict[str, Any]],
    summary: str,
    error: str,
) -> None:
    status = "error" if error else "done"
    now = datetime.now(timezone.utc).isoformat()
    with DB_LOCK, _get_connection() as conn:
        conn.execute(
            """
            UPDATE batch_job_files
            SET status = ?, output = ?, summary = ?, error = ?
            WHERE job_id = ? AND file_index = ?
            """,
            (
                status,
                json.dumps(output) if output is not None else None,
                summary,
                error,
                job_id,
                file_index,
            ),
        )
        if error:
            conn.execute(
                "UPDATE batch_jobs SET completed = completed + 1, failed = failed + 1, updated_at = ? WHERE job_id = ?",
                (now, job_id),
            )
        else:
            conn.execute(
                "UPDATE batch_jobs SET completed = completed + 1, updated_at = ? WHERE job_id = ?",
                (now, job_id),
            )

        row = conn.execute(
            "SELECT total, completed, failed, status FROM batch_jobs WHERE job_id = ?", (job_id,)
        ).fetchone()
        if row and row["completed"] >= row["total"] and row["status"] not in (
            "completed",
            "completed_with_errors",
        ):
            new_status = "completed_with_errors" if row["failed"] > 0 else "completed"
            conn.execute(
                "UPDATE batch_jobs SET status = ?, updated_at = ? WHERE job_id = ?",
                (new_status, now, job_id),
            )
        conn.commit()


def _fetch_job(job_id: str) -> Optional[dict[str, Any]]:
    with DB_LOCK, _get_connection() as conn:
        job_row = conn.execute("SELECT * FROM batch_jobs WHERE job_id = ?", (job_id,)).fetchone()
        if job_row is None:
            return None
        file_rows = conn.execute(
            "SELECT name, status, summary, error FROM batch_job_files WHERE job_id = ? ORDER BY file_index",
            (job_id,),
        ).fetchall()
    return {
        "job_id": job_row["job_id"],
        "workflow": job_row["workflow"],
        "status": job_row["status"],
        "total": job_row["total"],
        "completed": job_row["completed"],
        "failed": job_row["failed"],
        "model_name": job_row["model_name"],
        "thinking_budget": job_row["thinking_budget"],
        "created_at": job_row["created_at"],
        "files": [
            {
                "name": row["name"],
                "status": row["status"],
                "summary": row["summary"],
                "error": row["error"],
            }
            for row in file_rows
        ],
    }


def _fetch_job_history(workflow: Optional[str], limit: int) -> list[dict[str, Any]]:
    with DB_LOCK, _get_connection() as conn:
        if workflow:
            rows = conn.execute(
                """
                SELECT job_id, workflow, status, total, completed, failed, model_name, thinking_budget, created_at
                FROM batch_jobs WHERE workflow = ? ORDER BY created_at DESC LIMIT ?
                """,
                (workflow, limit),
            ).fetchall()
        else:
            rows = conn.execute(
                """
                SELECT job_id, workflow, status, total, completed, failed, model_name, thinking_budget, created_at
                FROM batch_jobs ORDER BY created_at DESC LIMIT ?
                """,
                (limit,),
            ).fetchall()
    return [dict(row) for row in rows]


def _fetch_completed_outputs(job_id: str) -> tuple[Optional[str], list[dict[str, Any]]]:
    with DB_LOCK, _get_connection() as conn:
        job_row = conn.execute("SELECT workflow FROM batch_jobs WHERE job_id = ?", (job_id,)).fetchone()
        if job_row is None:
            return None, []
        file_rows = conn.execute(
            "SELECT name, output FROM batch_job_files WHERE job_id = ? AND status = 'done' ORDER BY file_index",
            (job_id,),
        ).fetchall()
    return job_row["workflow"], [
        {"name": row["name"], "output": json.loads(row["output"])} for row in file_rows
    ]


def _fetch_failed_files(job_id: str) -> tuple[Optional[dict[str, Any]], list[dict[str, str]]]:
    with DB_LOCK, _get_connection() as conn:
        job_row = conn.execute(
            "SELECT workflow, model_name, thinking_budget FROM batch_jobs WHERE job_id = ?",
            (job_id,),
        ).fetchone()
        if job_row is None:
            return None, []
        file_rows = conn.execute(
            "SELECT name, text FROM batch_job_files WHERE job_id = ? AND status = 'error' ORDER BY file_index",
            (job_id,),
        ).fetchall()
    return dict(job_row), [{"name": row["name"], "text": row["text"]} for row in file_rows]


def _sanitize_file_name(value: str) -> str:
    return "".join(ch if ch.isalnum() or ch in "._-" else "_" for ch in value)


def _base_name_without_ext(file_name: str) -> str:
    if "." in file_name:
        return file_name.rsplit(".", 1)[0]
    return file_name


# ---------------------------------------------------------------------------
# Downstream pipeline calls
# ---------------------------------------------------------------------------

RETRIABLE_ERROR_MARKERS = ("not valid json", "parse attempts failed", "model response")
TRANSIENT_CALL_RETRY_ATTEMPTS = 2
TRANSIENT_CALL_RETRY_DELAY_SECONDS = 2


def _is_retriable(status_code: int, detail: Any) -> bool:
    if status_code >= 500:
        return True
    text = str(detail or "").lower()
    return any(marker in text for marker in RETRIABLE_ERROR_MARKERS)


def _post_json(service_name: str, url: str, payload: dict[str, Any]) -> dict[str, Any]:
    last_error: Optional[RuntimeError] = None
    for attempt in range(TRANSIENT_CALL_RETRY_ATTEMPTS + 1):
        try:
            resp = requests.post(url, json=payload, timeout=180)
        except requests.exceptions.ConnectionError as exc:
            raise RuntimeError(
                f"Could not reach the {service_name} service at {url}. Is it running?"
            ) from exc
        except requests.exceptions.Timeout as exc:
            raise RuntimeError(f"The {service_name} service timed out.") from exc

        if resp.ok:
            return resp.json()

        detail = None
        try:
            body = resp.json()
            detail = body.get("detail") if isinstance(body, dict) else None
        except ValueError:
            detail = None
        if detail is None:
            detail = resp.text[:500] or resp.reason

        last_error = RuntimeError(
            f"{service_name} service returned HTTP {resp.status_code}: {detail}"
        )
        if attempt < TRANSIENT_CALL_RETRY_ATTEMPTS and _is_retriable(resp.status_code, detail):
            time.sleep(TRANSIENT_CALL_RETRY_DELAY_SECONDS * (attempt + 1))
            continue
        raise last_error

    raise last_error  # pragma: no cover - loop always returns or raises above


def _run_em_pipeline(
    text: str, model_name: Optional[str] = None, thinking_budget: Optional[int] = None
) -> dict[str, Any]:
    evidence_payload: dict[str, Any] = {"documents": [{"generated_document": text}]}
    if model_name is not None:
        evidence_payload["model_name"] = model_name
    if thinking_budget is not None:
        evidence_payload["thinking_budget"] = thinking_budget

    evidence_json = _post_json("evidence", f"{EVIDENCE_URL}/predict", evidence_payload)
    em_json = _post_json("E&M resolver", f"{EM_URL}/resolve-predict", evidence_json)
    return {"evidence_result": evidence_json, "em_result": em_json}


def _run_cpt_pipeline(
    text: str, model_name: Optional[str] = None, thinking_budget: Optional[int] = None
) -> dict[str, Any]:
    payload: dict[str, Any] = {"text": text}
    if model_name is not None:
        payload["model_name"] = model_name
    if thinking_budget is not None:
        payload["thinking_budget"] = thinking_budget

    cpt_json = _post_json("CPT pipeline", f"{CPT_URL}/audit-cpt-codes", payload)
    return {"cpt_result": cpt_json}


def _run_pcs_pipeline(
    text: str, model_name: Optional[str] = None, thinking_budget: Optional[int] = None
) -> dict[str, Any]:
    payload: dict[str, Any] = {"generated_text": text}
    if model_name is not None:
        payload["model_name"] = model_name
    if thinking_budget is not None:
        payload["thinking_budget"] = thinking_budget

    pcs_json = _post_json("PCS pipeline", f"{PCS_URL}/pcs/code-detection", payload)
    return {"pcs_result": pcs_json}


WORKFLOW_RUNNERS = {
    "em": _run_em_pipeline,
    "cpt": _run_cpt_pipeline,
    "pcs": _run_pcs_pipeline,
}


def _summarize_em(output: dict[str, Any]) -> str:
    codes = output.get("em_result", {}).get("codes") or []
    if not codes:
        return "No codes"
    values = []
    for item in codes:
        if isinstance(item, (str, int, float)):
            values.append(str(item))
        elif isinstance(item, dict):
            values.append(
                str(item.get("Code") or item.get("code") or item.get("CPT_Code") or item.get("cpt_code") or "N/A")
            )
    return ", ".join(values) if values else "No codes"


def _summarize_cpt(output: dict[str, Any]) -> str:
    audited = output.get("cpt_result", {}).get("audited_codes") or []
    if not audited:
        return "No codes"
    return ", ".join(str(item.get("final_cpt_code", "N/A")) for item in audited)


def _summarize_pcs(output: dict[str, Any]) -> str:
    pcs_result = output.get("pcs_result") or {}
    if isinstance(pcs_result.get("results"), list) and pcs_result["results"]:
        source = pcs_result["results"][0].get("pcs_code_detection_output", {}) or {}
    else:
        source = pcs_result.get("pcs_code_detection_output", pcs_result) or {}
    billable = source.get("billable") or []
    if not billable:
        return "No billable codes"
    return ", ".join(str(item.get("code", "N/A")) for item in billable)


SUMMARIZERS = {"em": _summarize_em, "cpt": _summarize_cpt, "pcs": _summarize_pcs}


# ---------------------------------------------------------------------------
# Dynamic worker pool
# ---------------------------------------------------------------------------


def _process_one(job_id: str, file_index: int) -> None:
    inputs = _get_file_task_inputs(job_id, file_index)
    if inputs is None:
        return

    runner = WORKFLOW_RUNNERS[inputs["workflow"]]
    try:
        output = runner(
            inputs["text"],
            model_name=inputs["model_name"],
            thinking_budget=inputs["thinking_budget"],
        )
        summary = SUMMARIZERS[inputs["workflow"]](output)
        _record_file_result(job_id, file_index, output=output, summary=summary, error="")
    except Exception as exc:  # noqa: BLE001
        _record_file_result(job_id, file_index, output=None, summary="", error=str(exc))


class _Worker:
    def __init__(self, worker_id: int):
        self.worker_id = worker_id
        self.stop_event = threading.Event()
        self.thread = threading.Thread(
            target=self._run, daemon=True, name=f"batch-worker-{worker_id}"
        )

    def _run(self) -> None:
        while not self.stop_event.is_set():
            try:
                job_id, file_index = TASK_QUEUE.get(timeout=0.5)
            except queue.Empty:
                continue
            try:
                _process_one(job_id, file_index)
            except Exception:  # noqa: BLE001 - never let the worker thread die
                pass
            finally:
                TASK_QUEUE.task_done()

    def start(self) -> None:
        self.thread.start()

    def stop(self) -> None:
        self.stop_event.set()


_workers: list[_Worker] = []
_workers_lock = threading.Lock()
_next_worker_id = 0


def _ensure_concurrency(target: int) -> int:
    global _next_worker_id
    target = max(MIN_CONCURRENCY, min(MAX_CONCURRENCY, target))
    with _workers_lock:
        current = len(_workers)
        if target > current:
            for _ in range(target - current):
                worker = _Worker(_next_worker_id)
                _next_worker_id += 1
                _workers.append(worker)
                worker.start()
        elif target < current:
            excess = _workers[target:]
            del _workers[target:]
            for worker in excess:
                worker.stop()
        return target


def _current_concurrency() -> int:
    with _workers_lock:
        return len(_workers)


_init_db()
_ensure_concurrency(int(_get_setting("batch_concurrency", str(DEFAULT_CONCURRENCY))))


# ---------------------------------------------------------------------------
# API
# ---------------------------------------------------------------------------


class ConcurrencyUpdateRequest(BaseModel):
    concurrency: int


@app.get("/batch/settings")
def get_batch_settings():
    return {
        "concurrency": _current_concurrency(),
        "min_concurrency": MIN_CONCURRENCY,
        "max_concurrency": MAX_CONCURRENCY,
    }


@app.put("/batch/settings")
def update_batch_settings(body: ConcurrencyUpdateRequest):
    if not (MIN_CONCURRENCY <= body.concurrency <= MAX_CONCURRENCY):
        raise HTTPException(
            status_code=400,
            detail=f"concurrency must be between {MIN_CONCURRENCY} and {MAX_CONCURRENCY}",
        )
    applied = _ensure_concurrency(body.concurrency)
    _set_setting("batch_concurrency", str(applied))
    return {"concurrency": applied}


@app.post("/batch/jobs")
async def create_batch_job(
    workflow: str = Form(...),
    files: list[UploadFile] = File(...),
    model_name: Optional[str] = Form(default=None),
    thinking_budget: Optional[int] = Form(default=None),
):
    if workflow not in WORKFLOW_RUNNERS:
        raise HTTPException(status_code=400, detail="workflow must be one of: em, cpt, pcs")
    if not files:
        raise HTTPException(status_code=400, detail="At least one file is required")

    job_id = uuid.uuid4().hex
    file_entries = []
    for upload in files:
        raw = await upload.read()
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError:
            text = raw.decode("utf-8", errors="replace")
        file_entries.append({"name": upload.filename or "unnamed.txt", "text": text})

    _create_job_record(
        job_id,
        workflow,
        (model_name or "").strip() or None,
        thinking_budget,
        file_entries,
    )

    for index in range(len(file_entries)):
        TASK_QUEUE.put((job_id, index))

    return {"job_id": job_id, "total": len(file_entries)}


@app.get("/batch/jobs")
def list_batch_jobs(
    workflow: Optional[str] = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
):
    return {"jobs": _fetch_job_history(workflow, limit)}


@app.post("/batch/jobs/{job_id}/retry")
def retry_batch_job(job_id: str):
    job_row, failed_entries = _fetch_failed_files(job_id)
    if job_row is None:
        raise HTTPException(status_code=404, detail="Job not found")
    if not failed_entries:
        raise HTTPException(status_code=400, detail="No failed files to retry")

    new_job_id = uuid.uuid4().hex
    _create_job_record(
        new_job_id,
        job_row["workflow"],
        job_row["model_name"],
        job_row["thinking_budget"],
        failed_entries,
    )
    for index in range(len(failed_entries)):
        TASK_QUEUE.put((new_job_id, index))

    return {"job_id": new_job_id, "total": len(failed_entries)}


@app.get("/batch/jobs/{job_id}")
def get_batch_job(job_id: str):
    job = _fetch_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


def _split_output_parts(workflow: str, output: dict[str, Any]) -> list[tuple[Optional[str], Any]]:
    """Return [(file_name_suffix, content), ...] for a completed output.

    E&M produces two distinct JSON artifacts (evidence extraction, then the
    resolved E&M codes) that the single-document view already downloads as
    separate files, so batch output mirrors that instead of merging them.
    """
    if workflow == "em":
        return [
            ("evidence", output.get("evidence_result")),
            ("em", output.get("em_result")),
        ]
    if workflow == "cpt":
        return [(None, output.get("cpt_result"))]
    if workflow == "pcs":
        return [(None, output.get("pcs_result"))]
    return [(None, output)]


@app.get("/batch/jobs/{job_id}/download")
def download_batch_job(job_id: str):
    workflow, completed_files = _fetch_completed_outputs(job_id)
    if workflow is None:
        raise HTTPException(status_code=404, detail="Job not found")
    if not completed_files:
        raise HTTPException(status_code=400, detail="No completed results to download yet")

    buffer = io.BytesIO()
    used_names: set[str] = set()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        for file_entry in completed_files:
            base_name = _sanitize_file_name(_base_name_without_ext(file_entry["name"]))

            for suffix, content in _split_output_parts(workflow, file_entry["output"]):
                json_name = f"{base_name}.json" if suffix is None else f"{base_name}_{suffix}.json"
                dedup_suffix = 2
                while json_name in used_names:
                    stem = base_name if suffix is None else f"{base_name}_{suffix}"
                    json_name = f"{stem}_{dedup_suffix}.json"
                    dedup_suffix += 1
                used_names.add(json_name)

                zf.writestr(json_name, json.dumps(content, indent=2, ensure_ascii=False))

    buffer.seek(0)
    prefix = WORKFLOW_ZIP_PREFIX.get(workflow, workflow.upper())
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    zip_name = f"{prefix}_{timestamp}.zip"

    return StreamingResponse(
        buffer,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{zip_name}"'},
    )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8088)
