import os
from abc import ABC, abstractmethod
from dataclasses import dataclass

import httpx


class ProviderConfigurationError(RuntimeError):
    pass


@dataclass(slots=True)
class LLMMessage:
    role: str
    content: str


class LLMProvider(ABC):
    id: str

    @abstractmethod
    async def complete(self, messages: list[LLMMessage], model: str, system: str) -> str:
        raise NotImplementedError


class DemoProvider(LLMProvider):
    id = "demo"

    async def complete(self, messages: list[LLMMessage], model: str, system: str) -> str:
        last = messages[-1].content.strip()
        return (
            "Mode démonstration actif — aucun modèle externe n’est appelé. "
            f"J’ai bien reçu : « {last[:500]} ». "
            "Configure OpenAI, Anthropic ou démarre Ollama pour obtenir une réponse générative."
        )


class OpenAIProvider(LLMProvider):
    id = "openai"

    async def complete(self, messages: list[LLMMessage], model: str, system: str) -> str:
        key = os.getenv("OPENAI_API_KEY")
        if not key:
            raise ProviderConfigurationError("OPENAI_API_KEY n’est pas configurée")
        payload = {
            "model": model,
            "input": [{"role": item.role, "content": item.content} for item in messages],
            "instructions": system,
        }
        async with httpx.AsyncClient(timeout=90) as client:
            response = await client.post(
                "https://api.openai.com/v1/responses",
                headers={"Authorization": f"Bearer {key}"},
                json=payload,
            )
            response.raise_for_status()
            data = response.json()
        if data.get("output_text"):
            return data["output_text"]
        chunks = [
            content.get("text", "")
            for output in data.get("output", [])
            for content in output.get("content", [])
            if content.get("type") == "output_text"
        ]
        return "".join(chunks).strip()


class AnthropicProvider(LLMProvider):
    id = "anthropic"

    async def complete(self, messages: list[LLMMessage], model: str, system: str) -> str:
        key = os.getenv("ANTHROPIC_API_KEY")
        if not key:
            raise ProviderConfigurationError("ANTHROPIC_API_KEY n’est pas configurée")
        payload = {
            "model": model,
            "max_tokens": 2048,
            "system": system,
            "messages": [{"role": item.role, "content": item.content} for item in messages],
        }
        async with httpx.AsyncClient(timeout=90) as client:
            response = await client.post(
                "https://api.anthropic.com/v1/messages",
                headers={"x-api-key": key, "anthropic-version": "2023-06-01"},
                json=payload,
            )
            response.raise_for_status()
            data = response.json()
        return "".join(item.get("text", "") for item in data.get("content", [])).strip()


class OllamaProvider(LLMProvider):
    id = "ollama"

    async def complete(self, messages: list[LLMMessage], model: str, system: str) -> str:
        base_url = os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434").rstrip("/")
        payload = {
            "model": model,
            "stream": False,
            "messages": [
                {"role": "system", "content": system},
                *[{"role": item.role, "content": item.content} for item in messages],
            ],
        }
        try:
            async with httpx.AsyncClient(timeout=120) as client:
                response = await client.post(f"{base_url}/api/chat", json=payload)
                response.raise_for_status()
                return response.json()["message"]["content"].strip()
        except httpx.ConnectError as exc:
            raise ProviderConfigurationError("Ollama n’est pas démarré") from exc


class LLMRegistry:
    def __init__(self) -> None:
        self._providers: dict[str, LLMProvider] = {}

    def register(self, provider: LLMProvider) -> None:
        self._providers[provider.id] = provider

    def get(self, provider_id: str) -> LLMProvider:
        try:
            return self._providers[provider_id]
        except KeyError as exc:
            raise ProviderConfigurationError(f"Fournisseur LLM inconnu : {provider_id}") from exc

    def list(self) -> list[str]:
        return sorted(self._providers)


llm_registry = LLMRegistry()
for provider in (DemoProvider(), OpenAIProvider(), AnthropicProvider(), OllamaProvider()):
    llm_registry.register(provider)
