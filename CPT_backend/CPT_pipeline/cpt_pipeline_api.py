from __future__ import annotations

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

try:
    from CPT_pipeline.config import Settings, load_settings
    from CPT_pipeline.gemini_client import GeminiClient, GeminiClientError
    from CPT_pipeline.intermediate_store import IntermediateStore
    from CPT_pipeline.pipeline import CPTAuditPipeline, PipelineError
    from CPT_pipeline.retrieval_client import RetrievalClient
    from CPT_pipeline.schemas import Service1Request, Service1Response
except ImportError:
    # Support direct script execution from inside `CPT_pipeline/`:
    #   python cpt_pipeline_api.py
    from config import Settings, load_settings
    from gemini_client import GeminiClient, GeminiClientError
    from intermediate_store import IntermediateStore
    from pipeline import CPTAuditPipeline, PipelineError
    from retrieval_client import RetrievalClient
    from schemas import Service1Request, Service1Response

app = FastAPI(
    title="CPT Backend Pipeline API",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

_settings: Settings | None = None
_pipeline: CPTAuditPipeline | None = None


@app.on_event("startup")
def startup_event() -> None:
    global _settings
    global _pipeline

    _settings = load_settings()
    gemini_client = GeminiClient(_settings)
    retrieval_client = RetrievalClient(
        retrieval_url=_settings.retrieval_url,
        connect_timeout_seconds=_settings.retrieval_connect_timeout_seconds,
        read_timeout_seconds=_settings.retrieval_read_timeout_seconds,
        write_timeout_seconds=_settings.retrieval_write_timeout_seconds,
        pool_timeout_seconds=_settings.retrieval_pool_timeout_seconds,
    )
    intermediate_store = IntermediateStore(
        enabled=_settings.save_intermediate_outputs,
        output_dir=_settings.intermediate_output_dir,
    )
    _pipeline = CPTAuditPipeline(
        settings=_settings,
        gemini_client=gemini_client,
        retrieval_client=retrieval_client,
        intermediate_store=intermediate_store,
    )


@app.get("/")
def health_check() -> dict[str, str]:
    return {
        "status": "running",
        "service": "CPT Backend Pipeline API",
    }


@app.post("/audit-cpt-codes", response_model=Service1Response)
async def audit_cpt_codes(request: Service1Request) -> Service1Response:
    if _pipeline is None:
        raise HTTPException(status_code=503, detail="Pipeline is not initialized.")

    text = request.text.strip()
    if not text:
        raise HTTPException(status_code=400, detail="Field 'text' cannot be empty.")

    try:
        return await _pipeline.run(text)
    except (GeminiClientError, PipelineError) as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except Exception as exc:  # pragma: no cover
        raise HTTPException(status_code=500, detail=f"Unhandled error: {exc}") from exc


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        app,
        host="0.0.0.0",
        port=8084,
    )

