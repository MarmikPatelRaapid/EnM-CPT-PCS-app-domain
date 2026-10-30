"""Database-driven E&M code mapping with partial matching and debug logging."""

from __future__ import annotations

import logging
import re
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Union

LOGGER = logging.getLogger(__name__)

MdmInput = Optional[Union[str, int]]
NumberInput = Optional[Union[str, int, float]]


def _normalize_text(value: MdmInput) -> Optional[str]:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    text = text.replace("—", "-").replace("–", "-")
    text = re.sub(r"\s+", " ", text)
    return text.casefold()


def _normalize_mdm(value: MdmInput) -> Optional[str]:
    normalized = _normalize_text(value)
    if normalized is None:
        return None
    if "time only" in normalized:
        return "n/a - time only"
    return normalized


def _parse_optional_int(value: NumberInput, field_name: str) -> Optional[int]:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    try:
        return int(float(text))
    except ValueError as exc:
        raise ValueError(f"Invalid numeric value '{value}' for '{field_name}'.") from exc


def _time_in_range(
    time_value: int, row_min: Optional[int], row_max: Optional[int]
) -> bool:
    if row_min is not None and time_value < row_min:
        return False
    if row_max is not None and time_value > row_max:
        return False
    return True


def _code_rank_key(code: str) -> tuple[int, int, str]:
    text = str(code).strip()
    if text.isdigit():
        return (1, int(text), text)
    return (0, 0, text)


def _quote_identifier(identifier: str) -> str:
    # Safe quoting for SQLite identifiers used in SQL statements.
    return f"\"{identifier.replace('\"', '\"\"')}\""


@dataclass(frozen=True)
class DBMappingConfig:
    facility_type_col: str = "facility_type"
    service_type_col: str = "service_type"
    patient_type_col: str = "patient_type"
    mdm_level_col: str = "mdm_level"
    min_col: str = "Min"
    max_col: str = "Max"
    code_col: str = "Code"
    is_valid_mapping_col: str = "Is Valid Mapping?"
    valid_mapping_values: Sequence[str] = ("yes", "true", "1", "y")


