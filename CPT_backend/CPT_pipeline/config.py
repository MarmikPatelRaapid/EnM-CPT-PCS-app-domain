from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


@dataclass(frozen=True)
class Settings:
    vertex_project_id: str
    vertex_location: str
    vertex_serving_mode: str
    model_1_name: str
    model_2_name: str
    model_1_temperature: float
    model_1_top_p: float
    model_2_temperature: float
    model_2_top_p: float
    retrieval_url: str
    top_k: int
    retrieval_connect_timeout_seconds: float
    retrieval_read_timeout_seconds: Optional[float]
    retrieval_write_timeout_seconds: float
    retrieval_pool_timeout_seconds: float
    retrieval_concurrency_limit: int
    save_intermediate_outputs: bool
    intermediate_output_dir: str
    model_1_prompt_path: str
    model_2_prompt_path: str
    model_1_schema_path: str
    model_2_schema_path: str


def _strip_wrapping_quotes(value: str) -> str:
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        return value[1:-1]
    return value


def _load_dotenv_file() -> None:
    """Load .env from project root into os.environ without overriding existing vars."""
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


def _parse_optional_timeout_seconds(value: str, default: Optional[float]) -> Optional[float]:
    raw = value.strip().lower()
    if raw in {"", "none", "null"}:
        return default
    return float(raw)


def _parse_bool(value: str, default: bool) -> bool:
    raw = value.strip().lower()
    if raw in {"1", "true", "yes", "y", "on"}:
        return True
    if raw in {"0", "false", "no", "n", "off"}:
        return False
    return default


def _resolve_path(path_value: str, base_dir: Path) -> str:
    candidate = Path(path_value)
    if candidate.is_absolute():
        return str(candidate)
    return str((base_dir / candidate).resolve())


def load_settings() -> Settings:
    _load_dotenv_file()
    project_root = Path(__file__).resolve().parent.parent
    base_prompt_dir = _resolve_path(
        os.getenv("CPT_PROMPT_DIR", "CPT_pipeline/prompts"),
        project_root,
    )
    top_k = int(os.getenv("CPT_TOP_K", "5"))

    return Settings(
        vertex_project_id=os.getenv("VERTEX_PROJECT_ID", "").strip(),
        vertex_location=os.getenv("VERTEX_LOCATION", "us-central1").strip(),
        vertex_serving_mode=os.getenv("VERTEX_SERVING_MODE", "on_demand").strip(),
        model_1_name=os.getenv("CPT_MODEL_1_NAME", "gemini-2.5-flash"),
        model_2_name=os.getenv("CPT_MODEL_2_NAME", "gemini-2.5-flash"),
        model_1_temperature=float(os.getenv("CPT_MODEL_1_TEMPERATURE", "0.2")),
        model_1_top_p=float(os.getenv("CPT_MODEL_1_TOP_P", "0.95")),
        model_2_temperature=float(os.getenv("CPT_MODEL_2_TEMPERATURE", "0.2")),
        model_2_top_p=float(os.getenv("CPT_MODEL_2_TOP_P", "0.95")),
        retrieval_url=os.getenv(
            "CPT_RETRIEVAL_URL",
            "http://localhost:8083/retrieve",
        ).strip(),
        top_k=max(1, top_k),
        retrieval_connect_timeout_seconds=float(
            os.getenv("CPT_RETRIEVAL_CONNECT_TIMEOUT_SECONDS", "10")
        ),
        retrieval_read_timeout_seconds=_parse_optional_timeout_seconds(
            os.getenv("CPT_RETRIEVAL_READ_TIMEOUT_SECONDS", "none"),
            default=None,
        ),
        retrieval_write_timeout_seconds=float(
            os.getenv("CPT_RETRIEVAL_WRITE_TIMEOUT_SECONDS", "30")
        ),
        retrieval_pool_timeout_seconds=float(
            os.getenv("CPT_RETRIEVAL_POOL_TIMEOUT_SECONDS", "30")
        ),
        retrieval_concurrency_limit=max(
            1,
            int(os.getenv("CPT_RETRIEVAL_CONCURRENCY_LIMIT", "8")),
        ),
        save_intermediate_outputs=_parse_bool(
            os.getenv("CPT_SAVE_INTERMEDIATE_OUTPUTS", "true"),
            default=True,
        ),
        intermediate_output_dir=_resolve_path(
            os.getenv("CPT_INTERMEDIATE_OUTPUT_DIR", "CPT_pipeline/request_outputs"),
            project_root,
        ),
        model_1_prompt_path=_resolve_path(
            os.getenv(
                "CPT_MODEL_1_PROMPT_PATH",
                f"{base_prompt_dir}/model_1_system_prompt.txt",
            ),
            project_root,
        ),
        model_2_prompt_path=_resolve_path(
            os.getenv(
                "CPT_MODEL_2_PROMPT_PATH",
                f"{base_prompt_dir}/model_2_system_prompt.txt",
            ),
            project_root,
        ),
        model_1_schema_path=_resolve_path(
            os.getenv(
                "CPT_MODEL_1_SCHEMA_PATH",
                f"{base_prompt_dir}/model_1_response_schema.json",
            ),
            project_root,
        ),
        model_2_schema_path=_resolve_path(
            os.getenv(
                "CPT_MODEL_2_SCHEMA_PATH",
                f"{base_prompt_dir}/model_2_response_schema.json",
            ),
            project_root,
        ),
    )

