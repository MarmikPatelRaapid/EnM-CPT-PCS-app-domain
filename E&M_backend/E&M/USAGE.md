# E&M Code Mapper - Usage Guide

This project maps input fields to E&M codes using the processed CSV file:

- `E&M Data - E&M Mapping 3 processed.csv`

The system is designed so you can mostly update the CSV over time with minimal code changes.

## 1) Setup and Installation

From the project folder:

```bash
cd "/home/raghav/workspace/E&M"
uv venv .venv
source .venv/bin/activate
uv pip install -r requirements.txt
```

## 2) Files and How to Use Them

### `em_code_mapper.py` (core module)

This is the main reusable Python module.

Use this in your own Python code:

```python
from em_code_mapper import EMCodeMapper

mapper = EMCodeMapper("E&M Data - E&M Mapping 3 processed.csv")
codes = mapper.find_codes(
    facility_type="Telemedicine Services",
    service_type="Online Digital E/M (Asynchronous)",
)
print(codes)
```

Supported filters (all optional, partial input supported):

- `facility_type`
- `service_type`
- `patient_type`
- `mdm_level`
- `time_value`
- `patient_age`
- `patient_age_unit` (`days|months|years`)

If you pass fewer fields (for example only `facility_type`), all matching possible codes are returned.

---

### `em_code_mapper_db.py` (database-table based module)

Use this when your mapping data is stored in a DB table (SQLite).

```python
from em_code_mapper_db import EMCodeMapperDB

mapper = EMCodeMapperDB(
    db_path="em_mapping.db",
    table_name="em_mapping",
)
codes = mapper.find_codes(
    facility_type="Telemedicine Services",
    service_type="Online Digital E/M (Asynchronous)",
)
print(codes)
```

This module keeps the same matching behavior as CSV mapper:

- supports partial filters
- supports `time_value` input (matched against table `Time Min`/`Time Max` ranges)
- supports age filters (`patient_age` + `patient_age_unit`) matched against `Age Min`/`Age Max` with unit normalization
- normalizes time-only MDM text variants
- includes detailed logging for debugging

If your table uses different column names, pass `DBMappingConfig(...)` with custom names.

---

### `query_em_codes.py` (CLI input via command line arguments)

Run with command line options:

```bash
python3 query_em_codes.py --facility-type "Telemedicine Services"
```

Example with more filters:

```bash
python3 query_em_codes.py \
  --facility-type "Telemedicine Services" \
  --service-type "Brief Synchronous Communication (Virtual Check-In)" \
  --patient-type "Established Patient" \
  --mdm-level "N/A — Time only" \
  --time-value 7
```

Optional arguments:

- `--csv-path` to point to a different CSV
- `--log-level` (`DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL`)

Output is printed as JSON:

```json
{
  "count": 1,
  "codes": ["98016"]
}
```

---

### `direct_find_codes.py` (edit variables directly in file)

Use this when you want to write inputs inside a Python file and run directly.

1. Open `direct_find_codes.py`
2. Edit these variables:
   - `FACILITY_TYPE`
   - `SERVICE_TYPE`
   - `PATIENT_TYPE`
   - `MDM_LEVEL`
   - `TIME_VALUE`
3. Run:

```bash
python3 direct_find_codes.py
```

It prints JSON output with matched codes.

---

### `run_sanity_checks.py` (test runner)

Runs all automated tests every time you make changes.

```bash
python3 run_sanity_checks.py
```

## 3) Test Files

- `tests/test_em_code_mapper.py`  
  Tests core mapping behavior (partial filters, time-only normalization, time-range handling).

- `tests/test_query_em_codes.py`  
  Tests CLI helper and JSON output.

- `tests/test_direct_find_codes.py`  
  Tests direct script helper function.

## 4) Recommended Workflow After Any Change

1. Update code and/or CSV.
2. Run:

```bash
python3 run_sanity_checks.py
```

3. If tests pass, run the script style you use:
   - CLI style: `query_em_codes.py`
   - Editable input file style: `direct_find_codes.py`

## 5) Notes

- MDM time-only variants like `N/A — Time only` and `N/A - Time only` are handled.
- `mdm_level = N/A` in mapping rows is treated as wildcard (row can match regardless of classifier MDM level).
- `time_value` is matched against `Time Min`/`Time Max` ranges from Mapping 3.
- `patient_age` + `patient_age_unit` are normalized to days before comparing against mapping age ranges.
- Logging is enabled in the scripts for easier debugging.
- If CSV column names change in a future file, update `MappingConfig` in `em_code_mapper.py`.

