import json
import os
import sqlite3
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List, Optional

from google import genai
from google.genai import types


def _find_repo_root(start: Path) -> Path:
    current = start
    for _ in range(8):
        if (current / "prompts.db").exists():
            return current
        current = current.parent
    raise FileNotFoundError("Could not locate repository root containing prompts.db")


def _load_prompt_from_db(service: str, key: str) -> Optional[str]:
    db_path = _find_repo_root(Path(__file__).resolve()) / "prompts.db"
    conn = sqlite3.connect(str(db_path))
    try:
        row = conn.execute(
            "SELECT content FROM prompts WHERE service = ? AND key = ?", (service, key)
        ).fetchone()
    finally:
        conn.close()
    return row[0] if row else None


def _load_env_file(env_path: Path) -> None:
    if not env_path.exists():
        return
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip("'").strip('"')
        if key and key not in os.environ:
            os.environ[key] = value


BASE_DIR = Path(__file__).resolve().parent
_load_env_file(BASE_DIR / ".env")


@dataclass
class ModelConfig:
    serving_mode: str = "on_demand"
    model_name: str = "gemini-2.5-flash"
    endpoint_name: str = ""
    temperature: float = 0.3
    top_p: float = 0.25


PROJECT_ID = os.getenv("PROJECT_ID", "stg-raapid-genai")
LOCATION = os.getenv("LOCATION", "global")

MODEL_CONFIG = ModelConfig(
    serving_mode=os.getenv("MODEL_SERVING_MODE", "on_demand"),
    model_name=os.getenv("MODEL_NAME", "gemini-2.5-flash"),
    endpoint_name=os.getenv("MODEL_ENDPOINT_NAME", ""),
    temperature=float(os.getenv("MODEL_TEMPERATURE", "0.2")),
    top_p=float(os.getenv("MODEL_TOP_P", "0.95")),
)

PROMPT_FILE_PATH = Path(
    os.getenv(
        "PCS_SYNTHETIC_DATA_GENERATION_PROMPT_FILE_PATH",
        str(BASE_DIR / "prompts" / "pcs_synthetic_data_generation_prompt.txt"),
    )
)
PCS_CODES_FILE_PATH = Path(
    os.getenv("PCS_CODES_FILE_PATH", str(BASE_DIR / "icd10pcs_codes_2026.txt"))
)


class PCSGenerationError(Exception):
    pass


class InputValidationError(PCSGenerationError):
    pass


class ModelResponseError(PCSGenerationError):
    pass


def _load_system_prompt() -> str:
    db_prompt = _load_prompt_from_db("pcs_synthetic", "system_prompt")
    if db_prompt and db_prompt.strip():
        return db_prompt.strip()
    if not PROMPT_FILE_PATH.exists():
        raise PCSGenerationError(f"Prompt file not found: {PROMPT_FILE_PATH}")
    prompt = PROMPT_FILE_PATH.read_text(encoding="utf-8").strip()
    if not prompt:
        raise PCSGenerationError(f"Prompt file is empty: {PROMPT_FILE_PATH}")
    return prompt


@lru_cache(maxsize=1)
def _load_pcs_code_descriptions() -> Dict[str, str]:
    if not PCS_CODES_FILE_PATH.exists():
        raise PCSGenerationError(f"PCS reference file not found: {PCS_CODES_FILE_PATH}")
    mapping: Dict[str, str] = {}
    for raw_line in PCS_CODES_FILE_PATH.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line:
            continue
        parts = line.split(maxsplit=1)
        if len(parts) != 2:
            continue
        mapping[parts[0].upper()] = parts[1].strip()
    if not mapping:
        raise PCSGenerationError("No ICD-10-PCS code descriptions were loaded.")
    return mapping


def _parse_codes(raw_codes: Any) -> List[str]:
    if not isinstance(raw_codes, str) or not raw_codes.strip():
        raise InputValidationError("`icd10_pcs_code` must be a non-empty string.")
    codes = [c.strip().upper() for c in raw_codes.split(",") if c.strip()]
    if not codes:
        raise InputValidationError("No valid codes found in `icd10_pcs_code`.")
    invalid_codes = [code for code in codes if len(code) != 7 or not code.isalnum()]
    if invalid_codes:
        raise InputValidationError(
            f"Invalid ICD-10-PCS code format: {', '.join(invalid_codes)}."
        )
    return codes


