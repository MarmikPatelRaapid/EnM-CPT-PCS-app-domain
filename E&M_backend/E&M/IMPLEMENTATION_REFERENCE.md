# E&M Mapper Implementation Reference

This document is a long-term technical reference for future enhancements.
For day-to-day run commands, see `USAGE.md`.

## Purpose

The system resolves E&M `Code` values from mapping data using optional filters:

- `facility_type`
- `service_type`
- `patient_type`
- `mdm_level`
- `time_value` (visit time in minutes)

The same lookup behavior is implemented for both:

- CSV source (`em_code_mapper.py`)
- Database table source (`em_code_mapper_db.py`)

## Current Lookup Behavior

### 1) Partial filters are allowed

Any subset of fields can be supplied. Missing fields do not block a match.

### 2) Time logic is range-based

When `time_value` is provided, a row matches if:

- `row.Min <= time_value <= row.Max`
- If `row.Max` is empty/null, it is treated as open-ended upper range.
- If `row.Min` is empty/null, it is treated as open-ended lower range.

### 3) MDM normalization

MDM text is normalized so variants like:

- `N/A — Time only`
- `N/A - Time only`

resolve to the same canonical value.

### 4) Valid mapping filtering

If the validity column is present (`Is Valid Mapping?`), only truthy mappings are included.

## File Responsibilities

- `em_code_mapper.py`
  - Core CSV loader + in-memory matching.
  - Public class: `EMCodeMapper`
  - Config class: `MappingConfig`

- `em_code_mapper_db.py`
  - Core DB-table loader + in-memory matching.
  - Public class: `EMCodeMapperDB`
  - Config class: `DBMappingConfig`

- `query_em_codes.py`
  - CLI wrapper around CSV mapper.
  - Produces JSON response with `codes`.

- `direct_find_codes.py`
  - Editable script-style caller for quick local testing.

- `run_sanity_checks.py`
  - Unified test runner for all regression checks.

## Public API Surface (Stable)

The expected stable method is:

- `find_codes(...) -> list[str]`

Common arguments:

- `facility_type: Optional[str]`
- `service_type: Optional[str]`
- `patient_type: Optional[str]`
- `mdm_level: Optional[str]`
- `time_value: Optional[int|float|str]`

`time_value` is the only supported time input argument. Resource `Min`/`Max` values are used internally as range boundaries.

## Data Contract Expectations

### CSV source

Required logical columns (names can be remapped via `MappingConfig`):

- facility type
- service type
- patient type
- mdm level
- min time
- max time
- code

### DB source

Required logical columns are the same and can be remapped via `DBMappingConfig`.

For SQLite, table/column identifiers are quoted safely in the DB module.

## Logging and Debugging Contract

Logging is intentionally verbose around:

- source loading start/end
- filter criteria
- match counts
- row parse failures with traceback

When debugging production data mismatches, first compare:

1. normalized input values
2. normalized row values
3. range boundaries (`Min`, `Max`) for the target row

## Test Strategy Reference

Primary regression tests:

- `tests/test_em_code_mapper.py`
- `tests/test_em_code_mapper_db.py`
- `tests/test_query_em_codes.py`
- `tests/test_direct_find_codes.py`

Always run:

```bash
python3 run_sanity_checks.py
```

## Future Implementation Guidance

If future scaling is needed, prefer this order:

1. Keep single mapper instance alive (avoid repeated reloads).
2. Add in-memory indexes for frequent filters.
3. Add result caching for repeated input tuples.
4. Push filtering into SQL for DB mode at high volume.

Do not change matching semantics casually. Any semantic change should update:

- both CSV and DB mappers
- CLI/doc examples
- regression tests

## Change Checklist for Maintainers

Before shipping behavior changes:

1. Update both mappers (`em_code_mapper.py`, `em_code_mapper_db.py`).
2. Update wrappers (`query_em_codes.py`, `direct_find_codes.py`) if argument names changed.
3. Update docs (`USAGE.md` + this file).
4. Run `python3 run_sanity_checks.py`.

## MDM Classifier Feature Context

This section documents the newly added MDM classification feature and is additive only. Existing mapper behavior and matching semantics are unchanged.

### What was added

- `mdm_classifier.py`
  - New standalone classifier module (separate from `em_code_mapper.py` by design).
  - Public function: `classify_mdm_from_json(payload)`.
  - Returns:
    - `complexity`
    - `data_to_review`
    - `risk`
    - `mdm_level`
    - `details` (reasoning/evidence summary per criterion and final aggregation).

