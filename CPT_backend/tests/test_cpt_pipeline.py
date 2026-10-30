from __future__ import annotations

import asyncio
from typing import Any

from CPT_pipeline.config import Settings
from CPT_pipeline.pipeline import CPTAuditPipeline, build_retrieval_text, to_kb_candidates


class FakeGeminiClient:
    def __init__(self, model_1_payload: dict[str, Any], model_2_payload: dict[str, Any]):
        self._model_1_payload = model_1_payload
        self._model_2_payload = model_2_payload
        self.received_model_2_input: dict[str, Any] | None = None

    def call_model_1(self, medical_document_text: str) -> dict[str, Any]:
        return self._model_1_payload

    def call_model_2(
        self,
        medical_document_text: str,
        enriched_model_1_output: dict[str, Any],
    ) -> dict[str, Any]:
        self.received_model_2_input = enriched_model_1_output
        return self._model_2_payload


class FakeRetrievalClient:
    def __init__(self, results: dict[str, dict[str, Any]]):
        self._results = results
        self.calls: list[tuple[str, int]] = []

    async def retrieve(self, text: str, k: int) -> dict[str, Any]:
        self.calls.append((text, k))
        return self._results.get(
            text,
            {
                "top_k_suggested_code": [],
                "top_k_suggested_score": [],
            },
        )


def test_build_retrieval_text_from_normalized_fields() -> None:
    code_obj = {
        "norm_procedure_name": "Procedure Name",
        "norm_anatomy": "Anatomy",
        "norm_approach": "Open",
        "norm_procedure_type": "Excision",
        "norm_imaging_guidance": "Ultrasound",
        "norm_anesthesia_type": "General",
        "norm_other": [{"field_label": "Device", "text": "Stent"}],
    }

    result = build_retrieval_text(code_obj)

    assert result == "Procedure Name Anatomy Open Excision Ultrasound General Device Stent"


def test_build_retrieval_text_skips_empty_and_null_values() -> None:
    code_obj = {
        "norm_procedure_name": "Procedure Name",
        "norm_anatomy": "",
        "norm_approach": None,
        "norm_procedure_type": [],
        "norm_imaging_guidance": {},
        "norm_anesthesia_type": "General",
        "norm_other": "Other",
    }

    result = build_retrieval_text(code_obj)

    assert result == "Procedure Name General Other"


def test_to_kb_candidates_converts_response() -> None:
    retrieval_output = {
        "top_k_suggested_code": ["43253", "43235"],
        "top_k_suggested_score": [1.0, 0.943357],
    }

    result = to_kb_candidates(retrieval_output)

    assert result == [
        {"code": "43253", "similarity_score": "1.0"},
        {"code": "43235", "similarity_score": "0.943357"},
    ]


def _build_settings() -> Settings:
    return Settings(
        vertex_project_id="test-project",
        vertex_location="us-central1",
        vertex_serving_mode="on_demand",
        model_1_name="model-1",
        model_2_name="model-2",
        model_1_temperature=0.2,
        model_1_top_p=0.95,
        model_2_temperature=0.2,
        model_2_top_p=0.95,
        retrieval_url="http://localhost:8083/retrieve",
        top_k=5,
        retrieval_connect_timeout_seconds=10.0,
        retrieval_read_timeout_seconds=None,
        retrieval_write_timeout_seconds=30.0,
        retrieval_pool_timeout_seconds=30.0,
        retrieval_concurrency_limit=4,
        save_intermediate_outputs=False,
        intermediate_output_dir="tests/request_outputs",
        model_1_prompt_path="model1.txt",
        model_2_prompt_path="model2.txt",
        model_1_schema_path="model1.json",
        model_2_schema_path="model2.json",
    )


def test_pipeline_run_attaches_evidence_by_cpt_reference() -> None:
    model_1_payload = {
        "cpt_codes_found": [
            {
                "cpt_code": "43499",
                "norm_procedure_name": "Excision lesion",
                "norm_anatomy": "esophagus",
                "norm_approach": "open",
                "norm_procedure_type": "excision",
                "norm_imaging_guidance": "",
                "norm_anesthesia_type": "general",
                "norm_other": "none",
                "procedure_evidences": [
                    {
                        "text": "Excision of lesion",
                        "pg_no": 1,
                        "reftxtbefore": "before",
                        "reftxtafter": "after",
                    }
                ],
                "anatomy_evidences": [],
                "approach_evidences": [],
                "procedure_type_evidences": [],
                "imaging_guidance_evidences": [],
                "anesthesia_type_evidences": [],
                "other_evidences": [],
            }
        ]
    }
    model_2_payload = {
        "audited_codes": [
            {
                "original_cpt_code": "43499",
                "final_cpt_code": "43499",
                "final_cpt_code_description": "Unlisted procedure, esophagus",
                "final_cpt_code_justification": "Best fit",
            }
        ]
    }

    fake_gemini = FakeGeminiClient(model_1_payload=model_1_payload, model_2_payload=model_2_payload)
    retrieval_text = "Excision lesion esophagus open excision general none"
    fake_retrieval = FakeRetrievalClient(
        results={
            retrieval_text: {
                "top_k_suggested_code": ["43253"],
                "top_k_suggested_score": [0.98],
            }
        }
    )

    pipeline = CPTAuditPipeline(
        settings=_build_settings(),
        gemini_client=fake_gemini,
        retrieval_client=fake_retrieval,
    )

    response = asyncio.run(pipeline.run("sample medical note"))
    payload = response.model_dump(mode="json")

    assert fake_retrieval.calls == [(retrieval_text, 5)]
    assert fake_gemini.received_model_2_input is not None
    assert (
        fake_gemini.received_model_2_input["cpt_codes_found"][0]["cpt_code_from_knowledge_base"][0][
            "code"
        ]
        == "43253"
    )

    audited = payload["audited_codes"][0]
    assert audited["original_cpt_code"] == "43499"
    assert audited["final_cpt_code"] == "43499"
    assert audited["procedure_evidences"][0]["text"] == "Excision of lesion"


