from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from .em_resolution_step import EMResolutionStep
from .evidence_step import EvidencePredictionStep
from .paths import (
    EVIDENCE_PIPELINE_OUTPUT_DIR,
    EM_PIPELINE_OUTPUT_DIR,
    ROOT_PIPELINE_OUTPUT_DIR,
    SYNTHETIC_PIPELINE_OUTPUT_DIR,
)
from .schemas import (
    PerDocumentResult,
    PipelineRequest,
    PipelineResponse,
)
from .synthetic_step import SyntheticGenerationStep


class PipelineOrchestrator:
    def __init__(
        self,
        max_evidence_workers: int = 4,
        synthetic_step: Any | None = None,
        evidence_step: Any | None = None,
        em_step: Any | None = None,
        persist_outputs: bool = True,
    ) -> None:
        self._synthetic_step = synthetic_step or SyntheticGenerationStep()
        self._evidence_step = evidence_step or EvidencePredictionStep(
            max_workers=max_evidence_workers
        )
        self._em_step = em_step or EMResolutionStep()
        self._persist_outputs = persist_outputs

    @staticmethod
    def _write_json(path: Path, data: Any) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")

    def run(self, request: PipelineRequest) -> PipelineResponse:
        run_id = f"{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}_{uuid4().hex[:8]}"

        synthetic_output = self._synthetic_step.run(request)
        documents = synthetic_output.documents
        synthetic_raw_output = getattr(
            self._synthetic_step,
            "last_raw_output",
            synthetic_output.model_dump(by_alias=True),
        )
        if self._persist_outputs:
            self._write_json(
                SYNTHETIC_PIPELINE_OUTPUT_DIR / run_id / "synthetic_output.json",
                synthetic_raw_output,
            )

        evidence_outputs = self._evidence_step.run_parallel(documents)
        if self._persist_outputs:
            for index, evidence_payload in enumerate(evidence_outputs, start=1):
                self._write_json(
                    EVIDENCE_PIPELINE_OUTPUT_DIR / run_id / f"evidence_output_{index}.json",
                    evidence_payload,
                )

        results: list[PerDocumentResult] = []
        for index, (document, evidence_payload) in enumerate(
            zip(documents, evidence_outputs),
            start=1,
        ):
            em_output = self._em_step.run(evidence_payload)
            if self._persist_outputs:
                self._write_json(
                    EM_PIPELINE_OUTPUT_DIR / run_id / f"em_output_{index}.json",
                    em_output,
                )
            results.append(
                PerDocumentResult(
                    generated_document=document.generated_document,
                    em_code=document.em_code,
                    em_code_description=document.em_code_description,
                    rational=document.rational,
                    evidence_prediction=evidence_payload,
                    em_resolution=em_output,
                )
            )

        final_response = PipelineResponse(
            requested_em_code=request.em_code,
            requested_em_codes=request.em_codes_list,
            requested_documents=request.expected_documents,
            generated_documents_count=len(documents),
            results=results,
        )
        if self._persist_outputs:
            self._write_json(
                ROOT_PIPELINE_OUTPUT_DIR / f"{run_id}_final_response.json",
                final_response.model_dump(),
            )

        return final_response
