"""Small standalone API for viewing/editing prompts and response schemas
stored in prompts.db.

Run with: python prompts_api.py  (serves on port 8087)
"""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

ROOT = Path(__file__).resolve().parent
DB_PATH = ROOT / "prompts.db"

# Human-friendly grouping of (service, key) -> label, surfaced to the UI.
# Keeps the frontend decoupled from internal service/key naming.
PROMPT_CATALOG = [
    {
        "group": "E&M",
        "service": "em_synthetic",
        "key": "system_prompt",
        "label": "Synthetic Document Generation",
    },
    {
        "group": "E&M",
        "service": "em_evidence",
        "key": "prompt",
        "label": "Evidence Extraction",
    },
    {
        "group": "CPT",
        "service": "cpt_synthetic",
        "key": "system_prompt",
        "label": "Synthetic Document Generation",
    },
    {
        "group": "CPT",
        "service": "cpt_pipeline",
        "key": "model_1_system_prompt",
        "label": "Pipeline - Model 1 (Candidate Extraction)",
    },
    {
        "group": "CPT",
        "service": "cpt_pipeline",
        "key": "model_2_system_prompt",
        "label": "Pipeline - Model 2 (Code Resolution)",
    },
    {
        "group": "PCS",
        "service": "pcs_synthetic",
        "key": "system_prompt",
        "label": "Synthetic Document Generation",
    },
    {
        "group": "PCS",
        "service": "pcs_detection",
        "key": "Agent 1 - ICD-10-PCS Code Suggestion Prompt.txt",
        "label": "Code Detection - Agent 1 (Code Suggestion)",
    },
    {
        "group": "PCS",
        "service": "pcs_detection",
        "key": "Agent 2 - ICD-10-PCS Dynamic Code Detection Prompt.txt",
        "label": "Code Detection - Agent 2 (Dynamic Detection)",
    },
]


SCHEMA_CATALOG = [
    {
        "group": "E&M",
        "service": "em_synthetic",
        "key": "output_schema",
        "label": "Synthetic Document Generation - Output Schema",
    },
    {
        "group": "CPT",
        "service": "cpt_synthetic",
        "key": "output_schema",
        "label": "Synthetic Document Generation - Output Schema",
    },
    {
        "group": "CPT",
        "service": "cpt_pipeline",
        "key": "model_1_response_schema",
        "label": "Pipeline - Model 1 Response Schema",
    },
    {
        "group": "CPT",
        "service": "cpt_pipeline",
        "key": "model_2_response_schema",
        "label": "Pipeline - Model 2 Response Schema",
    },
    {
        "group": "PCS",
        "service": "pcs_detection",
        "key": "agent_1_schema",
        "label": "Code Detection - Agent 1 Schema",
    },
    {
        "group": "PCS",
        "service": "pcs_detection",
        "key": "agent_2_schema",
        "label": "Code Detection - Agent 2 Schema",
    },
]


def _get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn


class PromptUpdateRequest(BaseModel):
    content: str


class SchemaUpdateRequest(BaseModel):
    content: str


app = FastAPI(title="Prompts Management API")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173", "http://localhost", "http://127.0.0.1"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/prompts")
def list_prompts():
    conn = _get_connection()
    try:
        rows = {
            (row["service"], row["key"]): row
            for row in conn.execute("SELECT service, key, content, updated_at FROM prompts")
        }
    finally:
        conn.close()

    result = []
    for entry in PROMPT_CATALOG:
        row = rows.get((entry["service"], entry["key"]))
        result.append(
            {
                **entry,
                "content": row["content"] if row else "",
                "updated_at": row["updated_at"] if row else None,
                "length": len(row["content"]) if row else 0,
            }
        )
    return {"prompts": result}


@app.get("/prompts/{service}/{key:path}")
def get_prompt(service: str, key: str):
    conn = _get_connection()
    try:
        row = conn.execute(
            "SELECT content, updated_at FROM prompts WHERE service = ? AND key = ?",
            (service, key),
        ).fetchone()
    finally:
        conn.close()

    if row is None:
        raise HTTPException(status_code=404, detail="Prompt not found")

    return {"service": service, "key": key, "content": row["content"], "updated_at": row["updated_at"]}


@app.put("/prompts/{service}/{key:path}")
def update_prompt(service: str, key: str, body: PromptUpdateRequest):
    if not body.content.strip():
        raise HTTPException(status_code=400, detail="Prompt content cannot be empty")

    conn = _get_connection()
    try:
        now = datetime.now(timezone.utc).isoformat()
        cursor = conn.execute(
            """
            UPDATE prompts
            SET content = ?, updated_at = ?
            WHERE service = ? AND key = ?
            """,
            (body.content, now, service, key),
        )
        if cursor.rowcount == 0:
            raise HTTPException(status_code=404, detail="Prompt not found")
        conn.commit()
    finally:
        conn.close()

    return {"service": service, "key": key, "updated_at": now}


@app.get("/schemas")
def list_schemas():
    conn = _get_connection()
    try:
        rows = {
            (row["service"], row["key"]): row
            for row in conn.execute("SELECT service, key, content, updated_at FROM schemas")
        }
    finally:
        conn.close()

    result = []
    for entry in SCHEMA_CATALOG:
        row = rows.get((entry["service"], entry["key"]))
        result.append(
            {
                **entry,
                "content": row["content"] if row else "",
                "updated_at": row["updated_at"] if row else None,
                "length": len(row["content"]) if row else 0,
            }
        )
    return {"schemas": result}


@app.get("/schemas/{service}/{key:path}")
def get_schema(service: str, key: str):
    conn = _get_connection()
    try:
        row = conn.execute(
            "SELECT content, updated_at FROM schemas WHERE service = ? AND key = ?",
            (service, key),
        ).fetchone()
    finally:
        conn.close()

    if row is None:
        raise HTTPException(status_code=404, detail="Schema not found")

    return {"service": service, "key": key, "content": row["content"], "updated_at": row["updated_at"]}


@app.put("/schemas/{service}/{key:path}")
def update_schema(service: str, key: str, body: SchemaUpdateRequest):
    if not body.content.strip():
        raise HTTPException(status_code=400, detail="Schema content cannot be empty")

    try:
        json.loads(body.content)
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail=f"Schema must be valid JSON: {exc}") from exc

    conn = _get_connection()
    try:
        now = datetime.now(timezone.utc).isoformat()
        cursor = conn.execute(
            """
            UPDATE schemas
            SET content = ?, updated_at = ?
            WHERE service = ? AND key = ?
            """,
            (body.content, now, service, key),
        )
        if cursor.rowcount == 0:
            raise HTTPException(status_code=404, detail="Schema not found")
        conn.commit()
    finally:
        conn.close()

    return {"service": service, "key": key, "updated_at": now}


@app.get("/dropdown-options")
def list_dropdown_options():
    conn = _get_connection()
    try:
        rows = conn.execute(
            "SELECT category, label, value, is_default FROM dropdown_options ORDER BY category, sort_order"
        ).fetchall()
    finally:
        conn.close()

    grouped: dict[str, list[dict]] = {}
    for row in rows:
        grouped.setdefault(row["category"], []).append(
            {
                "label": row["label"],
                "value": row["value"],
                "is_default": bool(row["is_default"]),
            }
        )

    return {
        "model_options": grouped.get("model", []),
        "thinking_budget_options": grouped.get("thinking_budget", []),
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8087)
