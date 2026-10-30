# CPT Pipeline Run Guide

This guide explains how to run the full CPT backend flow end-to-end:

1. Retrieval service (`service_2`) on port `8083`
2. CPT audit orchestration pipeline (`service_1`) on port `8084`

## 1) Prerequisites

- Python 3.10+ (project currently uses Python 3.13)
- Existing virtual environment is available at:
  - `/home/raghav/workspace/E&M_full_application/CPT_backend/.venv`

### Install uv

Install `uv` (one-time):

```bash
python3 -m pip install --user uv
```

### Install dependencies with uv (using existing virtual env)

From repo root:

```bash
source .venv/bin/activate
uv pip install -r requirements.txt
```

- Vertex AI auth (one of the below):
  - `gcloud auth application-default login`
  - or set `GOOGLE_APPLICATION_CREDENTIALS=/path/to/service-account.json`

## 2) Set Required Environment Variables

Preferred: update the `.env` file at repo root (`/home/raghav/workspace/E&M_full_application/CPT_backend/.env`).
It is loaded automatically by `CPT_pipeline/config.py` at startup, so no separate `source .env` command is required.

Equivalent environment variables:

```bash
export VERTEX_PROJECT_ID="<your-gcp-project-id>"
export VERTEX_LOCATION="us-central1"
export VERTEX_SERVING_MODE="on_demand"
```

Optional overrides:

```bash
export CPT_MODEL_1_NAME="gemini-2.5-flash"
export CPT_MODEL_2_NAME="gemini-2.5-flash"
export CPT_MODEL_1_TEMPERATURE="0.2"
export CPT_MODEL_1_TOP_P="0.95"
export CPT_MODEL_2_TEMPERATURE="0.2"
export CPT_MODEL_2_TOP_P="0.95"
export CPT_TOP_K="5"
export CPT_RETRIEVAL_URL="http://localhost:8083/retrieve"
export CPT_RETRIEVAL_CONNECT_TIMEOUT_SECONDS="10"
export CPT_RETRIEVAL_READ_TIMEOUT_SECONDS="none"
export CPT_RETRIEVAL_WRITE_TIMEOUT_SECONDS="30"
export CPT_RETRIEVAL_POOL_TIMEOUT_SECONDS="30"
export CPT_RETRIEVAL_CONCURRENCY_LIMIT="8"
export CPT_SAVE_INTERMEDIATE_OUTPUTS="true"
export CPT_INTERMEDIATE_OUTPUT_DIR="CPT_pipeline/request_outputs"
```

## 3) Start service_2 (Retrieval API)

Run from `CPT_text_retrieval/text_retrieval` in terminal-1:

```bash
cd CPT_text_retrieval/text_retrieval
python text_retrieval_api.py
```

Health check:

```bash
curl -s http://localhost:8083/
```

## 4) Start service_1 (CPT Pipeline API)

Run from `CPT_pipeline` in terminal-2:

```bash
cd CPT_pipeline
python cpt_pipeline_api.py
```

Health check:

```bash
curl -s http://localhost:8084/
```

## 5) Call Full End-to-End Pipeline

```bash
curl -s -X POST "http://localhost:8084/audit-cpt-codes" \
  -H "Content-Type: application/json" \
  -d '{
    "text": "Postoperative diagnosis: Cervical Esophageal Leiomyoma. Procedure performed: Excision of cervical esophageal lesion with primary repair via cervical approach."
  }'
```

Expected response shape:

```json
{
  "audited_codes": [
    {
      "original_cpt_code": "string",
      "final_cpt_code": "string",
      "final_cpt_code_description": "string",
      "final_cpt_code_justification": "string",
      "procedure_evidences": [],
      "anatomy_evidences": [],
      "approach_evidences": [],
      "procedure_type_evidences": [],
      "imaging_guidance_evidences": [],
      "anesthesia_type_evidences": [],
      "other_evidences": []
    }
  ]
}
```

## 6) Run Pipeline Tests

```bash
python3 -m pytest tests/test_cpt_pipeline.py
```

## 7) Common Failure Checks

- `VERTEX_PROJECT_ID is required`: set `VERTEX_PROJECT_ID`.
- `VERTEX_LOCATION is required`: set `VERTEX_LOCATION`.
- `VERTEX_SERVING_MODE must be 'on_demand'`: set `VERTEX_SERVING_MODE=on_demand`.
- Retrieval connection errors: verify `service_2` is running and `CPT_RETRIEVAL_URL` is correct.
- Retrieval latency errors:
  - keep `CPT_RETRIEVAL_CONNECT_TIMEOUT_SECONDS` short (for network issues),
  - set `CPT_RETRIEVAL_READ_TIMEOUT_SECONDS=none` for slow retrieval responses.
- `502` from pipeline: inspect service_1 logs for Gemini schema/response validation issues.

## 8) Intermediate Outputs Per Request

If `CPT_SAVE_INTERMEDIATE_OUTPUTS=true`, each API request writes artifacts under:

`CPT_INTERMEDIATE_OUTPUT_DIR/<request_id>/`

Example files for one request:

- `00_request_input.json`
- `01_model_1_raw_output.json`
- `02_model_1_validated_output.json`
- `03_retrieval_trace.json`
- `04_model_1_enriched_output.json`
- `05_model_2_raw_output.json`
- `06_model_2_validated_output.json`
- `07_final_service_1_response.json`
- `99_error.json` (only when a request fails)

Mapping tips for manual validation:

- Use the request folder name (`request_id`) to trace one API call end-to-end.
- In `03_retrieval_trace.json`, each entry includes:
  - `code_index`
  - `cpt_code`
  - `query_text`
  - raw retrieval response and transformed `cpt_code_from_knowledge_base`
- Use `code_index` and `cpt_code` to match model_1 objects, retrieval results, enriched payload, model_2 output, and final response.