- `tests/test_mdm_classifier.py`
  - New unit-test suite covering complexity, data-to-review, risk, and final 2-of-3 MDM resolution.
  - Includes defaults, threshold behavior, cross-problem aggregation, normalization behavior, and required error handling.

- `direct_find_codes.py` (optional integration path)
  - Added `USE_MDM_CLASSIFIER` switch.
  - Added `MDM_SOURCE_JSON_PATH` (defaults to `EandM_Sample.json`).
  - When enabled:
    1. Loads JSON payload.
    2. Calls `classify_mdm_from_json`.
    3. Converts classifier output to mapper display form:
      - `Straightforward -> Straightforward`
       - `low -> Low`
       - `moderate -> Moderate`
       - `high -> High`
    4. Passes resolved value into `EMCodeMapper.find_codes`.
  - When disabled, existing manual `MDM_LEVEL` fallback behavior is preserved.

### Classification design notes

- Complexity:
  - Uses evidence-backed disease/problem entries (`disease_evidence` non-empty list).
  - Selects highest matching category among `Straightforward/low/moderate/high`.
  - If no qualifying complexity evidence exists, returns:
    - `complexity = ""`
    - details status/reason under `details.complexity`

- Data To Review:
  - Aggregates supported fields across all disease/problem entries.
  - Supports expression-style threshold logic using a small internal evaluator:
    - Operators: `#N(name)`, `|`, `&`, and parentheses.
    - Example expression form:
      - `#2(LimitedCategory1)|(Assessment requiring an independent historian)`
  - Uses separate Category 1 counts by level:
    - Limited: `review_of_prior_external_note`, `review_of_test_result`, `order_of_test`
    - Moderate/Extensive: above 3 + `assessment_requiring_independent_historian`
  - Category outputs are:
    - `minimal|limited|moderate|extensive`
  - Defaults to `minimal` with explanation when no evidence exists.
  - If evidence exists but thresholds are not met, remains `minimal` with explicit explanation.

- Risk:
  - Uses normalized `risk_of_morbidity.type` values across entries.
  - Category outputs are:
    - `minimal|low|moderate|high`
  - Internal MDM-equivalent mapping:
    - `minimal -> straightforward`
    - `low -> low`
    - `moderate -> moderate`
    - `high -> high`
  - Chooses highest available risk across entries.
  - If risk evidence exists but type is missing/invalid, classifier does not infer a category; behavior is surfaced in `details`.
  - Defaults to `minimal` (MDM-equivalent `straightforward`) when no valid type is present.

- Final MDM level:
  - Applies the 2-of-3 rule across normalized equivalents of `complexity`, `data_to_review`, and `risk`.
  - Implemented as median over ordered levels:
    - `straightforward < low < moderate < high`
  - Response details include:
    - `final_mdm.inputs` (criteria-native categories)
    - `final_mdm.normalized_inputs` (MDM-equivalent levels)

### Validation status at implementation time

- Focused classifier tests:
  - `python3 -m unittest tests/test_mdm_classifier.py` passed.
- Full regression suite:
  - `python3 run_sanity_checks.py` passed.

## Recent Feature Updates (Current Session)

This section captures incremental behavior updates added after the initial MDM classifier rollout.

### 1) Complexity rules are TSV-driven

- `mdm_classifier.py` complexity classification now loads rules from:
  - `E&M Data - Disease mapping from json.tsv`
- This removed hardcoded complexity category checks from classifier logic.
- Rule matching uses evidence-backed disease/problem entries and TSV-defined JSON paths + required counts.

### 2) TSV schema standardized for DB compatibility

- TSV header names were updated to DB-friendly snake_case:
  - `actual_name`
  - `norm_disease_count`
  - `json_class`
  - `json_sub_class`
  - `json_sub_sub_class`
- Classifier TSV loader now reads these exact column names via constants.

### 3) Final MDM "2 of 3" behavior lock-in

- Final `mdm_level` remains median-based over ordered levels.
- Explicitly validated case:
  - `complexity=Straightforward`, `data_to_review=limited`, `risk=high`
  - final `mdm_level=low`

### 4) Time source override for prolonged clinical staff services

- For these service types:
  - `Prolonged Clinical Staff Service (Office/Outpatient, with MD supervision)`
  - `Prolonged Clinical Staff Service (Office/Outpatient) - Additional Time`
- Time input is read from:
  - `staff_time_spent_with_patient.time_in_mins`
- For all other services, time input remains:
  - `physician_time_spent_with_patient.time_in_mins`

