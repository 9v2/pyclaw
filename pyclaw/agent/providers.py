"""Multi-provider abstraction for AI model calls.

Supports 4 providers:
  1. Antigravity — Google Cloud Code Assist (SSE streaming)
  2. OpenAI      — api.openai.com/v1/chat/completions
  3. Anthropic   — api.anthropic.com via OpenAI-compat
  4. Custom      — any OpenAI-compatible endpoint

If api_key is "secret", it passes "" to the Authorization header.
"""

from __future__ import annotations

import json
import secrets
from abc import ABC, abstractmethod
from typing import Any, AsyncIterator, Optional

import aiohttp

from pyclaw.config.config import Config


class Provider(ABC):
    """Abstract provider for AI model calls."""

    @abstractmethod
    async def stream(
        self,
        model: str,
        contents: list[dict[str, Any]],
        system_instruction: str | None = None,
        temperature: float = 0.7,
        max_output_tokens: int = 8192,
        tools: list[dict[str, Any]] | None = None,
    ) -> AsyncIterator[dict[str, Any]]:
        """Stream raw candidate/chunk dicts."""
        ...

    @abstractmethod
    async def fetch_models(self) -> list[dict[str, str]]:
        """Fetch available models. Returns [{"id": ..., "name": ...}]."""
        ...

    @staticmethod
    def from_config(cfg: Config) -> "Provider":
        """Create the appropriate provider from config."""
        provider_name = cfg.get("auth.provider", "antigravity")

        if provider_name == "antigravity":
            return AntigravityProvider(cfg)
        elif provider_name == "openai":
            return OpenAICompatProvider(
                api_key=cfg.get("auth.openai_api_key", ""),
                api_base="https://api.openai.com/v1",
                default_model=cfg.get("agent.model", "gpt-4o"),
            )
        elif provider_name == "anthropic":
            return OpenAICompatProvider(
                api_key=cfg.get("auth.anthropic_api_key", ""),
                api_base="https://api.anthropic.com/v1",
                default_model=cfg.get("agent.model", "claude-sonnet-4-20250514"),
            )
        elif provider_name == "custom":
            return OpenAICompatProvider(
                api_key=cfg.get("auth.custom_api_key", ""),
                api_base=cfg.get("auth.custom_api_base", ""),
                default_model=cfg.get("auth.custom_model") or cfg.get("agent.model", ""),
            )
        else:
            raise ValueError(f"Unknown provider: {provider_name}")


# ── Antigravity Provider ─────────────────────────────────────────────

class AntigravityProvider(Provider):
    """Google Cloud Code Assist via Antigravity API."""

    def __init__(self, cfg: Config) -> None:
        self._cfg = cfg

    async def stream(
        self,
        model: str,
        contents: list[dict[str, Any]],
        system_instruction: str | None = None,
        temperature: float = 0.7,
        max_output_tokens: int = 8192,
        tools: list[dict[str, Any]] | None = None,
    ) -> AsyncIterator[dict[str, Any]]:
        from pyclaw.agent.antigravity import stream_generate_raw
        from pyclaw.auth.google_auth import refresh_token_if_needed

        token = await refresh_token_if_needed(self._cfg)
        if not token:
            yield {"error": "Not authenticated — run `pyclaw onboard`"}
            return

        project_id = self._cfg.get("auth.project_id")

        async for candidate in stream_generate_raw(
            access_token=token,
            model=model,
            contents=contents,
            system_instruction=system_instruction,
            temperature=temperature,
            max_output_tokens=max_output_tokens,
            project_id=project_id,
            tools=tools,
        ):
            yield candidate

    async def fetch_models(self) -> list[dict[str, str]]:
        from pyclaw.agent.antigravity import fetch_available_models
        from pyclaw.auth.google_auth import refresh_token_if_needed

        token = await refresh_token_if_needed(self._cfg)
        if not token:
            return []

        data = await fetch_available_models(token, self._cfg.get("auth.project_id"))
        models_data = data.get("models", {})
        return [
            {"id": mid, "name": info.get("displayName", mid)}
            for mid, info in models_data.items()
        ]


# ── OpenAI-Compatible Provider ───────────────────────────────────────