class EMCodeMapperDB:
    """Loads E&M mappings from a database table and returns matching codes."""

    def __init__(
        self,
        db_path: Union[str, Path],
        table_name: str,
        config: Optional[DBMappingConfig] = None,
    ) -> None:
        self.db_path = Path(db_path)
        self.table_name = table_name
        self.config = config or DBMappingConfig()
        self._rows = self._load_rows()

    def _load_rows(self) -> List[Dict[str, Any]]:
        LOGGER.info("Loading E&M mapping table '%s' from '%s'.", self.table_name, self.db_path)
        if not self.db_path.exists():
            raise FileNotFoundError(f"Database file not found: {self.db_path}")

        parsed_rows: List[Dict[str, Any]] = []
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            headers = self._get_table_columns(conn)
            self._validate_required_columns(headers)
            query = f"SELECT * FROM {_quote_identifier(self.table_name)}"
            cursor = conn.execute(query)
            for row_number, raw_row in enumerate(cursor, start=1):
                raw_map = dict(raw_row)
                try:
                    if not self._is_valid_mapping(raw_map):
                        LOGGER.debug("Skipping invalid mapping row %s.", row_number)
                        continue
                    parsed_rows.append(
                        {
                            "facility_type": _normalize_text(
                                raw_map.get(self.config.facility_type_col)
                            ),
                            "service_type": _normalize_text(
                                raw_map.get(self.config.service_type_col)
                            ),
                            "patient_type": _normalize_text(
                                raw_map.get(self.config.patient_type_col)
                            ),
                            "mdm_level": _normalize_mdm(raw_map.get(self.config.mdm_level_col)),
                            "min": _parse_optional_int(
                                raw_map.get(self.config.min_col), self.config.min_col
                            ),
                            "max": _parse_optional_int(
                                raw_map.get(self.config.max_col), self.config.max_col
                            ),
                            "code": str(raw_map.get(self.config.code_col, "")).strip(),
                            "raw": raw_map,
                        }
                    )
                except Exception:
                    LOGGER.exception(
                        "Failed parsing row %s in table '%s'. Row value: %s",
                        row_number,
                        self.table_name,
                        raw_map,
                    )
                    raise
        finally:
            conn.close()

        LOGGER.info("Loaded %s valid mappings from table '%s'.", len(parsed_rows), self.table_name)
        return parsed_rows

    def _get_table_columns(self, conn: sqlite3.Connection) -> List[str]:
        pragma_query = f"PRAGMA table_info({_quote_identifier(self.table_name)})"
        table_info_rows = conn.execute(pragma_query).fetchall()
        if not table_info_rows:
            raise ValueError(f"Table '{self.table_name}' was not found or has no columns.")
        return [str(row["name"]) for row in table_info_rows]

    def _validate_required_columns(self, headers: Sequence[str]) -> None:
        required = {
            self.config.facility_type_col,
            self.config.service_type_col,
            self.config.patient_type_col,
            self.config.mdm_level_col,
            self.config.min_col,
            self.config.max_col,
            self.config.code_col,
        }
        missing = required - set(headers)
        if missing:
            raise ValueError(
                f"Missing required columns in table '{self.table_name}': {sorted(missing)}. "
                "Update DBMappingConfig if your table uses different names."
            )

    def _is_valid_mapping(self, row: Dict[str, Any]) -> bool:
        column_name = self.config.is_valid_mapping_col
        if column_name not in row:
            return True
        value = _normalize_text(row.get(column_name))
        if value is None:
            return True
        return value in {v.casefold() for v in self.config.valid_mapping_values}

    def find_matches(
        self,
        facility_type: Optional[str] = None,
        service_type: Optional[str] = None,
        patient_type: Optional[str] = None,
        mdm_level: Optional[str] = None,
        time_value: NumberInput = None,
    ) -> List[Dict[str, Any]]:
        normalized_criteria = {
            "facility_type": _normalize_text(facility_type),
            "service_type": _normalize_text(service_type),
            "patient_type": _normalize_text(patient_type),
            "mdm_level": _normalize_mdm(mdm_level),
            "time_value": _parse_optional_int(time_value, "time_value"),
        }
        LOGGER.info("Running DB code lookup with filters: %s", normalized_criteria)

        matches: List[Dict[str, Any]] = []
        for row in self._rows:
            if not self._matches_row(row, normalized_criteria):
                continue
            matches.append(row)
        LOGGER.info("Found %s matching rows from DB.", len(matches))
        return matches

    def find_codes(
        self,
        facility_type: Optional[str] = None,
        service_type: Optional[str] = None,
        patient_type: Optional[str] = None,
        mdm_level: Optional[str] = None,
        time_value: NumberInput = None,
    ) -> List[str]:
        normalized_mdm = _normalize_mdm(mdm_level)
        normalized_time = _parse_optional_int(time_value, "time_value")
        matches = self.find_matches(
            facility_type=facility_type,
            service_type=service_type,
            patient_type=patient_type,
            mdm_level=mdm_level,
            time_value=time_value,
        )
        seen = set()
        codes: List[str] = []
        for row in matches:
            code = row["code"]
            if code and code not in seen:
                seen.add(code)
                codes.append(code)

        if normalized_mdm is not None and normalized_time is not None and codes:
            highest_code = max(codes, key=_code_rank_key)
            LOGGER.debug(
                "Both mdm_level and time_value provided; returning highest matched DB code '%s'.",
                highest_code,
            )
            return [highest_code]

        LOGGER.debug("Returning %s unique DB codes.", len(codes))
        return codes

    @staticmethod
    def _matches_row(row: Dict[str, Any], criteria: Dict[str, Any]) -> bool:
        for field in ("facility_type", "service_type", "patient_type"):
            expected = criteria[field]
            if expected is None:
                continue
            if row[field] != expected:
                return False

        expected_mdm = criteria["mdm_level"]
        expected_time = criteria["time_value"]

        if expected_mdm is not None and expected_time is not None:
            mdm_matches = row["mdm_level"] == expected_mdm
            time_matches = _time_in_range(expected_time, row["min"], row["max"])
            return mdm_matches or time_matches

        if expected_mdm is not None and row["mdm_level"] != expected_mdm:
            return False

        if expected_time is not None and not _time_in_range(expected_time, row["min"], row["max"]):
            return False

        return True
