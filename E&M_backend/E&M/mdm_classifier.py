"""MDM level classifier based on extracted disease/problem JSON payloads."""

from __future__ import annotations

import csv
import logging
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from statistics import median
from typing import Any, Dict, Iterable, List, Tuple

LEVEL_ORDER = ("straightforward", "low", "moderate", "high")
LEVEL_RANK = {level: idx for idx, level in enumerate(LEVEL_ORDER)}
LOGGER = logging.getLogger(__name__)
COMPLEXITY_TO_MDM_LEVEL = {
    "Straightforward": "straightforward",
    "low": "low",
    "moderate": "moderate",
    "high": "high",
}
DATA_TO_REVIEW_TO_MDM_LEVEL = {
    "minimal": "straightforward",
    "limited": "low",
    "moderate": "moderate",
    "extensive": "high",
}
RISK_TO_MDM_LEVEL = {
    "minimal": "straightforward",
    "low": "low",
    "moderate": "moderate",
    "high": "high",
}

DATA_FIELD_ALIASES = {
    "review_of_prior_external_note": "review_of_prior_external_note",
    "review_of_test_result": "review_of_test_result",
    "order_of_test": "order_of_test",
    "assessment_requiring_independent_historian": (
        "assessment_requiring_independent_historian"
    ),
    "independent_interpretation_of_test": "independent_interpretation_of_test",
    "discussion_of_management_or_test_interpretation": (
        "discussion_of_management_or_test_interpretation"
    ),
}

SECTIONS = (
    "self_limited_minor_problem",
    "chronic_illness",
    "acute_illness",
    "undiagnosed_problem",
)

COMPLEXITY_RULES_TSV = Path(__file__).resolve().parent / "E&M Data - Disease mapping from json.tsv"
TSV_COL_ACTUAL_NAME = "actual_name"
TSV_COL_REQUIRED_COUNT = "norm_disease_count"
TSV_COL_JSON_CLASS = "json_class"
TSV_COL_JSON_SUB_CLASS = "json_sub_class"
TSV_COL_JSON_SUB_SUB_CLASS = "json_sub_sub_class"

_RULE_LEVEL_GROUPS = {
    "straightforward": {
        "1 self-limited or minor problem",
    },
    "low": {
        "2 or more self-limited or minor problems",
        "1 stable chronic illness",
        "1 acute, uncomplicated illness or injury",
        "1 stable, acute illness",
        "1 acute, uncomplicated illness or injury requiring hospital inpatient or observation level of care",
    },
    "moderate": {
        "2 or more stable chronic illnesses",
        "1 or more chronic illness with exacerbation, progression of side effect",
        "1 undiagnosed new problem with uncertain prognosis",
        "1 acute illness with systemic symptoms",
        "1 acute complicated injury",
    },
    "high": {
        "1 or more chronic illness with severe exacerbation, progression of side effect",
        "1 acute or chronic illness or injury posing a threat to life or body function",
    },
}
_RULE_LEVEL_BY_NAME = {
    " ".join(rule_name.replace("_", " ").replace("-", " ").strip().lower().split()): level
    for level, rule_names in _RULE_LEVEL_GROUPS.items()
    for rule_name in rule_names
}


@dataclass(frozen=True)
class ProblemEntry:
    path: Tuple[str, ...]
    payload: Dict[str, Any]


@dataclass(frozen=True)
class ComplexityRule:
    name: str
    required_count: int
    path: Tuple[str, ...]
    level: str


# Word-level aliases applied during normalization so equivalent (or misspelled)
# field names collapse to the same canonical token. For example, the JSON
# attribute "sever_exacerbation" is treated as "severe_exacerbation".
_WORD_ALIASES = {
    "sever": "severe",
}


def _normalize_token(value: str) -> str:
    words = value.replace("_", " ").replace("-", " ").strip().lower().split()
    return " ".join(_WORD_ALIASES.get(word, word) for word in words)


def _has_non_empty_list(value: Any) -> bool:
    return isinstance(value, list) and len(value) > 0


def _is_evidence_backed(entry: ProblemEntry) -> bool:
    return _has_non_empty_list(entry.payload.get("disease_evidence"))


def _matches_path(entry_path: Tuple[str, ...], expected_path: Iterable[str]) -> bool:
    normalized_entry = tuple(_normalize_token(part) for part in entry_path)
    normalized_expected = tuple(_normalize_token(part) for part in expected_path)
    if len(normalized_entry) < len(normalized_expected):
        return False
    return normalized_entry[: len(normalized_expected)] == normalized_expected