class OpenAICompatProvider(Provider):
    """OpenAI-compatible API (works for OpenAI, Anthropic via proxy, custom)."""

    def __init__(
        self,
        api_key: str,
        api_base: str,
        default_model: str = "",
    ) -> None:
        # "secret" means pass empty string
        self._api_key = "" if api_key == "secret" else (api_key or "")
        self._api_base = api_base.rstrip("/")
        self._default_model = default_model

    def _headers(self) -> dict[str, str]:
        headers: dict[str, str] = {"Content-Type": "application/json"}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"
        return headers

    def _convert_contents(
        self,
        contents: list[dict[str, Any]],
        system_instruction: str | None,
    ) -> list[dict[str, Any]]:
        """Convert Gemini-style contents to OpenAI messages format."""
        messages: list[dict[str, Any]] = []

        if system_instruction:
            messages.append({"role": "system", "content": system_instruction})

        for c in contents:
            role = c.get("role", "user")
            if role == "model":
                role = "assistant"

            parts = c.get("parts", [])
            # Check for function call / response
            for p in parts:
                if "functionCall" in p:
                    fc = p["functionCall"]
                    messages.append({
                        "role": "assistant",
                        "content": None,
                        "tool_calls": [{
                            "id": fc.get("id", secrets.token_hex(8)),
                            "type": "function",
                            "function": {
                                "name": fc["name"],
                                "arguments": json.dumps(fc.get("args", {})),
                            }
                        }],
                    })
                    continue
                if "functionResponse" in p:
                    fr = p["functionResponse"]
                    messages.append({
                        "role": "tool",
                        "tool_call_id": fr.get("id", ""),
                        "content": json.dumps(fr.get("response", {})),
                    })
                    continue
                if "text" in p:
                    messages.append({"role": role, "content": p["text"]})

        return messages

    def _convert_tools(self, tools: list[dict[str, Any]] | None) -> list[dict[str, Any]] | None:
        """Convert Gemini tools to OpenAI tools format."""
        if not tools:
            return None
        result: list[dict[str, Any]] = []
        for tool_group in tools:
            for fd in tool_group.get("functionDeclarations", []):
                result.append({
                    "type": "function",
                    "function": {
                        "name": fd["name"],
                        "description": fd.get("description", ""),
                        "parameters": fd.get("parameters", {}),
                    },
                })
        return result or None

    async def stream(
        self,
        model: str,
        contents: list[dict[str, Any]],
        system_instruction: str | None = None,
        temperature: float = 0.7,
        max_output_tokens: int = 8192,
        tools: list[dict[str, Any]] | None = None,
    ) -> AsyncIterator[dict[str, Any]]:
        messages = self._convert_contents(contents, system_instruction)
        openai_tools = self._convert_tools(tools)

        body: dict[str, Any] = {
            "model": model or self._default_model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_output_tokens,
            "stream": True,
        }
        if openai_tools:
            body["tools"] = openai_tools

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{self._api_base}/chat/completions",
                    headers=self._headers(),
                    json=body,
                    timeout=aiohttp.ClientTimeout(total=300),
                ) as resp:
                    if resp.status != 200:
                        error = await resp.text()
                        yield {"error": f"API error ({resp.status}): {error[:500]}"}
                        return

                    # Accumulated tool calls for this response
                    pending_tool_calls: dict[int, dict] = {}

                    async for line in resp.content:
                        decoded = line.decode("utf-8", errors="replace").strip()
                        if not decoded or decoded.startswith(":"):
                            continue
                        if decoded.startswith("data: "):
                            data_str = decoded[6:]
                            if data_str == "[DONE]":
                                break
                            try:
                                data = json.loads(data_str)
                                for choice in data.get("choices", []):
                                    delta = choice.get("delta", {})

                                    # Text content
                                    if delta.get("content"):
                                        yield {
                                            "content": {
                                                "role": "model",
                                                "parts": [{"text": delta["content"]}],
                                            }
                                        }

                                    # Tool calls
                                    for tc in delta.get("tool_calls", []):
                                        idx = tc.get("index", 0)
                                        if idx not in pending_tool_calls:
                                            pending_tool_calls[idx] = {
                                                "id": tc.get("id", ""),
                                                "name": "",
                                                "arguments": "",
                                            }
                                        ptc = pending_tool_calls[idx]
                                        if tc.get("id"):
                                            ptc["id"] = tc["id"]
                                        fn = tc.get("function", {})
                                        if fn.get("name"):
                                            ptc["name"] += fn["name"]
                                        if fn.get("arguments"):
                                            ptc["arguments"] += fn["arguments"]

                                    finish = choice.get("finish_reason")
                                    if finish:
                                        yield {"finishReason": finish.upper()}

                            except json.JSONDecodeError:
                                continue

                    # Emit accumulated tool calls
                    for ptc in pending_tool_calls.values():
                        try:
                            args = json.loads(ptc["arguments"])
                        except (json.JSONDecodeError, KeyError):
                            args = {}
                        yield {
                            "content": {
                                "role": "model",
                                "parts": [{
                                    "functionCall": {
                                        "name": ptc["name"],
                                        "args": args,
                                        "id": ptc["id"],
                                    }
                                }],
                            }
                        }

        except aiohttp.ClientError as exc:
            yield {"error": f"Connection error: {exc}"}
        except Exception as exc:
            yield {"error": f"Provider error: {exc}"}

    async def fetch_models(self) -> list[dict[str, str]]:
        """Try to fetch models from /v1/models."""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{self._api_base}/models",
                    headers=self._headers(),
                    timeout=aiohttp.ClientTimeout(total=10),
                ) as resp:
                    if resp.status != 200:
                        return []
                    data = await resp.json()
                    models = data.get("data", [])
                    return [
                        {"id": m.get("id", ""), "name": m.get("id", "")}
                        for m in models
                    ]
        except Exception:
            return []
