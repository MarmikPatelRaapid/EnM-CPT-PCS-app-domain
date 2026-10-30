# Frontend Implementation Context

## Purpose

`frontend` contains a React SPA for synthetic document generation and E&M coding analysis workflows used by domain experts.

## Core flow

1. Generate synthetic documents from selected categories, CPT input, and number of documents.
2. Select a generated document from sidebar.
3. Run E&M coding for selected document.
4. Review structured result cards and download evidence/E&M JSON files.

## API wiring

Configured in `src/App.jsx`:

- Synthetic service: `http://localhost:8082` (`POST /generate`)
- Evidence service: `http://localhost:8000` (`POST /predict`)
- E&M resolver service: `http://localhost:8081` (`POST /resolve-predict`)
- Frontend propagates correlation headers on evidence/resolver calls:
  - `X-Trace-Id`
  - `X-Document-Id`
- Synthetic payload uses `expected_output_documents` (single canonical field, typo variant removed).
- `/predict` payload from UI sends only selected document text:
  - `documents: [{ generated_document }]`

## Important UI/behavior decisions

- Category input uses chip-based multi-select.
- Category list includes merged value:
  - `Pathology & Laboratory`
  - `Medicines`
  - `Proprietary Laboratory Analyses (PLA)`
- Number of documents input is digits-only (no spinner arrows).
- Results are stored per document:
  - switching documents shows that document's own cached result,
  - no stale result leakage across documents.
- `Run E&M Coding` is enabled only when selected document CPT is in allowed E&M code list.
- Allowed E&M CPT list moved to:
  - `src/constants/emCodes.js`
- Document sidebar shows a derived category pill for each document based on synthetic `cpt_code`.
- Document sidebar also shows a CPT code pill per document using synthetic response `cpt_code`.
- Category pill is rendered below the document title for better readability with long labels.
- Raw JSON is not rendered on screen; users download:
  - `em_evidence_document_N.json`
  - `em_result_document_N.json`
- Document sidebar includes `+ Add Document` to create custom documents.
- Custom documents open in an editable text area where users can paste free text.
- For custom documents, `Run E&M Coding` is enabled when pasted text is non-empty.
- Generated documents are also editable in the document viewer; edited text is what gets sent to `/predict` when running E&M coding.
- Generated documents default to structured prose preview; `Edit Document` toggle switches to textarea mode for edits.
- Generated documents still use CPT whitelist-based eligibility gating.
- Document preview now supports inline evidence highlighting after coding results are available.
- Evidence matching uses `reftxtbefore + text + reftxtafter` first, then falls back to `text`-only matching when needed.
- Highlighting is pipeline-aware and follows the last coding run for the selected document (`em`, `cpt`, or `pcs`) to avoid stale cross-workflow highlights.
- E&M highlights are sourced from `emResult.evidences` for: `facility`, `service`, `patient`, `physician_time_spent_with_patient`, `staff_time_spent_with_patient`, `complexity`, `data_to_review`, and `risk_of_morbidity`.
- E&M evidence hover cards show category, final E&M code(s), and show final MDM level when category is `complexity`, `data_to_review`, or `risk_of_morbidity`.
- CPT highlights are sourced from `audited_codes[*]` evidence objects: `procedure_evidences`, `anatomy_evidences`, `approach_evidences`, `procedure_type_evidences`, `imaging_guidance_evidences`, `anesthesia_type_evidences`, and `other_evidences`.
- CPT evidence hover cards show object name, `final_cpt_code`, and CPT description.
- PCS highlights are sourced from `pcs_code_detection_output.billable/non_billable[*].evidences` across `evidence_for_first_character` through `evidence_for_seventh_character`.
- PCS evidence hover cards show billable/non-billable category, main code, procedure name, and character label.
- Hover/focus tooltip styling for evidence highlights is implemented in `src/styles.css` using `.evidence-highlight*` and `.evidence-tooltip*` classes.
- MDM result panel intentionally excludes the `Final MDM Rule` field (only level and category breakdown shown).
- MDM summary values are display-formatted in title case for readability (for example `moderate` -> `Moderate`).
- MDM panel hierarchy is explicit: `Final MDM Level` is highlighted as the primary flag, with criteria categories shown as indented supporting rows.
- MDM criteria rows use the same left-aligned label/value spacing pattern as `E&M Relational Parameters` to keep panel consistency.
- `Final MDM Level` primary row also follows left-aligned label/value spacing (no far-right push) for full consistency.
- `E&M Relational Parameters` panel values are visually emphasized with bold value text.
- Synthetic response `X-Trace-Id` is captured and attached to generated documents to correlate
  synthetic/evidence/em artifacts across services.

### CPT-to-category mapping used by sidebar labels

Implemented in `src/App.jsx`:

- Anesthesia: `00100` to `01999`
- Surgery: `10021` to `69990`
- E&M: code exists in `ALLOWED_EM_CODES` from `src/constants/emCodes.js`
- Radiology: `70010` to `79999`
- Pathology & Laboratory:
  - numeric `80047` to `89398`
- Medicines: `90281` to `99607` and code **not** in `ALLOWED_EM_CODES`
- Proprietary Laboratory Analyses (PLA):
  - U-codes `0001U` to `0599U`
- fallback category: `Unmapped`

## Branding

- App name: `Raapid E&M Coding Analysis tool`
- App name: `Synthetic Clinical Documentation & Coding Simulator`
- Header logo: `raapid_logo.png`
- Tab icon/favicon: `tab_icon.png`

## Styling and UX

- Main styles: `src/styles.css`
- Clinical/navy theme with modernized cards, chips, and hover interactions.
- Category chip hover behavior customized for both selected and unselected states.
- Category helper text (`Click one or more categories to select.`) is shown beside the
  `Category` label as secondary emphasis (reduced weight/color) to keep primary attention on field names.
- Top input labels are aligned with a dedicated label row layout for cleaner visual consistency.
- Input field names are intentionally larger/bolder for stronger primary emphasis, and helper text is lighter.
- CPT Codes textarea alignment is normalized by using the same label-row container pattern as all top inputs.
- Label/helper styling is class-based (`.field-label`, `.field-hint`) so helper text does not inherit primary label size/color.
- CPT codes textarea defaults to a single-line height (`rows=1`, `min-height: 42px`) to align with other top-row input controls.
- Category pills are sized for control-level alignment with adjacent inputs (`category-chip-grid` min-height and pill min-height/padding).

## Dev notes

- Vite watcher is configured with polling in `vite.config.js` to avoid EMFILE issues in constrained environments.
- Use root automation script to start/stop full stack:
  - `../start_services.sh start`
  - `../start_services.sh stop`
  - `../start_services.sh status`
- Frontend setup/run instructions are documented in:
  - `README.md`
- **Process rule:** after every implemented UI/API behavior change, update this file with the new behavior and affected files.

