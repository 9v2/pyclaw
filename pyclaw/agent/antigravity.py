"""Antigravity API client — low-level HTTP interface.

Direct HTTP calls to the Cloud Code Assist (Antigravity) endpoints.

API Spec reference:
  https://github.com/NoeFabris/opencode-antigravity-auth/blob/main/docs/ANTIGRAVITY_API_SPEC.md

Request format:
  {
    "project": "{project_id}",
    "model": "{model_id}",
    "request": {
      "contents": [{"role": "user", "parts": [{"text": "..."}]}],
      "generationConfig": {"maxOutputTokens": 1000, "temperature": 0.7},
      "systemInstruction": {"parts": [{"text": "..."}]}
    },
    "userAgent": "antigravity",
    "requestId": "{unique_id}"
  }
"""

from __future__ import annotations

import json
import secrets
from typing import Any, AsyncIterator, Optional

import aiohttp


# ── Endpoints ───────────────────────────────────────────────────────

BASE_URL = "https://cloudcode-pa.googleapis.com"

ENDPOINTS = {
    "stream": f"{BASE_URL}/v1internal:streamGenerateContent?alt=sse",
    "no_stream": f"{BASE_URL}/v1internal:generateContent",
    "models": f"{BASE_URL}/v1internal:fetchAvailableModels",
    "load": f"{BASE_URL}/v1internal:loadCodeAssist",
}

FALLBACK_ENDPOINTS = [
    "https://cloudcode-pa.googleapis.com",
    "https://daily-cloudcode-pa.sandbox.googleapis.com",
]


def _build_headers(access_token: str, streaming: bool = False) -> dict[str, str]:
    """Build request headers with Bearer auth (from API spec)."""
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
        "User-Agent": "antigravity/1.15.8 windows/amd64",
        "X-Goog-Api-Client": "google-cloud-sdk vscode_cloudshelleditor/0.1",
        "Client-Metadata": json.dumps({
            "ideType": "ANTIGRAVITY",
            "platform": "PLATFORM_UNSPECIFIED",
            "pluginType": "GEMINI",
        }),
    }
    if streaming:
        headers["Accept"] = "text/event-stream"
    return headers


