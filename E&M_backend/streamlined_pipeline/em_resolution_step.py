from __future__ import annotations

import sys
from typing import Callable

from .module_loader import load_module
from .paths import EM_DIR


class EMResolutionStep:
    def __init__(self, resolver_func: Callable[[dict], dict] | None = None) -> None:
        if resolver_func is not None:
            self._resolver_func = resolver_func
            return

        if str(EM_DIR) not in sys.path:
            sys.path.insert(0, str(EM_DIR))

        em_module = load_module(
            "json_em_code_service_module",
            EM_DIR / "json_em_code_service.py",
        )
        self._resolver_func = em_module.resolve_codes_from_payload

    @staticmethod
    def _normalize_evidence_payload(evidence_payload: object) -> dict:
        if isinstance(evidence_payload, dict):
            # Some model outputs wrap the actual payload in {"documents": [ ... ]}.
            documents = evidence_payload.get("documents")
            if isinstance(documents, list) and documents:
                first = documents[0]
                if isinstance(first, dict):
                    return first
            return evidence_payload

        if isinstance(evidence_payload, list) and evidence_payload:
            first = evidence_payload[0]
            if isinstance(first, dict):
                return first

        raise ValueError(
            "Evidence payload must be a JSON object or a non-empty list of JSON objects."
        )

    def run(self, evidence_payload: object) -> dict:
        normalized_payload = self._normalize_evidence_payload(evidence_payload)
        return self._resolver_func(normalized_payload)
