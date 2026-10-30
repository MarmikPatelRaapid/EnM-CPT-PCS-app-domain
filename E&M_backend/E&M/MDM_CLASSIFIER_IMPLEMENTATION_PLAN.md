# MDM Level Classifier Code-Agent Prompt

You are implementing an MDM level classifier for the existing E&M code lookup project.

Your goal is to read the clinical extraction JSON structure in `EandM_Sample.json`, classify the three MDM criteria, and produce the final `mdm_level`.

The three criteria are:

- Complexity
- Data To Review
- Risk

The final `mdm_level` must be one of:

- `straightforward`
- `low`
- `moderate`
- `high`

Use `MDM_level_decision.png` as the source of truth for the MDM classification table.

## Project Context

Reference files:

- `EandM_Sample.json`: sample input JSON structure
- `MDM_level_decision.png`: rule table for MDM level decision
- `E&M Data - Disease mapping from json.tsv`: source mapping from Complexity rule names to JSON class/subclass paths
- `em_code_mapper.py`: existing E&M code lookup mapper
- `direct_find_codes.py`: editable local runner
- `IMPLEMENTATION_REFERENCE.md`: existing project guidance
- `run_sanity_checks.py`: existing regression runner

Environment rules:

- Check whether `.venv` exists.
- If `.venv` exists, activate it before running tests.
- Always use `python3`, never plain `python`.
- Prefer standard library only unless the project already uses another dependency.

## Important Boundary

Do not put classification logic inside `em_code_mapper.py`.

Keep the existing mapper responsible only for mapping final filters to E&M codes.

Create a separate classifier module for deriving `mdm_level` from the JSON.

## Required New Module

Create:

- `mdm_classifier.py`

The module should expose one main public function:

- `classify_mdm_from_json(payload)`

This function should return a dictionary containing:

- `complexity`: classified Complexity level
- `data_to_review`: classified Data To Review level
- `risk`: classified Risk level
- `mdm_level`: final MDM level
- `details`: explanation object containing reasons/evidence summaries for each criterion

Use lowercase values in the classifier output:

- `straightforward`
- `low`
- `moderate`
- `high`

If this value is later passed into the existing code mapper, convert it to the mapper's expected display format, such as `Straightforward`, `Low`, `Moderate`, or `High`.

## JSON Structure To Support

The sample JSON contains top-level visit metadata:

- `facility.facility_type`
- `service.service_type`
- `patient.patient_type`
- `time_spent_with_patient.time_in_mins`

The classifier should focus on disease/problem sections.

Complexity is based on these top-level JSON sections:

- `self_limited_minor_problem`
- `chronic_illness`
- `acute_illness`
- `undiagnosed_problem`

`chronic_illness` contains:

- `stable`
- `unstable`
- `life_threatening`

`acute_illness` contains:

- `stable`
- `uncomplicated`
- `with_systemic_symptoms`
- `complicated_injury`
- `life_threatening`

`acute_illness.uncomplicated` may contain nested dictionaries, for example `requiring_hospitalization`, so traversal must support nested lists and dictionaries.

Each disease/problem entry may contain:

- `norm_disease_name`
- `disease_evidence`
- `data_to_review`
- `risk_of_morbidity`

`data_to_review` may contain:

- `review_of_prior_external_note`
- `review_of_test_result`
- `order_of_test`
- `assessment_requiring_independent_historian`
- `independent_interpretation_of_test`
- `discussion_of_management_or_test_interpretation`

`risk_of_morbidity` may contain:

- `type`
- `risk_evidences`

## Evidence Presence Rules

Treat evidence as present when the relevant evidence field contains a non-empty list.

For disease/problem entries, use `disease_evidence` to decide whether that disease/problem is evidence-backed for Complexity.

For Data To Review, evidence may appear under any disease/problem's `data_to_review` object.

For Risk, use `risk_of_morbidity.type` across disease/problem entries. If risk evidence is present but the type is missing or invalid, do not silently invent a category; document the behavior in code comments or tests.

## Complexity Classification Rules

Complexity must be classified from evidence-backed disease/problem entries.

Use `E&M Data - Disease mapping from json.tsv` as the reference for mapping Complexity rule names to JSON locations. The TSV columns identify the rule text, required disease count, JSON class, JSON subclass, and optional nested JSON sub-subclass. When classifying Complexity, use the TSV path mapping together with the MDM decision table image.

High Complexity:

- Evidence in `chronic_illness.severe exacerbation`
- Evidence in `chronic_illness.life_threatening`
- Evidence in `acute_illness.life_threatening`

Moderate Complexity:

- Two or more evidence-backed `chronic_illness.stable` entries
- Any evidence-backed `chronic_illness.exacerbation` entry
- Any evidence-backed `undiagnosed_problem` entry
- Any evidence-backed `acute_illness.with_systemic_symptoms` entry
- Any evidence-backed `acute_illness.complicated_injury` entry

Low Complexity:

- Two or more evidence-backed `self_limited_minor_problem` entries
- One evidence-backed `chronic_illness.stable` entry
- Any evidence-backed `acute_illness.stable` entry
- Any evidence-backed `acute_illness.uncomplicated.outpatient_other` entry
- Any evidence-backed `acute_illness.uncomplicated.requiring_hospitalization` entry

Straightforward Complexity:

- One evidence-backed `self_limited_minor_problem` entry

If multiple Complexity categories are satisfied, choose the highest category.

Do not default Complexity.

If no Complexity evidence satisfies any category:

- return `complexity` as an empty string `""`
- include missing-status and reason in `details.complexity`

## Data To Review Classification Rules

Data To Review is aggregated across all disease/problem entries, irrespective of which disease contains the evidence.

