import asyncio
import logging
from abc import ABC, abstractmethod

import config

logger = logging.getLogger(__name__)

# Network-level exception names that warrant a retry regardless of HTTP status.
_RETRYABLE_NETWORK_ERRORS = (
    "ReadError", "ConnectError", "RemoteProtocolError",
    "TimeoutException", "PoolTimeout", "ReadTimeout", "ConnectTimeout",
)


def _is_retryable(exc: Exception) -> bool:
    status = getattr(getattr(exc, "response", None), "status_code", None)
    if status in (429, 503):
        return True
    exc_name = type(exc).__name__
    return exc_name in _RETRYABLE_NETWORK_ERRORS


class LLMProvider(ABC):
    @abstractmethod
    async def _call_once(self, system_prompt: str, user_content: str) -> str: ...

    async def call_async(self, system_prompt: str, user_content: str) -> str:
        last_exc: Exception | None = None
        for attempt in range(config.RETRY_ATTEMPTS):
            try:
                return await self._call_once(system_prompt, user_content)
            except Exception as exc:
                if _is_retryable(exc):
                    wait = 2 ** attempt
                    logger.warning(
                        "%s (attempt %d/%d), retrying in %ds — %s",
                        type(exc).__name__, attempt + 1, config.RETRY_ATTEMPTS, wait, exc,
                    )
                    await asyncio.sleep(wait)
                    last_exc = exc
                else:
                    raise
        raise last_exc  # type: ignore[misc]


def get_provider() -> "LLMProvider":
    provider = config.LLM_PROVIDER
    if provider == "gemini_vertex":
        from src.llm.gemini_vertex import GeminiVertexProvider
        return GeminiVertexProvider()
    if provider == "azure_openai":
        from src.llm.azure_openai import AzureOpenAIProvider
        return AzureOpenAIProvider()
    if provider == "claude_vertex":
        from src.llm.claude_vertex import ClaudeVertexProvider
        return ClaudeVertexProvider()
    if provider == "openai":
        from src.llm.openai_provider import OpenAIProvider
        return OpenAIProvider()
    raise ValueError(f"Unknown LLM_PROVIDER: {provider!r}")
