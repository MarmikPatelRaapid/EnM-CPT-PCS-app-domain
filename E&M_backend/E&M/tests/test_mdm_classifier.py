import unittest

from mdm_classifier import COMPLEXITY_RULES_TSV, classify_mdm_from_json


def _problem(
    *,
    disease_evidence=None,
    data_to_review=None,
    risk_type=None,
    risk_evidences=None,
):
    entry = {}
    if disease_evidence is not None:
        entry["disease_evidence"] = disease_evidence
    if data_to_review is not None:
        entry["data_to_review"] = data_to_review
    if risk_type is not None or risk_evidences is not None:
        risk = {}
        if risk_type is not None:
            risk["type"] = risk_type
        if risk_evidences is not None:
            risk["risk_evidences"] = risk_evidences
        entry["risk_of_morbidity"] = risk
    return entry


def _payload(**sections):
    base = {
        "self_limited_minor_problem": [],
        "chronic_illness": {},
        "acute_illness": {},
        "undiagnosed_problem": [],
    }
    base.update(sections)
    return base


class TestMDMClassifierComplexity(unittest.TestCase):
    def test_complexity_tsv_headers_are_db_friendly(self) -> None:
        header_line = COMPLEXITY_RULES_TSV.read_text(encoding="utf-8-sig").splitlines()[0]
        self.assertEqual(
            header_line.split("\t"),
            [
                "actual_name",
                "norm_disease_count",
                "json_class",
                "json_sub_class",
                "json_sub_sub_class",
            ],
        )

    def test_high_complexity_beats_lower_categories(self) -> None:
        payload = _payload(
            chronic_illness={
                "stable": [_problem(disease_evidence=["e1"]), _problem(disease_evidence=["e2"])],
                "life_threatening": [_problem(disease_evidence=["critical"])],
            }
        )
        result = classify_mdm_from_json(payload)
        self.assertEqual(result["complexity"], "high")

    def test_two_stable_chronic_classifies_moderate(self) -> None:
        payload = _payload(
            chronic_illness={"stable": [_problem(disease_evidence=["e1"]), _problem(disease_evidence=["e2"])]}
        )
        result = classify_mdm_from_json(payload)
        self.assertEqual(result["complexity"], "moderate")

    def test_chronic_exacerbation_classifies_moderate(self) -> None:
        payload = _payload(chronic_illness={"exacerbation": [_problem(disease_evidence=["e1"])]})
        result = classify_mdm_from_json(payload)
        self.assertEqual(result["complexity"], "moderate")

    def test_one_stable_chronic_classifies_low(self) -> None:
        payload = _payload(chronic_illness={"stable": [_problem(disease_evidence=["e1"])]})
        result = classify_mdm_from_json(payload)
        self.assertEqual(result["complexity"], "low")

    def test_one_self_limited_classifies_straightforward(self) -> None:
        payload = _payload(self_limited_minor_problem=[_problem(disease_evidence=["e1"])])
        result = classify_mdm_from_json(payload)
        self.assertEqual(result["complexity"], "Straightforward")

    def test_two_self_limited_classifies_low(self) -> None:
        payload = _payload(
            self_limited_minor_problem=[_problem(disease_evidence=["e1"]), _problem(disease_evidence=["e2"])]
        )
        result = classify_mdm_from_json(payload)
        self.assertEqual(result["complexity"], "low")

    def test_no_complexity_evidence_returns_blank_complexity(self) -> None:
        payload = _payload(chronic_illness={"stable": [_problem(disease_evidence=[])]})
        result = classify_mdm_from_json(payload)
        self.assertEqual(result["complexity"], "")
        self.assertEqual(result["details"]["complexity"]["status"], "missing")
        self.assertIn("Complexity data not found", result["details"]["complexity"]["reason"])


class TestMDMClassifierDataToReview(unittest.TestCase):
    def test_no_data_evidence_defaults_minimal_with_minimal_explanation(self) -> None:
        payload = _payload(self_limited_minor_problem=[_problem(disease_evidence=["e1"])])
        result = classify_mdm_from_json(payload)
        self.assertEqual(result["data_to_review"], "minimal")
        self.assertIn("Minimal Data To Review", result["details"]["data_to_review"]["reason"])

    def test_two_category_1_fields_classify_low(self) -> None:
        payload = _payload(
            self_limited_minor_problem=[
                _problem(
                    disease_evidence=["e1"],
                    data_to_review={
                        "review_of_prior_external_note": ["a"],
                        "review_of_test_result": ["b"],
                    },
                )
            ]
        )
        result = classify_mdm_from_json(payload)
        self.assertEqual(result["data_to_review"], "limited")

    def test_three_category_1_fields_classify_moderate(self) -> None:
        payload = _payload(
            self_limited_minor_problem=[
                _problem(
                    disease_evidence=["e1"],
                    data_to_review={
                        "review_of_prior_external_note": ["a"],
                        "review_of_test_result": ["b"],
                        "order_of_test": ["c"],
                    },
                )
            ]
        )
        result = classify_mdm_from_json(payload)
        self.assertEqual(result["data_to_review"], "moderate")

    def test_discussion_of_management_classifies_moderate(self) -> None:
        payload = _payload(
            self_limited_minor_problem=[
                _problem(
                    disease_evidence=["e1"],
                    data_to_review={
                        "order_of_test": ["a"],
                        "discussion_of_management_or_test_interpretation": ["b"],
                    },
                )
            ]
        )
        result = classify_mdm_from_json(payload)
        self.assertEqual(result["data_to_review"], "moderate")

    def test_independent_historian_counts_toward_category_1_threshold(self) -> None:
        payload = _payload(
            self_limited_minor_problem=[
                _problem(
                    disease_evidence=["e1"],
                    data_to_review={
                        "review_of_prior_external_note": ["a"],
                        "review_of_test_result": ["b"],
                        "assessment_requiring_independent_historian": ["c"],
                    },
                )
            ]
        )
        result = classify_mdm_from_json(payload)
        self.assertEqual(result["data_to_review"], "moderate")

    def test_category_1_threshold_plus_independent_interpretation_is_high(self) -> None:
        payload = _payload(
            self_limited_minor_problem=[
                _problem(
                    disease_evidence=["e1"],
                    data_to_review={
                        "review_of_prior_external_note": ["a"],
                        "review_of_test_result": ["b"],
                        "order_of_test": ["c"],
                        "independent_interpretation_of_test": ["d"],
                    },
                )
            ]
        )
        result = classify_mdm_from_json(payload)
        self.assertEqual(result["data_to_review"], "extensive")

    def test_data_evidence_aggregates_across_different_problems(self) -> None:
        payload = _payload(
            self_limited_minor_problem=[
                _problem(
                    disease_evidence=["e1"],
                    data_to_review={"review_of_prior_external_note": ["a"]},
                )
            ],
            chronic_illness={
                "stable": [
                    _problem(
                        disease_evidence=["e2"],
                        data_to_review={"review_of_test_result": ["b"]},
                    )
                ]
            },
        )
        result = classify_mdm_from_json(payload)
        self.assertEqual(result["data_to_review"], "limited")

    def test_data_evidence_below_threshold_stays_minimal(self) -> None:
        payload = _payload(
            self_limited_minor_problem=[
                _problem(
                    disease_evidence=["e1"],
                    data_to_review={"review_of_prior_external_note": ["a"]},
                )
            ]
        )
        result = classify_mdm_from_json(payload)
        self.assertEqual(result["data_to_review"], "minimal")


