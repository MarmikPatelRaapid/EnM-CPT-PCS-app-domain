"""FastAPI service for JSON-driven E&M code resolution."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional
from uuid import uuid4

import uvicorn
from fastapi import FastAPI, Header, HTTPException, Query, Response
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from em_code_mapper import EMCodeMapper, configure_logging
from evidence_extractor import extract_evidences
from mdm_classifier import classify_mdm_from_json

LOGGER = logging.getLogger(__name__)

DEFAULT_CSV_PATH = Path(__file__).resolve().parent / "E&M Data - E&M Mapping 3 processed.csv"
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8081
DEFAULT_LOG_LEVEL = logging.INFO
SPECIAL_STAFF_TIME_SERVICE_TYPES = {
    "Prolonged Clinical Staff Service (Office/Outpatient, with MD supervision)",
    "Prolonged Clinical Staff Service (Office/Outpatient) - Additional Time",
}
ALLOWED_ORIGINS = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
]
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


def _ensure_document_id(header_document_id: str | None) -> str:
    normalized = _safe_token(header_document_id)
    if normalized:
        return normalized
    return "unknown_doc"


def _write_json(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def _to_mapper_mdm_display(level: Optional[str]) -> Optional[str]:
    if level is None:
        return None
    if not str(level).strip():
        return None
    mapping = {
        "straightforward": "Straightforward",
        "low": "Low",
        "moderate": "Moderate",
        "high": "High",
    }
    normalized = level.strip().lower()
    if normalized not in mapping:
        raise ValueError(f"Unsupported classifier MDM level: {level}")
    return mapping[normalized]


def _read_time(payload: Dict[str, Any], section: str) -> Optional[int]:
    node = payload.get(section)
    if not isinstance(node, dict):
        return None
    value = node.get("time_in_mins")
    if value is None:
        return None
    return int(value)


def extract_lookup_inputs_from_payload(payload: Dict[str, Any]) -> Dict[str, Optional[Any]]:
    facility_type = payload.get("facility", {}).get("facility_type")
    service_type = payload.get("service", {}).get("service_type")
    patient_type = payload.get("patient", {}).get("patient_type")

    if service_type in SPECIAL_STAFF_TIME_SERVICE_TYPES:
        time_value = _read_time(payload, "staff_time_spent_with_patient")
    else:
        time_value = _read_time(payload, "physician_time_spent_with_patient")

    patient_age_node = payload.get("patient_age")
    patient_age = None
    patient_age_unit = None
    if isinstance(patient_age_node, dict):
        patient_age = patient_age_node.get("age")
        patient_age_unit = patient_age_node.get("age_unit")

    return {
        "facility_type": facility_type,
        "service_type": service_type,
        "patient_type": patient_type,
        "time_value": time_value,
        "patient_age": patient_age,
        "patient_age_unit": patient_age_unit,
    }


def resolve_codes_from_payload(payload: Dict[str, Any], csv_path: Path = DEFAULT_CSV_PATH) -> Dict[str, Any]:
    lookup_inputs = extract_lookup_inputs_from_payload(payload)
    classification = classify_mdm_from_json(payload)
    evidences = extract_evidences(payload)
    mapper_filters = {
        **lookup_inputs,
        "mdm_level": _to_mapper_mdm_display(classification["mdm_level"]),
    }
    mapper = EMCodeMapper(csv_path=csv_path)
    codes = mapper.find_codes(**mapper_filters)
    return {
        "classification": classification,
        "evidences": evidences,
        "mapper_filters": mapper_filters,
        "codes": codes,
    }


def normalize_predict_output_payload(payload: Any) -> Dict[str, Any]:
    if isinstance(payload, dict):
        documents = payload.get("documents")
        if isinstance(documents, list) and documents:
            first = documents[0]
            if isinstance(first, dict):
                return first
        return payload

    if isinstance(payload, list) and payload:
        first = payload[0]
        if isinstance(first, dict):
            return first

    raise ValueError(
        "Expected a JSON object or a non-empty list of JSON objects "
        "(including /predict output with a documents array)."
    )


def resolve_codes_from_json_path(json_path: Path, csv_path: Path = DEFAULT_CSV_PATH) -> Dict[str, Any]:
    payload = json.loads(json_path.read_text(encoding="utf-8"))
    return resolve_codes_from_payload(payload, csv_path=csv_path)


app = FastAPI(title="E&M JSON Code Service")
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-Trace-Id"],
)


class ResolveRequest(BaseModel):
    json_path: str


@app.get("/health")
def health() -> Dict[str, str]:
    return {"status": "ok"}


@app.get("/resolve")
def resolve(json_path: str = Query(..., description="Absolute or relative path to payload JSON file")) -> Dict[str, Any]:
    try:
        return resolve_codes_from_json_path(Path(json_path), csv_path=DEFAULT_CSV_PATH)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail=f"Invalid JSON: {exc}") from exc
    except Exception as exc:  # pragma: no cover
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/resolve")
def resolve_with_body(request: ResolveRequest) -> Dict[str, Any]:
    try:
        return resolve_codes_from_json_path(Path(request.json_path), csv_path=DEFAULT_CSV_PATH)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail=f"Invalid JSON: {exc}") from exc
    except Exception as exc:  # pragma: no cover
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/resolve-predict")
def resolve_from_predict_output(
    payload: Dict[str, Any] | list[Any],
    response: Response,
    x_trace_id: str | None = Header(default=None, alias="X-Trace-Id"),
    x_document_id: str | None = Header(default=None, alias="X-Document-Id"),
) -> Dict[str, Any]:
    try:
        trace_id = _ensure_trace_id(x_trace_id)
        document_id = _ensure_document_id(x_document_id)
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        run_dir = OUTPUT_RUNS_DIR / trace_id

        normalized_payload = normalize_predict_output_payload(payload)
        output = resolve_codes_from_payload(normalized_payload, csv_path=DEFAULT_CSV_PATH)
        _write_json(run_dir / f"em_request_{document_id}_{timestamp}.json", normalized_payload)
        _write_json(run_dir / f"em_response_{document_id}_{timestamp}.json", output)
        response.headers["X-Trace-Id"] = trace_id
        return output
    except Exception as exc:  # pragma: no cover
        raise HTTPException(status_code=400, detail=str(exc)) from exc


def main() -> int:
    configure_logging(DEFAULT_LOG_LEVEL)
    LOGGER.info(
        "Starting FastAPI service on http://%s:%s (use /resolve?json_path=/path/file.json)",
        DEFAULT_HOST,
        DEFAULT_PORT,
    )
    uvicorn.run("json_em_code_service:app", host=DEFAULT_HOST, port=DEFAULT_PORT, reload=False)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
