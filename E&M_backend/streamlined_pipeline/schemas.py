from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field, model_validator


class PipelineRequest(BaseModel):
    EMcode: str
    EMcodedescription: str = ""
    total_no_of_documents: int = Field(
        ...,
        ge=1,
        description="Number of expected output documents.",
    )

    @model_validator(mode="before")
    @classmethod
    def normalize_input_shapes(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data

        normalized = dict(data)

        em_value = normalized.get("EMcode")
        if isinstance(em_value, list):
            normalized["EMcode"] = ", ".join(str(item) for item in em_value)

        return normalized

    @property
    def em_code(self) -> str:
        return self.EMcode

    @property
    def em_code_description(self) -> str:
        return self.EMcodedescription

    @property
    def em_codes_list(self) -> list[str]:
        return [code.strip() for code in self.EMcode.split(",") if code.strip()]

    @property
    def expected_documents(self) -> int:
        return self.total_no_of_documents


class GeneratedDocument(BaseModel):
    generated_document: str
    em_code: str = Field(alias="e&mcode")
    em_code_description: str = Field(default="", alias="e&mcodedescription")
    rational: str = ""

    model_config = {"populate_by_name": True}

    @model_validator(mode="before")
    @classmethod
    def normalize_document_keys(cls, data: Any) -> Any:
        if isinstance(data, dict):
            if "e&mcode" not in data and "em_code" in data:
                data = {**data, "e&mcode": data["em_code"]}
            if "e&mcodedescription" not in data and "em_code_description" in data:
                data = {**data, "e&mcodedescription": data["em_code_description"]}
            if "rational" not in data and "rationale" in data:
                data = {**data, "rational": data["rationale"]}
            if "rational" not in data and "Justification" in data:
                data = {**data, "rational": data["Justification"]}
            if "rational" not in data and "justification" in data:
                data = {**data, "rational": data["justification"]}
        return data


class SyntheticOutput(BaseModel):
    documents: list[GeneratedDocument]


class PerDocumentResult(BaseModel):
    generated_document: str
    em_code: str
    em_code_description: str
    rational: str
    evidence_prediction: dict[str, Any]
    em_resolution: dict[str, Any]


class PipelineResponse(BaseModel):
    requested_em_code: str
    requested_em_codes: list[str]
    requested_documents: int
    generated_documents_count: int
    results: list[PerDocumentResult]
