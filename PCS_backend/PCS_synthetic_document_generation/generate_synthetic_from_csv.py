import csv
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Dict, List, Tuple

from pcs_synthetic_data_generator import PCSGenerationError, generate_pcs_synthetic_data


BASE_DIR = Path(__file__).resolve().parent
CSV_FILE_PATH = BASE_DIR / "ICD-10-PCS  Sample Data - Sheet1.csv"
OUTPUT_DIR = BASE_DIR / "generated_documents"
TOTAL_NO_OF_DOCUMENTS = 2
MAX_WORKERS = 16


def _sanitize_for_filename(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9]+", "_", value.strip())
    return re.sub(r"_+", "_", cleaned).strip("_")


def _build_payload(row: Dict[str, str]) -> Dict[str, object]:
    codes = (row.get("Codes") or "").strip()
    category = (row.get("Category") or "").strip()
    if not codes or not category:
        raise ValueError("Row is missing Codes or Category value.")
    return {
        "code_category": [category],
        "icd10_pcs_code": codes,
        "total_no_of_documents": TOTAL_NO_OF_DOCUMENTS,
    }


def _save_documents(
    codes: str,
    category: str,
    documents: List[Dict[str, str]],
) -> List[Path]:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    codes_key = _sanitize_for_filename(codes)
    category_key = _sanitize_for_filename(category)
    saved_paths: List[Path] = []

    for document_number, doc in enumerate(documents, start=1):
        text = (doc.get("generated_document") or "").strip()
        if not text:
            continue
        file_name = f"{codes_key}_{category_key}_{document_number}.txt"
        file_path = OUTPUT_DIR / file_name
        file_path.write_text(text, encoding="utf-8")
        saved_paths.append(file_path)

    return saved_paths


def _process_row(row: Dict[str, str], row_number: int) -> Tuple[int, int, str]:
    payload = _build_payload(row)
    result = generate_pcs_synthetic_data(payload)
    documents = result.get("documents", [])
    saved = _save_documents(row["Codes"], row["Category"], documents)
    return row_number, len(saved), row["Codes"]


def main() -> None:
    if not CSV_FILE_PATH.exists():
        raise FileNotFoundError(f"CSV file not found: {CSV_FILE_PATH}")

    with CSV_FILE_PATH.open("r", encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))

    if not rows:
        print("No rows found in CSV.")
        return

    futures = []
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        for idx, row in enumerate(rows, start=2):
            futures.append(executor.submit(_process_row, row, idx))

        for future in as_completed(futures):
            try:
                row_number, saved_count, codes = future.result()
                print(f"Row {row_number} ({codes}): saved {saved_count} document(s).")
            except (PCSGenerationError, ValueError, KeyError) as exc:
                print(f"Failed row: {exc}")
            except Exception as exc:
                print(f"Unexpected failure: {exc}")


if __name__ == "__main__":
    main()