def _iter_problem_entries(node: Any, path: Tuple[str, ...]) -> Iterable[ProblemEntry]:
    if isinstance(node, dict):
        if any(
            key in node
            for key in (
                "norm_disease_name",
                "disease_evidence",
                "data_to_review",
                "risk_of_morbidity",
            )
        ):
            yield ProblemEntry(path=path, payload=node)

        for key, value in node.items():
            yield from _iter_problem_entries(value, path + (key,))
    elif isinstance(node, list):
        for value in node:
            yield from _iter_problem_entries(value, path)


def _collect_entries(payload: Dict[str, Any]) -> List[ProblemEntry]:
    entries: List[ProblemEntry] = []
    for section in SECTIONS:
        if section in payload:
            entries.extend(_iter_problem_entries(payload[section], (section,)))
    return entries


def _count_evidence(entries: List[ProblemEntry], *path_prefix: str) -> int:
    return sum(
        1 for entry in entries if _is_evidence_backed(entry) and _matches_path(entry.path, path_prefix)
    )


@lru_cache(maxsize=1)
def _load_complexity_rules() -> Tuple[ComplexityRule, ...]:
    rules: List[ComplexityRule] = []
    with COMPLEXITY_RULES_TSV.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        for row in reader:
            name = str(row.get(TSV_COL_ACTUAL_NAME, "")).strip()
            if not name:
                continue
            normalized_name = _normalize_token(name)
            if normalized_name not in _RULE_LEVEL_BY_NAME:
                continue

            required_count_raw = str(row.get(TSV_COL_REQUIRED_COUNT, "")).strip()
            if not required_count_raw:
                continue
            required_count = int(required_count_raw)
            path = tuple(
                part.strip()
                for part in (
                    row.get(TSV_COL_JSON_CLASS, ""),
                    row.get(TSV_COL_JSON_SUB_CLASS, ""),
                    row.get(TSV_COL_JSON_SUB_SUB_CLASS, ""),
                )
                if str(part).strip()
            )
            if not path:
                continue

            rules.append(
                ComplexityRule(
                    name=name,
                    required_count=required_count,
                    path=path,
                    level=_RULE_LEVEL_BY_NAME[normalized_name],
                )
            )
    return tuple(rules)


class _ExprParser:
    """Tiny boolean expression parser supporting #N(name), |, &, and parentheses."""

    def __init__(self, text: str, counts: Dict[str, int], flags: Dict[str, bool]) -> None:
        self.text = text
        self.counts = {_normalize_token(k): v for k, v in counts.items()}
        self.flags = {_normalize_token(k): v for k, v in flags.items()}
        self.idx = 0

    def parse(self) -> bool:
        value = self._parse_or()
        self._skip_ws()
        if self.idx != len(self.text):
            raise ValueError(f"Unexpected token near: {self.text[self.idx:]}")
        return value

    def _skip_ws(self) -> None:
        while self.idx < len(self.text) and self.text[self.idx].isspace():
            self.idx += 1

    def _consume(self, token: str) -> bool:
        self._skip_ws()
        if self.text.startswith(token, self.idx):
            self.idx += len(token)
            return True
        return False

    def _parse_or(self) -> bool:
        value = self._parse_and()
        while self._consume("|"):
            rhs = self._parse_and()
            value = value or rhs
        return value

    def _parse_and(self) -> bool:
        value = self._parse_factor()
        while self._consume("&"):
            rhs = self._parse_factor()
            value = value and rhs
        return value

    def _parse_factor(self) -> bool:
        self._skip_ws()
        if self._consume("("):
            value = self._parse_or()
            if not self._consume(")"):
                raise ValueError("Expected ')' in expression")
            return value
        if self._consume("#"):
            return self._parse_threshold()
        return self._parse_identifier()

    def _parse_threshold(self) -> bool:
        self._skip_ws()
        start = self.idx
        while self.idx < len(self.text) and self.text[self.idx].isdigit():
            self.idx += 1
        if start == self.idx:
            raise ValueError("Expected threshold digit after '#'")
        threshold = int(self.text[start:self.idx])
        self._skip_ws()
        if not self._consume("("):
            raise ValueError("Expected '(' after threshold")
        name_start = self.idx
        depth = 1
        while self.idx < len(self.text) and depth > 0:
            if self.text[self.idx] == "(":
                depth += 1
            elif self.text[self.idx] == ")":
                depth -= 1
                if depth == 0:
                    break
            self.idx += 1
        if self.idx >= len(self.text):
            raise ValueError("Expected ')' in threshold expression")
        raw_name = self.text[name_start:self.idx]
        self.idx += 1
        normalized_name = _normalize_token(raw_name)
        if normalized_name in self.flags:
            return int(self.flags[normalized_name]) >= threshold
        value = self.counts.get(normalized_name, 0)
        return value >= threshold

    def _parse_identifier(self) -> bool:
        self._skip_ws()
        start = self.idx
        while self.idx < len(self.text) and self.text[self.idx] not in "|&()":
            self.idx += 1
        name = self.text[start:self.idx].strip()
        if not name:
            raise ValueError("Expected identifier in expression")
        normalized_name = _normalize_token(name)
        if normalized_name in self.flags:
            return self.flags[normalized_name]
        return self.counts.get(normalized_name, 0) > 0


