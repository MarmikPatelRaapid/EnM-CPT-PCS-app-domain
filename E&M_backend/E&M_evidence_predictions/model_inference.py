import json
import re
from pathlib import Path

from google import genai
from google.genai import types


PROJECT_ID = "stg-raapid-genai"
LOCATION = "global"

MODEL_CONFIG = {
    "serving_mode": "on_demand",  # "on_demand" or "endpoint"
    "model_name": "gemini-2.5-pro",
    "endpoint_name": "",
    "temperature": 0.25,
    "top_p": 0.15,
}

BASE_DIR = Path(__file__).resolve().parent
PROMPT_FILE = BASE_DIR / "prompt.txt"
OUTPUT_SCHEMA_FILE = BASE_DIR / "output_schema.json"
DEFAULT_SYSTEM_PROMPT = (
    "Extract structured E&M evidence from each document. "
    "Return only valid JSON that follows the provided response schema."
)


def get_model_name() -> str:
    mode = MODEL_CONFIG.get("serving_mode", "on_demand")
    if mode == "on_demand":
        return MODEL_CONFIG["model_name"]
    if mode == "endpoint":
        endpoint_name = MODEL_CONFIG.get("endpoint_name", "").strip()
        if not endpoint_name:
            raise ValueError("Set MODEL_CONFIG['endpoint_name'] for endpoint mode.")
        return endpoint_name
    raise ValueError("serving_mode must be 'on_demand' or 'endpoint'.")


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _read_prompt() -> str:
    if PROMPT_FILE.exists():
        return _read_text(PROMPT_FILE)
    return DEFAULT_SYSTEM_PROMPT


def _parse_response_json(response_text: str) -> dict:
    text = response_text.strip()
    parse_errors: list[str] = []
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        parse_errors.append(f"direct_json: {exc}")

    fenced_match = re.search(r"```(?:json)?\s*(.*?)```", text, flags=re.DOTALL | re.IGNORECASE)
    if fenced_match:
        fenced_text = fenced_match.group(1).strip()
        try:
            return json.loads(fenced_text)
        except json.JSONDecodeError as exc:
            parse_errors.append(f"fenced_json: {exc}")

    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        try:
            return json.loads(text[start : end + 1])
        except json.JSONDecodeError as exc:
            parse_errors.append(f"substring_json: {exc}")

    raise ValueError(f"Model response is not valid JSON. Parse attempts failed: {parse_errors}")


def _extract_document_text(document_item: object) -> str:
    if isinstance(document_item, dict):
        return str(document_item.get("generated_document", "")).strip()
    return str(document_item or "").strip()


def generate_from_documents(documents: list[object]) -> dict:
    if not documents:
        raise ValueError("At least one generated_document text is required.")

    selected_text = _extract_document_text(documents[0])
    if not selected_text:
        raise ValueError("Selected generated_document text is empty.")

    prompt = _read_prompt()

    client = genai.Client(
        vertexai=True,
        project=PROJECT_ID,
        location=LOCATION,
    )

    response = client.models.generate_content(
        model=get_model_name(),
        contents=[types.Part.from_text(text=selected_text)],
        config=types.GenerateContentConfig(
            temperature=MODEL_CONFIG["temperature"],
            top_p=MODEL_CONFIG["top_p"],
            system_instruction=prompt,
            response_mime_type="application/json",
        ),
    )

    return _parse_response_json(response.text)
