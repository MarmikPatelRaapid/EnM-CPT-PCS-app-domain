import json
from dataclasses import dataclass

import jsonschema

from src.llm.base import LLMProvider
from src.prompt_loader import fetch_prompt, fetch_schema

PROMPT_NAME = "Agent 1 - ICD-10-PCS Code Suggestion Prompt.txt"


@dataclass
class Procedure:
    norm_procedure_name: str
    procedure_evidences: list[dict]


async def run_agent1(pages: dict[int, str], llm: LLMProvider) -> list[Procedure]:
    system_prompt = fetch_prompt(PROMPT_NAME)
    user_content = json.dumps({str(k): v for k, v in pages.items()}, ensure_ascii=False)

    raw = await llm.call_async(system_prompt, user_content)
    data = json.loads(raw)

    # Normalize: LLM sometimes returns [] directly when no procedures are found
    if isinstance(data, list):
        data = {"procedures": data}

    jsonschema.validate(instance=data, schema=fetch_schema("agent_1_schema"))

    return [
        Procedure(
            norm_procedure_name=p["norm_procedure_name"],
            procedure_evidences=p["procedure_evidences"],
        )
        for p in data["procedures"]
    ]
