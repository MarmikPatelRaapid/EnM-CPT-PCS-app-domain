from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class SyntheticSettings:
    vertex_project_id: str
    vertex_location: str
    vertex_serving_mode: str
    model_name: str
    temperature: float
    top_p: float
    prompt_path: str
    schema_path: str


def _strip_wrapping_quotes(value: str) -> str:
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        return value[1:-1]
    return value


def _load_dotenv_file() -> None:
    """Load CPT_backend/.env into os.environ without overriding existing vars."""
    project_root = Path(__file__).resolve().parent.parent
    dotenv_path = project_root / ".env"
    if not dotenv_path.exists():
        return

    for raw_line in dotenv_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export ") :].strip()
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if not key:
            continue
        if key in os.environ:
            continue
        os.environ[key] = _strip_wrapping_quotes(value)


def _resolve_path(path_value: str, base_dir: Path) -> str:
    candidate = Path(path_value)
    if candidate.is_absolute():
        return str(candidate)
    return str((base_dir / candidate).resolve())


def load_settings() -> SyntheticSettings:
    _load_dotenv_file()
    base_dir = Path(__file__).resolve().parent

    return SyntheticSettings(
        vertex_project_id=os.getenv("VERTEX_PROJECT_ID", "").strip(),
        vertex_location=os.getenv("VERTEX_LOCATION", "global").strip(),
        vertex_serving_mode=os.getenv("VERTEX_SERVING_MODE", "on_demand").strip(),
        model_name=os.getenv("CPT_SYNTH_MODEL_NAME", "gemini-2.5-flash").strip(),
        temperature=float(os.getenv("CPT_SYNTH_TEMPERATURE", "0.45")),
        top_p=float(os.getenv("CPT_SYNTH_TOP_P", "0.4")),
        prompt_path=_resolve_path(
            os.getenv(
                "CPT_SYNTH_PROMPT_PATH",
                "prompts/CPT_synthetic_data_generation_prompt.txt",
            ),
            base_dir,
        ),
        schema_path=_resolve_path(
            os.getenv(
                "CPT_SYNTH_SCHEMA_PATH",
                "prompts/output_schema.json",
            ),
            base_dir,
        ),
    )
