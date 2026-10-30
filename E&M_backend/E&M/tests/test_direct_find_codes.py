import unittest
from pathlib import Path

from direct_find_codes import get_codes


class TestDirectFindCodes(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.csv_path = Path(__file__).resolve().parents[1] / "E&M Data - E&M Mapping 2.csv"

    def test_get_codes_works_with_explicit_inputs(self) -> None:
        codes = get_codes(
            csv_path=self.csv_path,
            facility_type="Telemedicine Services",
            service_type="Online Digital E/M (Asynchronous)",
            patient_type=None,
            mdm_level=None,
            time_value=None,
        )
        self.assertEqual(codes, ["99421", "99422", "99423"])


if __name__ == "__main__":
    unittest.main()
