import json
import os
import re
import sqlite3
from pathlib import Path

from google import genai
from google.genai import types


def _find_repo_root(start: Path) -> Path:
    current = start
    for _ in range(8):
        if (current / "prompts.db").exists():
            return current
        current = current.parent
    raise FileNotFoundError("Could not locate repository root containing prompts.db")


def _load_prompt_from_db(service: str, key: str) -> str | None:
    db_path = _find_repo_root(Path(__file__).resolve()) / "prompts.db"
    conn = sqlite3.connect(str(db_path))
    try:
        row = conn.execute(
            "SELECT content FROM prompts WHERE service = ? AND key = ?", (service, key)
        ).fetchone()
    finally:
        conn.close()
    return row[0] if row else None


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


PROJECT_ID = os.getenv("VERTEX_PROJECT_ID", "raapid-genai")
LOCATION = os.getenv("VERTEX_LOCATION", "global")

MODEL_CONFIG = {
    "serving_mode": "on_demand",  # "on_demand" or "endpoint"
    "model_name": os.getenv("EM_EVIDENCE_MODEL_NAME", "gemini-2.5-pro"),
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
    db_prompt = _load_prompt_from_db("em_evidence", "prompt")
    if db_prompt:
        return db_prompt
    if PROMPT_FILE.exists():
        return _read_text(PROMPT_FILE)
    return DEFAULT_SYSTEM_PROMPT


def _escape_stray_quotes(text: str) -> str:
    """Best-effort repair for the most common way loose (schema-less) Gemini
    JSON mode breaks: a verbatim document snippet copied into a string value
    contains a literal `"` that the model didn't escape, which prematurely
    terminates the JSON string and desyncs the rest of the parse.

    Walks the text tracking string/escape state; a `"` encountered while
    inside a string is only treated as the real closing quote when the next
    non-whitespace character looks like valid JSON structure (`,`, `}`, `]`,
    `:`, or end of input) — otherwise it's a stray quote and gets escaped.
    """
    result: list[str] = []
    in_string = False
    i = 0
    n = len(text)
    while i < n:
        ch = text[i]
        if in_string and ch == "\\" and i + 1 < n:
            result.append(ch)
            result.append(text[i + 1])
            i += 2
            continue
        if ch == '"':
            if not in_string:
                in_string = True
                result.append(ch)
                i += 1
                continue
            j = i + 1
            while j < n and text[j] in " \t\r\n":
                j += 1
            next_char = text[j] if j < n else ""
            if next_char in (",", "}", "]", ":", ""):
                in_string = False
                result.append(ch)
            else:
                result.append('\\"')
            i += 1
            continue
        result.append(ch)
        i += 1
    return "".join(result)


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
    candidate = text[start : end + 1] if start != -1 and end != -1 and end > start else None
    if candidate is not None:
        try:
            return json.loads(candidate)
        except json.JSONDecodeError as exc:
            parse_errors.append(f"substring_json: {exc}")

        try:
            return json.loads(_escape_stray_quotes(candidate))
        except json.JSONDecodeError as exc:
            parse_errors.append(f"repaired_json: {exc}")

    raise ValueError(f"Model response is not valid JSON. Parse attempts failed: {parse_errors}")


def _extract_document_text(document_item: object) -> str:
    if isinstance(document_item, dict):
        return str(document_item.get("generated_document", "")).strip()
    return str(document_item or "").strip()


def generate_from_documents(
    documents: list[object],
    model_name: str | None = None,
    thinking_budget: int | None = None,
) -> dict:
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

    config_kwargs: dict = {
        "temperature": MODEL_CONFIG["temperature"],
        "top_p": MODEL_CONFIG["top_p"],
        "system_instruction": prompt,
        "response_mime_type": "application/json",
    }
    if thinking_budget is not None:
        config_kwargs["thinking_config"] = types.ThinkingConfig(thinking_budget=thinking_budget)

    response = client.models.generate_content(
        model=model_name or _load_default_model_from_db() or get_model_name(),
        contents=[types.Part.from_text(text=selected_text)],
        config=types.GenerateContentConfig(**config_kwargs),
    )

    try:
        return _parse_response_json(response.text)
    except ValueError:
        _save_unparseable_response(response.text)
        raise


def _save_unparseable_response(raw_text: str) -> None:
    """Keep the raw text Gemini returned when every parse strategy fails, so a
    failure can actually be diagnosed afterwards instead of only seeing the
    parser's error message."""
    try:
        from datetime import datetime, timezone

        debug_dir = BASE_DIR / "output" / "unparseable_responses"
        debug_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        (debug_dir / f"{timestamp}.txt").write_text(raw_text or "", encoding="utf-8")
    except Exception:
        pass  # Debug aid only — never let this mask the original parse error.
