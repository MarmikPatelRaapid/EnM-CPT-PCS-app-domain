import io
import json
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from query_em_codes import main, run_lookup


class TestQueryEmCodes(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.csv_path = Path(__file__).resolve().parents[1] / "E&M Data - E&M Mapping 2.csv"

    def test_run_lookup_with_partial_input(self) -> None:
        codes = run_lookup(
            csv_path=self.csv_path,
            facility_type="Telemedicine Services",
            service_type="Online Digital E/M (Asynchronous)",
        )
        self.assertEqual(codes, ["99421", "99422", "99423"])

    def test_run_lookup_time_only_case(self) -> None:
        codes = run_lookup(
            csv_path=self.csv_path,
            facility_type="Telemedicine Services",
            service_type="Brief Synchronous Communication (Virtual Check-In)",
            patient_type="Established Patient",
            mdm_level="N/A — Time only",
            time_value=7,
        )
        self.assertEqual(codes, ["98016"])

    def test_main_prints_json_output(self) -> None:
        stdout_buffer = io.StringIO()
        with redirect_stdout(stdout_buffer):
            exit_code = main(
                [
                    "--csv-path",
                    str(self.csv_path),
                    "--facility-type",
                    "Telemedicine Services",
                    "--service-type",
                    "Online Digital E/M (Asynchronous)",
                ]
            )
        self.assertEqual(exit_code, 0)
        payload = json.loads(stdout_buffer.getvalue())
        self.assertEqual(payload["count"], 3)
        self.assertEqual(payload["codes"], ["99421", "99422", "99423"])


if __name__ == "__main__":
    unittest.main()
