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

        # N/A rows are MDM wildcards but still enforce their time range, so an
        # out-of-range time must not match even though MDM is "N/A".
        codes_outside_na_time_range = self.mapper.find_codes(
            facility_type="Telemedicine Services",
            service_type="Brief Synchronous Communication (Virtual Check-In)",
            mdm_level="N/A - Time only",
            time_value=100,
        )
        self.assertEqual(codes_outside_na_time_range, [])

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


class TestNaMdmRowsEnforceTimeAndAge(unittest.TestCase):
    """N/A in the reference sheet matches any evidence MDM, but time/age still apply."""

    @classmethod
    def setUpClass(cls) -> None:
        project_root = Path(__file__).resolve().parents[1]
        cls.mapper_v3 = EMCodeMapper(project_root / "E&M Data - E&M Mapping 3 processed.csv")

    def test_na_rows_use_time_range_then_highest_code(self) -> None:
        params = {
            "facility_type": "Hospital Inpatient and Observation Care",
            "service_type": "Hospital Inpatient or Observation Discharge Services",
            "patient_type": "Established Patient",
            "mdm_level": "Moderate",
        }
        self.assertEqual(self.mapper_v3.find_codes(time_value=20, **params), ["99238"])
        self.assertEqual(self.mapper_v3.find_codes(time_value=45, **params), ["99239"])

    def test_na_rows_do_not_jump_to_open_ended_code(self) -> None:
        codes = self.mapper_v3.find_codes(
            facility_type="Telemedicine Services",
            service_type="Online Digital E/M (Asynchronous)",
            patient_type="Established Patient",
            mdm_level="High",
            time_value=15,
        )
        self.assertEqual(codes, ["99422"])

    def test_na_row_outside_time_range_does_not_match(self) -> None:
        codes = self.mapper_v3.find_codes(
            facility_type="Telemedicine Services",
            service_type="Brief Synchronous Communication (Virtual Check-In)",
            patient_type="Established Patient",
            mdm_level="Low",
            time_value=30,
        )
        self.assertEqual(codes, [])

    def test_na_rows_without_time_bounds_still_check_age(self) -> None:
        codes = self.mapper_v3.find_codes(
            facility_type="Preventive Medicine Services",
            service_type="Initial Comprehensive Preventive Medicine",
            patient_type="New Patient",
            mdm_level="Low",
            time_value=30,
            patient_age=6,
            patient_age_unit="months",
        )
        self.assertEqual(codes, ["99381"])

    def test_na_mdm_matches_any_level_when_no_time_given(self) -> None:
        codes = self.mapper_v3.find_codes(
            facility_type="Hospital Inpatient and Observation Care",
            service_type="Hospital Inpatient or Observation Discharge Services",
            patient_type="Established Patient",
            mdm_level="High",
        )
        self.assertEqual(codes, ["99238", "99239"])

    def test_mixed_sheet_na_row_needs_time_while_leveled_row_uses_mdm_or_time(self) -> None:
        csv_content = """facility_type,service_type,patient_type,mdm_level,Time Min,Time Max,Code,Is Valid Mapping?
F,S,P,N/A,10,20,1000,yes
F,S,P,High,30,40,0900,yes
"""
        with TemporaryDirectory() as temp_dir:
            csv_path = Path(temp_dir) / "mapping.csv"
            csv_path.write_text(csv_content, encoding="utf-8")
            mapper = EMCodeMapper(csv_path)
            params = {"facility_type": "F", "service_type": "S", "patient_type": "P"}

            self.assertEqual(mapper.find_codes(mdm_level="Low", time_value=15, **params), ["1000"])
            self.assertEqual(mapper.find_codes(mdm_level="Low", time_value=35, **params), ["0900"])
            self.assertEqual(mapper.find_codes(mdm_level="Low", time_value=50, **params), [])



