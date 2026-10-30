import asyncio
import json
from unittest.mock import AsyncMock, patch

import pytest

from main import run


def _make_agent2_mock(char_map: dict[str, str]):
    """Return a coroutine that maps current_code → next char deterministically."""
    async def _mock_agent2(pages, node, next_opts, res, llm):
        char = char_map.get(node.current_code)
        if char is None:
            return []
        return [{"next_character_value": char, "next_character_desc": "Test",
                 "next_character_evidences": []}]
    return _mock_agent2


@pytest.mark.asyncio
async def test_end_to_end_single_procedure_billable(tmp_path, agent1_response):
    doc = tmp_path / "patient.txt"
    doc.write_text("--- Page 1 ---\nPatient underwent laparoscopic appendectomy.")

    char_map = {
        "": "0", "0": "D", "0D": "T", "0DT": "J",
        "0DTJ": "4", "0DTJ4": "Z", "0DTJ4Z": "Z",
    }
    mock_llm = AsyncMock()
    mock_llm.call_async.return_value = json.dumps(agent1_response)

    with patch("main.get_provider", return_value=mock_llm), \
         patch("src.tree.traversal.run_agent2", side_effect=_make_agent2_mock(char_map)):
        result = await run(str(doc))

    assert len(result["billable"]) == 1
    assert result["billable"][0]["code"] == "0DTJ4ZZ"
    assert result["non_billable"] == []


@pytest.mark.asyncio
async def test_end_to_end_multi_procedure_parallel(tmp_path):
    doc = tmp_path / "patient.txt"
    doc.write_text("--- Page 1 ---\nMultiple procedures performed.")

    agent1_multi = {
        "procedures": [
            {"norm_procedure_name": f"Procedure {i}",
             "procedure_evidences": [{"text": f"proc{i}", "pg_no": 1,
                                      "reftxtbefore": "a", "reftxtafter": "b"}]}
            for i in range(3)
        ]
    }

    # All three procedures collapse to non_billable immediately (no chars returned)
    mock_llm = AsyncMock()
    mock_llm.call_async.return_value = json.dumps(agent1_multi)

    async def mock_agent2(pages, node, next_opts, res, llm):
        return []

    with patch("main.get_provider", return_value=mock_llm), \
         patch("src.tree.traversal.run_agent2", side_effect=mock_agent2):
        result = await run(str(doc))

    assert len(result["non_billable"]) == 3


@pytest.mark.asyncio
async def test_end_to_end_non_billable_stops_at_4(tmp_path, agent1_response):
    doc = tmp_path / "patient.txt"
    doc.write_text("--- Page 1 ---\nProcedure performed.")

    # returns chars for positions 1-4, then empty
    char_map = {"": "0", "0": "D", "0D": "T", "0DT": "J"}

    mock_llm = AsyncMock()
    mock_llm.call_async.return_value = json.dumps(agent1_response)

    with patch("main.get_provider", return_value=mock_llm), \
         patch("src.tree.traversal.run_agent2", side_effect=_make_agent2_mock(char_map)):
        result = await run(str(doc))

    assert result["billable"] == []
    assert len(result["non_billable"]) == 1
    assert result["non_billable"][0]["code"] == "0DTJ"


@pytest.mark.asyncio
async def test_retry_on_429_succeeds():
    """The base LLMProvider.call_async retries on HTTP 429 and succeeds on second attempt."""
    from src.llm.base import LLMProvider

    class FakeResponse:
        status_code = 429

    class RateLimitError(Exception):
        response = FakeResponse()

    call_count = 0

    class FlakyProvider(LLMProvider):
        async def _call_once(self, system_prompt, user_content):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise RateLimitError("rate limited")
            return '{"result": "ok"}'

    provider = FlakyProvider()
    with patch("asyncio.sleep", new_callable=AsyncMock):
        result = await provider.call_async("sys", "user")

    assert result == '{"result": "ok"}'
    assert call_count == 2


@pytest.mark.asyncio
async def test_max_retries_exceeded_raises():
    """After RETRY_ATTEMPTS exhausted, the 429 exception propagates."""
    from src.llm.base import LLMProvider
    import config

    class FakeResponse:
        status_code = 429

    class RateLimitError(Exception):
        response = FakeResponse()

    class AlwaysRateLimited(LLMProvider):
        async def _call_once(self, system_prompt, user_content):
            raise RateLimitError("always limited")

    provider = AlwaysRateLimited()
    with patch("asyncio.sleep", new_callable=AsyncMock):
        with pytest.raises(RateLimitError):
            await provider.call_async("sys", "user")


@pytest.mark.asyncio
async def test_provider_swap_same_result_structure(tmp_path, agent1_response):
    doc = tmp_path / "patient.txt"
    doc.write_text("--- Page 1 ---\nProcedure performed.")

    char_map = {
        "": "0", "0": "D", "0D": "T", "0DT": "J",
        "0DTJ": "4", "0DTJ4": "Z", "0DTJ4Z": "Z",
    }

    for _provider in ["gemini_vertex", "azure_openai"]:
        mock_llm = AsyncMock()
        mock_llm.call_async.return_value = json.dumps(agent1_response)

        with patch("main.get_provider", return_value=mock_llm), \
             patch("src.tree.traversal.run_agent2", side_effect=_make_agent2_mock(char_map)):
            result = await run(str(doc))

        assert "billable" in result
        assert "non_billable" in result
        assert len(result["billable"]) == 1