def test_pipeline_handles_multiple_cpt_codes_in_single_request() -> None:
    model_1_payload = {
        "cpt_codes_found": [
            {
                "cpt_code": "43235",
                "norm_procedure_name": "EGD diagnostic",
                "norm_anatomy": "esophagus stomach duodenum",
                "norm_approach": "endoscopic",
                "norm_procedure_type": "diagnostic",
                "norm_imaging_guidance": "",
                "norm_anesthesia_type": "moderate sedation",
                "norm_other": "biopsy forceps prepared",
                "procedure_evidences": [
                    {
                        "text": "EGD performed with full examination of esophagus, stomach and duodenum.",
                        "pg_no": 2,
                        "reftxtbefore": "Procedure:",
                        "reftxtafter": "No complications.",
                    }
                ],
                "anatomy_evidences": [],
                "approach_evidences": [],
                "procedure_type_evidences": [],
                "imaging_guidance_evidences": [],
                "anesthesia_type_evidences": [],
                "other_evidences": [],
            },
            {
                "cpt_code": "45378",
                "norm_procedure_name": "Colonoscopy diagnostic",
                "norm_anatomy": "colon",
                "norm_approach": "endoscopic",
                "norm_procedure_type": "diagnostic",
                "norm_imaging_guidance": "",
                "norm_anesthesia_type": "moderate sedation",
                "norm_other": "cecum reached",
                "procedure_evidences": [
                    {
                        "text": "Diagnostic colonoscopy performed to cecum.",
                        "pg_no": 3,
                        "reftxtbefore": "Second procedure:",
                        "reftxtafter": "Patient stable.",
                    }
                ],
                "anatomy_evidences": [],
                "approach_evidences": [],
                "procedure_type_evidences": [],
                "imaging_guidance_evidences": [],
                "anesthesia_type_evidences": [],
                "other_evidences": [],
            },
        ]
    }
    model_2_payload = {
        "audited_codes": [
            {
                "original_cpt_code": "43235",
                "final_cpt_code": "43235",
                "final_cpt_code_description": "Upper gastrointestinal endoscopy",
                "final_cpt_code_justification": "Diagnostic EGD documented.",
            },
            {
                "original_cpt_code": "45378",
                "final_cpt_code": "45378",
                "final_cpt_code_description": "Diagnostic colonoscopy",
                "final_cpt_code_justification": "Diagnostic colonoscopy to cecum documented.",
            },
        ]
    }

    fake_gemini = FakeGeminiClient(model_1_payload=model_1_payload, model_2_payload=model_2_payload)
    query_text_1 = (
        "EGD diagnostic esophagus stomach duodenum endoscopic diagnostic "
        "moderate sedation biopsy forceps prepared"
    )
    query_text_2 = "Colonoscopy diagnostic colon endoscopic diagnostic moderate sedation cecum reached"
    fake_retrieval = FakeRetrievalClient(
        results={
            query_text_1: {
                "top_k_suggested_code": ["43235", "43239"],
                "top_k_suggested_score": [0.992, 0.964],
            },
            query_text_2: {
                "top_k_suggested_code": ["45378", "45380"],
                "top_k_suggested_score": [0.989, 0.958],
            },
        }
    )

    pipeline = CPTAuditPipeline(
        settings=_build_settings(),
        gemini_client=fake_gemini,
        retrieval_client=fake_retrieval,
    )

    request_text = (
        "Patient underwent two procedures in one encounter: diagnostic EGD and "
        "diagnostic colonoscopy to cecum under moderate sedation."
    )
    response = asyncio.run(pipeline.run(request_text))
    payload = response.model_dump(mode="json")

    assert fake_retrieval.calls == [(query_text_1, 5), (query_text_2, 5)]
    assert fake_gemini.received_model_2_input is not None
    enriched_codes = fake_gemini.received_model_2_input["cpt_codes_found"]
    assert len(enriched_codes) == 2
    assert enriched_codes[0]["cpt_code_from_knowledge_base"][0]["code"] == "43235"
    assert enriched_codes[1]["cpt_code_from_knowledge_base"][0]["code"] == "45378"

    assert len(payload["audited_codes"]) == 2
    assert payload["audited_codes"][0]["original_cpt_code"] == "43235"
    assert payload["audited_codes"][0]["procedure_evidences"][0]["pg_no"] == 2
    assert payload["audited_codes"][1]["original_cpt_code"] == "45378"
    assert payload["audited_codes"][1]["procedure_evidences"][0]["pg_no"] == 3