class TestPhysicianAndStaffTimeRanges(unittest.TestCase):
    """Each row picks its time source from which Phy/Staff range columns it fills."""

    CSV = """facility_type,service_type,patient_type,mdm_level,Phy Time Min,Phy Time Max,Staff Time Min,Staff Time Max,Code,Is Valid Mapping?
F,PHY,P,N/A,10,20,,,1001,yes
F,STAFF,P,N/A,,,30,40,2001,yes
F,SAME,P,N/A,10,20,10,20,3001,yes
F,DIFF,P,N/A,10,20,30,40,4001,yes
F,NORANGE,P,N/A,,,,,5001,yes
F,LEVELED_STAFF,P,High,,,30,40,6001,yes
"""

    @classmethod
    def setUpClass(cls) -> None:
        cls._temp_dir = TemporaryDirectory()
        csv_path = Path(cls._temp_dir.name) / "mapping.csv"
        csv_path.write_text(cls.CSV, encoding="utf-8")
        cls.mapper = EMCodeMapper(csv_path)

    @classmethod
    def tearDownClass(cls) -> None:
        cls._temp_dir.cleanup()

    def codes(self, service: str, **kwargs):
        return self.mapper.find_codes(facility_type="F", service_type=service, patient_type="P", **kwargs)

    def test_physician_only_row_ignores_staff_time(self) -> None:
        self.assertEqual(self.codes("PHY", physician_time=15, staff_time=99), ["1001"])
        self.assertEqual(self.codes("PHY", physician_time=99, staff_time=15), [])

    def test_staff_only_row_ignores_physician_time(self) -> None:
        self.assertEqual(self.codes("STAFF", physician_time=5, staff_time=35), ["2001"])
        self.assertEqual(self.codes("STAFF", physician_time=35, staff_time=5), [])

    def test_staff_only_row_without_staff_time_treated_as_no_time(self) -> None:
        # Only physician time in evidence: no applicable time, so the row is not time-filtered.
        self.assertEqual(self.codes("STAFF", physician_time=35), ["2001"])

    def test_identical_ranges_use_physician_time(self) -> None:
        self.assertEqual(self.codes("SAME", physician_time=15, staff_time=99), ["3001"])
        self.assertEqual(self.codes("SAME", physician_time=99, staff_time=15), [])

    def test_identical_ranges_fall_back_to_staff_when_physician_missing(self) -> None:
        self.assertEqual(self.codes("SAME", staff_time=15), ["3001"])
        self.assertEqual(self.codes("SAME", staff_time=99), [])

    def test_different_ranges_match_when_either_time_in_range(self) -> None:
        self.assertEqual(self.codes("DIFF", physician_time=15, staff_time=99), ["4001"])
        self.assertEqual(self.codes("DIFF", physician_time=99, staff_time=35), ["4001"])
        self.assertEqual(self.codes("DIFF", physician_time=15, staff_time=35), ["4001"])
        self.assertEqual(self.codes("DIFF", physician_time=99, staff_time=99), [])

    def test_different_ranges_with_single_time_use_that_time(self) -> None:
        self.assertEqual(self.codes("DIFF", staff_time=35), ["4001"])
        self.assertEqual(self.codes("DIFF", staff_time=15), [])
        self.assertEqual(self.codes("DIFF", physician_time=15), ["4001"])

    def test_row_without_ranges_matches_any_time(self) -> None:
        self.assertEqual(self.codes("NORANGE", physician_time=500, staff_time=500), ["5001"])

    def test_leveled_staff_row_uses_mdm_or_staff_time(self) -> None:
        self.assertEqual(self.codes("LEVELED_STAFF", mdm_level="Low", staff_time=35), ["6001"])
        self.assertEqual(self.codes("LEVELED_STAFF", mdm_level="Low", staff_time=99), [])
        # Physician time alone does not apply to a staff-only row, so MDM decides.
        self.assertEqual(self.codes("LEVELED_STAFF", mdm_level="Low", physician_time=35), [])
        self.assertEqual(self.codes("LEVELED_STAFF", mdm_level="High", physician_time=99), ["6001"])

    def test_time_value_is_alias_for_physician_time(self) -> None:
        self.assertEqual(self.codes("PHY", time_value=15), ["1001"])
        self.assertEqual(self.codes("STAFF", time_value=5, staff_time=35), ["2001"])
        with self.assertRaises(ValueError):
            self.codes("PHY", time_value=15, physician_time=16)

    def test_legacy_time_min_max_columns_are_physician_ranges(self) -> None:
        csv_content = """facility_type,service_type,patient_type,mdm_level,Time Min, Time Max,Code
F,S,P,N/A,10,20,7001
"""
        with TemporaryDirectory() as temp_dir:
            csv_path = Path(temp_dir) / "legacy.csv"
            csv_path.write_text(csv_content, encoding="utf-8")
            mapper = EMCodeMapper(csv_path)
            params = {"facility_type": "F", "service_type": "S", "patient_type": "P"}
            self.assertEqual(mapper.find_codes(physician_time=15, staff_time=99, **params), ["7001"])
            self.assertEqual(mapper.find_codes(physician_time=99, staff_time=15, **params), [])


if __name__ == "__main__":
    unittest.main()
