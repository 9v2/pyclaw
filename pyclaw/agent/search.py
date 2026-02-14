"""Optional web search tools — Brave Search and Perplexity API.

Only registered when a search provider is configured in config.
Also includes a general web page reader.
"""

from __future__ import annotations

import json
import re
from typing import Any

import aiohttp

from pyclaw.agent.tools import Tool


class WebSearchTool(Tool):
    """Search the web using the configured provider."""

    def __init__(self, provider: str, api_key: str) -> None:
        super().__init__(
            name="web_search",
            description="Search the web for information. Returns a summary of search results.",
            parameters={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Search query",
                    },
                },
                "required": ["query"],
            },
        )
        self._provider = provider
        self._api_key = api_key

    async def execute(self, query: str, **_: Any) -> str:
        if self._provider == "brave":
            return await self._brave_search(query)
        elif self._provider == "perplexity":
            return await self._perplexity_search(query)
        return "Error: unknown search provider"

    async def _brave_search(self, query: str) -> str:
        url = "https://api.search.brave.com/res/v1/web/search"
        headers = {
            "Accept": "application/json",
            "Accept-Encoding": "gzip",
            "X-Subscription-Token": self._api_key,
        }
        params = {"q": query, "count": 5}

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    url, headers=headers, params=params,
                    timeout=aiohttp.ClientTimeout(total=10),
                ) as resp:
                    if resp.status != 200:
                        return f"Brave search error ({resp.status})"
                    data = await resp.json()

            results: list[str] = []
            for item in data.get("web", {}).get("results", [])[:5]:
                title = item.get("title", "")
                desc = item.get("description", "")
                link = item.get("url", "")
                results.append(f"**{title}**\n{desc}\n{link}")

            if not results:
                return f"No results for: {query}"
            return "\n\n".join(results)

        except Exception as exc:
            return f"Search error: {exc}"

    async def _perplexity_search(self, query: str) -> str:
        url = "https://api.perplexity.ai/chat/completions"
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }
        body = {
            "model": "sonar",
            "messages": [
                {"role": "user", "content": query}
            ],
            "max_tokens": 1024,
        }

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    url, headers=headers, json=body,
                    timeout=aiohttp.ClientTimeout(total=15),
                ) as resp:
                    if resp.status != 200:
                        return f"Perplexity error ({resp.status})"
                    data = await resp.json()

            choices = data.get("choices", [])
            if choices:
                return choices[0].get("message", {}).get("content", "No response")
            return "No response from Perplexity"

        except Exception as exc:
            return f"Search error: {exc}"


class ReadWebpageTool(Tool):
    """Fetch and read a webpage, stripping HTML tags."""

    def __init__(self) -> None:
        super().__init__(
            name="read_webpage",
            description="Fetch a URL and return its text content, with HTML tags stripped.",
            parameters={
                "type": "object",
                "properties": {
                    "url": {
                        "type": "string",
                        "description": "URL to fetch",
                    },
                },
                "required": ["url"],
            },
        )

    async def execute(self, url: str, **_: Any) -> str:
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    url,
                    timeout=aiohttp.ClientTimeout(total=15),
                    headers={"User-Agent": "Mozilla/5.0 (compatible; PyClaw/1.0)"},
                ) as resp:
                    if resp.status != 200:
                        return f"HTTP error ({resp.status}) for {url}"
                    html = await resp.text()

            # Strip HTML tags
            text = re.sub(r"<script[^>]*>.*?</script>", "", html, flags=re.DOTALL)
            text = re.sub(r"<style[^>]*>.*?</style>", "", text, flags=re.DOTALL)
            text = re.sub(r"<[^>]+>", " ", text)
            text = re.sub(r"\s+", " ", text).strip()

            if len(text) > 20000:
                text = text[:20000] + "\n... (truncated)"
            return text

        except Exception as exc:
            return f"Error fetching {url}: {exc}"
