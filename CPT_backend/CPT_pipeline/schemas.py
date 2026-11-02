from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class Evidence(BaseModel):
    text: str = ""
    pg_no: int = 0
    reftxtbefore: str = ""
    reftxtafter: str = ""


class OtherEvidence(Evidence):
    field_label: str = ""


class KnowledgeBaseCode(BaseModel):
    code: str
    similarity_score: str


class CPTCodeFound(BaseModel):
    model_config = ConfigDict(extra="allow")

    cpt_code: str = ""
    norm_procedure_name: Any = None
    norm_anatomy: Any = None
    norm_approach: Any = None
    norm_procedure_type: Any = None
    norm_imaging_guidance: Any = None
    norm_anesthesia_type: Any = None
    norm_other: Any = None
    procedure_evidences: list[Evidence] = Field(default_factory=list)
    anatomy_evidences: list[Evidence] = Field(default_factory=list)
    approach_evidences: list[Evidence] = Field(default_factory=list)
    procedure_type_evidences: list[Evidence] = Field(default_factory=list)
    imaging_guidance_evidences: list[Evidence] = Field(default_factory=list)
    anesthesia_type_evidences: list[Evidence] = Field(default_factory=list)
    other_evidences: list[OtherEvidence] = Field(default_factory=list)
    cpt_code_from_knowledge_base: list[KnowledgeBaseCode] = Field(default_factory=list)


class Model1Response(BaseModel):
    model_config = ConfigDict(extra="allow")
    cpt_codes_found: list[CPTCodeFound] = Field(default_factory=list)


class AuditedCode(BaseModel):
    original_cpt_code: str
    final_cpt_code: str
    final_cpt_code_description: str
    final_cpt_code_justification: str


class Model2Response(BaseModel):
    audited_codes: list[AuditedCode] = Field(default_factory=list)


class AuditCodeResponse(AuditedCode):
    procedure_evidences: list[Evidence] = Field(default_factory=list)
    anatomy_evidences: list[Evidence] = Field(default_factory=list)
    approach_evidences: list[Evidence] = Field(default_factory=list)
    procedure_type_evidences: list[Evidence] = Field(default_factory=list)
    imaging_guidance_evidences: list[Evidence] = Field(default_factory=list)
    anesthesia_type_evidences: list[Evidence] = Field(default_factory=list)
    other_evidences: list[OtherEvidence] = Field(default_factory=list)


class Service1Request(BaseModel):
    text: str
    model_name: str | None = None
    thinking_budget: int | None = None


class Service1Response(BaseModel):
    audited_codes: list[AuditCodeResponse] = Field(default_factory=list)

