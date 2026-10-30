from __future__ import annotations

import csv
import re
from pathlib import Path


class CodeDescriptionResolver:
    """Resolves E/M code descriptions from a TSV resource (Code<TAB>Description).

    Used to populate the ``EMcodedescription`` field of the synthetic-generation
    request when the caller does not supply one.
    """

    def __init__(self, tsv_path: str | Path, default_description: str = "") -> None:
        self._default_description = default_description
        self._descriptions = self._load(Path(tsv_path))

    @staticmethod
    def _load(tsv_path: Path) -> dict[str, str]:
        descriptions: dict[str, str] = {}
        if not tsv_path.exists():
            return descriptions

        with tsv_path.open("r", encoding="utf-8", newline="") as handle:
            reader = csv.reader(handle, delimiter="\t")
            for row in reader:
                if len(row) < 2:
                    continue
                code = row[0].strip()
                description = row[1].strip()
                if not code or code.lower() == "code":
                    continue
                descriptions[code.upper()] = description
        return descriptions

    def _lookup_single(self, code: str) -> str | None:
        return self._descriptions.get(code.strip().upper())

    def _expand_token(self, token: str) -> list[str]:
        """Expand a single token into one or more concrete codes.

        Supports plain codes and numeric ranges like ``99202-99205``.
        """
        token = token.strip()
        if not token:
            return []

        range_match = re.fullmatch(r"(\d{4,5})\s*-\s*(\d{4,5})", token)
        if range_match:
            start = int(range_match.group(1))
            end = int(range_match.group(2))
            if start <= end and (end - start) <= 1000:
                width = len(range_match.group(1))
                return [str(value).zfill(width) for value in range(start, end + 1)]
        return [token]

    def resolve(self, em_code: str) -> str:
        """Return a description string for one or more codes.

        ``em_code`` may be a single code, a comma-separated list, an
        ampersand-joined pair, or a numeric range. Codes missing from the
        resource are skipped; if nothing is found the configured default
        (possibly an empty string) is returned.
        """
        raw_tokens = re.split(r"[,&]", str(em_code or ""))
        found: list[tuple[str, str]] = []
        seen: set[str] = set()
        for raw_token in raw_tokens:
            for code in self._expand_token(raw_token):
                normalized = code.strip().upper()
                if not normalized or normalized in seen:
                    continue
                description = self._lookup_single(normalized)
                if description:
                    seen.add(normalized)
                    found.append((normalized, description))

        if not found:
            return self._default_description
        if len(found) == 1:
            return found[0][1]
        return "\n".join(f"{code}: {description}" for code, description in found)
