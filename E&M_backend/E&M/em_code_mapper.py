"""CSV-driven E&M code mapping with partial matching and debug logging."""

from __future__ import annotations

import csv
import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Union

LOGGER = logging.getLogger(__name__)

MdmInput = Optional[Union[str, int]]
NumberInput = Optional[Union[str, int, float]]


def configure_logging(level: int = logging.INFO) -> None:
    """Set a sensible default log format for troubleshooting."""
    logging.basicConfig(
        level=level,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    )


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

    if normalized == "n/a":
        return "n/a"
    # Keep all "time only" variants compatible (e.g., N/A — Time only).
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


def _normalize_age_unit(value: Optional[str]) -> Optional[str]:
    normalized = _normalize_text(value)
    if normalized is None:
        return None
    mapping = {
        "day": "days",
        "days": "days",
        "month": "months",
        "months": "months",
        "year": "years",
        "years": "years",
    }
    return mapping.get(normalized, normalized)


def _convert_age_to_days(age_value: int, age_unit: Optional[str]) -> Optional[int]:
    unit = _normalize_age_unit(age_unit)
    if unit is None:
        return None
    if unit == "days":
        return age_value
    if unit == "months":
        return age_value * 30
    if unit == "years":
        return age_value * 365
    raise ValueError(f"Unsupported age unit '{age_unit}'. Expected days/months/years.")


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


@dataclass(frozen=True)
class MappingConfig:
    facility_type_col: str = "facility_type"
    service_type_col: str = "service_type"
    patient_type_col: str = "patient_type"
    mdm_level_col: str = "mdm_level"
    min_col: str = "Time Min"
    max_col: str = "Time Max"
    age_min_col: str = "Age Min"
    age_max_col: str = "Age Max"
    age_unit_col: str = "Age unit"
    code_col: str = "Code"
    is_valid_mapping_col: str = "Is Valid Mapping?"
    valid_mapping_values: Sequence[str] = ("yes", "true", "1", "y")


