from __future__ import annotations

import asyncio
from typing import Any

from pydantic import ValidationError

try:
    from CPT_pipeline.config import Settings
    from CPT_pipeline.gemini_client import GeminiClient, GeminiClientError
    from CPT_pipeline.intermediate_store import IntermediateStore, RequestArtifactsContext
    from CPT_pipeline.retrieval_client import RetrievalClient, RetrievalClientError
    from CPT_pipeline.schemas import (
        AuditCodeResponse,
        Model1Response,
        Model2Response,
        Service1Response,
    )
except ImportError:
    from config import Settings
    from gemini_client import GeminiClient, GeminiClientError
    from intermediate_store import IntermediateStore, RequestArtifactsContext
    from retrieval_client import RetrievalClient, RetrievalClientError
    from schemas import (
        AuditCodeResponse,
        Model1Response,
        Model2Response,
        Service1Response,
    )

RETRIEVAL_TEXT_FIELDS = (
    "norm_procedure_name",
    "norm_anatomy",
    "norm_approach",
    "norm_procedure_type",
    "norm_imaging_guidance",
    "norm_anesthesia_type",
    "norm_other",
)


class PipelineError(RuntimeError):
    """Raised for model validation or orchestration failures."""


def flatten_to_text(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        text = value.strip()
        return [text] if text else []
    if isinstance(value, (int, float, bool)):
        return [str(value)]
    if isinstance(value, list):
        chunks: list[str] = []
        for item in value:
            chunks.extend(flatten_to_text(item))
        return chunks
    if isinstance(value, dict):
        chunks: list[str] = []
        for nested in value.values():
            chunks.extend(flatten_to_text(nested))
        return chunks
    return []


def build_retrieval_text(code_object: dict[str, Any]) -> str:
    parts: list[str] = []
    for field_name in RETRIEVAL_TEXT_FIELDS:
        parts.extend(flatten_to_text(code_object.get(field_name)))
    return " ".join(parts).strip()


def to_kb_candidates(retrieval_output: dict[str, Any]) -> list[dict[str, str]]:
    codes = retrieval_output.get("top_k_suggested_code", []) or []
    scores = retrieval_output.get("top_k_suggested_score", []) or []
    candidate_count = min(len(codes), len(scores))
    return [
        {
            "code": str(codes[idx]),
            "similarity_score": str(scores[idx]),
        }
        for idx in range(candidate_count)
    ]


def _sanitize_evidence(evidence_items: Any) -> list[dict[str, Any]]:
    if not isinstance(evidence_items, list):
        return []

    sanitized: list[dict[str, Any]] = []
    for item in evidence_items:
        if not isinstance(item, dict):
            continue
        sanitized.append(
            {
                "text": str(item.get("text", "")),
                "pg_no": int(item.get("pg_no", 0) or 0),
                "reftxtbefore": str(item.get("reftxtbefore", "")),
                "reftxtafter": str(item.get("reftxtafter", "")),
            }
        )
    return sanitized


def _sanitize_other_evidence(evidence_items: Any) -> list[dict[str, Any]]:
    if not isinstance(evidence_items, list):
        return []

    sanitized: list[dict[str, Any]] = []
    for item in evidence_items:
        if not isinstance(item, dict):
            continue
        sanitized.append(
            {
                "field_label": str(item.get("field_label", "")),
                "text": str(item.get("text", "")),
                "pg_no": int(item.get("pg_no", 0) or 0),
                "reftxtbefore": str(item.get("reftxtbefore", "")),
                "reftxtafter": str(item.get("reftxtafter", "")),
            }
        )
    return sanitized


class CPTAuditPipeline:
    def __init__(
        self,
        settings: Settings,
        gemini_client: GeminiClient,
        retrieval_client: RetrievalClient,
        intermediate_store: IntermediateStore | None = None,
    ):
        self._settings = settings
        self._gemini_client = gemini_client
        self._retrieval_client = retrieval_client
        self._intermediate_store = intermediate_store

    async def run(self, medical_document_text: str) -> Service1Response:
        context = self._start_request_context(medical_document_text)
        try:
            model_1_raw = self._gemini_client.call_model_1(medical_document_text)
            self._write_artifact(context, "01_model_1_raw_output.json", model_1_raw)

            model_1_validated = self._validate_model_1(model_1_raw)
            self._write_artifact(
                context,
                "02_model_1_validated_output.json",
                model_1_validated.model_dump(mode="json"),
            )

            enriched_codes, retrieval_trace = await self._enrich_with_retrieval(
                model_1_validated.cpt_codes_found
            )
            self._write_artifact(context, "03_retrieval_trace.json", {"items": retrieval_trace})

            enriched_model_1 = {
                **model_1_validated.model_dump(mode="json"),
                "cpt_codes_found": enriched_codes,
            }
            self._write_artifact(context, "04_model_1_enriched_output.json", enriched_model_1)

            model_2_raw = self._gemini_client.call_model_2(
                medical_document_text=medical_document_text,
                enriched_model_1_output=enriched_model_1,
            )
            self._write_artifact(context, "05_model_2_raw_output.json", model_2_raw)

            model_2_validated = self._validate_model_2(model_2_raw)
            self._write_artifact(
                context,
                "06_model_2_validated_output.json",
                model_2_validated.model_dump(mode="json"),
            )

            final_response = self._build_final_response(
                enriched_model_1_output=enriched_model_1,
                model_2_output=model_2_validated.model_dump(mode="json"),
            )
            self._write_artifact(
                context,
                "07_final_service_1_response.json",
                final_response.model_dump(mode="json"),
            )
            return final_response
        except Exception as exc:
            self._write_artifact(
                context,
                "99_error.json",
                {
                    "error": str(exc),
                    "error_type": exc.__class__.__name__,
                },
            )
            raise

    def _start_request_context(self, medical_document_text: str) -> RequestArtifactsContext | None:
        if self._intermediate_store is None:
            return None
        return self._intermediate_store.start_request(
            medical_document_text=medical_document_text,
            top_k=self._settings.top_k,
        )

    def _write_artifact(
        self,
        context: RequestArtifactsContext | None,
        file_name: str,
        payload: dict[str, Any],
    ) -> None:
        if self._intermediate_store is None:
            return
        self._intermediate_store.write_json(
            context=context,
            file_name=file_name,
            payload=payload,
        )

    def _validate_model_1(self, payload: dict[str, Any]) -> Model1Response:
        try:
            return Model1Response.model_validate(payload)
        except ValidationError as exc:
            raise PipelineError(f"Invalid model_1 response payload: {exc}") from exc

    def _validate_model_2(self, payload: dict[str, Any]) -> Model2Response:
        try:
            return Model2Response.model_validate(payload)
        except ValidationError as exc:
            raise PipelineError(f"Invalid model_2 response payload: {exc}") from exc

    async def _enrich_with_retrieval(
        self,
        cpt_codes_found: list[Any],
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        semaphore = asyncio.Semaphore(self._settings.retrieval_concurrency_limit)
        mutable_codes = [code.model_dump(mode="json") for code in cpt_codes_found]
        retrieval_trace: list[dict[str, Any]] = [{} for _ in mutable_codes]

        async def enrich_single(index: int, code_obj: dict[str, Any]) -> None:
            cpt_code = str(code_obj.get("cpt_code", ""))
            query_text = build_retrieval_text(code_obj)
            if not query_text:
                code_obj["cpt_code_from_knowledge_base"] = []
                retrieval_trace[index] = {
                    "code_index": index,
                    "cpt_code": cpt_code,
                    "query_text": "",
                    "status": "skipped_empty_query",
                    "retrieval_response": {
                        "top_k_suggested_code": [],
                        "top_k_suggested_score": [],
                    },
                    "cpt_code_from_knowledge_base": [],
                }
                return

            try:
                async with semaphore:
                    retrieval_output = await self._retrieval_client.retrieve(
                        text=query_text,
                        k=self._settings.top_k,
                    )
                candidates = to_kb_candidates(retrieval_output)
                code_obj["cpt_code_from_knowledge_base"] = candidates
                retrieval_trace[index] = {
                    "code_index": index,
                    "cpt_code": cpt_code,
                    "query_text": query_text,
                    "status": "success",
                    "retrieval_response": retrieval_output,
                    "cpt_code_from_knowledge_base": candidates,
                }
            except RetrievalClientError:
                code_obj["cpt_code_from_knowledge_base"] = []
                retrieval_trace[index] = {
                    "code_index": index,
                    "cpt_code": cpt_code,
                    "query_text": query_text,
                    "status": "failed",
                    "retrieval_response": {
                        "top_k_suggested_code": [],
                        "top_k_suggested_score": [],
                    },
                    "cpt_code_from_knowledge_base": [],
                }

        await asyncio.gather(
            *(enrich_single(index, code_obj) for index, code_obj in enumerate(mutable_codes))
        )
        return mutable_codes, retrieval_trace

    def _build_final_response(
        self,
        enriched_model_1_output: dict[str, Any],
        model_2_output: dict[str, Any],
    ) -> Service1Response:
        cpt_map: dict[str, dict[str, Any]] = {}
        for code_obj in enriched_model_1_output.get("cpt_codes_found", []):
            cpt_key = str(code_obj.get("cpt_code", "")).strip()
            if cpt_key:
                cpt_map[cpt_key] = code_obj

        audited_codes_output: list[AuditCodeResponse] = []
        for audited in model_2_output.get("audited_codes", []):
            original_code = str(audited.get("original_cpt_code", "")).strip()
            source = cpt_map.get(original_code, {})

            audited_codes_output.append(
                AuditCodeResponse.model_validate(
                    {
                        "original_cpt_code": original_code,
                        "final_cpt_code": str(audited.get("final_cpt_code", "")),
                        "final_cpt_code_description": str(
                            audited.get("final_cpt_code_description", "")
                        ),
                        "final_cpt_code_justification": str(
                            audited.get("final_cpt_code_justification", "")
                        ),
                        "procedure_evidences": _sanitize_evidence(
                            source.get("procedure_evidences")
                        ),
                        "anatomy_evidences": _sanitize_evidence(source.get("anatomy_evidences")),
                        "approach_evidences": _sanitize_evidence(
                            source.get("approach_evidences")
                        ),
                        "procedure_type_evidences": _sanitize_evidence(
                            source.get("procedure_type_evidences")
                        ),
                        "imaging_guidance_evidences": _sanitize_evidence(
                            source.get("imaging_guidance_evidences")
                        ),
                        "anesthesia_type_evidences": _sanitize_evidence(
                            source.get("anesthesia_type_evidences")
                        ),
                        "other_evidences": _sanitize_other_evidence(
                            source.get("other_evidences")
                        ),
                    }
                )
            )

        return Service1Response(audited_codes=audited_codes_output)

