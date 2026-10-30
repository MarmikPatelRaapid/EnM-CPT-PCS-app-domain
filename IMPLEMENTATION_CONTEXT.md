# Medical Coding Assistant - Implementation Context

## Scope of work completed

This project now includes a working React single-page application in `frontend` integrated with real backend services in `E&M_backend` for:

- synthetic clinical document generation,
- E&M evidence generation,
- E&M code resolution from evidence output.

No mocked APIs are used.

---

## Backend API contracts implemented in frontend

### 1) Synthetic document generation

- **Service:** `E&M_backend/E&M_Synthetic_data_generation/main.py`
- **Endpoint:** `POST /generate`
- **Default port:** `8082`
- **Request body used by UI:**
  - `category: string` (backend currently expects one category string)
  - `cpt_codes: string[]`
  - `expected_outout_documents: number` (typo is intentional in backend schema)
- **Response used by UI:**
  - `documents: []` where each entry can include:
    - `generated_document`
    - `cpt_code` or `"cpt code"`
    - `rational`/`rationale`/`Justification`

### 2) E&M evidence generation

- **Service:** `E&M_backend/E&M_evidence_predictions/api_server.py`
- **Endpoint:** `POST /predict`
- **Default port:** `8000`
- **Request body used by UI:**
  - `documents: [{ generated_document, "cpt code", rational }]`
- **Response:** arbitrary evidence JSON produced by model, later sent directly to resolver endpoint.

### 3) E&M code resolution

- **Service:** `E&M_backend/E&M/json_em_code_service.py`
- **Default port:** `8081`
- Existing endpoint:
  - `POST /resolve` with `{ json_path }` (path-based only)
- **New endpoint added:**
  - `POST /resolve-predict`
  - Accepts raw `/predict` response JSON (object or list / `documents`-wrapped payload)
  - Normalizes payload then calls existing `resolve_codes_from_payload(...)`

---

## Backend changes made

### A) Added direct resolver endpoint for predict output

Updated `E&M_backend/E&M/json_em_code_service.py`:

- Added `normalize_predict_output_payload(payload)` to support:
  - evidence object directly,
  - `{"documents":[{...}]}` wrapped output,
  - list of objects.
- Added endpoint:
  - `@app.post("/resolve-predict")`
  - resolves codes without requiring file paths.

### B) Enabled CORS for frontend calls from Vite dev server

Added CORS middleware allowing:

- `http://localhost:5173`
- `http://127.0.0.1:5173`

Files updated:

- `E&M_backend/E&M_Synthetic_data_generation/main.py`
- `E&M_backend/E&M_evidence_predictions/api_server.py`
- `E&M_backend/E&M/json_em_code_service.py`

---

## Frontend architecture and behavior

Main implementation file: `frontend/src/App.jsx`

### API configuration

Single top-level config object:

```js
const API_BASE_URLS = {
  synthetic: "http://localhost:8082",
  evidence: "http://localhost:8000",
  em: "http://localhost:8081"
};
```

### UI layout

- Top panel: category, CPT input, number of docs, generate button.
- Left sidebar: generated document list.
- Main panel: document viewer + run coding + results + download actions.

### Category selection UX

Replaced native multi-select with clickable chip-based multi-select so users do not need Ctrl/Cmd multi-selection.

### Document viewer formatting

Document text is rendered as readable prose paragraphs (formatting only; no semantic rewrite).

### Results display policy

UI does **not** display raw JSON blocks.
Instead:

- shows Final E&M Codes prominently,
- shows MDM Criteria Summary (final level + child criteria categories + final rule),
- shows mapper filters with user-friendly labels.

### Download actions

Per selected document:

- `Download Evidence JSON`
- `Download E&M JSON`

Files are downloaded as:

- `em_evidence_document_N.json`
- `em_result_document_N.json`

### Per-document result state (critical fix)

Resolved confusion where result from one document appeared while another document was selected.

Current behavior:

- results cached per document ID,
- navigating back to a previously processed document restores its result,
- unprocessed documents show no result (placeholder),
- errors are also tracked per document.

---

## UI/UX updates completed

- Modernized styling in `frontend/src/styles.css`:
  - cleaner cards and spacing,
  - improved typography,
  - chip controls and code badges,
  - sidebar and panel polish.
- Loading and disabled states retained.
- Existing clinical dark/light visual theme preserved and refined.

---

## Issues resolved during implementation

1. **Single base URL mismatch**
   - Resolved by using separate service base URLs per backend.

2. **`/resolve` required `json_path` only**
   - Resolved by adding `/resolve-predict` endpoint to accept raw evidence JSON.

3. **Frontend CORS errors across different backend ports**
   - Resolved by enabling CORS in all required backend services.

4. **Vite `EMFILE: too many open files` on `npm run dev`**
   - Resolved in `frontend/vite.config.js` by enabling polling watcher:
     - `server.watch.usePolling = true`
     - `server.watch.interval = 1000`

5. **Final E&M code chips showed `N/A`**
   - Resolved by supporting both:
     - `codes: ["99211", "99213"]` (string array),
     - `codes: [{ code: "..." }]` (object array).

6. **MDM panel showed too many normalized input fields**
   - Simplified to requested fields only:
     - MDM Level,
     - Complexity Category,
     - Data To Review Category,
     - Risk Category,
     - Final MDM Rule.

7. **Result persistence confusion when switching documents**
   - Fixed with per-document result/error caching.

---

## Key files changed

### Backend

- `E&M_backend/E&M/json_em_code_service.py`
- `E&M_backend/E&M_evidence_predictions/api_server.py`
- `E&M_backend/E&M_Synthetic_data_generation/main.py`

### Frontend

- `frontend/src/App.jsx`
- `frontend/src/styles.css`
- `frontend/vite.config.js`

### New reference file

- `IMPLEMENTATION_CONTEXT.md` (this document)

---

## Run notes

Typical local ports used:

- synthetic: `8082`
- evidence: `8000`
- em resolver: `8081`
- frontend dev: `5173`

If watcher limits appear again in shell sessions, increase file limit temporarily:

```bash
ulimit -n 8192
```

