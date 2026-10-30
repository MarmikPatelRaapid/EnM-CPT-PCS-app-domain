import json

import pytest

from src.agents.agent1 import run_agent1


@pytest.mark.asyncio
async def test_agent1_returns_procedures(sample_pages, agent1_response, make_mock_llm):
    llm = make_mock_llm(agent1_response)
    procedures = await run_agent1(sample_pages, llm)
    assert len(procedures) == 1
    assert procedures[0].norm_procedure_name == "Laparoscopic Appendectomy"


@pytest.mark.asyncio
async def test_agent1_validates_schema(sample_pages, make_mock_llm):
    import jsonschema
    bad_response = {"procedures": [{"procedure_evidences": []}]}  # missing norm_procedure_name
    llm = make_mock_llm(bad_response)
    with pytest.raises(jsonschema.ValidationError):
        await run_agent1(sample_pages, llm)


@pytest.mark.asyncio
async def test_agent1_handles_empty_procedures(sample_pages, make_mock_llm):
    llm = make_mock_llm({"procedures": []})
    procedures = await run_agent1(sample_pages, llm)
    assert procedures == []


@pytest.mark.asyncio
async def test_agent1_passes_all_pages(sample_pages, agent1_response, make_mock_llm):
    llm = make_mock_llm(agent1_response)
    await run_agent1(sample_pages, llm)
    call_args = llm.call_async.call_args
    user_content = call_args[0][1]
    assert "laparoscopic appendectomy" in user_content.lower()
    assert "No complications" in user_content


@pytest.mark.asyncio
async def test_agent1_uses_system_prompt(sample_pages, agent1_response, make_mock_llm):
    llm = make_mock_llm(agent1_response)
    await run_agent1(sample_pages, llm)
    call_args = llm.call_async.call_args
    system_prompt = call_args[0][0]
    assert "PCS" in system_prompt
