import json
import re
import sys
from pathlib import Path

from google import genai
from google.genai import types

BASE_DIR = Path(__file__).resolve().parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from config import load_settings

SETTINGS = load_settings()
PROJECT_ID = SETTINGS.vertex_project_id
LOCATION = SETTINGS.vertex_location

MODEL_CONFIG = {
    "serving_mode": "on_demand",
    "model_name": "gemini-2.5-flash",
    "endpoint_name": "",
    "temperature": 0.2,
}

INPUT_DIR = BASE_DIR / "input"
OUTPUT_DIR = BASE_DIR / "output"
JSON_OUTPUT_DIR = OUTPUT_DIR / "json_outputs"
TEXT_OUTPUT_DIR = OUTPUT_DIR / "text_outputs"

PROMPT_FILE = SETTINGS.prompt_path
OUTPUT_SCHEMA_FILE = SETTINGS.schema_path


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


def read_json(path: str | Path) -> dict:
    with open(path, "r", encoding="utf-8") as fp:
        return json.load(fp)


def read_text(path: str | Path) -> str:
    return Path(path).read_text(encoding="utf-8")


def write_json(path: str | Path, data: dict) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as fp:
        json.dump(data, fp, indent=2, ensure_ascii=False)


def write_text(path: str | Path, content: str) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def load_input_json_files(input_dir: Path) -> list[Path]:
    files = sorted(input_dir.glob("*.json"))
    if not files:
        raise FileNotFoundError(f"No JSON files found in: {input_dir}")
    return files


def build_user_input(input_json: dict) -> str:
    return json.dumps(input_json, indent=2)


def normalize_em_code(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9]+", "_", value.strip().lower()).strip("_")
    return cleaned or "no_em"


def save_generated_documents(input_name: str, output_json: dict) -> int:
    documents = output_json.get("documents", [])
    em_counts: dict[str, int] = {}
    saved_count = 0

    for doc in documents:
        generated_text = str(doc.get("generated_document", "")).strip()
        if not generated_text:
            continue

        em_code = normalize_em_code(str(doc.get("e&mcode", "")))
        em_counts[em_code] = em_counts.get(em_code, 0) + 1
        index = em_counts[em_code]

        filename = f"{em_code}_synthetic_text_{index}.txt"
        write_text(TEXT_OUTPUT_DIR / input_name / filename, generated_text)
        saved_count += 1

    return saved_count


def generate_output() -> None:
    prompt = read_text(PROMPT_FILE)
    output_schema = read_json(OUTPUT_SCHEMA_FILE)
    input_json_files = load_input_json_files(INPUT_DIR)
    system_prompt = prompt

    client = genai.Client(
        vertexai=True,
        project=PROJECT_ID,
        location=LOCATION,
    )

    saved_files: list[Path] = []
    saved_text_count = 0
    for input_path in input_json_files:
        input_json = read_json(input_path)
        response = client.models.generate_content(
            model=get_model_name(),
            contents=[
                types.Part.from_text(
                    text=build_user_input(input_json)
                )
            ],
            config=types.GenerateContentConfig(
                temperature=MODEL_CONFIG["temperature"],
                system_instruction=system_prompt,
                response_mime_type="application/json",
                response_schema=output_schema,
            ),
        )

        output_json = json.loads(response.text)
        output_file = JSON_OUTPUT_DIR / f"{input_path.stem}_output.json"
        write_json(output_file, output_json)
        saved_files.append(output_file)
        saved_text_count += save_generated_documents(input_path.stem, output_json)

    print(f"Saved {len(saved_files)} output JSON file(s) in: {JSON_OUTPUT_DIR}")
    print(f"Saved {saved_text_count} synthetic text file(s) in: {TEXT_OUTPUT_DIR}")


def main() -> None:
    generate_output()


if __name__ == "__main__":
    main()
