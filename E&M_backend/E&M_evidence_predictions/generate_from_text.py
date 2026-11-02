import json
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


PROJECT_ID = "raapid-genai"
LOCATION = "global"

MODEL_CONFIG = {
    "serving_mode": "on_demand",  # "on_demand" or "endpoint"
    "model_name": "gemini-2.5-pro",
    "endpoint_name": "",
    "temperature": 0.25,
    "top_p": 0.15,
}

BASE_DIR = Path(__file__).resolve().parent
INPUT_DIR = BASE_DIR / "input"
OUTPUT_DIR = BASE_DIR / "output"
JSON_OUTPUT_DIR = OUTPUT_DIR / "json_outputs"

PROMPT_FILE = BASE_DIR / "prompt.txt"
OUTPUT_SCHEMA_FILE = BASE_DIR / "output_schema.json"


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


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def read_json(path: Path) -> dict:
    with open(path, "r", encoding="utf-8") as fp:
        return json.load(fp)


def write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as fp:
        json.dump(data, fp, indent=2, ensure_ascii=False)


def load_input_text_files(input_dir: Path) -> list[Path]:
    files = sorted(input_dir.glob("*.txt"))
    if not files:
        raise FileNotFoundError(f"No text files found in: {input_dir}")
    return files


def parse_response_json(response_text: str) -> dict:
    text = response_text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    fenced_match = re.search(r"```(?:json)?\s*(.*?)```", text, flags=re.DOTALL | re.IGNORECASE)
    if fenced_match:
        fenced_text = fenced_match.group(1).strip()
        return json.loads(fenced_text)

    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        return json.loads(text[start : end + 1])

    raise ValueError("Model response is not valid JSON.")


def generate_output() -> None:
    prompt = _load_prompt_from_db("em_evidence", "prompt")
    output_schema = read_json(OUTPUT_SCHEMA_FILE)
    input_text_files = load_input_text_files(INPUT_DIR)

    client = genai.Client(
        vertexai=True,
        project=PROJECT_ID,
        location=LOCATION,
    )

    saved_files: list[Path] = []
    for input_path in input_text_files:
        input_text = read_text(input_path)
        response = client.models.generate_content(
            model=get_model_name(),
            contents=[types.Part.from_text(text=input_text)],
            config=types.GenerateContentConfig(
                temperature=MODEL_CONFIG["temperature"],
                top_p=MODEL_CONFIG["top_p"],
                system_instruction=prompt,
                response_mime_type="application/json",
                response_schema=output_schema,
            ),
        )

        output_json = parse_response_json(response.text)
        output_path = JSON_OUTPUT_DIR / f"{input_path.stem}_output.json"
        write_json(output_path, output_json)
        saved_files.append(output_path)

    print(f"Saved {len(saved_files)} output JSON file(s) in: {JSON_OUTPUT_DIR}")


def main() -> None:
    generate_output()


if __name__ == "__main__":
    main()
