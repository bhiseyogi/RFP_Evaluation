"""Thin LLM client layer. Every provider takes (system, user) and returns raw text."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from . import config
from .mock_provider import mock_response

PROVIDERS = {
    "anthropic": "Anthropic Claude",
    "openai": "OpenAI-compatible (OpenAI, Groq, Gemini, Ollama...)",
    "mock": "Offline mock (no API key, keyword heuristic)",
    "mock_faulty": "Offline mock - deliberately malformed output (validation demo)",
}


class LLMError(Exception):
    """Any provider/network/auth failure, with a user-presentable message."""


class LLMClient(Protocol):
    provider: str
    model: str

    def complete(self, system: str, user: str) -> str: ...


@dataclass
class AnthropicClient:
    api_key: str
    model: str = config.DEFAULT_ANTHROPIC_MODEL
    provider: str = "anthropic"
    max_tokens: int = 4000

    def complete(self, system: str, user: str) -> str:
        try:
            import anthropic
        except ImportError as exc:
            raise LLMError("The 'anthropic' package is not installed.") from exc
        client = anthropic.Anthropic(api_key=self.api_key, timeout=120)
        kwargs = dict(model=self.model, max_tokens=self.max_tokens, system=system,
                      messages=[{"role": "user", "content": user}])
        try:
            try:
                resp = client.messages.create(temperature=0, **kwargs)
            except anthropic.BadRequestError as exc:
                if "temperature" not in str(exc).lower():
                    raise
                resp = client.messages.create(**kwargs)  # some models do not accept temperature
        except anthropic.AuthenticationError as exc:
            raise LLMError("Anthropic rejected the API key.") from exc
        except anthropic.APIError as exc:
            raise LLMError(f"Anthropic API error: {exc}") from exc
        return "".join(b.text for b in resp.content if getattr(b, "type", "") == "text")


@dataclass
class OpenAICompatClient:
    api_key: str
    model: str = config.DEFAULT_OPENAI_MODEL
    base_url: str | None = None
    provider: str = "openai"

    def complete(self, system: str, user: str) -> str:
        try:
            import openai
        except ImportError as exc:
            raise LLMError("The 'openai' package is not installed.") from exc
        client = openai.OpenAI(api_key=self.api_key or "not-needed", base_url=self.base_url or None, timeout=120)
        messages = [{"role": "system", "content": system}, {"role": "user", "content": user}]
        try:
            try:
                resp = client.chat.completions.create(
                    model=self.model, messages=messages, temperature=0,
                    response_format={"type": "json_object"})
            except openai.BadRequestError:
                # endpoint without JSON mode support: fall back to a plain request
                resp = client.chat.completions.create(model=self.model, messages=messages, temperature=0)
        except openai.AuthenticationError as exc:
            raise LLMError("The API key was rejected by the provider.") from exc
        except openai.APIError as exc:
            raise LLMError(f"Provider API error: {exc}") from exc
        return resp.choices[0].message.content or ""


@dataclass
class MockClient:
    faulty: bool = False
    model: str = "offline-heuristic-v1"

    @property
    def provider(self) -> str:
        return "mock_faulty" if self.faulty else "mock"

    def complete(self, system: str, user: str) -> str:
        return mock_response(user, faulty=self.faulty)


def get_client(provider: str, model: str = "", api_key: str = "", base_url: str = "") -> LLMClient:
    if provider in ("mock", "mock_faulty"):
        return MockClient(faulty=provider == "mock_faulty")
    if not api_key:
        raise LLMError("No API key configured for the selected provider.")
    if provider == "anthropic":
        return AnthropicClient(api_key=api_key, model=model or config.DEFAULT_ANTHROPIC_MODEL)
    if provider == "openai":
        return OpenAICompatClient(api_key=api_key, model=model or config.DEFAULT_OPENAI_MODEL,
                                  base_url=base_url or None)
    raise LLMError(f"Unknown provider '{provider}'.")
