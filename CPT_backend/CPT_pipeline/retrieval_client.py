from __future__ import annotations

from typing import Any
from typing import Optional

import httpx


class RetrievalClientError(RuntimeError):
    """Raised when retrieval service call fails."""


class RetrievalClient:
    def __init__(
        self,
        retrieval_url: str,
        connect_timeout_seconds: float,
        read_timeout_seconds: Optional[float],
        write_timeout_seconds: float,
        pool_timeout_seconds: float,
    ):
        self._retrieval_url = retrieval_url
        self._timeout = httpx.Timeout(
            connect=connect_timeout_seconds,
            read=read_timeout_seconds,
            write=write_timeout_seconds,
            pool=pool_timeout_seconds,
        )

    async def retrieve(self, text: str, k: int) -> dict[str, Any]:
        payload = {"text": text, "k": k}
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                response = await client.post(self._retrieval_url, json=payload)
            response.raise_for_status()
            return response.json()
        except Exception as exc:
            raise RetrievalClientError(f"Retrieval request failed: {exc}") from exc

