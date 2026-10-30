import pytest

from src.prompt_loader import fetch_prompt


def test_fetch_agent1_prompt():
    text = fetch_prompt("Agent 1 - ICD-10-PCS Code Suggestion Prompt.txt")
    assert len(text) > 100
    assert "PCS" in text


def test_fetch_agent2_prompt():
    text = fetch_prompt("Agent 2 - ICD-10-PCS Dynamic Code Detection Prompt.txt")
    assert "[##Current value" in text
    assert "[##Next Digit" in text


def test_missing_prompt_raises(tmp_path, monkeypatch):
    import src.prompt_loader as pl
    monkeypatch.setattr(pl, "PROMPT_DIR", tmp_path)
    with pytest.raises(FileNotFoundError):
        fetch_prompt("nonexistent.txt")
