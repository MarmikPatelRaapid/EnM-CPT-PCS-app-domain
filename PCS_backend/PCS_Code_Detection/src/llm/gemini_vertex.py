from google import genai
from google.genai import types

import config
from src.llm.base import LLMProvider


class GeminiVertexProvider(LLMProvider):
    def __init__(self):
        self.client = genai.Client(
            vertexai=True,
            project=config.PROJECT_ID,
            location=config.LOCATION,
        )

    async def _call_once(self, system_prompt: str, user_content: str) -> str:
        config_kwargs = {
            "temperature": config.TEMPERATURE,
            "top_p": config.TOP_P,
            "max_output_tokens": 65536,
            "response_mime_type": "application/json",
            "system_instruction": [types.Part.from_text(text=system_prompt)],
        }
        thinking_budget = getattr(config, "THINKING_BUDGET", None)
        if thinking_budget is not None:
            config_kwargs["thinking_config"] = types.ThinkingConfig(thinking_budget=thinking_budget)
        gen_config = types.GenerateContentConfig(**config_kwargs)
        response = await self.client.aio.models.generate_content(
            model=config.MODEL_NAME,
            contents=[types.Content(
                role="user",
                parts=[types.Part.from_text(text=user_content)],
            )],
            config=gen_config,
        )
        return response.text
