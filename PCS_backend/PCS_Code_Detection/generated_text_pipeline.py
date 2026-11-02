import asyncio
import sqlite3
from pathlib import Path

import config
from src.agents.agent1 import run_agent1
from src.llm.base import get_provider
from src.pcs_resources import PCSResources
from src.result_collector import classify
from src.tree.models import PCSNode
from src.tree.traversal import expand_node


def _find_repo_root(start: Path) -> Path:
    current = start
    for _ in range(8):
        if (current / "prompts.db").exists():
            return current
        current = current.parent
    raise FileNotFoundError("Could not locate repository root containing prompts.db")


def _load_default_model_from_db() -> str | None:
    """The DB-backed dropdown is the single source of truth for which model
    to use by default; falls back to None (caller uses config.MODEL_NAME)
    only if the DB has no default row configured."""
    db_path = _find_repo_root(Path(__file__).resolve()) / "prompts.db"
    conn = sqlite3.connect(str(db_path))
    try:
        row = conn.execute(
            "SELECT value FROM dropdown_options WHERE category = 'model' AND is_default = 1"
        ).fetchone()
    finally:
        conn.close()
    return row[0] if row and row[0] else None


class GeneratedTextPipelineError(Exception):
    """Raised when generated text pipeline input is invalid."""


def _validate_generated_text(generated_text: str) -> str:
    if not isinstance(generated_text, str):
        raise GeneratedTextPipelineError("`generated_text` must be a string.")
    cleaned = generated_text.strip()
    if not cleaned:
        raise GeneratedTextPipelineError("`generated_text` cannot be empty.")
    return cleaned


async def run_generated_text_pipeline(
    generated_text: str,
    model_name: str | None = None,
    thinking_budget: int | None = None,
) -> dict:
    """
    Run PCS code detection from generated text without filesystem input.

    This mirrors the orchestration in `main.run`, but uses a synthetic single-page
    input map instead of `read_document_dir`.
    """
    cleaned_text = _validate_generated_text(generated_text)
    pages = {1: cleaned_text}

    previous_model_name = config.MODEL_NAME
    previous_thinking_budget = getattr(config, "THINKING_BUDGET", None)
    resolved_model_name = model_name or _load_default_model_from_db()
    if resolved_model_name is not None:
        config.MODEL_NAME = resolved_model_name
    if thinking_budget is not None:
        config.THINKING_BUDGET = thinking_budget

    try:
        llm = get_provider()
        resources = PCSResources()

        procedures = await run_agent1(pages, llm)
        semaphore = asyncio.Semaphore(config.MAX_CONCURRENCY)

        root_tasks = []
        for proc in procedures:
            root_tasks.append(
                expand_node(
                    PCSNode(proc, current_code="", accumulated_evidences={}),
                    pages,
                    resources,
                    llm,
                    semaphore,
                )
            )

        all_batches = await asyncio.gather(*root_tasks)
        all_codes = [code for batch in all_batches for code in batch]
        return classify(all_codes)
    finally:
        config.MODEL_NAME = previous_model_name
        config.THINKING_BUDGET = previous_thinking_budget

