"""FastAPI service for JSON-driven E&M code resolution."""

from __future__ import annotations

import csv
import json
import logging
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional
from uuid import uuid4

import uvicorn
from fastapi import FastAPI, File, Header, HTTPException, Query, Response, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from em_code_mapper import EMCodeMapper, configure_logging
from evidence_extractor import extract_evidences
from mdm_classifier import classify_mdm_from_json
from process_em_mapping_csv import process_csv

LOGGER = logging.getLogger(__name__)

SERVICE_DIR = Path(__file__).resolve().parent
DEFAULT_CSV_PATH = SERVICE_DIR / "E&M Data - E&M Mapping 3 processed.csv"
RAW_CSV_PATH = SERVICE_DIR / "E&M Data - E&M Mapping 3.csv"
MAPPING_BACKUPS_DIR = SERVICE_DIR / "mapping_backups"
# The live mapping CSV is gitignored (it's user-editable via the Code
# mapping upload feature, same reasoning as prompts.db), so a fresh
# checkout has no mapping file at all until someone uploads one. Bootstrap
# it from this tracked seed copy instead of starting with a broken resolver.
SEED_CSV_PATH = SERVICE_DIR / "seed_data" / "em_mapping_seed.csv"
if not DEFAULT_CSV_PATH.exists() and SEED_CSV_PATH.exists():
    shutil.copyfile(SEED_CSV_PATH, DEFAULT_CSV_PATH)
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8081
DEFAULT_LOG_LEVEL = logging.INFO
ALLOWED_ORIGINS = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "http://localhost",
    "http://127.0.0.1",
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
    text = str(value).strip()
    if not text or text.casefold() in {"not found", "not_found"}:
        # The extraction prompt explicitly emits this literal when time
        # wasn't documented — "unspecified", not an error. None already
        # means "don't filter on time" downstream in em_code_mapper.py.
        return None
    try:
        return int(float(text))
    except ValueError as exc:
        raise ValueError(f"Invalid numeric value '{value}' for '{section}.time_in_mins'.") from exc


def extract_lookup_inputs_from_payload(payload: Dict[str, Any]) -> Dict[str, Optional[Any]]:
    facility_type = payload.get("facility", {}).get("facility_type")
    service_type = payload.get("service", {}).get("service_type")
    patient_type = payload.get("patient", {}).get("patient_type")

    # Both times are passed through; the mapping sheet decides per row whether
    # physician time, staff time, or either applies (Phy/Staff Time Min/Max).
    physician_time = _read_time(payload, "physician_time_spent_with_patient")
    staff_time = _read_time(payload, "staff_time_spent_with_patient")

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
        "physician_time": physician_time,
        "staff_time": staff_time,
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


# ---------------------------------------------------------------------------
# Code-mapping CSV management (upload a raw sheet, expand it, replace the
# live mapping file the resolver reads on every request above).
# ---------------------------------------------------------------------------


def _count_csv_rows(path: Path) -> Optional[int]:
    if not path.exists():
        return None
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return sum(1 for _ in csv.DictReader(handle))


