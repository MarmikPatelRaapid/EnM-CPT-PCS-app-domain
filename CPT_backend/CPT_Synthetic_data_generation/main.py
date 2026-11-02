from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

import uvicorn
from fastapi import FastAPI, Header, HTTPException, Response
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, model_validator

try:
    from CPT_Synthetic_data_generation.config import SyntheticSettings, load_settings
    from CPT_Synthetic_data_generation.synthetic_generator import (
        CPTSyntheticService,
        SyntheticGenerationError,
    )
except ImportError:
    # Support direct script execution from inside `CPT_Synthetic_data_generation/`:
    #   python main.py
    from config import SyntheticSettings, load_settings
    from synthetic_generator import CPTSyntheticService, SyntheticGenerationError


app = FastAPI(title="CPT Synthetic Data Generator API")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173", "http://localhost", "http://127.0.0.1"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-Trace-Id"],
)

OUTPUT_RUNS_DIR = Path(__file__).resolve().parent / "output" / "ui_runs"

_settings: SyntheticSettings | None = None
_service: CPTSyntheticService | None = None


@app.on_event("startup")
def startup_event() -> None:
    global _settings
    global _service
    _settings = load_settings()
    _service = CPTSyntheticService(_settings)


def _safe_token(value: str | None) -> str:
    raw = str(value or "").strip()
    if not raw:
        return ""
    allowed = []
    for char in raw:
        if char.isalnum() or char in {"-", "_"}:
            allowed.append(char)
    return "".join(allowed)


def _ensure_trace_id(header_trace_id: str | None) -> str:
    normalized = _safe_token(header_trace_id)
    if normalized:
        return normalized
    return f"{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}_{uuid4().hex[:8]}"


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


class GenerateRequest(BaseModel):
    code_category: str
    cptcode: str
    total_no_of_documents: int = Field(
        ..., ge=1, description="Number of documents expected."
    )
    model_name: str | None = None
    thinking_budget: int | None = None

    @model_validator(mode="before")
    @classmethod
    def normalize_input_shapes(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        normalized = dict(data)
        category_value = normalized.get("code_category")
        if isinstance(category_value, list):
            normalized["code_category"] = ", ".join(
                str(item) for item in category_value
            )
        cpt_value = normalized.get("cptcode")
        if isinstance(cpt_value, list):
            normalized["cptcode"] = ", ".join(str(item) for item in cpt_value)
        return normalized


@app.get("/")
def health_check() -> dict[str, str]:
    return {"status": "running", "service": "CPT Synthetic Data Generator API"}


@app.post("/generate", response_model=dict[str, Any])
def generate_documents(
    payload: GenerateRequest,
    response: Response,
    x_trace_id: str | None = Header(default=None, alias="X-Trace-Id"),
) -> dict[str, Any]:
    if _service is None:
        raise HTTPException(status_code=503, detail="Service is not initialized.")
    try:
        trace_id = _ensure_trace_id(x_trace_id)
        request_snapshot = payload.model_dump()
        output = _service.generate(
            code_category=payload.code_category,
            cpt_code=payload.cptcode,
            total_no_of_documents=payload.total_no_of_documents,
            model_name=payload.model_name,
            thinking_budget=payload.thinking_budget,
        )
        run_dir = OUTPUT_RUNS_DIR / trace_id
        _write_json(run_dir / "synthetic_request.json", request_snapshot)
        _write_json(run_dir / "synthetic_response.json", output)
        response.headers["X-Trace-Id"] = trace_id
        return output
    except SyntheticGenerationError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


if __name__ == "__main__":
    reload_enabled = os.getenv("RELOAD", "false").lower() in {"1", "true", "yes"}
    port = int(os.getenv("PORT", "8086"))
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=reload_enabled)
