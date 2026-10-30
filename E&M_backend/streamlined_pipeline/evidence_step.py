from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from typing import Callable

from .module_loader import load_module
from .paths import EVIDENCE_DIR
from .schemas import GeneratedDocument


class EvidencePredictionStep:
    def __init__(
        self,
        max_workers: int = 4,
        predictor_func: Callable[[list[dict]], dict] | None = None,
    ) -> None:
        self._max_workers = max_workers
        if predictor_func is not None:
            self._predictor_func = predictor_func
            return

        evidence_module = load_module(
            "evidence_model_inference_module",
            EVIDENCE_DIR / "model_inference.py",
        )
        self._predictor_func = evidence_module.generate_from_documents

    def _predict_one(self, document: GeneratedDocument) -> dict:
        # Evidence model should consume only the generated document text.
        doc_payload = [{"generated_document": document.generated_document}]
        return self._predictor_func(doc_payload)

    def run_parallel(self, documents: list[GeneratedDocument]) -> list[dict]:
        if not documents:
            return []

        worker_count = min(self._max_workers, len(documents))
        with ThreadPoolExecutor(max_workers=worker_count) as executor:
            return list(executor.map(self._predict_one, documents))
