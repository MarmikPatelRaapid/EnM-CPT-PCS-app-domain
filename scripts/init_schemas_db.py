"""One-time/idempotent seeder: loads all response-schema .json files into prompts.db.

Run with: python scripts/init_schemas_db.py
"""
from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DB_PATH = ROOT / "prompts.db"

# (service, key, file path relative to ROOT)
SCHEMA_FILES = [
    (
        "cpt_synthetic",
        "output_schema",
        "CPT_backend/CPT_Synthetic_data_generation/prompts/output_schema.json",
    ),
    (
        "cpt_pipeline",
        "model_1_response_schema",
        "CPT_backend/CPT_pipeline/prompts/model_1_response_schema.json",
    ),
    (
        "cpt_pipeline",
        "model_2_response_schema",
        "CPT_backend/CPT_pipeline/prompts/model_2_response_schema.json",
    ),
    (
        "em_synthetic",
        "output_schema",
        "E&M_backend/E&M_Synthetic_data_generation/prompts/output_schema.json",
    ),
    (
        "pcs_detection",
        "agent_1_schema",
        "PCS_backend/PCS_Code_Detection/schemas/agent_1_schema.json",
    ),
    (
        "pcs_detection",
        "agent_2_schema",
        "PCS_backend/PCS_Code_Detection/schemas/agent_2_schema.json",
    ),
]


def main() -> None:
    conn = sqlite3.connect(str(DB_PATH))
    try:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS schemas (
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
        for service, key, rel_path in SCHEMA_FILES:
            file_path = ROOT / rel_path
            if not file_path.exists():
                print(f"SKIP (missing file): {rel_path}")
                continue
            content = file_path.read_text(encoding="utf-8")
            conn.execute(
                """
                INSERT INTO schemas (service, key, content, source_path, updated_at)
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
