"""Edit input values in this file, then run to print matching E&M codes."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Optional, Union

from em_code_mapper import EMCodeMapper, configure_logging
from mdm_classifier import classify_mdm_from_json

NumberInput = Optional[Union[int, float, str]]

# Update these values directly, then run: python3 direct_find_codes.py
CSV_PATH = Path(__file__).resolve().parent / "E&M Data - E&M Mapping 2.csv"
MDM_SOURCE_JSON_PATH = Path(__file__).resolve().parent / "EandM_Sample.json"
FACILITY_TYPE: Optional[str] = "Non-Face-to-Face Services"
SERVICE_TYPE: Optional[str] = "Self-Measured Blood Pressure - Patient Education & Device Calibration"
PATIENT_TYPE: Optional[str] = "New or Established Patient"
MDM_LEVEL: Optional[str] = None
TIME_VALUE: NumberInput = None
USE_MDM_CLASSIFIER = False


def _to_mapper_mdm_display(level: str) -> str:
    mapping = {
        "straightforward": "Straightforward",
        "low": "Low",
        "moderate": "Moderate",
        "high": "High",
    }
    normalized = level.strip().lower()
    if normalized not in mapping:
        raise ValueError(f"Unsupported classifier MDM level: {level}")
    return mapping[normalized]


def _resolve_mdm_level_from_classifier(
    fallback_mdm_level: Optional[str],
    use_classifier: bool,
    json_path: Path,
) -> Optional[str]:
    if not use_classifier:
        return fallback_mdm_level

    payload = json.loads(json_path.read_text(encoding="utf-8"))
    classification = classify_mdm_from_json(payload)
    return _to_mapper_mdm_display(classification["mdm_level"])


def get_codes(
    csv_path: Path = CSV_PATH,
    facility_type: Optional[str] = FACILITY_TYPE,
    service_type: Optional[str] = SERVICE_TYPE,
    patient_type: Optional[str] = PATIENT_TYPE,
    mdm_level: Optional[str] = MDM_LEVEL,
    time_value: NumberInput = TIME_VALUE,
    use_mdm_classifier: bool = USE_MDM_CLASSIFIER,
    mdm_source_json_path: Path = MDM_SOURCE_JSON_PATH,
) -> list[str]:
    resolved_mdm_level = _resolve_mdm_level_from_classifier(
        fallback_mdm_level=mdm_level,
        use_classifier=use_mdm_classifier,
        json_path=mdm_source_json_path,
    )
    mapper = EMCodeMapper(csv_path=csv_path)
    return mapper.find_codes(
        facility_type=facility_type,
        service_type=service_type,
        patient_type=patient_type,
        mdm_level=resolved_mdm_level,
        time_value=time_value,
    )


def main() -> int:
    configure_logging(logging.INFO)
    codes = get_codes()
    print(json.dumps({"count": len(codes), "codes": codes}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