def _evaluate_expr(expr: str, counts: Dict[str, int], flags: Dict[str, bool]) -> bool:
    return _ExprParser(expr, counts, flags).parse()


def _classify_complexity(entries: List[ProblemEntry]) -> Tuple[str, str, Dict[str, Any]]:
    rules = _load_complexity_rules()
    matched_rules: List[Dict[str, Any]] = []

    for rule in rules:
        observed_count = _count_evidence(entries, *rule.path)
        if observed_count >= rule.required_count:
            matched_rules.append(
                {
                    "name": rule.name,
                    "level": rule.level,
                    "required_count": rule.required_count,
                    "observed_count": observed_count,
                    "path": list(rule.path),
                }
            )

    if not matched_rules:
        detail = {
            "category": "",
            "mdm_level_equivalent": "",
            "rules_source": str(COMPLEXITY_RULES_TSV.name),
            "matched_rules": [],
            "reason": "Complexity data not found. Returning blank complexity value.",
            "status": "missing",
        }
        return "", "", detail

    level = max((rule["level"] for rule in matched_rules), key=LEVEL_RANK.get)
    category = "Straightforward" if level == "straightforward" else level
    mdm_level = COMPLEXITY_TO_MDM_LEVEL[category]
    detail = {
        "category": category,
        "mdm_level_equivalent": mdm_level,
        "rules_source": str(COMPLEXITY_RULES_TSV.name),
        "matched_rules": matched_rules,
        "reason": "Highest matching complexity level selected from TSV-driven rule matches.",
    }
    return category, mdm_level, detail


def _classify_data_to_review(entries: List[ProblemEntry]) -> Tuple[str, str, Dict[str, Any]]:
    field_hits = {canonical: False for canonical in DATA_FIELD_ALIASES.values()}
    evidence_seen = False

    for entry in entries:
        data = entry.payload.get("data_to_review")
        if not isinstance(data, dict):
            continue
        for key, value in data.items():
            canonical = DATA_FIELD_ALIASES.get(key)
            if canonical is None:
                continue
            if _has_non_empty_list(value):
                field_hits[canonical] = True
                evidence_seen = True

    limited_category_1_count = sum(
        1
        for key in (
            "review_of_prior_external_note",
            "review_of_test_result",
            "order_of_test",
        )
        if field_hits[key]
    )
    moderate_extensive_category_1_count = sum(
        1
        for key in (
            "review_of_prior_external_note",
            "review_of_test_result",
            "order_of_test",
            "assessment_requiring_independent_historian",
        )
        if field_hits[key]
    )
    independent_historian = field_hits["assessment_requiring_independent_historian"]
    independent_interpretation = field_hits["independent_interpretation_of_test"]
    management_discussion = field_hits["discussion_of_management_or_test_interpretation"]
    moderate_category_hits = sum(
        (
            moderate_extensive_category_1_count >= 3,
            independent_interpretation,
            management_discussion,
        )
    )

    counts = {
        "LimitedCategory1": limited_category_1_count,
        "ModerateExtensiveCategory1": moderate_extensive_category_1_count,
        "ModerateHighCategories": moderate_category_hits,
    }
    flags = {
        "Assessment requiring an independent historian": independent_historian,
        "Independent interpretation of test": independent_interpretation,
        "Discussion of management or test interpretation": management_discussion,
    }

    low_expr = "#2(LimitedCategory1)|(Assessment requiring an independent historian)"
    moderate_expr = (
        "#3(ModerateExtensiveCategory1)|#1(Independent interpretation of test)|#1(Discussion of management or test interpretation)"
    )
    high_expr = "#2(ModerateHighCategories)"

    is_high = _evaluate_expr(high_expr, counts, flags)
    is_moderate = _evaluate_expr(moderate_expr, counts, flags)
    is_low = _evaluate_expr(low_expr, counts, flags)

    if is_high:
        category = "extensive"
        reason = "At least two moderate/high data categories were met."
    elif is_moderate:
        category = "moderate"
        reason = "Moderate threshold met by category-1 count, interpretation, or discussion."
    elif is_low:
        category = "limited"
        reason = "Low/limited threshold met by category-1 count or independent historian."
    elif not evidence_seen:
        category = "minimal"
        reason = "Minimal Data To Review: no supported evidence found."
    else:
        category = "minimal"
        reason = "Supported evidence found, but no low/moderate/high threshold was met."

    mdm_level = DATA_TO_REVIEW_TO_MDM_LEVEL[category]
    detail = {
        "category": category,
        "mdm_level_equivalent": mdm_level,
        "field_hits": field_hits,
        "counts": counts,
        "evaluated_expressions": {
            "low": low_expr,
            "moderate": moderate_expr,
            "high": high_expr,
        },
        "reason": reason,
    }
    return category, mdm_level, detail


