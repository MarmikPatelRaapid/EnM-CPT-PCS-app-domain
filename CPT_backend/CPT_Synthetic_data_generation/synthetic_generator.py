from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

from google import genai
from google.genai import types
from google.genai.types import HttpOptions

try:
    from CPT_Synthetic_data_generation.config import SyntheticSettings
except ImportError:
    from config import SyntheticSettings


def _find_repo_root(start: Path) -> Path:
    current = start
    for _ in range(8):
        if (current / "prompts.db").exists():
            return current
        current = current.parent
    raise FileNotFoundError("Could not locate repository root containing prompts.db")


def _load_prompt_from_db(service: str, key: str) -> str:
    db_path = _find_repo_root(Path(__file__).resolve()) / "prompts.db"
    conn = sqlite3.connect(str(db_path))
    try:
        row = conn.execute(
            "SELECT content FROM prompts WHERE service = ? AND key = ?", (service, key)
        ).fetchone()
    finally:
        conn.close()
    if row is None:
        raise RuntimeError(f"Prompt not found in prompts.db: service={service!r} key={key!r}")
    return row[0]


def _load_schema_from_db(service: str, key: str) -> dict[str, Any]:
    db_path = _find_repo_root(Path(__file__).resolve()) / "prompts.db"
    conn = sqlite3.connect(str(db_path))
    try:
        row = conn.execute(
            "SELECT content FROM schemas WHERE service = ? AND key = ?", (service, key)
        ).fetchone()
    finally:
        conn.close()
    if row is None:
        raise RuntimeError(f"Schema not found in prompts.db: service={service!r} key={key!r}")
    return json.loads(row[0])


class SyntheticGenerationError(RuntimeError):
    """Raised when the CPT synthetic generation request or parsing fails."""


class CPTSyntheticService:
    def __init__(self, settings: SyntheticSettings) -> None:
        if not settings.vertex_project_id:
            raise SyntheticGenerationError(
                "VERTEX_PROJECT_ID is required for Vertex AI Gemini."
            )
        if not settings.vertex_location:
            raise SyntheticGenerationError(
                "VERTEX_LOCATION is required for Vertex AI Gemini."
            )
        if settings.vertex_serving_mode.lower() != "on_demand":
            raise SyntheticGenerationError("VERTEX_SERVING_MODE must be 'on_demand'.")

        self._settings = settings
        self._client = genai.Client(
            vertexai=True,
            project=settings.vertex_project_id,
            location=settings.vertex_location,
            http_options=HttpOptions(api_version="v1"),
        )
    @property
    def system_prompt(self) -> str:
        return _load_prompt_from_db("cpt_synthetic", "system_prompt")

    @property
    def output_schema(self) -> dict[str, Any]:
        return _load_schema_from_db("cpt_synthetic", "output_schema")

    def generate(
        self,
        code_category: str,
        cpt_code: str,
        total_no_of_documents: int,
    ) -> dict[str, Any]:
        payload = {
            "code_category": code_category,
            "cptcode": cpt_code,
            "total_no_of_documents": total_no_of_documents,
        }
        try:
            response = self._client.models.generate_content(
                model=self._settings.model_name,
                contents=[types.Part.from_text(text=json.dumps(payload, indent=2))],
                config=types.GenerateContentConfig(
                    temperature=self._settings.temperature,
                    top_p=self._settings.top_p,
                    system_instruction=self.system_prompt,
                    response_mime_type="application/json",
                    response_schema=self.output_schema,
                ),
            )
        except Exception as exc:
            raise SyntheticGenerationError(f"Gemini request failed: {exc}") from exc

        text = (response.text or "").strip()
        if not text:
            raise SyntheticGenerationError("Gemini returned an empty response body.")

        try:
            return json.loads(text)
        except json.JSONDecodeError as exc:
            raise SyntheticGenerationError(
                f"Gemini returned non-JSON content: {text}"
            ) from exc
