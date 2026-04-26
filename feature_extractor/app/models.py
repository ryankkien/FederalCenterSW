import json
import re
from typing import Any, Protocol

import openai

from app.config import get_openai_api_key, get_openai_llm_model

OPENAI_MODEL = get_openai_llm_model()


class LLMClient(Protocol):
    @property
    def model_name(self) -> str: ...

    def complete(self, system: str, user: str, max_tokens: int) -> str: ...

    def complete_json(self, system: str, user: str, max_tokens: int) -> Any: ...


def _parse_json_response(raw: str) -> Any:
    text = re.sub(r"^```[a-z]*\n?|```$", "", raw.strip(), flags=re.MULTILINE).strip()
    return json.loads(text)


class OpenAIClient:
    def __init__(self) -> None:
        api_key = get_openai_api_key()
        if not api_key:
            raise RuntimeError("OPENAI_API_KEY is required for feature extraction.")
        self._client = openai.OpenAI(api_key=api_key)

    @property
    def model_name(self) -> str:
        return OPENAI_MODEL

    def complete(self, system: str, user: str, max_tokens: int) -> str:
        response = self._client.chat.completions.create(
            model=OPENAI_MODEL,
            max_tokens=max_tokens,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        )
        return response.choices[0].message.content

    def complete_json(self, system: str, user: str, max_tokens: int) -> Any:
        response = self._client.chat.completions.create(
            model=OPENAI_MODEL,
            max_tokens=max_tokens,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        )
        raw = response.choices[0].message.content
        return _parse_json_response(raw)


def get_llm_client() -> LLMClient:
    return OpenAIClient()
