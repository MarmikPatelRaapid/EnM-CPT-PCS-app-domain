"""Expand combined patient_type/mdm_level values into separate CSV rows."""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Dict, List

BASE_DIR = Path(__file__).resolve().parent
INPUT_CSV_PATH = BASE_DIR / "E&M Data - E&M Mapping 3.csv"
OUTPUT_CSV_PATH = BASE_DIR / "E&M Data - E&M Mapping 3 processed.csv"


def split_patient_type(value: str) -> List[str]:
    text = (value or "").strip()
    if " or " not in text:
        return [text]

    parts = [part.strip() for part in text.split(" or ") if part.strip()]
    if text in {"New or Established", "New or Established Patient"}:
        return ["New Patient", "Established Patient"]
    if text.endswith(" Patient"):
        parts = [part if part.endswith("Patient") else f"{part} Patient" for part in parts]
    return parts


def split_simple_or(value: str) -> List[str]:
    text = (value or "").strip()
    if " or " not in text:
        return [text]
    return [part.strip() for part in text.split(" or ") if part.strip()]


def expand_row(row: Dict[str, str]) -> List[Dict[str, str]]:
    patient_types = split_patient_type(row.get("patient_type", ""))
    mdm_levels = split_simple_or(row.get("mdm_level", ""))

    expanded_rows: List[Dict[str, str]] = []
    for patient_type in patient_types:
        for mdm_level in mdm_levels:
            new_row = dict(row)
            new_row["patient_type"] = patient_type
            new_row["mdm_level"] = mdm_level
            expanded_rows.append(new_row)
    return expanded_rows


def process_csv(input_path: Path, output_path: Path) -> int:
    with input_path.open("r", encoding="utf-8-sig", newline="") as input_file:
        reader = csv.DictReader(input_file)
        if reader.fieldnames is None:
            raise ValueError(f"CSV file '{input_path}' does not contain headers.")

        rows: List[Dict[str, str]] = []
        for row in reader:
            rows.extend(expand_row(row))

    with output_path.open("w", encoding="utf-8", newline="") as output_file:
        writer = csv.DictWriter(output_file, fieldnames=reader.fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    return len(rows)


def main() -> int:
    row_count = process_csv(INPUT_CSV_PATH, OUTPUT_CSV_PATH)
    print(f"Wrote {row_count} rows to {OUTPUT_CSV_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
