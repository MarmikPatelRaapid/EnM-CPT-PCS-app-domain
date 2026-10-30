import json
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from fastapi import FastAPI, Header, HTTPException, Response
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from model_inference import generate_from_documents


class DocumentInput(BaseModel):
    generated_document: str


class PredictionRequest(BaseModel):
    documents: list[DocumentInput]


OUTPUT_RUNS_DIR = Path(__file__).resolve().parent / "output" / "ui_runs"


def _safe_token(value: str | None) -> str:
    raw = str(value or "").strip()
    if not raw:
        return ""
    allowed = []
    for char in raw:
        if char.isalnum() or char in {"-", "_"}:
            allowed.append(char)
    return "".join(allowed)


def _ensure_trace_id(header_trace_id: str | None) -> str:
    normalized = _safe_token(header_trace_id)
    if normalized:
        return normalized
    return f"{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}_{uuid4().hex[:8]}"


def _ensure_document_id(header_document_id: str | None) -> str:
    normalized = _safe_token(header_document_id)
    if normalized:
        return normalized
    return "unknown_doc"


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


app = FastAPI(title="E&M Evidence Prediction API")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-Trace-Id"],
)


@app.post("/predict")
def predict(
    payload: PredictionRequest,
    response: Response,
    x_trace_id: str | None = Header(default=None, alias="X-Trace-Id"),
    x_document_id: str | None = Header(default=None, alias="X-Document-Id"),
) -> dict:
    try:
        trace_id = _ensure_trace_id(x_trace_id)
        document_id = _ensure_document_id(x_document_id)
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        run_dir = OUTPUT_RUNS_DIR / trace_id

        generated_documents = [doc.generated_document for doc in payload.documents]
        request_snapshot = {
            "documents": [
                {"generated_document": generated_document} for generated_document in generated_documents
            ]
        }
        output = generate_from_documents(generated_documents)
        _write_json(run_dir / f"evidence_request_{document_id}_{timestamp}.json", request_snapshot)
        _write_json(run_dir / f"evidence_response_{document_id}_{timestamp}.json", output)
        response.headers["X-Trace-Id"] = trace_id
        return output
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


def main() -> None:
    import uvicorn

    uvicorn.run("api_server:app", host="0.0.0.0", port=8000, reload=False)


if __name__ == "__main__":
    main()
