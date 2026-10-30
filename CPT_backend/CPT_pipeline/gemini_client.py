from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from google import genai
from google.genai.types import GenerateContentConfig, HttpOptions

try:
    from CPT_pipeline.config import Settings
except ImportError:
    from config import Settings


class GeminiClientError(RuntimeError):
    """Raised when Gemini request or response parsing fails."""


class GeminiClient:
    def __init__(self, settings: Settings):
        if not settings.vertex_project_id:
            raise GeminiClientError("VERTEX_PROJECT_ID is required for Vertex AI Gemini.")
        if not settings.vertex_location:
            raise GeminiClientError("VERTEX_LOCATION is required for Vertex AI Gemini.")
        if settings.vertex_serving_mode.lower() != "on_demand":
            raise GeminiClientError("VERTEX_SERVING_MODE must be 'on_demand'.")

        self._settings = settings
        self._client = genai.Client(
            vertexai=True,
            project=settings.vertex_project_id,
            location=settings.vertex_location,
            http_options=HttpOptions(api_version="v1"),
        )

    @staticmethod
    def _read_text_file(path: str) -> str:
        return Path(path).read_text(encoding="utf-8")

    @staticmethod
    def _read_json_file(path: str) -> dict[str, Any]:
        return json.loads(Path(path).read_text(encoding="utf-8"))

    def call_model_1(self, medical_document_text: str) -> dict[str, Any]:
        prompt = self._read_text_file(self._settings.model_1_prompt_path)
        schema = self._read_json_file(self._settings.model_1_schema_path)
        user_contents = (
            "### Medical Document Text\n"
            f"{medical_document_text.strip()}\n"
        )
        return self._generate_json(
            model_name=self._settings.model_1_name,
            system_prompt=prompt,
            response_schema=schema,
            user_contents=user_contents,
            temperature=self._settings.model_1_temperature,
            top_p=self._settings.model_1_top_p,
        )

    def call_model_2(
        self,
        medical_document_text: str,
        enriched_model_1_output: dict[str, Any],
    ) -> dict[str, Any]:
        prompt = self._read_text_file(self._settings.model_2_prompt_path)
        schema = self._read_json_file(self._settings.model_2_schema_path)
        user_contents = (
            "### Medical Document Text\n"
            f"{medical_document_text.strip()}\n\n"
            "### Extracted CPT Candidates with Normalized Fields, Document Evidences, and Knowledge-Base Top-K Suggestions\n"
            f"{json.dumps(enriched_model_1_output, ensure_ascii=True)}\n"
        )
        return self._generate_json(
            model_name=self._settings.model_2_name,
            system_prompt=prompt,
            response_schema=schema,
            user_contents=user_contents,
            temperature=self._settings.model_2_temperature,
            top_p=self._settings.model_2_top_p,
        )

    def _generate_json(
        self,
        model_name: str,
        system_prompt: str,
        response_schema: dict[str, Any],
        user_contents: str,
        temperature: float,
        top_p: float,
    ) -> dict[str, Any]:
        try:
            response = self._client.models.generate_content(
                model=model_name,
                contents=user_contents,
                config=GenerateContentConfig(
                    system_instruction=system_prompt,
                    response_mime_type="application/json",
                    response_schema=response_schema,
                    temperature=temperature,
                    top_p=top_p,
                ),
            )
        except Exception as exc:
            raise GeminiClientError(f"Gemini request failed: {exc}") from exc

        text = (response.text or "").strip()
        if not text:
            raise GeminiClientError("Gemini returned an empty response body.")

        try:
            return json.loads(text)
        except json.JSONDecodeError as exc:
            raise GeminiClientError(f"Gemini returned non-JSON content: {text}") from exc

