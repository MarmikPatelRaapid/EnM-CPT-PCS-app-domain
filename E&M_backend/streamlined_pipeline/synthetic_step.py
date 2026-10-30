from __future__ import annotations

from typing import Any

from .module_loader import load_module
from .paths import SYNTHETIC_DIR
from .schemas import PipelineRequest, SyntheticOutput


class SyntheticGenerationStep:
    def __init__(self, service: Any | None = None) -> None:
        self.last_raw_output: dict[str, Any] = {}
        if service is not None:
            self._service = service
            return

        synthetic_module = load_module(
            "synthetic_model_service_module",
            SYNTHETIC_DIR / "synthetic_model_service.py",
        )
        self._service = synthetic_module.SyntheticModelService()

    def run(self, request: PipelineRequest) -> SyntheticOutput:
        raw_output = self._service.generate(
            em_code=request.em_code,
            em_code_description=request.em_code_description,
            total_no_of_documents=request.expected_documents,
        )
        self.last_raw_output = raw_output
        return SyntheticOutput.model_validate(raw_output)
