from __future__ import annotations

from fastapi.testclient import TestClient

from streamlined_pipeline.evidence_step import EvidencePredictionStep
from streamlined_pipeline.em_resolution_step import EMResolutionStep
from streamlined_pipeline.orchestrator import PipelineOrchestrator
from streamlined_pipeline.schemas import GeneratedDocument, PipelineRequest, SyntheticOutput
from streamlined_pipeline_api import app
import streamlined_pipeline_api


class FakeSyntheticStep:
    def __init__(self) -> None:
        self.last_request: PipelineRequest | None = None

    def run(self, request: PipelineRequest) -> SyntheticOutput:
        self.last_request = request
        return SyntheticOutput.model_validate(
            {
                "documents": [
                    {
                        "generated_document": "doc text one",
                        "e&mcode": "99213",
                        "e&mcodedescription": "Office visit, established patient",
                        "rational": "first rationale",
                    },
                    {
                        "generated_document": "doc text two",
                        "e&mcode": "99214",
                        "e&mcodedescription": "Office visit, established patient",
                        "rational": "second rationale",
                    },
                ]
            }
        )


class FakeEvidenceStep:
    def __init__(self) -> None:
        self.last_documents = []

    def run_parallel(self, documents):
        self.last_documents = documents
        return [
            {"facility": {"facility_type": "Telemedicine Services"}, "doc_id": "one"},
            {"facility": {"facility_type": "Office or Other Outpatient Services"}, "doc_id": "two"},
        ]


class FakeEMStep:
    def __init__(self) -> None:
        self.last_payloads = []

    def run(self, evidence_payload: dict) -> dict:
        self.last_payloads.append(evidence_payload)
        return {"resolved_code": f"code-for-{evidence_payload['doc_id']}"}


def test_pipeline_orchestrator_flows_data_across_all_steps() -> None:
    synthetic_step = FakeSyntheticStep()
    evidence_step = FakeEvidenceStep()
    em_step = FakeEMStep()
    orchestrator = PipelineOrchestrator(
        synthetic_step=synthetic_step,
        evidence_step=evidence_step,
        em_step=em_step,
        persist_outputs=False,
    )

    request = PipelineRequest(
        EMcode="99213,99214",
        EMcodedescription="Office or other outpatient visit",
        total_no_of_documents=2,
    )

    output = orchestrator.run(request)

    assert synthetic_step.last_request is not None
    assert synthetic_step.last_request.em_codes_list == ["99213", "99214"]
    assert [doc.generated_document for doc in evidence_step.last_documents] == [
        "doc text one",
        "doc text two",
    ]
    assert [payload["doc_id"] for payload in em_step.last_payloads] == ["one", "two"]
    assert output.generated_documents_count == 2
    assert output.results[0].em_resolution["resolved_code"] == "code-for-one"
    assert output.results[1].em_resolution["resolved_code"] == "code-for-two"


def test_pipeline_api_returns_orchestrated_response(monkeypatch) -> None:
    synthetic_step = FakeSyntheticStep()
    evidence_step = FakeEvidenceStep()
    em_step = FakeEMStep()
    orchestrator = PipelineOrchestrator(
        synthetic_step=synthetic_step,
        evidence_step=evidence_step,
        em_step=em_step,
        persist_outputs=False,
    )

    monkeypatch.setattr(streamlined_pipeline_api, "get_orchestrator", lambda: orchestrator)

    client = TestClient(app)
    response = client.post(
        "/run-pipeline",
        json={
            "EMcode": "99213,99214",
            "EMcodedescription": "Office or other outpatient visit",
            "total_no_of_documents": 2,
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["requested_em_code"] == "99213,99214"
    assert payload["generated_documents_count"] == 2
    assert len(payload["results"]) == 2
    assert payload["results"][0]["evidence_prediction"]["doc_id"] == "one"
    assert payload["results"][1]["em_resolution"]["resolved_code"] == "code-for-two"


def test_em_resolution_step_normalizes_list_wrapped_payload() -> None:
    received = {}

    def fake_resolver(payload: dict) -> dict:
        received["payload"] = payload
        return {"ok": True}

    step = EMResolutionStep(resolver_func=fake_resolver)
    output = step.run([{"facility": {"facility_type": "Telemedicine Services"}}])

    assert output == {"ok": True}
    assert received["payload"] == {"facility": {"facility_type": "Telemedicine Services"}}


def test_evidence_step_sends_only_generated_document_text() -> None:
    captured = {}

    def fake_predictor(documents: list[dict]) -> dict:
        captured["documents"] = documents
        return {"ok": True}

    step = EvidencePredictionStep(predictor_func=fake_predictor)
    doc = GeneratedDocument.model_validate(
        {
            "generated_document": "sample ehr text",
            "e&mcode": "99213",
            "e&mcodedescription": "Office visit, established patient",
            "Justification": "some reason",
        }
    )
    output = step.run_parallel([doc])

    assert output == [{"ok": True}]
    assert captured["documents"] == [{"generated_document": "sample ehr text"}]
