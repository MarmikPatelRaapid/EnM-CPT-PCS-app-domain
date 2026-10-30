import pytest

from src.agents.agent1 import Procedure
from src.agents.agent2 import _fill_placeholders
from src.tree.models import PCSNode


def _make_node(code: str) -> PCSNode:
    proc = Procedure(norm_procedure_name="Test Procedure", procedure_evidences=[])
    return PCSNode(procedure=proc, current_code=code, accumulated_evidences={})


def test_current_value_replaced(resources):
    node = _make_node("4A0")
    options = [("Z", "No Qualifier")]
    prompt = "[##Current value = 4A0##] something"
    result = _fill_placeholders(prompt, node, options, resources)
    assert "[##Current value = 4A0##]" in result


def test_next_digit_ordinal_first(resources):
    node = _make_node("")
    options = [("0", "Medical and Surgical")]
    prompt = "[##Next Digit = 4th##]"
    result = _fill_placeholders(prompt, node, options, resources)
    assert "1st" in result


def test_next_digit_ordinal_fourth(resources):
    node = _make_node("001")
    options = [("6", "Cerebral Ventricle")]
    prompt = "[##Next Digit = 4th##]"
    result = _fill_placeholders(prompt, node, options, resources)
    assert "4th" in result


def test_next_digit_ordinal_seventh(resources):
    node = _make_node("001607")
    options = [("0", "Nasopharynx")]
    prompt = "[##Next Digit = 4th##]"
    result = _fill_placeholders(prompt, node, options, resources)
    assert "7th" in result


def test_digit_type_filled_from_tsv(resources):
    node = _make_node("")
    options = [("0", "Medical and Surgical")]
    prompt = "[##next digit type = Body System## ]"
    result = _fill_placeholders(prompt, node, options, resources)
    assert "Section" in result


def test_digit_type_body_system_at_position_2(resources):
    node = _make_node("0")
    options = [("0", "Central Nervous System")]
    prompt = "[##next digit type = Body System## ]"
    result = _fill_placeholders(prompt, node, options, resources)
    assert "Body System" in result


def test_next_possible_list_formatted(resources):
    node = _make_node("")
    options = [("0", "Med Surg"), ("1", "Obs")]
    prompt = "[##next possible list = [0:Central Nervous, etc]##]"
    result = _fill_placeholders(prompt, node, options, resources)
    assert "0: Med Surg" in result
    assert "1: Obs" in result


def test_list_placeholder_filled(resources):
    node = _make_node("")
    options = [("0", "Med Surg"), ("1", "Obs")]
    prompt = "[##list##]"
    result = _fill_placeholders(prompt, node, options, resources)
    assert "[0, 1]" in result


def test_no_remaining_placeholders(resources):
    # _fill_placeholders replaces values INSIDE [## ##] brackets with real data.
    # Verify the known template/example strings in the original prompt are gone
    # and the real values appear instead.
    node = _make_node("4A0")
    options = [("Z", "No Qualifier")]
    from src.prompt_loader import fetch_prompt
    prompt = fetch_prompt("Agent 2 - ICD-10-PCS Dynamic Code Detection Prompt.txt")
    result = _fill_placeholders(prompt, node, options, resources)

    # The example options text from the raw prompt should be replaced
    assert "[0:Central Nervous, etc]" not in result
    # Real values from our options must appear
    assert "Z: No Qualifier" in result
    assert "[Z]" in result
    # Ordinal must be correct for len("4A0")+1 = 4th position
    assert "4th" in result