def _classify_risk(entries: List[ProblemEntry]) -> Tuple[str, str, Dict[str, Any]]:
    found_types: List[str] = []
    invalid_risk_entries = 0
    risk_evidence_without_valid_type = 0

    for entry in entries:
        risk = entry.payload.get("risk_of_morbidity")
        if not isinstance(risk, dict):
            continue

        normalized_type = _normalize_token(str(risk.get("type", "")))
        if normalized_type in RISK_TO_MDM_LEVEL:
            found_types.append(normalized_type)
            continue

        invalid_risk_entries += 1
        if _has_non_empty_list(risk.get("risk_evidences")):
            # Intentional behavior per spec: do not infer category when type is missing/invalid.
            risk_evidence_without_valid_type += 1

    if not found_types:
        category = "minimal"
        reason = "Minimal Risk: no valid risk type found."
    else:
        category = max((risk_type for risk_type in found_types), key=lambda risk_type: LEVEL_RANK[RISK_TO_MDM_LEVEL[risk_type]])
        reason = "Highest risk category selected across all disease/problem entries."

    mdm_level = RISK_TO_MDM_LEVEL[category]
    detail = {
        "category": category,
        "mdm_level_equivalent": mdm_level,
        "raw_risk_types": found_types,
        "invalid_risk_entries": invalid_risk_entries,
        "risk_evidence_without_valid_type": risk_evidence_without_valid_type,
        "reason": reason,
    }
    return category, mdm_level, detail


def _resolve_final_mdm_level(
    complexity_mdm_level: str,
    data_to_review_mdm_level: str,
    risk_mdm_level: str,
) -> Tuple[str, str, List[str]]:
    inputs = [complexity_mdm_level, data_to_review_mdm_level, risk_mdm_level]
    available_levels = [level for level in inputs if level in LEVEL_RANK]
    missing_levels = [label for label, level in zip(("complexity", "data_to_review", "risk"), inputs) if level not in LEVEL_RANK]

    if not available_levels:
        return "", "No criteria levels were available; returning blank final MDM.", missing_levels

    if len(available_levels) == 1:
        return (
            available_levels[0],
            "Single available criterion used for final MDM level.",
            missing_levels,
        )

    ranks = sorted(LEVEL_RANK[level] for level in available_levels)
    if len(ranks) == 2:
        # Use midpoint with half-up behavior for two available criteria.
        final_rank = int(((ranks[0] + ranks[1]) / 2) + 0.5)
        return (
            LEVEL_ORDER[final_rank],
            "Two available criteria used; final MDM is midpoint of the two levels.",
            missing_levels,
        )

    final_rank = int(median(ranks))
    return LEVEL_ORDER[final_rank], "Median of ordered criteria levels (2-of-3 rule).", missing_levels


def classify_mdm_from_json(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Classify complexity, data-to-review, risk, and final MDM level."""
    entries = _collect_entries(payload)

    complexity, complexity_mdm_level, complexity_detail = _classify_complexity(entries)
    data_to_review, data_to_review_mdm_level, data_detail = _classify_data_to_review(entries)
    risk, risk_mdm_level, risk_detail = _classify_risk(entries)
    final_level, final_rule, missing_criteria = _resolve_final_mdm_level(
        complexity_mdm_level,
        data_to_review_mdm_level,
        risk_mdm_level,
    )
    if missing_criteria:
        LOGGER.warning("MDM computed with missing criteria: %s", ", ".join(missing_criteria))

    return {
        "complexity": complexity,
        "data_to_review": data_to_review,
        "risk": risk,
        "mdm_level": final_level,
        "details": {
            "complexity": complexity_detail,
            "data_to_review": data_detail,
            "risk": risk_detail,
            "final_mdm": {
                "inputs": {
                    "complexity": complexity,
                    "data_to_review": data_to_review,
                    "risk": risk,
                },
                "normalized_inputs": {
                    "complexity": complexity_mdm_level,
                    "data_to_review": data_to_review_mdm_level,
                    "risk": risk_mdm_level,
                },
                "rule": final_rule,
                "missing_criteria": missing_criteria,
                "level": final_level,
            },
        },
    }