For initial implementation, each supported Data To Review field should count once if evidence is present anywhere in the JSON.

Category 1: Tests and documents:

- `review_of_prior_external_note`
- `review_of_test_result`
- `order_of_test`

Category 2:

- For limited/low: `assessment_requiring_independent_historian`
- For moderate/high: `independent_interpretation_of_test`

Category 3:

- `discussion_of_management_or_test_interpretation`

Low / Limited Data To Review:

- Any combination of 2 fields from Category 1, or
- Assessment requiring an independent historian

Moderate Data To Review:

- Any combination of 3 fields from Category 1 plus independent historian, or
- Independent interpretation of test, or
- Discussion of management or test interpretation

High / Extensive Data To Review:

- At least 2 of the 3 moderate/high data categories are satisfied:
  - Category 1 threshold met
  - Independent interpretation of test present
  - Discussion of management or test interpretation present

Default rule:

- If no Data To Review evidence is present anywhere in the JSON, classify Data To Review as `minimal`.
- In details, also include the MDM-equivalent level (`straightforward`).

If Data To Review evidence is present but does not meet Limited, Moderate, or Extensive thresholds, classify it as `minimal` and explain that evidence was present but no threshold was met.

## Risk Classification Rules

Risk is based on `risk_of_morbidity.type` across all disease/problem entries.

Supported risk values:

- `minimal`
- `low`
- `moderate`
- `high`

Normalize whitespace and case before comparing risk values.

Map risk values as:

- `minimal` maps to MDM-equivalent level `straightforward`
- `low` maps to `low`
- `moderate` maps to `moderate`
- `high` maps to `high`

If multiple diseases/problems have different risk types, choose the highest risk category.

Default rule:

- If no Risk evidence/type is present anywhere in the JSON, classify Risk as `minimal`.
- In details, also include the MDM-equivalent level (`straightforward`).

## Final MDM Level Rule

Final MDM level is decided from the three already-classified criteria:

- Complexity
- Data To Review
- Risk

The final selected level must satisfy the "2 of 3 criteria" rule from the image.

In practical terms:

- If two or more criteria meet the same level, use that level.
- If one criterion is higher than the other two, lower the final result according to the other criteria.
- The final level should be equivalent to the median of the three ordered levels.

Use this ordering:

- `straightforward`
- `low`
- `moderate`
- `high`

Examples:

- Complexity `low`, Data To Review `moderate`, Risk `high` gives final `moderate`
- Complexity `low`, Data To Review `low`, Risk `high` gives final `low`
- Complexity `low`, Data To Review `straightforward`, Risk `straightforward` gives final `straightforward`

## Required Tests

Create:

- `tests/test_mdm_classifier.py`

Add tests for Complexity:

- High complexity beats lower categories when life-threatening evidence exists.
- Two stable chronic illnesses classify as `moderate`.
- One stable chronic illness classifies as `low`.
- One self-limited/minor problem classifies as `straightforward`.
- Two self-limited/minor problems classify as `low`.
- No Complexity evidence returns `complexity=""` with missing-status details.

Add tests for Data To Review:

- No Data To Review evidence defaults to `minimal` with a Minimal explanation.
- Two Category 1 fields classify as `low`.
- Three Category 1 fields classify as `moderate`.
- Category 1 threshold plus independent interpretation classifies as `high`.
- Evidence can be aggregated across different diseases/problems.
- Evidence present but below threshold classifies as `minimal`.

Add tests for Risk:

- No Risk evidence defaults to `minimal` with a Minimal explanation.
- Highest risk type wins across diseases/problems.
- `minimal` risk maps to MDM-equivalent `straightforward`.
- Risk type normalization handles mixed case and surrounding whitespace.

Add tests for final MDM:

- `low`, `moderate`, `high` gives final `moderate`.
- `low`, `low`, `high` gives final `low`.
- `low`, `minimal`, `minimal` gives final `straightforward`.

## Optional Integration With `direct_find_codes.py`

After classifier tests pass, optionally update `direct_find_codes.py` so it can compute `MDM_LEVEL` from `EandM_Sample.json`.

Keep the existing manual `MDM_LEVEL` value as a fallback.

Add a switch such as:

- `USE_MDM_CLASSIFIER`

When the switch is enabled:

1. Load `EandM_Sample.json`.
2. Call the new classifier.
3. Convert the returned final `mdm_level` to the mapper's expected display value.
4. Pass the resolved level into `EMCodeMapper.find_codes`.

When the switch is disabled:

1. Use the manually configured `MDM_LEVEL`.

Do not remove existing direct lookup behavior.

## Verification Commands

Run the focused classifier tests:

- `python3 -m unittest tests/test_mdm_classifier.py`

Run the full project regression suite:

- `python3 run_sanity_checks.py`

If `.venv` exists, activate it before running either command.

## Completion Criteria

The implementation is complete when:

- `mdm_classifier.py` exists.
- `tests/test_mdm_classifier.py` exists.
- Complexity is evidence-backed and returns blank (`""`) with details when missing.
- Data To Review defaults to `minimal` (MDM-equivalent `straightforward`) when no evidence exists.
- Risk defaults to `minimal` (MDM-equivalent `straightforward`) when no evidence/type exists.
- The final MDM level follows the 2-of-3 criteria rule.
- The classifier returns explainable details for each criterion.
- Focused classifier tests pass.
- Existing project sanity checks pass.

## Do Not Do

- Do not implement MDM classification inside `em_code_mapper.py`.
- Do not change existing mapper matching semantics.
- Do not silently default Complexity.
- Do not ignore nested disease/problem structures.
- Do not remove manual `MDM_LEVEL` fallback from `direct_find_codes.py`.
