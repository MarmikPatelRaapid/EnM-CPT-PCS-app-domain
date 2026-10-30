# CPT Pipeline Implementation Context

This document captures the full implementation context of the CPT backend pipeline completed in this workspace.

## Scope Implemented

Implemented an end-to-end `service_1` pipeline that:

1. Accepts medical document text.
2. Calls Gemini model_1 for CPT extraction.
3. Builds retrieval query text per detected CPT object.
4. Calls retrieval `service_2` (`/retrieve`) in parallel for top-k CPT candidates.
5. Enriches model_1 output with `cpt_code_from_knowledge_base`.
6. Calls Gemini model_2 for CPT auditing.
7. Returns final audited CPT response with evidence arrays attached.

## Primary Files Added/Updated

### New service package

- `CPT_pipeline/cpt_pipeline_api.py`
- `CPT_pipeline/config.py`
- `CPT_pipeline/gemini_client.py`
- `CPT_pipeline/retrieval_client.py`
- `CPT_pipeline/pipeline.py`
- `CPT_pipeline/schemas.py`
- `CPT_pipeline/intermediate_store.py`
- `CPT_pipeline/__init__.py`

### Prompt/schema files

- `CPT_pipeline/prompts/model_1_system_prompt.txt`
- `CPT_pipeline/prompts/model_2_system_prompt.txt`
- `CPT_pipeline/prompts/model_1_response_schema.json`
- `CPT_pipeline/prompts/model_2_response_schema.json`

### Docs/config/tests

- `CPT_pipeline/README.md`
- `.env`
- `requirements.txt`
- `tests/test_cpt_pipeline.py`

## API Endpoints

### service_1 (pipeline)

- `POST /audit-cpt-codes`
- Request:

```json
{
  "text": "medical document text"
}
```

- Response (shape):

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

### service_2 (existing retrieval service)

- `POST /retrieve`
- Request:

```json
{
  "text": "retrieval query text",
  "k": 5
}
```

- Response:

```json
{
  "top_k_suggested_code": ["43253", "43235"],
  "top_k_suggested_score": [1.0, 0.943357]
}
```

## Key Design Decisions

### 1) Query text construction for retrieval

For each `cpt_codes_found` object, query text is built by concatenating non-empty values from:

- `norm_procedure_name`
- `norm_anatomy`
- `norm_approach`
- `norm_procedure_type`
- `norm_imaging_guidance`
- `norm_anesthesia_type`
- `norm_other`

Nested/list/dict values are flattened safely.

### 2) CPT reference mapping

Evidence mapping uses CPT reference value:

- model_1: `cpt_code`
- model_2: `original_cpt_code`

This reference is used to attach the correct evidence arrays into final response.

### 3) Vertex AI Gemini initialization

Gemini client uses Vertex AI config:

- `VERTEX_PROJECT_ID`
- `VERTEX_LOCATION`
- `VERTEX_SERVING_MODE=on_demand`

`GEMINI_API_KEY` is not used.

### 4) Clear model input context

Model input payload is sent as structured text sections (not generic field-only JSON labels), including:

- medical document text
- enriched extracted CPT JSON context for model_2

### 5) Retrieval timeout strategy

Implemented practical phase-based timeout controls:

- connect timeout (short)
- read timeout (configurable, can be `none`)
- write timeout
- pool timeout

This avoids premature failure for slow retrieval responses.

### 6) Automatic `.env` loading

`.env` is loaded programmatically in `config.py` at startup.
No separate `source .env` command is required.

### 7) Path resolution robustness

Prompt/schema paths are resolved relative to project root, so startup works from different current working directories.

### 8) Dual import mode support

Pipeline supports both:

- package mode (`python -m ...`)
- direct script mode (`python cpt_pipeline_api.py` from inside `CPT_pipeline`)

Implemented import fallbacks in related modules.

### 9) Intermediate output persistence

Per-request artifacts are stored with shared `request_id` to simplify manual validation across all stages.

## Intermediate Artifacts (Per Request)

Config:

- `CPT_SAVE_INTERMEDIATE_OUTPUTS=true|false`
- `CPT_INTERMEDIATE_OUTPUT_DIR=CPT_pipeline/request_outputs`

Output directory pattern:

- `CPT_pipeline/request_outputs/<request_id>/`

Saved files:

- `00_request_input.json`
- `01_model_1_raw_output.json`
- `02_model_1_validated_output.json`
- `03_retrieval_trace.json`
- `04_model_1_enriched_output.json`
- `05_model_2_raw_output.json`
- `06_model_2_validated_output.json`
- `07_final_service_1_response.json`
- `99_error.json` (on failure)

`03_retrieval_trace.json` includes:

- `code_index`
- `cpt_code`
- `query_text`
- retrieval raw response
- transformed `cpt_code_from_knowledge_base`

This enables deterministic manual mapping across pipeline stages.

## Environment Variables

Current `.env` supports:

- `VERTEX_PROJECT_ID`
- `VERTEX_LOCATION`
- `VERTEX_SERVING_MODE`
- `CPT_MODEL_1_NAME`
- `CPT_MODEL_2_NAME`
- `CPT_RETRIEVAL_URL`
- `CPT_TOP_K`
- `CPT_RETRIEVAL_CONNECT_TIMEOUT_SECONDS`
- `CPT_RETRIEVAL_READ_TIMEOUT_SECONDS`
- `CPT_RETRIEVAL_WRITE_TIMEOUT_SECONDS`
- `CPT_RETRIEVAL_POOL_TIMEOUT_SECONDS`
- `CPT_RETRIEVAL_CONCURRENCY_LIMIT`
- `CPT_SAVE_INTERMEDIATE_OUTPUTS`
- `CPT_INTERMEDIATE_OUTPUT_DIR`
- optional prompt/schema overrides

## Run Commands

From repository root:

1) Start retrieval service (`service_2`) in terminal-1:

```bash
cd CPT_text_retrieval/text_retrieval
python text_retrieval_api.py
```

2) Start pipeline service (`service_1`) in terminal-2:

```bash
cd CPT_pipeline
python cpt_pipeline_api.py
```

3) Call API:

```bash
curl -s -X POST "http://localhost:8084/audit-cpt-codes" \
  -H "Content-Type: application/json" \
  -d '{"text":"<medical document text>"}'
```

## Tests Added

In `tests/test_cpt_pipeline.py`:

- retrieval text construction from normalized fields
- handling empty/null normalized fields
- retrieval response conversion to `cpt_code_from_knowledge_base`
- evidence attachment by CPT reference
- multi-CPT-in-single-request scenario

Recent test status:

- `python3 -m pytest tests/test_cpt_pipeline.py`
- `5 passed`

## Frequent Runtime Errors and Resolutions

### Prompt/schema file not found

Resolved by path normalization relative to project root in `config.py`.

### Gemini schema validation errors

Resolved by using valid JSON Schema documents in prompt schema files (not example JSON output).

### Direct script import failures

Resolved by adding import fallbacks in:

- `cpt_pipeline_api.py`
- `pipeline.py`
- `gemini_client.py`

### Slow retrieval timeouts

Resolved by phase-based timeout config and allowing `CPT_RETRIEVAL_READ_TIMEOUT_SECONDS=none`.

