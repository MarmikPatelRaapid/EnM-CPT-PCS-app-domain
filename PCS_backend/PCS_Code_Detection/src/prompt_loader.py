import json
import sqlite3
from pathlib import Path

PROMPT_DIR = Path(__file__).parent.parent / "prompts"
SCHEMA_DIR = Path(__file__).parent.parent / "schemas"


def _find_repo_root(start: Path) -> Path:
    current = start
    for _ in range(8):
        if (current / "prompts.db").exists():
            return current
        current = current.parent
    raise FileNotFoundError("Could not locate repository root containing prompts.db")


def fetch_prompt(prompt_name: str) -> str:
    db_path = _find_repo_root(Path(__file__).resolve()) / "prompts.db"
    conn = sqlite3.connect(str(db_path))
    try:
        row = conn.execute(
            "SELECT content FROM prompts WHERE service = ? AND key = ?",
            ("pcs_detection", prompt_name),
        ).fetchone()
    finally:
        conn.close()
    if row is not None:
        return row[0]

    path = PROMPT_DIR / prompt_name
    return path.read_text(encoding="utf-8")


def fetch_schema(schema_name: str) -> dict:
    db_path = _find_repo_root(Path(__file__).resolve()) / "prompts.db"
    conn = sqlite3.connect(str(db_path))
    try:
        row = conn.execute(
            "SELECT content FROM schemas WHERE service = ? AND key = ?",
            ("pcs_detection", schema_name),
        ).fetchone()
    finally:
        conn.close()
    if row is not None:
        return json.loads(row[0])

    path = SCHEMA_DIR / f"{schema_name}.json"
    return json.loads(path.read_text(encoding="utf-8"))
