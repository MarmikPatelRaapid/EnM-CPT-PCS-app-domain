from openai import AsyncAzureOpenAI

import config
from src.llm.base import LLMProvider


class AzureOpenAIProvider(LLMProvider):
    def __init__(self):
        from azure.identity.aio import DefaultAzureCredential
        from azure.identity import get_bearer_token_provider

        credential = DefaultAzureCredential()
        token_provider = get_bearer_token_provider(
            credential, "https://cognitiveservices.azure.com/.default"
        )
        self.client = AsyncAzureOpenAI(
            azure_endpoint=config.AZURE_ENDPOINT,
            azure_ad_token_provider=token_provider,
            api_version=config.AZURE_API_VER,
        )

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
