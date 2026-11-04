from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

from google import genai
from google.genai.types import GenerateContentConfig, HttpOptions, HttpRetryOptions, ThinkingConfig

try:
    from CPT_pipeline.config import Settings
except ImportError:
    from config import Settings


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


def _load_default_model_from_db() -> str | None:
    """The DB-backed dropdown is the single source of truth for which model
    to use by default; falls back to None (caller uses its own settings
    default) only if the DB has no default row configured."""
    db_path = _find_repo_root(Path(__file__).resolve()) / "prompts.db"
    conn = sqlite3.connect(str(db_path))
    try:
        row = conn.execute(
            "SELECT value FROM dropdown_options WHERE category = 'model' AND is_default = 1"
        ).fetchone()
    finally:
        conn.close()
    return row[0] if row and row[0] else None


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
            http_options=HttpOptions(
                api_version="v1",
                # The SDK retries 429/5xx internally by default (5 attempts,
                # backoff up to 60s each) with no visibility to the caller —
                # under Vertex AI quota pressure that silently eats minutes
                # per call, well past batch_api's 180s per-request timeout,
                # and surfaces as a plain "timed out" with no real cause.
                # Cap each HTTP attempt and shorten the retry budget so a
                # throttled call fails fast with a clear error instead of
                # hanging: two sequential calls per request (model 1 and
                # model 2) now bound to roughly 80s worst case, not minutes.
                timeout=20_000,
                retry_options=HttpRetryOptions(attempts=2, initial_delay=1.0, max_delay=10.0),
            ),
        )

    @staticmethod
    def _read_text_file(path: str) -> str:
        return Path(path).read_text(encoding="utf-8")

    @staticmethod
    def _read_json_file(path: str) -> dict[str, Any]:
        return json.loads(Path(path).read_text(encoding="utf-8"))

    def call_model_1(
        self,
        medical_document_text: str,
        model_name: str | None = None,
        thinking_budget: int | None = None,
    ) -> dict[str, Any]:
        prompt = _load_prompt_from_db("cpt_pipeline", "model_1_system_prompt")
        schema = _load_schema_from_db("cpt_pipeline", "model_1_response_schema")
        user_contents = (
            "### Medical Document Text\n"
            f"{medical_document_text.strip()}\n"
        )
        return self._generate_json(
            model_name=model_name or _load_default_model_from_db() or self._settings.model_1_name,
            system_prompt=prompt,
            response_schema=schema,
            user_contents=user_contents,
            temperature=self._settings.model_1_temperature,
            top_p=self._settings.model_1_top_p,
            thinking_budget=thinking_budget,
        )

    def call_model_2(
        self,
        medical_document_text: str,
        enriched_model_1_output: dict[str, Any],
        model_name: str | None = None,
        thinking_budget: int | None = None,
    ) -> dict[str, Any]:
        prompt = _load_prompt_from_db("cpt_pipeline", "model_2_system_prompt")
        schema = _load_schema_from_db("cpt_pipeline", "model_2_response_schema")
        user_contents = (
            "### Medical Document Text\n"
            f"{medical_document_text.strip()}\n\n"
            "### Extracted CPT Candidates with Normalized Fields, Document Evidences, and Knowledge-Base Top-K Suggestions\n"
            f"{json.dumps(enriched_model_1_output, ensure_ascii=True)}\n"
        )
        return self._generate_json(
            model_name=model_name or _load_default_model_from_db() or self._settings.model_2_name,
            system_prompt=prompt,
            response_schema=schema,
            user_contents=user_contents,
            temperature=self._settings.model_2_temperature,
            top_p=self._settings.model_2_top_p,
            thinking_budget=thinking_budget,
        )

    def _generate_json(
        self,
        model_name: str,
        system_prompt: str,
        response_schema: dict[str, Any],
        user_contents: str,
        temperature: float,
        top_p: float,
        thinking_budget: int | None = None,
    ) -> dict[str, Any]:
        config_kwargs: dict[str, Any] = {
            "system_instruction": system_prompt,
            "response_mime_type": "application/json",
            "response_schema": response_schema,
            "temperature": temperature,
            "top_p": top_p,
        }
        if thinking_budget is not None:
            config_kwargs["thinking_config"] = ThinkingConfig(thinking_budget=thinking_budget)

        try:
            response = self._client.models.generate_content(
                model=model_name,
                contents=user_contents,
                config=GenerateContentConfig(**config_kwargs),
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

