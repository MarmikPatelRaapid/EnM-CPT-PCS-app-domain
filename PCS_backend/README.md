# PCS Pipeline API

This project exposes two APIs for the PCS pipeline:

- `POST /pcs/synthetic-data` to generate synthetic PCS clinical text.
- `POST /pcs/code-detection` to run PCS code detection on generated text.

The API server entrypoint is `pcs_pipeline_api.py` and is directly runnable with Python.

## Prerequisites

- Python 3.10+ recommended
- [`uv`](https://docs.astral.sh/uv/) installed

## Installation (using uv)

Run from:

`/home/raghav/workspace/E&M_full_application/PCS_backend`

1. Create virtual environment:

```bash
uv venv
```

2. Activate virtual environment:

```bash
source .venv/bin/activate
```

3. Install all project dependencies from the root requirements file:

```bash
uv pip install -r requirements.txt
```

This installs API, synthetic generation, PCS detection core, optional provider SDKs, and test dependencies.

## Run the API server

Direct run (no uvicorn command needed):

```bash
python pcs_pipeline_api.py
```

Defaults:

- Host: `0.0.0.0`
- Port: `8085`
- Reload: disabled

Optional environment variables:

```bash
API_HOST=0.0.0.0 API_PORT=8085 API_RELOAD=true python pcs_pipeline_api.py
```

API docs:

- Swagger UI: `http://localhost:8085/docs`
- OpenAPI JSON: `http://localhost:8085/openapi.json`

## API Usage

### 1) Generate synthetic data

```bash
curl -X POST "http://localhost:8085/pcs/synthetic-data" \
  -H "Content-Type: application/json" \
  -d '{
    "categories": ["Medical and Surgical"],
    "icd10_pcs_code": "0DTJ4ZZ",
    "total_no_of_documents": 1
  }'
```

### 2A) Run PCS detection from raw generated text

```bash
curl -X POST "http://localhost:8085/pcs/code-detection" \
  -H "Content-Type: application/json" \
  -d '{
    "generated_text": "Patient underwent laparoscopic appendectomy without complications."
  }'
```

### 2B) Run PCS detection from synthetic response format

```bash
curl -X POST "http://localhost:8085/pcs/code-detection" \
  -H "Content-Type: application/json" \
  -d '{
    "documents": [
      {
        "generated_document": "Patient underwent laparoscopic appendectomy without complications.",
        "icd10_pcs_code": "0DTJ4ZZ",
        "icd10_pcs_code_description": "Resection of appendix, percutaneous endoscopic approach",
        "rational": "example"
      }
    ]
  }'
```

## Notes

- `PCS_synthetic_document_generation/.env` is read by the synthetic generator module.
- Ensure cloud/model credentials are available in your runtime environment before calling production model paths.
