import unittest
from tempfile import TemporaryDirectory
from pathlib import Path

from em_code_mapper import EMCodeMapper


class TestEMCodeMapper(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        project_root = Path(__file__).resolve().parents[1]
        csv_path = project_root / "E&M Data - E&M Mapping 2.csv"
        cls.mapper = EMCodeMapper(csv_path)
        csv_path_v3 = project_root / "E&M Data - E&M Mapping 3 processed.csv"
        cls.mapper_v3 = EMCodeMapper(csv_path_v3)

    def test_facility_only_returns_all_possible_codes(self) -> None:
        codes = self.mapper.find_codes(facility_type="Telemedicine Services")

        self.assertEqual(len(codes), 20)
        self.assertIn("98016", codes)
        self.assertIn("99423", codes)

    def test_facility_and_service_filters_return_expected_subset(self) -> None:
        codes = self.mapper.find_codes(
            facility_type="Telemedicine Services",
            service_type="Online Digital E/M (Asynchronous)",
        )

        self.assertEqual(codes, ["99421", "99422", "99423"])

    def test_time_only_variants_are_normalized(self) -> None:
        params = {
            "facility_type": "Hospital Inpatient and Observation Care",
            "service_type": "Hospital Inpatient or Observation Discharge Services",
            "patient_type": "New or Established",
        }
        em_dash_codes = self.mapper.find_codes(mdm_level="N/A — Time only", **params)
        hyphen_codes = self.mapper.find_codes(mdm_level="N/A - Time only", **params)

        self.assertEqual(em_dash_codes, ["99238", "99239"])
        self.assertEqual(hyphen_codes, em_dash_codes)

    def test_time_value_matches_when_inside_range(self) -> None:
        codes = self.mapper.find_codes(
            facility_type="Telemedicine Services",
            service_type="Brief Synchronous Communication (Virtual Check-In)",
            mdm_level="N/A - Time only",
            time_value=7,
        )

        self.assertEqual(codes, ["98016"])

    def test_when_mdm_and_time_are_both_given_either_can_match(self) -> None:
        # MDM mismatches, but time range matches; row should still match.
        codes_from_time_match = self.mapper.find_codes(
            facility_type="Telemedicine Services",
            service_type="Brief Synchronous Communication (Virtual Check-In)",
            mdm_level="Low",
            time_value=7,
        )
        self.assertEqual(codes_from_time_match, ["98016"])

        # MDM matches, but time is outside range; row should still match.
        codes_from_mdm_match = self.mapper.find_codes(
            facility_type="Telemedicine Services",
            service_type="Brief Synchronous Communication (Virtual Check-In)",
            mdm_level="N/A - Time only",
            time_value=100,
        )
        self.assertEqual(codes_from_mdm_match, ["98016"])

    def test_when_both_mdm_and_time_are_given_returns_highest_code_only(self) -> None:
        codes = self.mapper.find_codes(
            facility_type="Telemedicine Services",
            service_type="Synchronous Audio-Video",
            patient_type="Established Patient",
            mdm_level="High",
            time_value=10,
        )
        self.assertEqual(codes, ["98007"])

    def test_exact_mdm_matches_are_prioritized_over_na_fallback_rows(self) -> None:
        csv_content = """facility_type,service_type,patient_type,mdm_level,Time Min,Time Max,Code,Is Valid Mapping?
Test Facility,Test Service,Test Patient,N/A,10,20,1000,yes
Test Facility,Test Service,Test Patient,High,30,40,0900,yes
"""
        with TemporaryDirectory() as temp_dir:
            csv_path = Path(temp_dir) / "mapping.csv"
            csv_path.write_text(csv_content, encoding="utf-8")
            mapper = EMCodeMapper(csv_path)

            mdm_only_codes = mapper.find_codes(
                facility_type="Test Facility",
                service_type="Test Service",
                patient_type="Test Patient",
                mdm_level="High",
            )
            self.assertEqual(mdm_only_codes, ["0900"])

            mdm_and_time_codes = mapper.find_codes(
                facility_type="Test Facility",
                service_type="Test Service",
                patient_type="Test Patient",
                mdm_level="High",
                time_value=15,
            )
            self.assertEqual(mdm_and_time_codes, ["0900"])

    def test_invalid_numeric_filter_raises(self) -> None:
        with self.assertRaises(ValueError):
            self.mapper.find_codes(facility_type="Telemedicine Services", time_value="bad-value")

    def test_min_max_input_arguments_are_not_supported(self) -> None:
        with self.assertRaises(TypeError):
            self.mapper.find_codes(facility_type="Telemedicine Services", Min=10)

    def test_v3_exact_mdm_rows_are_preferred_over_na_wildcard(self) -> None:
        codes = self.mapper_v3.find_codes(
            facility_type="Office or Other Outpatient Services",
            service_type="Office or Other Outpatient Visit",
            patient_type="Established Patient",
            mdm_level="High",
        )
        self.assertEqual(codes, ["99215"])

    def test_v3_age_filter_normalizes_units_before_matching(self) -> None:
        codes = self.mapper_v3.find_codes(
            facility_type="Preventive Medicine Services",
            service_type="Initial Comprehensive Preventive Medicine",
            patient_type="New Patient",
            mdm_level="N/A",
            patient_age=6,
            patient_age_unit="months",
        )
        self.assertEqual(codes, ["99381"])


if __name__ == "__main__":
    unittest.main()
