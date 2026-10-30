import anthropic

import config
from src.llm.base import LLMProvider


class ClaudeVertexProvider(LLMProvider):
    def __init__(self):
        self.client = anthropic.AsyncAnthropicVertex(
            project_id=config.PROJECT_ID,
            region=config.LOCATION,
        )

    async def _call_once(self, system_prompt: str, user_content: str) -> str:
        response = await self.client.messages.create(
            model=config.MODEL_NAME,
            max_tokens=8192,
            temperature=config.TEMPERATURE,
            system=system_prompt,
            messages=[{"role": "user", "content": user_content}],
        )
        return response.content[0].text
