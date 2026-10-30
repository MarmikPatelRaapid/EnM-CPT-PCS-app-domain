import json
from unittest.mock import AsyncMock

import pytest

from src.agents.agent1 import Procedure
from src.pcs_resources import PCSResources
from src.tree.models import PCSNode


@pytest.fixture(scope="session")
def resources():
    return PCSResources()


@pytest.fixture
def sample_pages():
    return {
        1: "Patient underwent laparoscopic appendectomy.",
        2: "No complications noted.",
    }


@pytest.fixture
def sample_procedure():
    return Procedure(
        norm_procedure_name="Laparoscopic Appendectomy",
        procedure_evidences=[
            {
                "text": "laparoscopic appendectomy",
                "pg_no": 1,
                "reftxtbefore": "underwent ",
                "reftxtafter": ". No comp",
            }
        ],
    )


@pytest.fixture
def sample_node(sample_procedure):
    return PCSNode(procedure=sample_procedure, current_code="", accumulated_evidences={})


@pytest.fixture
def make_mock_llm():
    def _make(response_json: dict):
        mock = AsyncMock()
        mock.call_async.return_value = json.dumps(response_json)
        return mock

    return _make


@pytest.fixture
def agent1_response():
    return {
        "procedures": [
            {
                "norm_procedure_name": "Laparoscopic Appendectomy",
                "procedure_evidences": [
                    {
                        "text": "appendectomy",
                        "pg_no": 1,
                        "reftxtbefore": "underwent ",
                        "reftxtafter": " No comp",
                    }
                ],
            }
        ]
    }


@pytest.fixture
def agent2_single_char_response():
    return {
        "norm_procedure": "Laparoscopic Appendectomy",
        "current_code": "",
        "next_character_data": [
            {
                "next_character_value": "0",
                "next_character_desc": "Medical and Surgical",
                "next_character_evidences": [
                    {
                        "text": "appendectomy",
                        "pg_no": 1,
                        "reftxtbefore": "underwent ",
                        "reftxtafter": " No comp",
                    }
                ],
            }
        ],
    }


@pytest.fixture
def agent2_multi_char_response():
    return {
        "norm_procedure": "Procedure X",
        "current_code": "",
        "next_character_data": [
            {
                "next_character_value": "0",
                "next_character_desc": "Medical and Surgical",
                "next_character_evidences": [
                    {"text": "surgical", "pg_no": 1, "reftxtbefore": "xxx", "reftxtafter": "yyy"}
                ],
            },
            {
                "next_character_value": "B",
                "next_character_desc": "Imaging",
                "next_character_evidences": [
                    {"text": "imaging", "pg_no": 2, "reftxtbefore": "aaa", "reftxtafter": "bbb"}
                ],
            },
        ],
    }


@pytest.fixture
def agent2_not_found_response():
    return {
        "norm_procedure": "Unknown Procedure",
        "current_code": "001",
        "next_character_data": [],
    }
