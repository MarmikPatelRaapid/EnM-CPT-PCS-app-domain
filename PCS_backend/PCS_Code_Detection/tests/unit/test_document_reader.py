import pytest

from src.document_reader import read_txt


def test_multi_page_parsing(tmp_path):
    doc = tmp_path / "doc.txt"
    doc.write_text(
        "--- Page 1 ---\nFirst page content.\n--- Page 2 ---\nSecond page content."
    )
    pages = read_txt(str(doc))
    assert pages == {1: "First page content.", 2: "Second page content."}


def test_no_markers_is_page_1(tmp_path):
    doc = tmp_path / "doc.txt"
    doc.write_text("Some text without markers.")
    pages = read_txt(str(doc))
    assert pages == {1: "Some text without markers."}


def test_whitespace_stripped(tmp_path):
    doc = tmp_path / "doc.txt"
    doc.write_text("--- Page 1 ---\n\n  content  \n\n--- Page 2 ---\n\ncontent2\n")
    pages = read_txt(str(doc))
    assert pages[1] == "content"
    assert pages[2] == "content2"


def test_page_numbers_as_keys(tmp_path):
    doc = tmp_path / "doc.txt"
    doc.write_text("--- Page 3 ---\nThird.\n--- Page 7 ---\nSeventh.")
    pages = read_txt(str(doc))
    assert 3 in pages
    assert 7 in pages
