import csv
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import process_em_mapping_csv as processor
from process_em_mapping_csv import expand_row


class TestProcessEMMappingCsv(unittest.TestCase):
    def test_expands_patient_type_and_mdm_level_or_values(self) -> None:
        row = {
            "facility_type": "Hospital Inpatient and Observation Care",
            "service_type": "Initial Hospital Inpatient or Observation Care",
            "patient_type": "New or Established",
            "mdm_level": "Straightforward or Low",
            "Code": "99221",
        }

        expanded = expand_row(row)

        self.assertEqual(
            [
                (item["patient_type"], item["mdm_level"], item["Code"])
                for item in expanded
            ],
            [
                ("New Patient", "Straightforward", "99221"),
                ("New Patient", "Low", "99221"),
                ("Established Patient", "Straightforward", "99221"),
                ("Established Patient", "Low", "99221"),
            ],
        )

    def test_expands_new_or_established_patient_phrase(self) -> None:
        row = {
            "patient_type": "New or Established Patient",
            "mdm_level": "Moderate",
            "Code": "99244",
        }

        expanded = expand_row(row)

        self.assertEqual(
            [item["patient_type"] for item in expanded],
            ["New Patient", "Established Patient"],
        )
        self.assertEqual([item["mdm_level"] for item in expanded], ["Moderate", "Moderate"])

    def test_main_uses_paths_configured_in_code(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            input_path = Path(temp_dir) / "raw.csv"
            output_path = Path(temp_dir) / "processed.csv"
            input_path.write_text(
                "patient_type,mdm_level,Code\n"
                "New or Established,Straightforward or Low,99221\n",
                encoding="utf-8",
            )

            with (
                patch.object(processor, "INPUT_CSV_PATH", input_path, create=True),
                patch.object(processor, "OUTPUT_CSV_PATH", output_path, create=True),
                patch("sys.argv", ["process_em_mapping_csv.py"]),
            ):
                self.assertEqual(processor.main(), 0)

            with output_path.open("r", encoding="utf-8", newline="") as output_file:
                rows = list(csv.DictReader(output_file))

            self.assertEqual(len(rows), 4)
            self.assertEqual(rows[-1]["patient_type"], "Established Patient")
            self.assertEqual(rows[-1]["mdm_level"], "Low")


if __name__ == "__main__":
    unittest.main()