def _file_info(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {"exists": False, "rows": None, "updated_at": None}
    stat = path.stat()
    return {
        "exists": True,
        "rows": _count_csv_rows(path),
        "updated_at": datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat(),
    }


def _mapping_status() -> Dict[str, Any]:
    return {"raw": _file_info(RAW_CSV_PATH), "processed": _file_info(DEFAULT_CSV_PATH)}


def _list_mapping_backups() -> list[Dict[str, Any]]:
    if not MAPPING_BACKUPS_DIR.exists():
        return []
    backups = []
    for processed_backup in sorted(MAPPING_BACKUPS_DIR.glob("*_processed.csv"), reverse=True):
        backup_id = processed_backup.name[: -len("_processed.csv")]
        raw_backup = MAPPING_BACKUPS_DIR / f"{backup_id}_raw.csv"
        backups.append(
            {
                "id": backup_id,
                "created_at": datetime.fromtimestamp(
                    processed_backup.stat().st_mtime, tz=timezone.utc
                ).isoformat(),
                "rows": _count_csv_rows(processed_backup),
                "has_raw": raw_backup.exists(),
            }
        )
    return backups


def _backup_current_mapping() -> Optional[str]:
    """Snapshot whatever mapping files currently exist before replacing them,
    so a bad upload (one that still passed validation but turns out wrong
    some other way) can be rolled back without needing git."""
    if not DEFAULT_CSV_PATH.exists() and not RAW_CSV_PATH.exists():
        return None
    MAPPING_BACKUPS_DIR.mkdir(parents=True, exist_ok=True)
    backup_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    if DEFAULT_CSV_PATH.exists():
        shutil.copyfile(DEFAULT_CSV_PATH, MAPPING_BACKUPS_DIR / f"{backup_id}_processed.csv")
    if RAW_CSV_PATH.exists():
        shutil.copyfile(RAW_CSV_PATH, MAPPING_BACKUPS_DIR / f"{backup_id}_raw.csv")
    return backup_id


def _validate_processed_mapping(csv_path: Path) -> None:
    """Construct the same EMCodeMapper the live resolver uses on every
    request — if a freshly processed CSV can't load through it (missing
    columns, unparseable values), it would break every E&M code
    resolution, so reject the upload before it ever reaches that file."""
    EMCodeMapper(csv_path=csv_path)


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


@app.get("/em-mapping/status")
def em_mapping_status() -> Dict[str, Any]:
    return _mapping_status()


@app.get("/em-mapping/backups")
def em_mapping_backups() -> Dict[str, Any]:
    return {"backups": _list_mapping_backups()}


@app.post("/em-mapping/upload")
async def em_mapping_upload(file: UploadFile = File(...)) -> Dict[str, Any]:
    raw_bytes = await file.read()
    if not raw_bytes.strip():
        raise HTTPException(status_code=400, detail="Uploaded file is empty.")

    tmp_dir = SERVICE_DIR / "output" / "mapping_uploads_tmp"
    tmp_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    tmp_raw_path = tmp_dir / f"{stamp}_raw.csv"
    tmp_processed_path = tmp_dir / f"{stamp}_processed.csv"

    try:
        tmp_raw_path.write_bytes(raw_bytes)

        try:
            row_count = process_csv(tmp_raw_path, tmp_processed_path)
        except Exception as exc:
            raise HTTPException(
                status_code=400, detail=f"Could not expand the uploaded CSV: {exc}"
            ) from exc

        try:
            _validate_processed_mapping(tmp_processed_path)
        except Exception as exc:
            raise HTTPException(
                status_code=400,
                detail=f"Processed CSV failed validation, nothing was replaced: {exc}",
            ) from exc

        backup_id = _backup_current_mapping()
        shutil.copyfile(tmp_raw_path, RAW_CSV_PATH)
        shutil.copyfile(tmp_processed_path, DEFAULT_CSV_PATH)
    finally:
        tmp_raw_path.unlink(missing_ok=True)
        tmp_processed_path.unlink(missing_ok=True)

    return {"backup_id": backup_id, "rows": row_count, "status": _mapping_status()}


@app.post("/em-mapping/backups/{backup_id}/restore")
def em_mapping_restore(backup_id: str) -> Dict[str, Any]:
    safe_id = _safe_token(backup_id)
    processed_backup = MAPPING_BACKUPS_DIR / f"{safe_id}_processed.csv"
    raw_backup = MAPPING_BACKUPS_DIR / f"{safe_id}_raw.csv"
    if not processed_backup.exists():
        raise HTTPException(status_code=404, detail="Backup not found.")

    try:
        _validate_processed_mapping(processed_backup)
    except Exception as exc:
        raise HTTPException(
            status_code=400, detail=f"Backup failed validation, nothing was restored: {exc}"
        ) from exc

    _backup_current_mapping()
    shutil.copyfile(processed_backup, DEFAULT_CSV_PATH)
    if raw_backup.exists():
        shutil.copyfile(raw_backup, RAW_CSV_PATH)

    return {"restored_from": safe_id, "status": _mapping_status()}


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
