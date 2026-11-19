import json
import os
import re
import sqlite3
from concurrent.futures import ThreadPoolExecutor
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


PROJECT_ID = os.getenv("VERTEX_PROJECT_ID", "raapid-genai")
LOCATION = os.getenv("VERTEX_LOCATION", "global")

TEMPERATURE = 0.25
TOP_P = 0.15

BASE_DIR = Path(__file__).resolve().parent

# E&M evidence extraction runs as two independent, parallel Gemini calls
# against the same document instead of one mega-prompt: prompt_1 pulls visit
# info/time/demographics (light extraction, low thinking suffices), prompt_2
# pulls MDM (problems/data/risk — denser reasoning, so medium thinking). Each
# call's own default is intentionally fixed here rather than resolved from
# the shared DB dropdown default (dropdown_options), since that single
# global default can't represent "low for call 1, medium for call 2" at
# once. An explicit per-request override (from the UI or a batch run) still
# applies to both calls identically.
PROMPT_CALLS = {
    "prompt_1": {"default_model": "gemini-3.8-flash", "default_thinking_budget": 1024},
    "prompt_2": {"default_model": "gemini-3.8-flash", "default_thinking_budget": 4096},
}


_CONTROL_CHAR_ESCAPES = {
    "\n": "\\n",
    "\r": "\\r",
    "\t": "\\t",
    "\b": "\\b",
    "\f": "\\f",
}


def _escape_stray_quotes(text: str) -> str:
    """Best-effort repair for the two most common ways loose (schema-less)
    Gemini JSON mode breaks a response that was otherwise meant to be valid
    JSON:

    1. A verbatim document snippet copied into a string value contains a
       literal `"` the model didn't escape, prematurely terminating the
       JSON string and desyncing the rest of the parse.
    2. The model emits a literal newline/tab/etc. *inside* a string value
       instead of escaping it as `\\n`/`\\t` — raw control characters are
       themselves illegal inside a JSON string.

    Walks the text tracking string/escape state. A `"` encountered while
    inside a string is only treated as the real closing quote when the next
    non-whitespace character looks like valid JSON structure (`,`, `}`, `]`,
    `:`, or end of input) — otherwise it's a stray quote and gets escaped.
    Any raw control character encountered while inside a string gets escaped
    to its proper JSON representation.
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
        if in_string and ch in _CONTROL_CHAR_ESCAPES:
            result.append(_CONTROL_CHAR_ESCAPES[ch])
            i += 1
            continue
        if in_string and ord(ch) < 0x20:
            result.append(f"\\u{ord(ch):04x}")
            i += 1
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


def _run_prompt_call(
    call_key: str,
    document_text: str,
    model_name: str | None,
    thinking_budget: int | None,
) -> dict:
    call_config = PROMPT_CALLS[call_key]
    prompt = _load_prompt_from_db("em_evidence", call_key)
    if not prompt:
        raise ValueError(f"Prompt not found in prompts.db: service='em_evidence' key='{call_key}'")

    resolved_model = model_name or call_config["default_model"]
    resolved_thinking = (
        thinking_budget if thinking_budget is not None else call_config["default_thinking_budget"]
    )

    client = genai.Client(
        vertexai=True,
        project=PROJECT_ID,
        location=LOCATION,
    )

    config_kwargs: dict = {
        "temperature": TEMPERATURE,
        "top_p": TOP_P,
        "system_instruction": prompt,
        "response_mime_type": "application/json",
    }
    if resolved_thinking is not None:
        config_kwargs["thinking_config"] = types.ThinkingConfig(thinking_budget=resolved_thinking)

    response = client.models.generate_content(
        model=resolved_model,
        contents=[types.Part.from_text(text=document_text)],
        config=types.GenerateContentConfig(**config_kwargs),
    )

    try:
        return _parse_response_json(response.text)
    except ValueError:
        _save_unparseable_response(call_key, response.text)
        raise


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

    # The two calls extract disjoint top-level fields from the same
    # document (visit info/time/demographics vs. MDM), so they run in
    # parallel and their results are simply merged — the downstream
    # resolver already expects one object with both sets of keys.
    with ThreadPoolExecutor(max_workers=2) as executor:
        future_1 = executor.submit(_run_prompt_call, "prompt_1", selected_text, model_name, thinking_budget)
        future_2 = executor.submit(_run_prompt_call, "prompt_2", selected_text, model_name, thinking_budget)
        result_1 = future_1.result()
        result_2 = future_2.result()

    return {**result_1, **result_2}


def _save_unparseable_response(call_key: str, raw_text: str) -> None:
    """Keep the raw text Gemini returned when every parse strategy fails, so a
    failure can actually be diagnosed afterwards instead of only seeing the
    parser's error message."""
    try:
        from datetime import datetime, timezone

        debug_dir = BASE_DIR / "output" / "unparseable_responses"
        debug_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        (debug_dir / f"{timestamp}_{call_key}.txt").write_text(raw_text or "", encoding="utf-8")
    except Exception:
        pass  # Debug aid only — never let this mask the original parse error.
