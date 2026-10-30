import sqlite3
import tempfile
import unittest
from pathlib import Path

from em_code_mapper_db import DBMappingConfig, EMCodeMapperDB


class TestEMCodeMapperDB(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        temp_dir = tempfile.TemporaryDirectory()
        cls._temp_dir = temp_dir
        cls.db_path = Path(temp_dir.name) / "em_mapping.db"
        cls._build_test_db(cls.db_path)

    @classmethod
    def tearDownClass(cls) -> None:
        cls._temp_dir.cleanup()

    @staticmethod
    def _build_test_db(db_path: Path) -> None:
        conn = sqlite3.connect(db_path)
        try:
            conn.execute(
                """
                CREATE TABLE em_mapping (
                    facility_type TEXT,
                    service_type TEXT,
                    patient_type TEXT,
                    mdm_level TEXT,
                    Min TEXT,
                    Max TEXT,
                    Code TEXT,
                    "Is Valid Mapping?" TEXT
                )
                """
            )
            rows = [
                (
                    "Telemedicine Services",
                    "Online Digital E/M (Asynchronous)",
                    "Established Patient",
                    "N/A - Time only",
                    "5",
                    "10",
                    "99421",
                    "yes",
                ),
                (
                    "Telemedicine Services",
                    "Online Digital E/M (Asynchronous)",
                    "Established Patient",
                    "N/A - Time only",
                    "11",
                    "20",
                    "99422",
                    "yes",
                ),
                (
                    "Telemedicine Services",
                    "Brief Synchronous Communication (Virtual Check-In)",
                    "Established Patient",
                    "N/A — Time only",
                    "5",
                    "10",
                    "98016",
                    "yes",
                ),
                (
                    "Telemedicine Services",
                    "Brief Synchronous Communication (Virtual Check-In)",
                    "Established Patient",
                    "N/A — Time only",
                    "1",
                    "2",
                    "INVALID-CODE",
                    "no",
                ),
                (
                    "Telemedicine Services",
                    "Synchronous Audio-Video",
                    "Established Patient",
                    "High",
                    "60",
                    "99",
                    "98004",
                    "yes",
                ),
                (
                    "Telemedicine Services",
                    "Synchronous Audio-Video",
                    "Established Patient",
                    "Low",
                    "10",
                    "19",
                    "98007",
                    "yes",
                ),
            ]
            conn.executemany(
                """
                INSERT INTO em_mapping (
                    facility_type, service_type, patient_type, mdm_level,
                    Min, Max, Code, "Is Valid Mapping?"
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                rows,
            )
            conn.commit()
        finally:
            conn.close()

    def test_facility_only_returns_all_codes(self) -> None:
        mapper = EMCodeMapperDB(self.db_path, table_name="em_mapping")
        codes = mapper.find_codes(facility_type="Telemedicine Services")
        self.assertEqual(codes, ["99421", "99422", "98016", "98004", "98007"])

    def test_time_only_variant_normalization_works(self) -> None:
        mapper = EMCodeMapperDB(self.db_path, table_name="em_mapping")
        codes = mapper.find_codes(
            facility_type="Telemedicine Services",
            service_type="Brief Synchronous Communication (Virtual Check-In)",
            mdm_level="N/A - Time only",
            time_value=8,
        )
        self.assertEqual(codes, ["98016"])

    def test_when_mdm_and_time_are_both_given_either_can_match(self) -> None:
        mapper = EMCodeMapperDB(self.db_path, table_name="em_mapping")
        codes_from_time_match = mapper.find_codes(
            facility_type="Telemedicine Services",
            service_type="Brief Synchronous Communication (Virtual Check-In)",
            mdm_level="Low",
            time_value=8,
        )
        self.assertEqual(codes_from_time_match, ["98016"])

        codes_from_mdm_match = mapper.find_codes(
            facility_type="Telemedicine Services",
            service_type="Brief Synchronous Communication (Virtual Check-In)",
            mdm_level="N/A - Time only",
            time_value=100,
        )
        self.assertEqual(codes_from_mdm_match, ["98016"])

    def test_when_both_mdm_and_time_are_given_returns_highest_code_only(self) -> None:
        mapper = EMCodeMapperDB(self.db_path, table_name="em_mapping")
        codes = mapper.find_codes(
            facility_type="Telemedicine Services",
            service_type="Synchronous Audio-Video",
            patient_type="Established Patient",
            mdm_level="High",
            time_value=10,
        )
        self.assertEqual(codes, ["98007"])

    def test_invalid_numeric_input_raises(self) -> None:
        mapper = EMCodeMapperDB(self.db_path, table_name="em_mapping")
        with self.assertRaises(ValueError):
            mapper.find_codes(time_value="bad")

    def test_min_max_input_arguments_are_not_supported(self) -> None:
        mapper = EMCodeMapperDB(self.db_path, table_name="em_mapping")
        with self.assertRaises(TypeError):
            mapper.find_codes(Max=20)

    def test_supports_custom_column_names(self) -> None:
        mapper = EMCodeMapperDB(
            self.db_path,
            table_name="em_mapping",
            config=DBMappingConfig(code_col="Code"),
        )
        codes = mapper.find_codes(service_type="Online Digital E/M (Asynchronous)")
        self.assertEqual(codes, ["99421", "99422"])


if __name__ == "__main__":
    unittest.main()
