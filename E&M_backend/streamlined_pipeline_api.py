from __future__ import annotations

import os
from functools import lru_cache

import uvicorn
from fastapi import FastAPI, HTTPException

from streamlined_pipeline import PipelineOrchestrator, PipelineRequest, PipelineResponse


app = FastAPI(title="E&M End-to-End Pipeline API")


@lru_cache(maxsize=1)
def get_orchestrator() -> PipelineOrchestrator:
    return PipelineOrchestrator()


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/run-pipeline", response_model=PipelineResponse)
def run_pipeline(payload: PipelineRequest) -> PipelineResponse:
    try:
        return get_orchestrator().run(payload)
    except Exception as exc:  # pragma: no cover
        raise HTTPException(status_code=500, detail=str(exc)) from exc


def main() -> None:
    reload_enabled = os.getenv("RELOAD", "false").lower() in {"1", "true", "yes"}
    port = int(os.getenv("PORT", "8090"))
    uvicorn.run("streamlined_pipeline_api:app", host="0.0.0.0", port=port, reload=reload_enabled)


if __name__ == "__main__":
    main()