### 5) New JSON-driven FastAPI service

- Added: `json_em_code_service.py`
- Running `python3 json_em_code_service.py` now starts FastAPI directly.
- Endpoints:
  - `GET /health`
  - `GET /resolve?json_path=...`
  - `POST /resolve` with body:
    - `{"json_path": "/absolute/path/to/file.json"}`
- Service flow:
  - reads payload from JSON path
  - extracts mapper inputs from JSON
  - classifies MDM from same JSON
  - resolves E&M codes through mapper
  - response fields are:
    - `classification`
    - `evidences`
    - `mapper_filters`
    - `codes`
  - `lookup_inputs` and `count` are intentionally omitted.

### 6) Mapper matching semantics update (CSV + DB)

- Files updated:
  - `em_code_mapper.py`
  - `em_code_mapper_db.py`
- New rule when both `mdm_level` and `time_value` are supplied:
  - row matches if `mdm_level` matches **OR** `time_value` is in range
- `facility_type`, `service_type`, and `patient_type` continue to match strictly when provided.

### 8) Final code winner rule when MDM+Time both supplied

- Applies to both:
  - `em_code_mapper.py`
  - `em_code_mapper_db.py`
- When **both** `mdm_level` and `time_value` are provided:
  1. row eligibility is computed using the OR rule (`mdm_level` match OR `time_value` in range)
  2. if multiple codes are matched, mapper returns **one final code only**
  3. returned code is the **highest numeric code** among matched candidates
- Example:
  - Inputs: `Telemedicine Services`, `Synchronous Audio-Video`, `Established Patient`, `mdm_level=High`, `time_value=10`
  - Candidates: `98004`, `98007`
  - Final returned code: `98007`

### 7) Test coverage added for all updates

- New/updated tests include:
  - `tests/test_mdm_classifier.py`
  - `tests/test_json_em_code_service.py`
  - `tests/test_em_code_mapper.py`
  - `tests/test_em_code_mapper_db.py`
- Full test suite status after updates:
  - `python3 run_sanity_checks.py` passed.

### 9) Evidence aggregation added to final JSON response

- Added module:
  - `evidence_extractor.py`
- Integration point:
  - `json_em_code_service.py` now calls `extract_evidences(payload)` and includes it in `/resolve` response under `evidences`.

- Final response shape (new field):
  - `evidences.facility`
  - `evidences.service`
  - `evidences.patient`
  - `evidences.physician_time_spent_with_patient`
  - `evidences.staff_time_spent_with_patient`
  - `evidences.complexity`
  - `evidences.data_to_review`
  - `evidences.risk_of_morbidity`

- Aggregation rules:
  - `facility`: unique values from `facility.evidences`
  - `service`: unique values from `service.evidences`
  - `patient`: unique values from `patient.evidences`
  - `physician_time_spent_with_patient`: unique values from `physician_time_spent_with_patient.evidences`
  - `staff_time_spent_with_patient`: unique values from `staff_time_spent_with_patient.evidences`
  - `complexity`: combine all `disease_evidence` entries across all MDM sections and de-duplicate
  - `data_to_review`: combine all evidences from every `data_to_review` subcategory across all MDM sections and de-duplicate
  - `risk_of_morbidity`: combine all `risk_of_morbidity.risk_evidences` across all MDM sections and de-duplicate

- MDM sections used for cross-section evidence collection:
  - `self_limited_minor_problem`
  - `chronic_illness`
  - `acute_illness`
  - `undiagnosed_problem`

- De-duplication behavior:
  - de-duplication is stable and preserves first-seen order.

### 10) Mapping 3 + Age-aware lookup support

- `json_em_code_service.py` default mapping source is now:
  - `E&M Data - E&M Mapping 3 processed.csv`
- Mapper now supports Mapping 3 time headers:
  - `Time Min`
  - `Time Max`
- Backward compatibility retained for legacy header aliases:
  - `Min`
  - `Max`
- Added new optional mapper inputs:
  - `patient_age`
  - `patient_age_unit` (`days|months|years`)
- Age matching semantics:
  - both request age and row age ranges are normalized to days before comparison.
  - age filter is applied only when both age and unit are present.

### 11) MDM `N/A` wildcard behavior

- In mapping rows, `mdm_level = N/A` is now treated as wildcard.
- Practical effect:
  - rows tagged `N/A` do not block match on MDM criteria.
  - time and other strict filters (`facility_type`, `service_type`, `patient_type`) continue to apply.