class EMCodeMapper:
    """Loads a CSV map and returns matching codes for provided filters."""

    _COLUMN_ALIASES = {
        "time min": ("min",),
        "time max": ("max",),
        "age min": (),
        "age max": (),
        "age unit": (),
    }

    def __init__(self, csv_path: Union[str, Path], config: Optional[MappingConfig] = None):
        self.csv_path = Path(csv_path)
        self.config = config or MappingConfig()
        self._rows = self._load_rows()

    def _load_rows(self) -> List[Dict[str, Any]]:
        LOGGER.info("Loading E&M mapping file from '%s'.", self.csv_path)
        if not self.csv_path.exists():
            raise FileNotFoundError(f"Mapping file not found: {self.csv_path}")

        with self.csv_path.open("r", encoding="utf-8-sig", newline="") as file_handle:
            reader = csv.DictReader(file_handle)
            if reader.fieldnames is None:
                raise ValueError(f"CSV file '{self.csv_path}' does not contain headers.")

            self._validate_required_columns(reader.fieldnames)
            parsed_rows: List[Dict[str, Any]] = []

            for row_number, raw_row in enumerate(reader, start=2):
                try:
                    if not self._is_valid_mapping(raw_row):
                        LOGGER.debug("Skipping invalid mapping row %s.", row_number)
                        continue

                    age_min = _parse_optional_int(
                        self._get_field(raw_row, self.config.age_min_col),
                        self.config.age_min_col,
                    )
                    age_max = _parse_optional_int(
                        self._get_field(raw_row, self.config.age_max_col),
                        self.config.age_max_col,
                    )
                    age_unit = _normalize_age_unit(
                        self._get_field(raw_row, self.config.age_unit_col)
                    )
                    age_min_days = (
                        _convert_age_to_days(age_min, age_unit)
                        if age_min is not None and age_unit is not None
                        else None
                    )
                    age_max_days = (
                        _convert_age_to_days(age_max, age_unit)
                        if age_max is not None and age_unit is not None
                        else None
                    )

                    parsed_rows.append(
                        {
                            "facility_type": _normalize_text(
                                self._get_field(raw_row, self.config.facility_type_col)
                            ),
                            "service_type": _normalize_text(
                                self._get_field(raw_row, self.config.service_type_col)
                            ),
                            "patient_type": _normalize_text(
                                self._get_field(raw_row, self.config.patient_type_col)
                            ),
                            "mdm_level": _normalize_mdm(
                                self._get_field(raw_row, self.config.mdm_level_col)
                            ),
                            "min": _parse_optional_int(
                                self._get_field(raw_row, self.config.min_col),
                                self.config.min_col,
                            ),
                            "max": _parse_optional_int(
                                self._get_field(raw_row, self.config.max_col),
                                self.config.max_col,
                            ),
                            "age_min_days": age_min_days,
                            "age_max_days": age_max_days,
                            "code": str(self._get_field(raw_row, self.config.code_col) or "").strip(),
                            "raw": raw_row,
                        }
                    )
                except Exception:
                    LOGGER.exception(
                        "Failed parsing row %s in '%s'. Row value: %s",
                        row_number,
                        self.csv_path,
                        raw_row,
                    )
                    raise

        LOGGER.info("Loaded %s valid mappings from '%s'.", len(parsed_rows), self.csv_path)
        return parsed_rows

    @staticmethod
    def _canonical_header(value: str) -> str:
        return str(value).strip().casefold()

    def _column_candidates(self, column_name: str) -> List[str]:
        canonical = self._canonical_header(column_name)
        aliases = self._COLUMN_ALIASES.get(canonical, ())
        return [column_name, *aliases]

    def _get_field(self, row: Dict[str, Any], column_name: str) -> Any:
        for candidate in self._column_candidates(column_name):
            if candidate in row:
                return row.get(candidate)
            expected = self._canonical_header(candidate)
            for key, value in row.items():
                if self._canonical_header(key) == expected:
                    return value
        return None

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
        canonical_headers = {self._canonical_header(header) for header in headers}
        missing = {
            col
            for col in required
            if not any(
                self._canonical_header(candidate) in canonical_headers
                for candidate in self._column_candidates(col)
            )
        }
        if missing:
            raise ValueError(
                f"Missing required columns in mapping CSV: {sorted(missing)}. "
                "Update MappingConfig if your file uses different names."
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
        patient_age: NumberInput = None,
        patient_age_unit: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Return all rows matching any provided subset of filters."""
        normalized_criteria = {
            "facility_type": _normalize_text(facility_type),
            "service_type": _normalize_text(service_type),
            "patient_type": _normalize_text(patient_type),
            "mdm_level": _normalize_mdm(mdm_level),
            "time_value": _parse_optional_int(time_value, "time_value"),
            "patient_age": _parse_optional_int(patient_age, "patient_age"),
            "patient_age_unit": _normalize_age_unit(patient_age_unit),
        }
        if (
            normalized_criteria["patient_age"] is None
            and normalized_criteria["patient_age_unit"] is not None
        ):
            raise ValueError("patient_age_unit provided without patient_age.")

        age_days = None
        if normalized_criteria["patient_age"] is not None:
            age_days = _convert_age_to_days(
                normalized_criteria["patient_age"],
                normalized_criteria["patient_age_unit"],
            )
        normalized_criteria["patient_age_days"] = age_days
        LOGGER.info("Running code lookup with filters: %s", normalized_criteria)

        matches: List[Dict[str, Any]] = []
        for row in self._rows:
            if not self._matches_row(row, normalized_criteria):
                continue
            matches.append(row)

        LOGGER.info("Found %s matching rows.", len(matches))
        return matches

    def find_codes(
        self,
        facility_type: Optional[str] = None,
        service_type: Optional[str] = None,
        patient_type: Optional[str] = None,
        mdm_level: Optional[str] = None,
        time_value: NumberInput = None,
        patient_age: NumberInput = None,
        patient_age_unit: Optional[str] = None,
    ) -> List[str]:
        """Return unique codes for filters; supports partial input."""
        normalized_mdm = _normalize_mdm(mdm_level)
        normalized_time = _parse_optional_int(time_value, "time_value")
        matches = self.find_matches(
            facility_type=facility_type,
            service_type=service_type,
            patient_type=patient_type,
            mdm_level=mdm_level,
            time_value=time_value,
            patient_age=patient_age,
            patient_age_unit=patient_age_unit,
        )
        selected_matches = matches
        if normalized_mdm is not None and matches:
            exact_mdm_matches = [
                row for row in matches if row["mdm_level"] == normalized_mdm
            ]
            if exact_mdm_matches:
                LOGGER.debug(
                    "Exact MDM matches found (%s); prioritizing them over fallback rows.",
                    len(exact_mdm_matches),
                )
                selected_matches = exact_mdm_matches

        seen = set()
        codes: List[str] = []
        for row in selected_matches:
            code = row["code"]
            if code and code not in seen:
                seen.add(code)
                codes.append(code)

        if normalized_mdm is not None and normalized_time is not None and codes:
            highest_code = max(codes, key=_code_rank_key)
            LOGGER.debug(
                "Both mdm_level and time_value provided; returning highest matched code '%s'.",
                highest_code,
            )
            return [highest_code]

        LOGGER.debug("Returning %s unique codes.", len(codes))
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
        expected_age_days = criteria["patient_age_days"]

        if expected_age_days is not None and not _time_in_range(
            expected_age_days,
            row["age_min_days"],
            row["age_max_days"],
        ):
            return False

        if expected_mdm is not None and expected_time is not None:
            mdm_matches = row["mdm_level"] in {expected_mdm, "n/a"}
            time_matches = _time_in_range(expected_time, row["min"], row["max"])
            return mdm_matches or time_matches

        if expected_mdm is not None and row["mdm_level"] not in {expected_mdm, "n/a"}:
            return False

        if expected_time is not None and not _time_in_range(expected_time, row["min"], row["max"]):
            return False

        return True
