from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4
from typing import Any


@dataclass(frozen=True)
class RequestArtifactsContext:
    request_id: str
    request_dir: Path


class IntermediateStore:
    def __init__(self, enabled: bool, output_dir: str):
        self._enabled = enabled
        self._output_dir = Path(output_dir).resolve()
        if self._enabled:
            self._output_dir.mkdir(parents=True, exist_ok=True)

    def start_request(self, medical_document_text: str, top_k: int) -> RequestArtifactsContext | None:
        if not self._enabled:
            return None

        timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S_%fZ")
        request_id = f"{timestamp}_{uuid4().hex[:8]}"
        request_dir = self._output_dir / request_id
        request_dir.mkdir(parents=True, exist_ok=True)

        self.write_json(
            context=RequestArtifactsContext(request_id=request_id, request_dir=request_dir),
            file_name="00_request_input.json",
            payload={
                "request_id": request_id,
                "medical_document_text": medical_document_text,
                "top_k": top_k,
            },
        )
        return RequestArtifactsContext(request_id=request_id, request_dir=request_dir)

    def write_json(
        self,
        context: RequestArtifactsContext | None,
        file_name: str,
        payload: dict[str, Any],
    ) -> None:
        if not self._enabled or context is None:
            return
        output_path = context.request_dir / file_name
        output_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, default=str),
            encoding="utf-8",
        )