class TestMDMClassifierRisk(unittest.TestCase):
    def test_no_risk_evidence_defaults_minimal_with_minimal_explanation(self) -> None:
        payload = _payload(self_limited_minor_problem=[_problem(disease_evidence=["e1"])])
        result = classify_mdm_from_json(payload)
        self.assertEqual(result["risk"], "minimal")
        self.assertIn("Minimal Risk", result["details"]["risk"]["reason"])

    def test_highest_risk_type_wins(self) -> None:
        payload = _payload(
            self_limited_minor_problem=[_problem(disease_evidence=["e1"], risk_type="low")],
            chronic_illness={"stable": [_problem(disease_evidence=["e2"], risk_type="high")]},
        )
        result = classify_mdm_from_json(payload)
        self.assertEqual(result["risk"], "high")

    def test_minimal_risk_category_is_minimal(self) -> None:
        payload = _payload(self_limited_minor_problem=[_problem(disease_evidence=["e1"], risk_type="minimal")])
        result = classify_mdm_from_json(payload)
        self.assertEqual(result["risk"], "minimal")

    def test_risk_type_normalization_handles_whitespace_and_case(self) -> None:
        payload = _payload(
            self_limited_minor_problem=[_problem(disease_evidence=["e1"], risk_type="  MoDerAte  ")]
        )
        result = classify_mdm_from_json(payload)
        self.assertEqual(result["risk"], "moderate")


class TestMDMClassifierFinalLevel(unittest.TestCase):
    def test_low_moderate_high_gives_moderate(self) -> None:
        payload = _payload(
            chronic_illness={"stable": [_problem(disease_evidence=["e1"])]},
            self_limited_minor_problem=[
                _problem(
                    disease_evidence=["e2"],
                    data_to_review={
                        "review_of_prior_external_note": ["a"],
                        "review_of_test_result": ["b"],
                        "order_of_test": ["c"],
                    },
                    risk_type="high",
                )
            ],
        )
        result = classify_mdm_from_json(payload)
        self.assertEqual(result["complexity"], "low")
        self.assertEqual(result["data_to_review"], "moderate")
        self.assertEqual(result["risk"], "high")
        self.assertEqual(result["mdm_level"], "moderate")

    def test_low_low_high_gives_low(self) -> None:
        payload = _payload(
            chronic_illness={"stable": [_problem(disease_evidence=["e1"])]},
            self_limited_minor_problem=[
                _problem(
                    disease_evidence=["e2"],
                    data_to_review={
                        "review_of_prior_external_note": ["a"],
                        "review_of_test_result": ["b"],
                    },
                    risk_type="high",
                )
            ],
        )
        result = classify_mdm_from_json(payload)
        self.assertEqual(result["mdm_level"], "low")

    def test_low_minimal_minimal_gives_straightforward(self) -> None:
        payload = _payload(chronic_illness={"stable": [_problem(disease_evidence=["e1"])]})
        result = classify_mdm_from_json(payload)
        self.assertEqual(result["complexity"], "low")
        self.assertEqual(result["data_to_review"], "minimal")
        self.assertEqual(result["risk"], "minimal")
        self.assertEqual(result["mdm_level"], "straightforward")

    def test_straightforward_limited_high_gives_low(self) -> None:
        payload = _payload(
            self_limited_minor_problem=[
                _problem(
                    disease_evidence=["e1"],
                    data_to_review={
                        "review_of_prior_external_note": ["a"],
                        "review_of_test_result": ["b"],
                    },
                    risk_type="high",
                )
            ]
        )
        result = classify_mdm_from_json(payload)
        self.assertEqual(result["complexity"], "Straightforward")
        self.assertEqual(result["data_to_review"], "limited")
        self.assertEqual(result["risk"], "high")
        self.assertEqual(result["mdm_level"], "low")


if __name__ == "__main__":
    unittest.main()
