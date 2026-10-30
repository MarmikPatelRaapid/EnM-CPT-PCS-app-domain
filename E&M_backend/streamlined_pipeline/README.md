# Streamlined E&M Pipeline

This package orchestrates the full workflow across:

- `E&M_Synthetic_data_generation`
- `E&M_evidence_predictions`
- `E&M`

## Workflow

1. Generate synthetic documents from:
   - `category` (list input; first item used)
   - `cpt_codes` (string input; comma-separated values supported)
   - `expected_outout_documents` (or `expected_output_documents`)
2. Run evidence prediction **in parallel**, one generated document at a time.
   - Only `generated_document` text is sent to evidence model for each item.
3. Send each evidence output into `E&M/json_em_code_service.py` via `resolve_codes_from_payload`.
4. Return one final response JSON with all per-document outputs.

## Input Contract (current)

`POST /run-pipeline` expects:

```json
{
  "category": ["E&M"],
  "cpt_codes": "99202-99499",
  "expected_outout_documents": 4
}
```

Notes:

- `category` can be list-style; first value is used downstream.
- `cpt_codes` can be single string or comma-separated string.
- misspelled `expected_outout_documents` is intentionally supported.
- optional alias `expected_output_documents` is also supported.

## Output Persistence

For every API run, intermediate and final JSON artifacts are saved:

- Synthetic output:
  - `E&M_Synthetic_data_generation/output/pipeline_runs/<run_id>/synthetic_output.json`
- Evidence outputs:
  - `E&M_evidence_predictions/output/pipeline_runs/<run_id>/evidence_output_*.json`
- E&M resolver outputs:
  - `E&M/output/pipeline_runs/<run_id>/em_output_*.json`
- Final API response:
  - `pipeline_output/<run_id>_final_response.json`

## Run API

From workspace root:

```bash
python streamlined_pipeline_api.py
```

Optional:

```bash
PORT=8090 RELOAD=true python streamlined_pipeline_api.py
```

## Endpoint

- `POST /run-pipeline`

Example request:

```json
{
  "category": ["E&M"],
  "cpt_codes": "99202-99499",
  "expected_outout_documents": 2
}
```
