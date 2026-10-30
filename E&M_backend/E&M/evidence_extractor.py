"""Evidence aggregation helpers for API response payloads."""

from __future__ import annotations

import json
from typing import Any, Dict, Iterable, List, Set

SECTIONS = (
    "self_limited_minor_problem",
    "chronic_illness",
    "acute_illness",
    "undiagnosed_problem",
)


def _iter_problem_nodes(node: Any) -> Iterable[Dict[str, Any]]:
    if isinstance(node, dict):
        if any(
            key in node
            for key in (
                "disease_evidence",
                "data_to_review",
                "risk_of_morbidity",
            )
        ):
            yield node

        for value in node.values():
            yield from _iter_problem_nodes(value)
    elif isinstance(node, list):
        for value in node:
            yield from _iter_problem_nodes(value)


def _iter_section_problem_nodes(payload: Dict[str, Any]) -> Iterable[Dict[str, Any]]:
    for section in SECTIONS:
        if section in payload:
            yield from _iter_problem_nodes(payload.get(section))


def _iter_list_values(value: Any) -> Iterable[Any]:
    if not isinstance(value, list):
        return
    for item in value:
        yield item


def _fingerprint(value: Any) -> str:
    try:
        return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    except TypeError:
        return repr(value)


def _append_unique(items: List[Any], seen: Set[str], value: Any) -> None:
    marker = _fingerprint(value)
    if marker in seen:
        return
    seen.add(marker)
    items.append(value)


def _top_level_evidences(payload: Dict[str, Any], section_name: str) -> List[Any]:
    section = payload.get(section_name)
    if not isinstance(section, dict):
        return []

    unique: List[Any] = []
    seen: Set[str] = set()
    for evidence in _iter_list_values(section.get("evidences")):
        _append_unique(unique, seen, evidence)
    return unique


def _collect_complexity_evidences(payload: Dict[str, Any]) -> List[Any]:
    unique: List[Any] = []
    seen: Set[str] = set()
    for node in _iter_section_problem_nodes(payload):
        for evidence in _iter_list_values(node.get("disease_evidence")):
            _append_unique(unique, seen, evidence)
    return unique


def _collect_data_to_review_evidences(payload: Dict[str, Any]) -> List[Any]:
    unique: List[Any] = []
    seen: Set[str] = set()
    for node in _iter_section_problem_nodes(payload):
        data_to_review = node.get("data_to_review")
        if not isinstance(data_to_review, dict):
            continue
        for subcategory_evidences in data_to_review.values():
            for evidence in _iter_list_values(subcategory_evidences):
                _append_unique(unique, seen, evidence)
    return unique


def _collect_risk_evidences(payload: Dict[str, Any]) -> List[Any]:
    unique: List[Any] = []
    seen: Set[str] = set()
    for node in _iter_section_problem_nodes(payload):
        risk_of_morbidity = node.get("risk_of_morbidity")
        if not isinstance(risk_of_morbidity, dict):
            continue
        for evidence in _iter_list_values(risk_of_morbidity.get("risk_evidences")):
            _append_unique(unique, seen, evidence)
    return unique


def extract_evidences(payload: Dict[str, Any]) -> Dict[str, List[Any]]:
    """Build response-ready evidences object using de-duplicated values."""
    return {
        "facility": _top_level_evidences(payload, "facility"),
        "service": _top_level_evidences(payload, "service"),
        "patient": _top_level_evidences(payload, "patient"),
        "physician_time_spent_with_patient": _top_level_evidences(
            payload, "physician_time_spent_with_patient"
        ),
        "staff_time_spent_with_patient": _top_level_evidences(payload, "staff_time_spent_with_patient"),
        "complexity": _collect_complexity_evidences(payload),
        "data_to_review": _collect_data_to_review_evidences(payload),
        "risk_of_morbidity": _collect_risk_evidences(payload),
    }
