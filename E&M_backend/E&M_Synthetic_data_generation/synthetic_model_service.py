from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from google import genai
from google.genai import types

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
        self.system_prompt = Path(self.settings.prompt_path).read_text(encoding="utf-8")
        self.output_schema = json.loads(
            Path(self.settings.schema_path).read_text(encoding="utf-8")
        )
        self.code_descriptions = CodeDescriptionResolver(
            self.settings.code_descriptions_path,
            default_description=self.settings.default_code_description,
        )

    def resolve_code_description(self, em_code: str) -> str:
        return self.code_descriptions.resolve(em_code)

    def generate(
        self,
        em_code: str,
        em_code_description: str,
        total_no_of_documents: int,
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
        response = self.client.models.generate_content(
            model=_get_model_name(self.settings),
            contents=[types.Part.from_text(text=json.dumps(payload, indent=2))],
            config=types.GenerateContentConfig(
                temperature=self.settings.temperature,
                top_p=self.settings.top_p,
                system_instruction=self.system_prompt,
                response_mime_type="application/json",
                response_schema=self.output_schema,
            ),
        )
        return json.loads(response.text)
