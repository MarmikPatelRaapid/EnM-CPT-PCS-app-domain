from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path
from typing import Any

from google import genai
from google.genai import types


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


# This module is imported both directly (FastAPI app / batch script) and via
# importlib from the streamlined pipeline, so ensure the service folder is on
# the path before importing its sibling modules.
BASE_DIR = Path(__file__).resolve().parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from code_descriptions import CodeDescriptionResolver
from config import SyntheticSettings, load_settings


def _get_model_name(settings: SyntheticSettings) -> str:
    mode = settings.vertex_serving_mode or "on_demand"
    if mode == "on_demand":
        return settings.model_name

    if mode == "endpoint":
        endpoint_name = settings.endpoint_name.strip()
        if not endpoint_name:
            raise ValueError("Set EM_SYNTH_ENDPOINT_NAME for endpoint serving mode.")
        return endpoint_name

    raise ValueError("VERTEX_SERVING_MODE must be 'on_demand' or 'endpoint'.")


class SyntheticModelService:
    def __init__(self, settings: SyntheticSettings | None = None) -> None:
        self.settings = settings or load_settings()
        self.client = genai.Client(
            vertexai=True,
            project=self.settings.vertex_project_id,
            location=self.settings.vertex_location,
        )
        self.code_descriptions = CodeDescriptionResolver(
            self.settings.code_descriptions_path,
            default_description=self.settings.default_code_description,
        )

    @property
    def system_prompt(self) -> str:
        return _load_prompt_from_db("em_synthetic", "system_prompt")

    @property
    def output_schema(self) -> dict[str, Any]:
        return _load_schema_from_db("em_synthetic", "output_schema")

    def resolve_code_description(self, em_code: str) -> str:
        return self.code_descriptions.resolve(em_code)

    def generate(
        self,
        em_code: str,
        em_code_description: str,
        total_no_of_documents: int,
        model_name: str | None = None,
        thinking_budget: int | None = None,
    ) -> dict[str, Any]:
        # Callers (UI / pipeline) usually do not supply a description, so map it
        # from the resource file when missing; fall back to the configured default.
        resolved_description = str(em_code_description or "").strip()
        if not resolved_description:
            resolved_description = self.resolve_code_description(em_code)

        payload = {
            "EMcode": em_code,
            "EMcodedescription": resolved_description,
            "total_no_of_documents": total_no_of_documents,
        }
        config_kwargs: dict[str, Any] = {
            "temperature": self.settings.temperature,
            "top_p": self.settings.top_p,
            "system_instruction": self.system_prompt,
            "response_mime_type": "application/json",
            "response_schema": self.output_schema,
        }
        if thinking_budget is not None:
            config_kwargs["thinking_config"] = types.ThinkingConfig(thinking_budget=thinking_budget)

        resolved_model = model_name
        if resolved_model is None and (self.settings.vertex_serving_mode or "on_demand") == "on_demand":
            resolved_model = _load_default_model_from_db()
        if resolved_model is None:
            resolved_model = _get_model_name(self.settings)

        response = self.client.models.generate_content(
            model=resolved_model,
            contents=[types.Part.from_text(text=json.dumps(payload, indent=2))],
            config=types.GenerateContentConfig(**config_kwargs),
        )
        return json.loads(response.text)
