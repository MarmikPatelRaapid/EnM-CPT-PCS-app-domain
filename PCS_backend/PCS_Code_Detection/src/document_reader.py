import json
from pathlib import Path


def read_document_dir(directory: str) -> dict[int, str]:
    """Read a directory of <page_no>.txt or <page_no>.json files and return {page_no: content}."""
    pages: dict[int, str] = {}
    for file in Path(directory).iterdir():
        if file.stem.isdigit():
            page_no = int(file.stem)
            if file.suffix == ".txt":
                pages[page_no] = file.read_text(encoding="utf-8")
            elif file.suffix == ".json":
                data = json.loads(file.read_text(encoding="utf-8"))
                pages[page_no] = data["text"]
    return pages
