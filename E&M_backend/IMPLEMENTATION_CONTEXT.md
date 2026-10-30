# Backend Implementation Context

## Purpose

`E&M_backend` provides FastAPI services for:

- synthetic document generation,
- E&M evidence extraction,
- E&M code resolution.

The frontend integrates directly with these services.

## Active service endpoints

### Synthetic generation service

File: `E&M_Synthetic_data_generation/main.py`

- `POST /generate`
- Request body supports:
  - `category: list[str]` (also accepts legacy string and normalizes to list)
  - `cpt_codes: list[str]`
  - `expected_output_documents: int`
- Accepts/creates `X-Trace-Id` and persists outputs under:
  - `E&M_Synthetic_data_generation/output/ui_runs/<trace_id>/`
  - files: `synthetic_request.json`, `synthetic_response.json`

### Evidence prediction service

File: `E&M_evidence_predictions/api_server.py`

- `POST /predict`
- Input: `documents: [{ generated_document }]`
- Output: evidence JSON used by resolver.
- Accepts `X-Trace-Id` and `X-Document-Id` headers.
- Persists outputs under:
  - `E&M_evidence_predictions/output/ui_runs/<trace_id>/`
  - files:
    - `evidence_request_<document_id>_<timestamp>.json`
    - `evidence_response_<document_id>_<timestamp>.json`
- Evidence model receives only selected document text (`generated_document` from first request item).
- Evidence inference helper explicitly extracts `generated_document` if list items are objects, and
  falls back to direct string handling for compatibility.

### E&M resolver service

File: `E&M/json_em_code_service.py`

- `POST /resolve` (path-based: `{ json_path }`)
- `POST /resolve-predict` (added for frontend integration; accepts raw predict output)
- `POST /resolve-predict` accepts `X-Trace-Id` and `X-Document-Id`, and persists:
  - `E&M/output/ui_runs/<trace_id>/`
  - files:
    - `em_request_<document_id>_<timestamp>.json`
    - `em_response_<document_id>_<timestamp>.json`

## Key compatibility and normalization logic

### Category label normalization updates

In `E&M_Synthetic_data_generation/main.py`:

- legacy category values `Pathology` and `Laboratory` are normalized to:
  - `Pathology & Laboratory`
- legacy category value `Pathology and Laboratory` is normalized to:
  - `Pathology & Laboratory`
- legacy category value `Medicine` is normalized to:
  - `Medicines`
- duplicates are removed while preserving order.

This aligns backend behavior with updated prompt category definitions.

### Category schema update details

Synthetic service was changed from single category string to category list:

- previous: `category: str`
- current: `category: list[str]`

Backward compatibility remains enabled via request normalization in `GenerateRequest.normalize_category`.

## CORS

CORS is enabled for local frontend origins (`localhost:5173`, `127.0.0.1:5173`) in:

- `E&M_Synthetic_data_generation/main.py`
- `E&M_evidence_predictions/api_server.py`
- `E&M/json_em_code_service.py`
- CORS now exposes `X-Trace-Id` response header so frontend can propagate correlation IDs.

## Prompt alignment notes

Synthetic prompt in `E&M_Synthetic_data_generation/prompt.txt` defines category values including:

- `Anesthesia`
- `Surgery`
- `E&M`
- `Radiology`
- `Pathology & Laboratory`
- `Medicines`
- `Proprietary Laboratory Analyses (PLA)`

Backend normalization is intentionally aligned to this set.

## Operational ports (current defaults)

- Synthetic: `8082`
- Evidence: `8000`
- Resolver: `8081`

## Automation script

Project root includes `start_services.sh` to manage full-stack startup:

- `./start_services.sh start` -> starts all 3 backend APIs + frontend dev server
- `./start_services.sh stop` -> stops tracked processes
- `./start_services.sh status` -> shows running status from PID file
- logs are written to `.runtime/logs/`
- PIDs are stored in `.runtime/pids.env`

## Maintenance note

- **Process rule:** after every backend contract/normalization change, update this file with:
  - what changed,
  - which endpoint/file changed,
  - compatibility impact on frontend clients.

