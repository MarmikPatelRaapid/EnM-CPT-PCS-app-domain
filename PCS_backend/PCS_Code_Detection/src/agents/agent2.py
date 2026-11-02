import json
import re

import jsonschema

from src.llm.base import LLMProvider
from src.pcs_resources import PCSResources
from src.prompt_loader import fetch_prompt, fetch_schema
from src.tree.models import PCSNode

PROMPT_NAME = "Agent 2 - ICD-10-PCS Dynamic Code Detection Prompt.txt"

_ORDINALS = ["1st", "2nd", "3rd", "4th", "5th", "6th", "7th"]

_POSITION_KEYS = [
    "evidence_for_first_character",
    "evidence_for_second_character",
    "evidence_for_third_character",
    "evidence_for_fourth_character",
    "evidence_for_fifth_character",
    "evidence_for_sixth_character",
    "evidence_for_seventh_character",
]


def _fill_placeholders(
    prompt: str,
    node: PCSNode,
    next_options: list[tuple[str, str]],
    resources: PCSResources,
) -> str:
    current_code = node.current_code
    position = len(current_code) + 1
    ordinal = _ORDINALS[position - 1]
    first_digit = current_code[0] if current_code else ""
    digit_type = resources.get_digit_type(first_digit, position)

    options_str = ", ".join(f"{code}: {label}" for code, label in next_options)
    list_str = ", ".join(code for code, _ in next_options)
    options_formatted = f"[{options_str}]"
    list_formatted = f"[{list_str}]"

    replacements = {
        r"\[##Current value = .*?##\]": f"{current_code}",
        r"\[##Next Digit = .*?##\]": f"{ordinal}",
        r"\[##next digit type = .*?##\s*\]": f"{digit_type}",
        r"\[##next possible list = .*?##\]": options_formatted,
        r"\[##list##\]": list_formatted,
    }

    for pattern, replacement in replacements.items():
        prompt = re.sub(pattern, replacement, prompt)

    return prompt


async def run_agent2(
    pages: dict[int, str],
    node: PCSNode,
    next_options: list[tuple[str, str]],
    resources: PCSResources,
    llm: LLMProvider,
) -> list[dict]:
    raw_prompt = fetch_prompt(PROMPT_NAME)
    system_prompt = _fill_placeholders(raw_prompt, node, next_options, resources)

    input_json = {
        "norm_procedure": node.procedure.norm_procedure_name,
        "current_code": node.current_code,
        "evidences": node.accumulated_evidences,
    }

    user_content = (
        "--- CLINICAL DOCUMENT ---\n"
        + json.dumps({str(k): v for k, v in pages.items()}, ensure_ascii=False)
        + "\n\n--- PCS TRAVERSAL STATE ---\n"
        + json.dumps(input_json, ensure_ascii=False)
    )

    raw = await llm.call_async(system_prompt, user_content)

    _BORDER = "─" * 80
    print(f"\n{_BORDER}")
    print(f"  Agent 2 output  |  procedure: {node.procedure.norm_procedure_name}  |  current_code: \"{node.current_code}\"")
    print(_BORDER)
    print(raw)
    print(_BORDER, flush=True)

    data = json.loads(raw)
    jsonschema.validate(instance=data, schema=fetch_schema("agent_2_schema"))

    return [
        item
        for item in data["next_character_data"]
        if item["next_character_value"] not in ("not_found", "")
    ]
