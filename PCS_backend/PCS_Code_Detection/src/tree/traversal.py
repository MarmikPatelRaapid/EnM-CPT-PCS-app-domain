import asyncio
import sys

from src.agents.agent2 import run_agent2
from src.llm.base import LLMProvider
from src.pcs_resources import PCSResources
from src.tree.models import PCSCode, PCSNode


def _log(msg: str) -> None:
    """Debug trace → stderr (visible alongside retry warnings)."""
    print(msg, flush=True, file=sys.stderr)


def _progress(msg: str) -> None:
    """Intermediate progress → stdout so it appears in the live result stream."""
    print(msg, flush=True)


POSITION_KEYS = [
    "evidence_for_first_character",
    "evidence_for_second_character",
    "evidence_for_third_character",
    "evidence_for_fourth_character",
    "evidence_for_fifth_character",
    "evidence_for_sixth_character",
    "evidence_for_seventh_character",
]


async def expand_node(
    node: PCSNode,
    pages: dict[int, str],
    resources: PCSResources,
    llm: LLMProvider,
    semaphore: asyncio.Semaphore,
) -> list[PCSCode]:
    proc = node.procedure.norm_procedure_name
    code = node.current_code or '""'

    if len(node.current_code) == 7:
        _log(f"[BILLABLE]  {proc} | code={node.current_code}")
        _progress(f"  ✓ BILLABLE    [{node.current_code}]  {proc}")
        return [PCSCode(
            code=node.current_code,
            procedure_name=node.procedure.norm_procedure_name,
            status="billable",
            evidences=node.accumulated_evidences,
        )]

    next_options = resources.get_next_options(node.current_code)
    if not next_options:
        _log(f"[TSV DEAD-END] {proc} | code={code} → non_billable")
        _progress(f"  ✗ NON-BILLABLE [{node.current_code}]  {proc}  (TSV dead-end)")
        return [PCSCode(
            code=node.current_code,
            procedure_name=node.procedure.norm_procedure_name,
            status="non_billable",
            evidences=node.accumulated_evidences,
        )]

    options_display = [f"{c}:{l}" for c, l in next_options]
    _log(f"[CALLING Agent2] {proc} | current_code={code} | options={options_display}")
    _progress(f"  → Char {len(node.current_code) + 1}/7  code={code:>7}  calling Agent 2 ...")

    async with semaphore:
        branches = await run_agent2(pages, node, next_options, resources, llm)

    if not branches:
        _log(f"[NO EVIDENCE]  {proc} | code={code} → non_billable")
        _progress(f"  ✗ NON-BILLABLE [{node.current_code}]  {proc}  (no evidence)")
        return [PCSCode(
            code=node.current_code,
            procedure_name=node.procedure.norm_procedure_name,
            status="non_billable",
            evidences=node.accumulated_evidences,
        )]

    selected = [item["next_character_value"] for item in branches]
    _log(f"[Agent2 RESULT] {proc} | code={code} → selected={selected}")
    _progress(f"       selected={selected}  → new code(s): "
              + ", ".join(node.current_code + c for c in selected))

    child_tasks = []
    for item in branches:
        char = item["next_character_value"]
        char_evidences = item["next_character_evidences"]
        position_key = POSITION_KEYS[len(node.current_code)]
        new_evidences = {**node.accumulated_evidences, position_key: char_evidences}
        child = PCSNode(node.procedure, node.current_code + char, new_evidences)
        child_tasks.append(expand_node(child, pages, resources, llm, semaphore))

    results = await asyncio.gather(*child_tasks)
    return [code for batch in results for code in batch]
