import importlib.util
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field


BASE_DIR = Path(__file__).resolve().parent
DETECTION_DIR = BASE_DIR / "PCS_Code_Detection"

detect_dir_str = str(DETECTION_DIR)
if detect_dir_str not in sys.path:
    # Required so `PCS_Code_Detection/generated_text_pipeline.py` can resolve
    # its existing absolute imports like `import config` and `from src...`.
    sys.path.insert(0, detect_dir_str)


def _load_module(module_name: str, module_path: Path):
    spec = importlib.util.spec_from_file_location(module_name, module_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Could not load module `{module_name}` from `{module_path}`.")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_generated_text_pipeline = _load_module(
    "generated_text_pipeline",
    DETECTION_DIR / "generated_text_pipeline.py",
)
GeneratedTextPipelineError = _generated_text_pipeline.GeneratedTextPipelineError
run_generated_text_pipeline = _generated_text_pipeline.run_generated_text_pipeline

_synthetic_generator = _load_module(
    "pcs_synthetic_data_generator",
    BASE_DIR / "PCS_synthetic_document_generation" / "pcs_synthetic_data_generator.py",
)
InputValidationError = _synthetic_generator.InputValidationError
PCSGenerationError = _synthetic_generator.PCSGenerationError
generate_pcs_synthetic_data = _synthetic_generator.generate_pcs_synthetic_data


class SyntheticDataRequest(BaseModel):
    categories: List[str] = Field(..., min_length=1)
    icd10_pcs_code: str
    total_no_of_documents: int = Field(..., gt=0)


class PCSCodeDetectionRequest(BaseModel):
    generated_text: Optional[str] = None
    documents: Optional[List[Dict[str, Any]]] = None
    model_name: Optional[str] = None
    thinking_budget: Optional[int] = None


app = FastAPI(title="PCS Pipeline API")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173", "http://localhost", "http://127.0.0.1"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(RequestValidationError)
async def request_validation_exception_handler(_, exc: RequestValidationError) -> JSONResponse:
    return JSONResponse(
        status_code=400,
        content={"detail": exc.errors()},
    )


@app.post("/pcs/synthetic-data")
async def create_synthetic_data(request: SyntheticDataRequest) -> Dict[str, List[Dict[str, str]]]:
    payload = {
        "code_category": request.categories,
        "icd10_pcs_code": request.icd10_pcs_code,
        "total_no_of_documents": request.total_no_of_documents,
    }
    try:
        return generate_pcs_synthetic_data(payload)
    except InputValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except PCSGenerationError as exc:
        raise HTTPException(status_code=500, detail="Synthetic data generation failed.") from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail="Internal server error.") from exc


@app.post("/pcs/code-detection")
async def run_pcs_code_detection(request: PCSCodeDetectionRequest) -> Any:
    has_text = isinstance(request.generated_text, str) and bool(request.generated_text.strip())
    has_documents = isinstance(request.documents, list) and len(request.documents) > 0

    if has_text and has_documents:
        raise HTTPException(
            status_code=400,
            detail="Provide either `generated_text` or `documents`, not both.",
        )
    if not has_text and not has_documents:
        raise HTTPException(
            status_code=400,
            detail="Provide `generated_text` or a non-empty `documents` list.",
        )

    try:
        if has_text:
            return await run_generated_text_pipeline(
                request.generated_text or "",
                model_name=request.model_name,
                thinking_budget=request.thinking_budget,
            )

        results: List[Dict[str, Any]] = []
        for index, document in enumerate(request.documents or []):
            text = document.get("generated_document")
            if not isinstance(text, str) or not text.strip():
                raise HTTPException(
                    status_code=400,
                    detail=f"`documents[{index}].generated_document` must be a non-empty string.",
                )
            detection_result = await run_generated_text_pipeline(
                text,
                model_name=request.model_name,
                thinking_budget=request.thinking_budget,
            )
            results.append(
                {
                    **document,
                    "pcs_code_detection_output": detection_result,
                }
            )

        return {"results": results}
    except HTTPException:
        raise
    except GeneratedTextPipelineError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail="PCS code detection failed.") from exc


if __name__ == "__main__":
    import uvicorn

    host = os.getenv("API_HOST", "0.0.0.0")
    port = int(os.getenv("API_PORT", "8085"))
    reload_enabled = os.getenv("API_RELOAD", "false").lower() == "true"
    uvicorn.run("pcs_pipeline_api:app", host=host, port=port, reload=reload_enabled)
