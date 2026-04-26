from typing import Protocol

import anthropic
import openai

from app.config import get_anthropic_api_key, get_model_preference, get_openai_api_key

CLAUDE_MODEL = "claude-sonnet-4-6"
OPENAI_MODEL = "gpt-4o-mini"


class LLMClient(Protocol):
    @property
    def model_name(self) -> str: ...

    def complete(self, system: str, user: str, max_tokens: int) -> str: ...


class ClaudeClient:
    def __init__(self) -> None:
        self._client = anthropic.Anthropic(api_key=get_anthropic_api_key())

    @property
    def model_name(self) -> str:
        return CLAUDE_MODEL

    def complete(self, system: str, user: str, max_tokens: int) -> str:
        message = self._client.messages.create(
            model=CLAUDE_MODEL,
            max_tokens=max_tokens,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
        return message.content[0].text


class OpenAIClient:
    def __init__(self) -> None:
        self._client = openai.OpenAI(api_key=get_openai_api_key())

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


def get_llm_client() -> LLMClient:
    pref = get_model_preference()
    if pref == "claude" and get_anthropic_api_key():
        return ClaudeClient()
    if get_openai_api_key():
        return OpenAIClient()
    if get_anthropic_api_key():
        return ClaudeClient()
    raise RuntimeError(
        "No LLM API key configured. Set ANTHROPIC_API_KEY or OPENAI_API_KEY."
    )
