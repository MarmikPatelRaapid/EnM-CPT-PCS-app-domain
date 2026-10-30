import os

from openai import AsyncOpenAI

import config
from src.llm.base import LLMProvider


class OpenAIProvider(LLMProvider):
    def __init__(self):
        self.client = AsyncOpenAI(api_key=os.environ["OPENAI_API_KEY"])

    async def _call_once(self, system_prompt: str, user_content: str) -> str:
        response = await self.client.chat.completions.create(
            model=config.MODEL_NAME,
            temperature=config.TEMPERATURE,
            top_p=config.TOP_P,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content},
            ],
        )
        return response.choices[0].message.content
