import asyncio
import json
from dataclasses import asdict
from pathlib import Path

import config
from src.agents.agent1 import Procedure, run_agent1
from src.document_reader import read_document_dir
from src.llm.base import get_provider
from src.pcs_resources import PCSResources
from src.result_collector import classify
from src.tree.models import PCSNode
from src.tree.traversal import expand_node


def _out_dir(doc_dir: str) -> Path:
    input_name = Path(doc_dir).name
    out_dir = Path(doc_dir).parent.parent / "output_data" / input_name
    out_dir.mkdir(parents=True, exist_ok=True)
    return out_dir


def _save_ner_output(procedures: list[Procedure], doc_dir: str) -> Path:
    out_file = _out_dir(doc_dir) / "agent1_ner.json"
    payload = [asdict(p) for p in procedures]
    out_file.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    return out_file


def _save_final_output(result: dict, doc_dir: str) -> Path:
    out_file = _out_dir(doc_dir) / "pcs_codes.json"
    out_file.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    return out_file


async def run(doc_dir: str) -> dict:
    pages = read_document_dir(doc_dir)
    llm = get_provider()
    resources = PCSResources()

    procedures = await run_agent1(pages, llm)
    ner_path = _save_ner_output(procedures, doc_dir)
    print(f"Agent 1 NER output saved → {ner_path}")

    semaphore = asyncio.Semaphore(config.MAX_CONCURRENCY)
    root_tasks = []
    for proc in procedures:
        print(f"\n[Procedure] {proc.norm_procedure_name}", flush=True)
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
    result = classify(all_codes)

    final_path = _save_final_output(result, doc_dir)
    print(f"Final PCS codes saved    → {final_path}")

    return result


if __name__ == "__main__":
    import sys

    if len(sys.argv) != 2:
        print("Usage: python main.py <path/to/ocr_directory>")
        sys.exit(1)

    result = asyncio.run(run(sys.argv[1]))
    print(json.dumps(result, indent=2, ensure_ascii=False))
