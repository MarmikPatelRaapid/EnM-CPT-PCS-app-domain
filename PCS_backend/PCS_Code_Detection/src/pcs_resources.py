import csv
from pathlib import Path

RESOURCES_DIR = Path(__file__).parent.parent / "resources"


class PCSResources:
    def __init__(self):
        self._traversal: dict[str, list[tuple[str, str]]] = {}
        self._digit_headers: dict[str, list[str]] = {}
        self._load_traversal()
        self._load_digit_headers()

    def _load_traversal(self) -> None:
        path = RESOURCES_DIR / "pcs_traversal.tsv"
        with path.open(encoding="utf-8") as f:
            reader = csv.DictReader(f, delimiter="\t")
            for row in reader:
                key = row["current_string"]
                entry = (row["next_code"], row["next_label"])
                self._traversal.setdefault(key, []).append(entry)

    def _load_digit_headers(self) -> None:
        path = RESOURCES_DIR / "digit_wise_header.tsv"
        with path.open(encoding="utf-8") as f:
            reader = csv.DictReader(f, delimiter="\t")
            for row in reader:
                first_digit = row["first_digit"]
                self._digit_headers[first_digit] = [
                    row["first_digit_type"],
                    row["second_digit_type"],
                    row["third_digit_type"],
                    row["fourth_digit_type"],
                    row["fifth_digit_type"],
                    row["sixth_digit_type"],
                    row["seventh_digit_type"],
                ]

    def get_next_options(self, current_string: str) -> list[tuple[str, str]]:
        return self._traversal.get(current_string, [])

    def get_digit_type(self, first_digit: str, position: int) -> str:
        """Return the digit type label for `position` (1-based) given the section `first_digit`."""
        if position == 1:
            return "Section"
        headers = self._digit_headers[first_digit]
        return headers[position - 1]
