import pytest

from src.pcs_resources import PCSResources


def test_root_returns_all_sections(resources):
    options = resources.get_next_options("")
    codes = [c for c, _ in options]
    assert "0" in codes
    assert len(options) >= 17


def test_known_string_returns_children(resources):
    options = resources.get_next_options("0")
    assert len(options) > 0


def test_unknown_string_returns_empty(resources):
    assert resources.get_next_options("ZZZZZZZ") == []


def test_digit_type_position_1_always_section(resources):
    assert resources.get_digit_type("0", 1) == "Section"


def test_digit_type_empty_first_digit_position_1(resources):
    assert resources.get_digit_type("", 1) == "Section"


def test_digit_type_position_2_body_system(resources):
    assert resources.get_digit_type("0", 2) == "Body System"


def test_digit_type_imaging_section_position_3(resources):
    assert resources.get_digit_type("B", 3) == "Type"


def test_digit_type_unknown_first_digit_raises(resources):
    with pytest.raises(KeyError):
        resources.get_digit_type("Z", 2)


def test_next_options_7char_code_is_empty(resources):
    # A completed 7-char code has no further children in the traversal TSV
    assert resources.get_next_options("0016070") == []
