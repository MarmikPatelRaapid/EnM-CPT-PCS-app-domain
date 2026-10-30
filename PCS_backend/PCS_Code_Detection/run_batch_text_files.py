"""
Batch runner for flat .txt inputs.

Input layout:
    <root_dir>/
        *.txt

Output layout:
    <output_root>/<input_file_stem>/
        agent1_ner.json
        pcs_codes.json

Also writes:
    <output_root>/prediction_report.csv
"""

import asyncio
import csv
import json
from dataclasses import asdict
from pathlib import Path

import config
from src.agents.agent1 import run_agent1
from src.llm.base import get_provider
from src.pcs_resources import PCSResources
from src.result_collector import classify
from src.tree.models import PCSNode
from src.tree.traversal import expand_node

# ---------------------------
# Configure paths here
# ---------------------------
PROJECT_ROOT = Path(__file__).resolve().parent.parent
INPUT_ROOT_DIR = PROJECT_ROOT / "PCS_synthetic_document_generation" / "generated_documents"
OUTPUT_ROOT_DIR = INPUT_ROOT_DIR / "batch_output"
FILE_CONCURRENCY = 8


def _extract_expected_code(input_file: Path) -> str:
    # Expected format: <expected_code>_anything.txt
    return input_file.stem.split("_", 1)[0]


def _collect_predicted_codes(result: dict) -> list[tuple[str, str]]:
    rows: list[tuple[str, str]] = []
    for entry in result.get("billable", []):
        code = entry.get("code", "")
        if code:
            rows.append((code, "billable"))
    for entry in result.get("non_billable", []):
        code = entry.get("code", "")
        if code:
            rows.append((code, "non_billable"))
    return rows


def _rows_for_report(input_filename: str, expected_code: str, predicted_codes: list[tuple[str, str]]) -> list[dict]:
    rows: list[dict] = []
    seen_codes: set[str] = set()
    unique_predicted: list[tuple[str, str]] = []
    for code, code_type in predicted_codes:
        if code not in seen_codes:
            seen_codes.add(code)
            unique_predicted.append((code, code_type))

    has_match = any(code == expected_code for code, _ in unique_predicted)
    for code, code_type in unique_predicted:
        rows.append(
            {
                "input_filename": input_filename,
                "expected_code": expected_code,
                "predicted_code": code,
                "predicted_code_type": code_type,
                "status": "match" if code == expected_code else "extra",
            }
        )

    if not has_match:
        rows.append(
            {
                "input_filename": input_filename,
                "expected_code": expected_code,
                "predicted_code": "",
                "predicted_code_type": "",
                "status": "miss",
            }
        )

    return rows


async def _process_one_file(
    input_file: Path,
    output_root: Path,
    resources: PCSResources,
    llm,
    tree_semaphore: asyncio.Semaphore,
    file_semaphore: asyncio.Semaphore,
) -> tuple[str, str, list[tuple[str, str]]]:
    async with file_semaphore:
        out_dir = output_root / input_file.stem
        out_dir.mkdir(parents=True, exist_ok=True)
        ner_out = out_dir / "agent1_ner.json"
        codes_out = out_dir / "pcs_codes.json"
        expected_code = _extract_expected_code(input_file)

        if ner_out.exists() and codes_out.exists():
            try:
                existing_result = json.loads(codes_out.read_text(encoding="utf-8"))
                predicted_codes = _collect_predicted_codes(existing_result)
                print(f"[SKIP] Already processed -> {input_file.name}")
                return (input_file.name, expected_code, predicted_codes)
            except Exception:
                # If output exists but is unreadable/corrupt, regenerate.
                print(f"[REPROCESS] Corrupt output detected -> {input_file.name}")

        text = input_file.read_text(encoding="utf-8")
        pages = {1: text}

        procedures = await run_agent1(pages, llm)
        ner_out.write_text(
            json.dumps([asdict(p) for p in procedures], indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

        root_tasks = [
            expand_node(
                PCSNode(proc, current_code="", accumulated_evidences={}),
                pages,
                resources,
                llm,
                tree_semaphore,
            )
            for proc in procedures
        ]
        all_batches = await asyncio.gather(*root_tasks) if root_tasks else []
        all_codes = [code for batch in all_batches for code in batch]
        result = classify(all_codes)

        codes_out.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")

        predicted_codes = _collect_predicted_codes(result)
        print(f"[DONE] Processed -> {input_file.name}")
        return (input_file.name, expected_code, predicted_codes)


async def run_batch_from_flat_txt(
    root_dir: Path,
    output_dir: Path | None = None,
    file_concurrency: int | None = None,
) -> None:
    root = root_dir
    if not root.exists() or not root.is_dir():
        raise ValueError(f"Invalid root directory: {root}")

    input_files = sorted(p for p in root.iterdir() if p.is_file() and p.suffix.lower() == ".txt")
    if not input_files:
        print(f"No .txt files found directly under {root}")
        return

    output_root = output_dir if output_dir else root / "batch_output"
    output_root.mkdir(parents=True, exist_ok=True)

    max_file_concurrency = file_concurrency if file_concurrency is not None else min(8, len(input_files))
    max_file_concurrency = max(1, max_file_concurrency)

    print(f"Found {len(input_files)} file(s) under {root}")
    print(f"Output root: {output_root}")
    print(f"File concurrency: {max_file_concurrency}")
    print(f"Tree concurrency: {config.MAX_CONCURRENCY}")

    llm = get_provider()
    resources = PCSResources()
    tree_semaphore = asyncio.Semaphore(config.MAX_CONCURRENCY)
    file_semaphore = asyncio.Semaphore(max_file_concurrency)

    tasks = [
        _process_one_file(
            input_file=input_file,
            output_root=output_root,
            resources=resources,
            llm=llm,
            tree_semaphore=tree_semaphore,
            file_semaphore=file_semaphore,
        )
        for input_file in input_files
    ]

    report_rows: list[dict] = []
    results = await asyncio.gather(*tasks, return_exceptions=True)
    for result in results:
        if isinstance(result, Exception):
            print(f"[ERROR] {result}")
            continue
        input_filename, expected_code, predicted_codes = result
        report_rows.extend(_rows_for_report(input_filename, expected_code, predicted_codes))

    report_path = output_root / "prediction_report.csv"
    with report_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "input_filename",
                "expected_code",
                "predicted_code",
                "predicted_code_type",
                "status",
            ],
        )
        writer.writeheader()
        writer.writerows(report_rows)

    print(f"Report saved -> {report_path}")
    print("Batch complete.")


if __name__ == "__main__":
    asyncio.run(
        run_batch_from_flat_txt(
            root_dir=INPUT_ROOT_DIR,
            output_dir=OUTPUT_ROOT_DIR,
            file_concurrency=FILE_CONCURRENCY,
        )
    )
