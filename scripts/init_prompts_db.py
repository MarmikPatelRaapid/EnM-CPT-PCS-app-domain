"""One-time/idempotent seeder: loads all prompt .txt files into prompts.db.

Run with: python scripts/init_prompts_db.py
"""
from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DB_PATH = ROOT / "prompts.db"

# (service, key, file path relative to ROOT)
PROMPT_FILES = [
    (
        "cpt_synthetic",
        "system_prompt",
        "CPT_backend/CPT_Synthetic_data_generation/prompts/CPT_synthetic_data_generation_prompt.txt",
    ),
    (
        "cpt_pipeline",
        "model_1_system_prompt",
        "CPT_backend/CPT_pipeline/prompts/model_1_system_prompt.txt",
    ),
    (
        "cpt_pipeline",
        "model_2_system_prompt",
        "CPT_backend/CPT_pipeline/prompts/model_2_system_prompt.txt",
    ),
    (
        "em_synthetic",
        "system_prompt",
        "E&M_backend/E&M_Synthetic_data_generation/prompts/EandM_synthetic_data_generation_prompt.txt",
    ),
    (
        "em_evidence",
        "prompt",
        "E&M_backend/E&M_evidence_predictions/prompt.txt",
    ),
    (
        "pcs_synthetic",
        "system_prompt",
        "PCS_backend/PCS_synthetic_document_generation/prompts/pcs_synthetic_data_generation_prompt.txt",
    ),
    (
        "pcs_detection",
        "Agent 1 - ICD-10-PCS Code Suggestion Prompt.txt",
        "PCS_backend/PCS_Code_Detection/prompts/Agent 1 - ICD-10-PCS Code Suggestion Prompt.txt",
    ),
    (
        "pcs_detection",
        "Agent 2 - ICD-10-PCS Dynamic Code Detection Prompt.txt",
        "PCS_backend/PCS_Code_Detection/prompts/Agent 2 - ICD-10-PCS Dynamic Code Detection Prompt.txt",
    ),
]


def main() -> None:
    conn = sqlite3.connect(str(DB_PATH))
    try:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS prompts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                service TEXT NOT NULL,
                key TEXT NOT NULL,
                content TEXT NOT NULL,
                source_path TEXT,
                updated_at TEXT NOT NULL,
                UNIQUE(service, key)
            )
            """
        )

        now = datetime.now(timezone.utc).isoformat()
        for service, key, rel_path in PROMPT_FILES:
            file_path = ROOT / rel_path
            if not file_path.exists():
                print(f"SKIP (missing file): {rel_path}")
                continue
            content = file_path.read_text(encoding="utf-8")
            conn.execute(
                """
                INSERT INTO prompts (service, key, content, source_path, updated_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(service, key) DO UPDATE SET
                    content = excluded.content,
                    source_path = excluded.source_path,
                    updated_at = excluded.updated_at
                """,
                (service, key, content, rel_path, now),
            )
            print(f"Loaded: service={service} key={key!r} ({len(content)} chars)")

        conn.commit()
    finally:
        conn.close()

    print(f"\nDatabase ready at: {DB_PATH}")


if __name__ == "__main__":
    main()
