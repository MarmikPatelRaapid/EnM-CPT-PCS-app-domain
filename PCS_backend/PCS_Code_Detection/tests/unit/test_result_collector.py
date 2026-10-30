import pytest

from src.result_collector import classify
from src.tree.models import PCSCode


def _code(code: str, proc: str, status: str) -> PCSCode:
    return PCSCode(code=code, procedure_name=proc, status=status, evidences={})


def test_7char_classified_billable():
    codes = [_code("0DTJ4ZZ", "Appendectomy", "billable")]
    result = classify(codes)
    assert len(result["billable"]) == 1
    assert result["billable"][0]["code"] == "0DTJ4ZZ"
    assert result["non_billable"] == []


def test_short_code_classified_non_billable():
    codes = [_code("0DT", "Appendectomy", "non_billable")]
    result = classify(codes)
    assert len(result["non_billable"]) == 1
    assert result["non_billable"][0]["code"] == "0DT"
    assert result["billable"] == []


def test_grouped_by_procedure():
    codes = [
        _code("0DTJ4ZZ", "Appendectomy", "billable"),
        _code("0DT", "Appendectomy", "non_billable"),
        _code("0016070", "Bypass", "billable"),
    ]
    result = classify(codes)
    assert len(result["billable"]) == 2
    assert len(result["non_billable"]) == 1
    proc_names = [e["procedure_name"] for e in result["billable"]]
    assert "Appendectomy" in proc_names
    assert "Bypass" in proc_names


def test_empty_input_returns_empty():
    result = classify([])
    assert result == {"billable": [], "non_billable": []}
