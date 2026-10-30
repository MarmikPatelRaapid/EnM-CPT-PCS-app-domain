"""CLI helper to query E&M codes by input fields."""

from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path
from typing import Optional, Sequence

from em_code_mapper import EMCodeMapper, configure_logging

LOGGER = logging.getLogger(__name__)


def _optional_text(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    stripped = value.strip()
    return stripped if stripped else None


def run_lookup(
    csv_path: Path,
    facility_type: Optional[str] = None,
    service_type: Optional[str] = None,
    patient_type: Optional[str] = None,
    mdm_level: Optional[str] = None,
    time_value: Optional[int] = None,
) -> list[str]:
    mapper = EMCodeMapper(csv_path=csv_path)
    return mapper.find_codes(
        facility_type=_optional_text(facility_type),
        service_type=_optional_text(service_type),
        patient_type=_optional_text(patient_type),
        mdm_level=_optional_text(mdm_level),
        time_value=time_value,
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Query E&M codes using facility/service/patient/MDM/time filters."
    )
    parser.add_argument(
        "--csv-path",
        default=str(Path(__file__).resolve().parent / "E&M Data - E&M Mapping 2.csv"),
        help="Path to mapping CSV file.",
    )
    parser.add_argument("--facility-type", default=None, help="facility_type filter")
    parser.add_argument("--service-type", default=None, help="service_type filter")
    parser.add_argument("--patient-type", default=None, help="patient_type filter")
    parser.add_argument("--mdm-level", default=None, help="mdm_level filter")
    parser.add_argument("--time-value", type=int, default=None, help="Visit time in minutes")
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
        help="Logging level for troubleshooting.",
    )
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    configure_logging(getattr(logging, args.log_level))
    try:
        codes = run_lookup(
            csv_path=Path(args.csv_path),
            facility_type=args.facility_type,
            service_type=args.service_type,
            patient_type=args.patient_type,
            mdm_level=args.mdm_level,
            time_value=args.time_value,
        )
        print(json.dumps({"count": len(codes), "codes": codes}, indent=2))
        return 0
    except Exception:
        LOGGER.exception("Failed to query E&M codes.")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