## 6) `mdm_classifier.py` Usage (MDM Classification from JSON)

`mdm_classifier.py` is a standalone classifier that derives:

- `complexity`
- `data_to_review`
- `risk`
- final `mdm_level`

from extracted clinical JSON payloads (for example `EandM_Sample.json`).

### Direct module usage

```python
import json
from mdm_classifier import classify_mdm_from_json

with open("EandM_Sample.json", "r", encoding="utf-8") as f:
    payload = json.load(f)

result = classify_mdm_from_json(payload)
print(result["complexity"])
print(result["data_to_review"])
print(result["risk"])
print(result["mdm_level"])
print(result["details"])  # evidence/reason summary
```

### Output format

Returned levels are lowercase:

- `mdm_level`: `straightforward|low|moderate|high`

Criterion categories in classifier output:

- `complexity`: `Straightforward|low|moderate|high`
- `data_to_review`: `minimal|limited|moderate|extensive`
- `risk`: `minimal|low|moderate|high`

If you need to pass classifier output into `EMCodeMapper.find_codes`, convert the final level to mapper display form:

- `straightforward -> Straightforward`
- `low -> Low`
- `moderate -> Moderate`
- `high -> High`

### Optional use through `direct_find_codes.py`

`direct_find_codes.py` supports optional classifier-driven MDM resolution.

1. Open `direct_find_codes.py`
2. Set:
   - `USE_MDM_CLASSIFIER = True`
   - `MDM_SOURCE_JSON_PATH` to your JSON file path (if different from default)
3. Run:

```bash
python3 direct_find_codes.py
```

When `USE_MDM_CLASSIFIER` is `False`, manual `MDM_LEVEL` behavior remains unchanged.

## 7) `json_em_code_service.py` Usage (FastAPI)

`json_em_code_service.py` runs a FastAPI service that resolves E&M codes from a JSON file path using Mapping 3.

### Start service

```bash
python3 json_em_code_service.py
```

Default bind:

- Host: `127.0.0.1`
- Port: `8081`

### Health check

```bash
curl "http://127.0.0.1:8081/health"
```

### Resolve using query parameter (GET)

```bash
curl "http://127.0.0.1:8081/resolve?json_path=/absolute/path/EandM_Sample.json"
```

### Resolve using request body (POST)

Use this when you do not want the file path visible in URL query string.

```bash
curl -X POST "http://127.0.0.1:8081/resolve" \
  -H "Content-Type: application/json" \
  -d '{"json_path":"/absolute/path/EandM_Sample.json"}'
```

### Response shape

The service returns:

- `classification`
- `mapper_filters`
- `codes`

Notes:

- `lookup_inputs` and `count` are intentionally omitted from the response.
- If Complexity cannot be derived, `classification.complexity` is returned as `""` and the reason is included under `classification.details.complexity`.
- `classification.details.final_mdm` includes both criteria categories (`inputs`) and normalized MDM inputs (`normalized_inputs`).

### Service input behavior notes

- For prolonged clinical staff service types:
  - `Prolonged Clinical Staff Service (Office/Outpatient, with MD supervision)`
  - `Prolonged Clinical Staff Service (Office/Outpatient) - Additional Time`
  - `time_value` is sourced from `staff_time_spent_with_patient.time_in_mins`.
- For other service types:
  - `time_value` is sourced from `physician_time_spent_with_patient.time_in_mins`.
- Age filter inputs are sourced from:
  - `patient_age.age`
  - `patient_age.age_unit`
- Accepted `patient_age.age_unit` values:
  - `days`, `months`, `years`
- Age is normalized internally to days before mapping comparison.

## 8) Matching Semantics Note (MDM + Time Together)

In both CSV and DB mappers:

- if only `mdm_level` is provided, normal MDM matching is used
- if only `time_value` is provided, normal range matching is used
- if both `mdm_level` and `time_value` are provided, either condition can satisfy row matching (`mdm_level` match OR `time_value` in range)
- `facility_type`, `service_type`, and `patient_type` filters remain strict when provided

### Final code selection when both MDM and Time are provided

When both `mdm_level` and `time_value` are supplied and multiple rows match after the OR logic:

- mapper returns a **single code only**
- selected code is the **highest numeric code** among matched candidates

Example:

- matched candidates: `98004`, `98007`
- returned code: `98007`
