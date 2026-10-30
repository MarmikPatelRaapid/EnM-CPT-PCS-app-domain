"""
Batch runner — processes every document under a root directory.

Directory layout expected:
    <root>/
        <doc_folder>/
            <ocr_folder>/       # any folder whose name contains "ocr" or "oct"
                1.txt
                2.txt
                ...

Outputs written per doc:
    <root>/<doc_folder>/agent1_ner.json
    <root>/<doc_folder>/pcs_codes.json

Usage:
    python run_batch.py /Users/nishith/PCS/code_data/TestCaseDocuments
"""

import asyncio
import json
import sys
from dataclasses import asdict
from pathlib import Path

import config
from src.agents.agent1 import run_agent1
from src.document_reader import read_document_dir
from src.llm.base import get_provider
from src.pcs_resources import PCSResources
from src.result_collector import classify
from src.tree.models import PCSNode
from src.tree.traversal import expand_node


def _find_ocr_folder(doc_dir: Path) -> Path | None:
    """Return the first subdirectory whose name contains 'ocr' or 'oct'."""
    for sub in doc_dir.iterdir():
        if sub.is_dir() and any(kw in sub.name.lower() for kw in ("ocr", "oct")):
            return sub
    return None


async def _process_doc(
    doc_dir: Path,
    resources: PCSResources,
    llm,
    semaphore: asyncio.Semaphore,
) -> dict:
    ocr_folder = _find_ocr_folder(doc_dir)
    if ocr_folder is None:
        print(f"  [SKIP] No OCR folder found in {doc_dir.name}")
        return {}

    print(f"\n{'='*60}")
    print(f"  Processing: {doc_dir.name}")
    print(f"  OCR folder: {ocr_folder.name}")
    print(f"{'='*60}")

    pages = read_document_dir(str(ocr_folder))

    # --- Agent 1 ---
    procedures = await run_agent1(pages, llm)
    ner_out = doc_dir / "agent1_ner.json"
    ner_out.write_text(
        json.dumps([asdict(p) for p in procedures], indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    print(f"  Agent 1 NER saved  → {ner_out}")

    # --- Agent 2 tree traversal ---
    root_tasks = [
        expand_node(
            PCSNode(proc, current_code="", accumulated_evidences={}),
            pages,
            resources,
            llm,
            semaphore,
        )
        for proc in procedures
    ]
    all_batches = await asyncio.gather(*root_tasks)
    all_codes = [code for batch in all_batches for code in batch]
    result = classify(all_codes)

    codes_out = doc_dir / "pcs_codes.json"
    codes_out.write_text(
        json.dumps(result, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    print(f"  PCS codes saved    → {codes_out}")

    billable = [e["code"] for e in result["billable"]]
    non_bill = [e["code"] for e in result["non_billable"]]
    print(f"  Billable:     {billable}")
    print(f"  Non-billable: {non_bill}")

    return result


async def run_batch(root_dir: str) -> None:
    root = Path(root_dir)
    doc_dirs = sorted(
        d for d in root.iterdir()
        if d.is_dir() and not d.name.startswith(".")
    )

    if not doc_dirs:
        print(f"No document folders found under {root}")
        return

    print(f"Found {len(doc_dirs)} document(s) under {root}")

    llm = get_provider()
    resources = PCSResources()
    semaphore = asyncio.Semaphore(config.MAX_CONCURRENCY)

    for doc_dir in doc_dirs:
        try:
            await _process_doc(doc_dir, resources, llm, semaphore)
        except Exception as exc:
            print(f"  [ERROR] {doc_dir.name}: {exc}")

    print(f"\nBatch complete — {len(doc_dirs)} document(s) processed.")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python run_batch.py <root_dir>")
        sys.exit(1)

    asyncio.run(run_batch(sys.argv[1]))
