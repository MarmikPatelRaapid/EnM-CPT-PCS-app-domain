import json

import jsonschema
import pytest

from src.agents.agent1 import Procedure
from src.agents.agent2 import run_agent2
from src.tree.models import PCSNode


def _make_node(code: str, evidences: dict | None = None) -> PCSNode:
    proc = Procedure(
        norm_procedure_name="Laparoscopic Appendectomy",
        procedure_evidences=[],
    )
    return PCSNode(procedure=proc, current_code=code, accumulated_evidences=evidences or {})


@pytest.mark.asyncio
async def test_agent2_returns_single_char(
    sample_pages, resources, agent2_single_char_response, make_mock_llm
):
    llm = make_mock_llm(agent2_single_char_response)
    node = _make_node("")
    options = resources.get_next_options("")
    result = await run_agent2(sample_pages, node, options, resources, llm)
    assert len(result) == 1
    assert result[0]["next_character_value"] == "0"


@pytest.mark.asyncio
async def test_agent2_returns_multiple_chars(
    sample_pages, resources, agent2_multi_char_response, make_mock_llm
):
    llm = make_mock_llm(agent2_multi_char_response)
    node = _make_node("")
    options = resources.get_next_options("")
    result = await run_agent2(sample_pages, node, options, resources, llm)
    assert len(result) == 2


@pytest.mark.asyncio
async def test_agent2_empty_data_returns_empty_list(
    sample_pages, resources, agent2_not_found_response, make_mock_llm
):
    llm = make_mock_llm(agent2_not_found_response)
    node = _make_node("001")
    options = resources.get_next_options("001")
    result = await run_agent2(sample_pages, node, options, resources, llm)
    assert result == []


@pytest.mark.asyncio
async def test_agent2_input_json_structure(
    sample_pages, resources, agent2_single_char_response, make_mock_llm
):
    llm = make_mock_llm(agent2_single_char_response)
    node = _make_node("0")
    options = resources.get_next_options("0")
    await run_agent2(sample_pages, node, options, resources, llm)
    user_content = llm.call_async.call_args[0][1]
    assert "norm_procedure" in user_content
    assert "current_code" in user_content
    assert "evidences" in user_content


@pytest.mark.asyncio
async def test_agent2_evidences_passed_correctly(
    sample_pages, resources, agent2_single_char_response, make_mock_llm
):
    llm = make_mock_llm(agent2_single_char_response)
    prior_evidence = [{"text": "appendectomy", "pg_no": 1, "reftxtbefore": "a", "reftxtafter": "b"}]
    node = _make_node("0", {"evidence_for_first_character": prior_evidence})
    options = resources.get_next_options("0")
    await run_agent2(sample_pages, node, options, resources, llm)
    user_content = llm.call_async.call_args[0][1]
    assert "evidence_for_first_character" in user_content


@pytest.mark.asyncio
async def test_agent2_validates_output_schema(sample_pages, resources, make_mock_llm):
    bad_response = {"norm_procedure": "X", "current_code": ""}  # missing next_character_data
    llm = make_mock_llm(bad_response)
    node = _make_node("")
    options = resources.get_next_options("")
    with pytest.raises(jsonschema.ValidationError):
        await run_agent2(sample_pages, node, options, resources, llm)


@pytest.mark.asyncio
async def test_agent2_filters_not_found_value(
    sample_pages, resources, make_mock_llm
):
    response = {
        "norm_procedure": "X",
        "current_code": "",
        "next_character_data": [
            {
                "next_character_value": "not_found",
                "next_character_desc": "not_found",
                "next_character_evidences": [],
            }
        ],
    }
    llm = make_mock_llm(response)
    node = _make_node("")
    options = resources.get_next_options("")
    result = await run_agent2(sample_pages, node, options, resources, llm)
    assert result == []
