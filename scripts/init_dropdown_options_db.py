"""One-time/idempotent seeder: loads model & thinking-budget dropdown options
into prompts.db, so the frontend reads its choices (and defaults) from the DB
instead of a hardcoded list.

Run with: python scripts/init_dropdown_options_db.py
"""
from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DB_PATH = ROOT / "prompts.db"

# (category, label, value, is_default, sort_order)
OPTIONS = [
    ("model", "Service default", "", 0, 0),
    ("model", "Gemini 3.8 Flash", "gemini-3.8-flash", 1, 1),
    ("model", "Gemini 2.5 Flash", "gemini-2.5-flash", 0, 2),
    ("model", "Gemini 2.5 Pro", "gemini-2.5-pro", 0, 3),
    ("thinking_budget", "Service default", "", 0, 0),
    ("thinking_budget", "Dynamic", "-1", 0, 1),
    ("thinking_budget", "Off", "0", 0, 2),
    ("thinking_budget", "Low (1,024)", "1024", 1, 3),
    ("thinking_budget", "Medium (4,096)", "4096", 0, 4),
    ("thinking_budget", "High (16,384)", "16384", 0, 5),
]


def main() -> None:
    conn = sqlite3.connect(str(DB_PATH))
    try:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS dropdown_options (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                category TEXT NOT NULL,
                label TEXT NOT NULL,
                value TEXT NOT NULL,
                is_default INTEGER NOT NULL DEFAULT 0,
                sort_order INTEGER NOT NULL DEFAULT 0,
                updated_at TEXT NOT NULL,
                UNIQUE(category, value)
            )
            """
        )

        now = datetime.now(timezone.utc).isoformat()
        for category, label, value, is_default, sort_order in OPTIONS:
            conn.execute(
                """
                INSERT INTO dropdown_options (category, label, value, is_default, sort_order, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(category, value) DO UPDATE SET
                    label = excluded.label,
                    is_default = excluded.is_default,
                    sort_order = excluded.sort_order,
                    updated_at = excluded.updated_at
                """,
                (category, label, value, is_default, sort_order, now),
            )
            print(f"Loaded: category={category!r} label={label!r} value={value!r} default={bool(is_default)}")

        conn.commit()
    finally:
        conn.close()

    print(f"\nDatabase ready at: {DB_PATH}")


if __name__ == "__main__":
    main()
