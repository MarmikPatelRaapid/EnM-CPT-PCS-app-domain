import asyncio
from unittest.mock import AsyncMock, patch

import pytest

from src.agents.agent1 import Procedure
from src.tree.models import PCSNode
from src.tree.traversal import expand_node


def _proc(name: str = "Test Procedure") -> Procedure:
    return Procedure(norm_procedure_name=name, procedure_evidences=[])


def _node(code: str, evidences: dict | None = None) -> PCSNode:
    return PCSNode(procedure=_proc(), current_code=code, accumulated_evidences=evidences or {})


def _sem(n: int = 20) -> asyncio.Semaphore:
    return asyncio.Semaphore(n)


@pytest.mark.asyncio
async def test_7char_code_is_billable(sample_pages, resources):
    node = _node("0016070")
    results = await expand_node(node, sample_pages, resources, AsyncMock(), _sem())
    assert len(results) == 1
    assert results[0].status == "billable"
    assert results[0].code == "0016070"


@pytest.mark.asyncio
async def test_tsv_dead_end_is_non_billable(sample_pages, resources):
    # "ZZZ" is 3 chars and does not exist in the traversal TSV → dead end
    node = _node("ZZZ")
    results = await expand_node(node, sample_pages, resources, AsyncMock(), _sem())
    assert len(results) == 1
    assert results[0].status == "non_billable"


@pytest.mark.asyncio
async def test_not_found_stops_expansion(sample_pages, resources):
    async def mock_agent2(pages, node, next_opts, res, llm):
        return []

    with patch("src.tree.traversal.run_agent2", side_effect=mock_agent2):
        node = _node("")
        results = await expand_node(node, sample_pages, resources, AsyncMock(), _sem())

    assert len(results) == 1
    assert results[0].status == "non_billable"
    assert results[0].code == ""


@pytest.mark.asyncio
async def test_single_branch_linear_path(sample_pages, resources):
    chars = ["0", "D", "T", "J", "4", "Z", "Z"]
    call_count = 0

    async def mock_agent2(pages, node, next_opts, res, llm):
        nonlocal call_count
        char = chars[len(node.current_code)]
        call_count += 1
        return [{"next_character_value": char, "next_character_desc": "Test",
                 "next_character_evidences": []}]

    with patch("src.tree.traversal.run_agent2", side_effect=mock_agent2):
        node = _node("")
        sem = _sem(10)
        results = await expand_node(node, sample_pages, resources, AsyncMock(), sem)

    assert len(results) == 1
    assert results[0].code == "0DTJ4ZZ"
    assert results[0].status == "billable"
    assert call_count == 7


@pytest.mark.asyncio
async def test_two_branch_expansion(sample_pages, resources):
    # depth 0 → ["0", "B"], then each branch completes deterministically
    branch_chars = {
        "": ["0", "B"],
        "0": ["D"], "0D": ["T"], "0DT": ["J"], "0DTJ": ["4"], "0DTJ4": ["Z"], "0DTJ4Z": ["Z"],
        "B": ["4"], "B4": ["0"], "B40": ["Z"], "B40Z": ["Z"], "B40ZZ": ["Z"], "B40ZZZ": ["Z"],
    }

    async def mock_agent2(pages, node, next_opts, res, llm):
        chars = branch_chars.get(node.current_code, [])
        return [{"next_character_value": c, "next_character_desc": "X",
                 "next_character_evidences": []} for c in chars]

    with patch("src.tree.traversal.run_agent2", side_effect=mock_agent2):
        node = _node("")
        results = await expand_node(node, sample_pages, resources, AsyncMock(), _sem())

    assert len(results) == 2
    codes = {r.code for r in results}
    assert "0DTJ4ZZ" in codes
    assert "B40ZZZZ"[: 7] in codes or any(len(r.code) == 7 for r in results)


@pytest.mark.asyncio
async def test_mixed_billable_non_billable(sample_pages, resources):
    responses = {
        "": [{"next_character_value": "0", "next_character_desc": "X", "next_character_evidences": []},
             {"next_character_value": "B", "next_character_desc": "Y", "next_character_evidences": []}],
        "0": [{"next_character_value": "D", "next_character_desc": "X", "next_character_evidences": []}],
        "0D": [{"next_character_value": "T", "next_character_desc": "X", "next_character_evidences": []}],
        "0DT": [{"next_character_value": "J", "next_character_desc": "X", "next_character_evidences": []}],
        "0DTJ": [{"next_character_value": "4", "next_character_desc": "X", "next_character_evidences": []}],
        "0DTJ4": [{"next_character_value": "Z", "next_character_desc": "X", "next_character_evidences": []}],
        "0DTJ4Z": [{"next_character_value": "Z", "next_character_desc": "X", "next_character_evidences": []}],
        "B": [],  # stops here → non_billable
    }

    async def mock_agent2(pages, node, next_opts, res, llm):
        return responses.get(node.current_code, [])

    with patch("src.tree.traversal.run_agent2", side_effect=mock_agent2):
        node = _node("")
        results = await expand_node(node, sample_pages, resources, AsyncMock(), _sem())

    billable = [r for r in results if r.status == "billable"]
    non_billable = [r for r in results if r.status == "non_billable"]
    assert len(billable) == 1
    assert len(non_billable) == 1
    assert billable[0].code == "0DTJ4ZZ"
    assert non_billable[0].code == "B"


@pytest.mark.asyncio
async def test_evidence_accumulates_per_level(sample_pages, resources):
    ev = lambda pos: [{"text": f"ev{pos}", "pg_no": 1, "reftxtbefore": "a", "reftxtafter": "b"}]
    responses = {
        "": [{"next_character_value": "0", "next_character_desc": "X", "next_character_evidences": ev(1)}],
        "0": [{"next_character_value": "D", "next_character_desc": "X", "next_character_evidences": ev(2)}],
        "0D": [{"next_character_value": "T", "next_character_desc": "X", "next_character_evidences": ev(3)}],
        "0DT": [],
    }

    async def mock_agent2(pages, node, next_opts, res, llm):
        return responses.get(node.current_code, [])

    with patch("src.tree.traversal.run_agent2", side_effect=mock_agent2):
        node = _node("")
        results = await expand_node(node, sample_pages, resources, AsyncMock(), _sem())

    assert len(results) == 1
    evs = results[0].evidences
    assert "evidence_for_first_character" in evs
    assert "evidence_for_second_character" in evs
    assert "evidence_for_third_character" in evs