def _validate_and_prepare_input(input_data: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(input_data, dict):
        raise InputValidationError("Input must be a dictionary.")

    required = ["code_category", "icd10_pcs_code", "total_no_of_documents"]
    missing = [key for key in required if key not in input_data]
    if missing:
        raise InputValidationError(f"Missing required fields: {', '.join(missing)}")

    categories = input_data["code_category"]
    if not isinstance(categories, list) or not categories or not all(isinstance(v, str) and v.strip() for v in categories):
        raise InputValidationError("`code_category` must be a non-empty list of strings.")

    total = input_data["total_no_of_documents"]
    if not isinstance(total, int) or total <= 0:
        raise InputValidationError("`total_no_of_documents` must be a positive integer.")

    codes = _parse_codes(input_data["icd10_pcs_code"])
    code_mapping = _load_pcs_code_descriptions()
    missing_codes = [code for code in codes if code not in code_mapping]
    if missing_codes:
        raise InputValidationError(
            f"Code description not found for: {', '.join(missing_codes)}"
        )

    return {
        "code_category": [v.strip() for v in categories],
        "icd10_pcs_code": ", ".join(codes),
        "icd10_pcs_code_description": {code: code_mapping[code] for code in codes},
        "total_no_of_documents": total,
    }


def _build_client(client: Optional[genai.Client] = None) -> genai.Client:
    if client is not None:
        return client
    return genai.Client(vertexai=True, project=PROJECT_ID, location=LOCATION)


def _parse_json_response(text: str) -> Dict[str, Any]:
    raw = (text or "").strip()
    if not raw:
        raise ModelResponseError("Model returned empty content.")
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        start = raw.find("{")
        end = raw.rfind("}")
        if start == -1 or end == -1 or end <= start:
            raise ModelResponseError("Model response is not valid JSON.")
        try:
            return json.loads(raw[start : end + 1])
        except json.JSONDecodeError as exc:
            raise ModelResponseError("Model returned malformed JSON.") from exc


def _normalize_document(doc: Dict[str, Any]) -> Dict[str, str]:
    if not isinstance(doc, dict):
        raise ModelResponseError("Each item in `documents` must be an object.")

    normalized = {
        "generated_document": str(doc.get("generated_document", "")).strip(),
        "icd10_pcs_code": str(doc.get("icd10_pcs_code", doc.get("icd10pcscode", ""))).strip(),
        "icd10_pcs_code_description": str(
            doc.get("icd10_pcs_code_description", doc.get("icd10pcscodedescription", ""))
        ).strip(),
        "rational": str(doc.get("rational", doc.get("rationale", ""))).strip(),
    }
    missing = [k for k, v in normalized.items() if not v]
    if missing:
        raise ModelResponseError(
            f"Document is missing required output field(s): {', '.join(missing)}"
        )
    return normalized


def _validate_output(payload: Dict[str, Any]) -> Dict[str, List[Dict[str, str]]]:
    if not isinstance(payload, dict):
        raise ModelResponseError("Model output must be a JSON object.")
    documents = payload.get("documents")
    if not isinstance(documents, list) or not documents:
        raise ModelResponseError("Model output must include a non-empty `documents` list.")
    return {"documents": [_normalize_document(doc) for doc in documents]}


def generate_pcs_synthetic_data(
    input_data: Dict[str, Any],
    client: Optional[genai.Client] = None,
    model_config: ModelConfig = MODEL_CONFIG,
) -> Dict[str, List[Dict[str, str]]]:
    prepared_input = _validate_and_prepare_input(input_data)
    system_prompt = _load_system_prompt()
    llm_client = _build_client(client)

    gen_config = types.GenerateContentConfig(
        temperature=model_config.temperature,
        top_p=model_config.top_p,
        response_mime_type="application/json",
        system_instruction=[types.Part.from_text(text=system_prompt)],
    )

    try:
        response = llm_client.models.generate_content(
            model=model_config.model_name,
            contents=[
                types.Content(
                    role="user",
                    parts=[
                        types.Part.from_text(
                            text="The following JSON is the required input to generate synthetic ICD-10-PCS clinical documents."
                        ),
                        types.Part.from_text(text=json.dumps(prepared_input)),
                    ],
                )
            ],
            config=gen_config,
        )
        payload = _parse_json_response(response.text if hasattr(response, "text") else "")
        return _validate_output(payload)
    except PCSGenerationError:
        raise
    except Exception as exc:
        raise PCSGenerationError(f"Failed to generate synthetic PCS data: {exc}") from exc
