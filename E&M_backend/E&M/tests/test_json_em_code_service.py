import unittest
from pathlib import Path
from tempfile import NamedTemporaryFile

from fastapi.testclient import TestClient

from json_em_code_service import app, extract_lookup_inputs_from_payload


class TestJsonEMCodeService(unittest.TestCase):
    def setUp(self) -> None:
        self.client = TestClient(app)

    def test_special_service_uses_staff_time_value(self) -> None:
        payload = {
            "facility": {"facility_type": "Facility A"},
            "service": {
                "service_type": "Prolonged Clinical Staff Service (Office/Outpatient, with MD supervision)"
            },
            "patient": {"patient_type": "New or Established Patient"},
            "physician_time_spent_with_patient": {"time_in_mins": 10},
            "staff_time_spent_with_patient": {"time_in_mins": 65},
        }
        result = extract_lookup_inputs_from_payload(payload)
        self.assertEqual(result["time_value"], 65)

    def test_non_special_service_uses_physician_time_value(self) -> None:
        payload = {
            "facility": {"facility_type": "Facility A"},
            "service": {"service_type": "Transitional Care Management - High MDM"},
            "patient": {"patient_type": "New or Established Patient"},
            "physician_time_spent_with_patient": {"time_in_mins": 35},
            "staff_time_spent_with_patient": {"time_in_mins": 70},
            "patient_age": {"age": 6, "age_unit": "months"},
        }
        result = extract_lookup_inputs_from_payload(payload)
        self.assertEqual(result["time_value"], 35)
        self.assertEqual(result["patient_age"], 6)
        self.assertEqual(result["patient_age_unit"], "months")

    def test_empty_time_objects_return_none_time_value(self) -> None:
        payload = {
            "facility": {"facility_type": "Facility A"},
            "service": {"service_type": "Transitional Care Management - High MDM"},
            "patient": {"patient_type": "New or Established Patient"},
            "physician_time_spent_with_patient": {},
            "staff_time_spent_with_patient": {},
        }
        result = extract_lookup_inputs_from_payload(payload)
        self.assertIsNone(result["time_value"])

    def test_special_service_with_empty_staff_time_returns_none(self) -> None:
        payload = {
            "facility": {"facility_type": "Facility A"},
            "service": {
                "service_type": "Prolonged Clinical Staff Service (Office/Outpatient, with MD supervision)"
            },
            "patient": {"patient_type": "New or Established Patient"},
            "physician_time_spent_with_patient": {},
            "staff_time_spent_with_patient": {},
        }
        result = extract_lookup_inputs_from_payload(payload)
        self.assertIsNone(result["time_value"])

    def test_resolve_post_succeeds_when_both_time_objects_are_empty(self) -> None:
        payload = {
            "facility": {"facility_type": "Telemedicine Services"},
            "service": {"service_type": "Synchronous Audio-Video"},
            "patient": {"patient_type": "Established Patient"},
            "physician_time_spent_with_patient": {},
            "staff_time_spent_with_patient": {},
            "self_limited_minor_problem": [],
            "chronic_illness": {"life_threatening": [{"disease_evidence": ["critical"]}]},
            "acute_illness": {},
            "undiagnosed_problem": [],
        }
        with NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as handle:
            handle.write(__import__("json").dumps(payload))
            json_path = Path(handle.name)
        try:
            response = self.client.post("/resolve", json={"json_path": str(json_path)})
            self.assertEqual(response.status_code, 200)
            body = response.json()
            self.assertIn("codes", body)
            self.assertIn("classification", body)
            self.assertIn("mapper_filters", body)
            self.assertIsNone(body["mapper_filters"]["time_value"])
            self.assertNotIn("lookup_inputs", body)
            self.assertNotIn("count", body)
        finally:
            json_path.unlink(missing_ok=True)

    def test_resolve_endpoint_returns_payload_result(self) -> None:
        payload = {
            "facility": {"facility_type": "Telemedicine Services"},
            "service": {"service_type": "Online Digital E/M (Asynchronous)"},
            "patient": {"patient_type": "Established Patient"},
            "physician_time_spent_with_patient": {"time_in_mins": 10},
            "staff_time_spent_with_patient": {"time_in_mins": 60},
            "self_limited_minor_problem": [
                {
                    "disease_evidence": ["e1"],
                    "data_to_review": {
                        "review_of_prior_external_note": ["a"],
                        "review_of_test_result": ["b"],
                    },
                    "risk_of_morbidity": {"type": "low"},
                }
            ],
            "chronic_illness": {},
            "acute_illness": {},
            "undiagnosed_problem": [],
        }
        with NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as handle:
            handle.write(__import__("json").dumps(payload))
            json_path = Path(handle.name)
        try:
            response = self.client.get("/resolve", params={"json_path": str(json_path)})
            self.assertEqual(response.status_code, 200)
            body = response.json()
            self.assertIn("codes", body)
            self.assertIn("classification", body)
            self.assertIn("evidences", body)
            self.assertIn("mapper_filters", body)
            self.assertNotIn("lookup_inputs", body)
            self.assertNotIn("count", body)
        finally:
            json_path.unlink(missing_ok=True)

    def test_resolve_endpoint_missing_file_returns_404(self) -> None:
        response = self.client.get("/resolve", params={"json_path": "/tmp/does-not-exist-surely.json"})
        self.assertEqual(response.status_code, 404)

    def test_resolve_post_with_json_path_in_body(self) -> None:
        payload = {
            "facility": {"facility_type": "Telemedicine Services"},
            "service": {"service_type": "Online Digital E/M (Asynchronous)"},
            "patient": {"patient_type": "Established Patient"},
            "physician_time_spent_with_patient": {"time_in_mins": 10},
            "staff_time_spent_with_patient": {"time_in_mins": 60},
            "self_limited_minor_problem": [
                {
                    "disease_evidence": ["e1"],
                    "data_to_review": {
                        "review_of_prior_external_note": ["a"],
                        "review_of_test_result": ["b"],
                    },
                    "risk_of_morbidity": {"type": "low"},
                }
            ],
            "chronic_illness": {},
            "acute_illness": {},
            "undiagnosed_problem": [],
        }
        with NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as handle:
            handle.write(__import__("json").dumps(payload))
            json_path = Path(handle.name)
        try:
            response = self.client.post("/resolve", json={"json_path": str(json_path)})
            self.assertEqual(response.status_code, 200)
            body = response.json()
            self.assertIn("codes", body)
            self.assertIn("classification", body)
            self.assertIn("mapper_filters", body)
            self.assertNotIn("lookup_inputs", body)
            self.assertNotIn("count", body)
        finally:
            json_path.unlink(missing_ok=True)

    def test_resolve_endpoint_missing_complexity_returns_blank_complexity(self) -> None:
        payload = {
            "facility": {"facility_type": "Office or Other Outpatient Services"},
            "service": {"service_type": "Office or Other Outpatient Visit"},
            "patient": {"patient_type": "Established Patient"},
            "physician_time_spent_with_patient": {"time_in_mins": 25},
            "staff_time_spent_with_patient": {},
            "self_limited_minor_problem": [],
            "chronic_illness": {},
            "acute_illness": {},
            "undiagnosed_problem": [],
        }
        with NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as handle:
            handle.write(__import__("json").dumps(payload))
            json_path = Path(handle.name)
        try:
            response = self.client.get("/resolve", params={"json_path": str(json_path)})
            self.assertEqual(response.status_code, 200)
            body = response.json()
            self.assertEqual(body["classification"]["complexity"], "")
            self.assertIn("Complexity data not found", body["classification"]["details"]["complexity"]["reason"])
        finally:
            json_path.unlink(missing_ok=True)

    def test_resolve_endpoint_returns_deduplicated_evidences(self) -> None:
        payload = {
            "facility": {"facility_type": "Telemedicine Services", "evidences": ["f1", "f1", "f2"]},
            "service": {
                "service_type": "Online Digital E/M (Asynchronous)",
                "evidences": ["s1", "s1", "s2"],
            },
            "patient": {"patient_type": "Established Patient", "evidences": ["p1", "p1"]},
            "physician_time_spent_with_patient": {"time_in_mins": 25, "evidences": ["pt1", "pt1"]},
            "staff_time_spent_with_patient": {"time_in_mins": 50, "evidences": ["st1", "st1"]},
            "self_limited_minor_problem": [
                {
                    "disease_evidence": ["d1", "d1"],
                    "data_to_review": {
                        "review_of_prior_external_note": ["r1", "r1"],
                        "review_of_test_result": ["r2"],
                    },
                    "risk_of_morbidity": {"type": "low", "risk_evidences": ["k1", "k1"]},
                }
            ],
            "chronic_illness": {
                "stable": [
                    {
                        "disease_evidence": ["d2", "d1"],
                        "data_to_review": {"order_of_test": ["r3", "r2"]},
                        "risk_of_morbidity": {"type": "moderate", "risk_evidences": ["k2", "k1"]},
                    }
                ]
            },
            "acute_illness": {},
            "undiagnosed_problem": [],
        }
        with NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as handle:
            handle.write(__import__("json").dumps(payload))
            json_path = Path(handle.name)
        try:
            response = self.client.get("/resolve", params={"json_path": str(json_path)})
            self.assertEqual(response.status_code, 200)
            body = response.json()
            self.assertEqual(
                body["evidences"],
                {
                    "facility": ["f1", "f2"],
                    "service": ["s1", "s2"],
                    "patient": ["p1"],
                    "physician_time_spent_with_patient": ["pt1"],
                    "staff_time_spent_with_patient": ["st1"],
                    "complexity": ["d1", "d2"],
                    "data_to_review": ["r1", "r2", "r3"],
                    "risk_of_morbidity": ["k1", "k2"],
                },
            )
        finally:
            json_path.unlink(missing_ok=True)


if __name__ == "__main__":
    unittest.main()
