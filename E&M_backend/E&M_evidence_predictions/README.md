# E&M Evidence Predictions API

## Setup with uv

1. Install `uv` on your machine.
2. From this project folder, run:

```bash
uv sync
```

This creates a local virtual environment and installs dependencies from `pyproject.toml`.

## Run API

### Option 1: Run as Python file

```bash
uv run python api_server.py
```

### Option 2: Run installed script

```bash
uv run em-evidence-api
```

The API runs at `http://localhost:8000`.

## Test Endpoint

```bash
curl -X POST "http://localhost:8000/predict" \
  -H "Content-Type: application/json" \
  -d '{
    "documents": [
      {
        "generated_document": "EHR data",
        "cpt code": "cpt_code",
        "rational": "string"
      }
    ]
  }'
```

## Configuration

Update `PROJECT_ID` in `model_inference.py` before running against Vertex AI.