def _build_request_body(
    model: str,
    contents: list[dict[str, Any]],
    system_instruction: str | None = None,
    temperature: float = 0.7,
    max_output_tokens: int = 1000,
    project_id: str | None = None,
    tools: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Build the Antigravity API request body with the `request` wrapper."""

    # Inner request object (Gemini-style)
    inner_request: dict[str, Any] = {
        "contents": contents,
        "generationConfig": {
            "maxOutputTokens": max_output_tokens,
            "temperature": temperature,
        },
    }

    if system_instruction:
        inner_request["systemInstruction"] = {
            "parts": [{"text": system_instruction}],
        }

    if tools:
        inner_request["tools"] = tools

    # Outer body
    body: dict[str, Any] = {
        "model": model,
        "request": inner_request,
        "userAgent": "antigravity",
        "requestId": secrets.token_hex(16),
    }

    if project_id:
        body["project"] = project_id

    return body


# ── Streaming Generation ────────────────────────────────────────────

async def stream_generate(
    access_token: str,
    model: str,
    contents: list[dict[str, Any]],
    system_instruction: str | None = None,
    temperature: float = 0.7,
    max_output_tokens: int = 1000,
    project_id: str | None = None,
    tools: list[dict[str, Any]] | None = None,
) -> AsyncIterator[str]:
    """Stream text from the Antigravity API via SSE.

    Yields text chunks as they arrive from the model.
    """
    headers = _build_headers(access_token, streaming=True)
    body = _build_request_body(
        model, contents, system_instruction,
        temperature, max_output_tokens, project_id, tools,
    )

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                ENDPOINTS["stream"],
                headers=headers,
                json=body,
                timeout=aiohttp.ClientTimeout(total=300),
            ) as resp:
                if resp.status != 200:
                    error_text = await resp.text()
                    yield f"\n\n⚠️  API error ({resp.status}): {error_text[:500]}"
                    return

                # Parse SSE stream
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
                            # Response is wrapped in "response" object
                            response = data.get("response", data)
                            candidates = response.get("candidates", [])
                            for candidate in candidates:
                                content = candidate.get("content", {})
                                parts = content.get("parts", [])
                                for part in parts:
                                    text = part.get("text", "")
                                    if text:
                                        yield text
                        except json.JSONDecodeError:
                            continue

    except aiohttp.ClientError as exc:
        yield f"\n\n⚠️  connection error: {exc}"
    except Exception as exc:
        yield f"\n\n⚠️  model error: {exc}"


async def stream_generate_raw(
    access_token: str,
    model: str,
    contents: list[dict[str, Any]],
    system_instruction: str | None = None,
    temperature: float = 0.7,
    max_output_tokens: int = 1000,
    project_id: str | None = None,
    tools: list[dict[str, Any]] | None = None,
) -> AsyncIterator[dict[str, Any]]:
    """Stream raw parsed SSE chunks from the Antigravity API.

    Yields full candidate dicts including functionCall parts,
    used by the agent's tool-call loop.
    """
    headers = _build_headers(access_token, streaming=True)
    body = _build_request_body(
        model, contents, system_instruction,
        temperature, max_output_tokens, project_id, tools,
    )

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                ENDPOINTS["stream"],
                headers=headers,
                json=body,
                timeout=aiohttp.ClientTimeout(total=300),
            ) as resp:
                if resp.status != 200:
                    error_text = await resp.text()
                    yield {"error": f"API error ({resp.status}): {error_text[:500]}"}
                    return

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
                            response = data.get("response", data)
                            candidates = response.get("candidates", [])
                            for candidate in candidates:
                                yield candidate
                        except json.JSONDecodeError:
                            continue

    except aiohttp.ClientError as exc:
        yield {"error": f"connection error: {exc}"}
    except Exception as exc:
        yield {"error": f"model error: {exc}"}


# ── Non-Streaming Generation ────────────────────────────────────────

async def generate(
    access_token: str,
    model: str,
    contents: list[dict[str, Any]],
    system_instruction: str | None = None,
    temperature: float = 0.7,
    max_output_tokens: int = 1000,
    project_id: str | None = None,
) -> str:
    """Non-streaming generation — returns the full response text."""
    headers = _build_headers(access_token)
    body = _build_request_body(
        model, contents, system_instruction,
        temperature, max_output_tokens, project_id,
    )

    async with aiohttp.ClientSession() as session:
        async with session.post(
            ENDPOINTS["no_stream"],
            headers=headers,
            json=body,
            timeout=aiohttp.ClientTimeout(total=300),
        ) as resp:
            if resp.status != 200:
                error_text = await resp.text()
                return f"⚠️  API error ({resp.status}): {error_text[:500]}"

            data = await resp.json()
            # Response is wrapped in "response" object
            response = data.get("response", data)
            candidates = response.get("candidates", [])
            texts: list[str] = []
            for candidate in candidates:
                content = candidate.get("content", {})
                for part in content.get("parts", []):
                    texts.append(part.get("text", ""))
            return "".join(texts)


# ── Fetch Available Models ──────────────────────────────────────────

async def fetch_available_models(
    access_token: str,
    project_id: str | None = None,
) -> dict[str, Any]:
    """Fetch available models and their quota info from Antigravity."""
    headers = _build_headers(access_token)
    body: dict[str, Any] = {}
    if project_id:
        body["project"] = project_id

    for endpoint in FALLBACK_ENDPOINTS:
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{endpoint}/v1internal:fetchAvailableModels",
                    headers=headers,
                    json=body,
                    timeout=aiohttp.ClientTimeout(total=15),
                ) as resp:
                    if resp.ok:
                        return await resp.json()
        except Exception:
            continue

    return {}


# ── Fetch Usage / Credits ───────────────────────────────────────────

async def fetch_usage(
    access_token: str,
) -> dict[str, Any]:
    """Fetch credit usage and plan info from the loadCodeAssist endpoint."""
    headers = _build_headers(access_token)

    for endpoint in FALLBACK_ENDPOINTS:
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{endpoint}/v1internal:loadCodeAssist",
                    headers=headers,
                    json={"metadata": {
                        "ideType": "ANTIGRAVITY",
                        "platform": "PLATFORM_UNSPECIFIED",
                        "pluginType": "GEMINI",
                    }},
                    timeout=aiohttp.ClientTimeout(total=15),
                ) as resp:
                    if resp.ok:
                        return await resp.json()
        except Exception:
            continue

    return {}
