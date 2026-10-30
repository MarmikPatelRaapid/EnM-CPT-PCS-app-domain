from typing import Any

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4
import uvicorn
from fastapi import FastAPI, Header, HTTPException, Response
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, model_validator

from synthetic_model_service import SyntheticModelService


app = FastAPI(title="E&M Synthetic Data Generator API")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-Trace-Id"],
)
service = SyntheticModelService()
OUTPUT_RUNS_DIR = Path(__file__).resolve().parent / "output" / "ui_runs"


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
    EMcode: str
    EMcodedescription: str = ""
    total_no_of_documents: int = Field(..., ge=1, description="Number of documents expected.")

    @model_validator(mode="before")
    @classmethod
    def normalize_input_shapes(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        normalized = dict(data)
        em_value = normalized.get("EMcode")
        if isinstance(em_value, list):
            normalized["EMcode"] = ", ".join(str(item) for item in em_value)
        return normalized


@app.post("/generate", response_model=dict[str, Any])
def generate_documents(
    payload: GenerateRequest,
    response: Response,
    x_trace_id: str | None = Header(default=None, alias="X-Trace-Id"),
) -> dict[str, Any]:
    try:
        trace_id = _ensure_trace_id(x_trace_id)
        request_snapshot = payload.model_dump()
        output = service.generate(
            em_code=payload.EMcode,
            em_code_description=payload.EMcodedescription,
            total_no_of_documents=payload.total_no_of_documents,
        )
        run_dir = OUTPUT_RUNS_DIR / trace_id
        _write_json(run_dir / "synthetic_request.json", request_snapshot)
        _write_json(run_dir / "synthetic_response.json", output)
        response.headers["X-Trace-Id"] = trace_id
        return output
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


if __name__ == "__main__":
    reload_enabled = os.getenv("RELOAD", "false").lower() in {"1", "true", "yes"}
    port = int(os.getenv("PORT", "8082"))
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=reload_enabled)
