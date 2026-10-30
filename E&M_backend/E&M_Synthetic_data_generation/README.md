# E&M Synthetic Data Generation API

## Setup with uv

1. Install `uv` on your device.
2. Copy this project folder to the target device.
3. From this folder, run:

```bash
uv sync
```

This creates a local virtual environment and installs all dependencies.

## Run API

```bash
uv run python main.py
```

Optional (enable auto-reload for development):

```bash
RELOAD=true PORT=8082 uv run python main.py
```

## API Endpoint

- `POST /generate`

Request body:

```json
{
  "category": "orthopedic",
  "cpt_codes": ["99213", "97110"],
  "expected_outout_documents": 2
}
```

You can also send `expected_output_documents` (correct spelling), which is supported too.

## Notes

- Update `PROJECT_ID` and `LOCATION` in `synthetic_model_service.py`.
- Keep `output_schema.json` in the project root.
- Optionally add `prompt.txt` in the project root to customize system instruction.
