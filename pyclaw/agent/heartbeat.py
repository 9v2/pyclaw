"""Heartbeat — periodic health check, outputs to markdown.

Writes status to ``~/.pyclaw/heartbeat.md`` as a markdown table
that's easy for both humans and LLMs to read.
"""

from __future__ import annotations

import asyncio
import logging
import time
from pathlib import Path
from typing import Any

import aiohttp
import aiofiles

from pyclaw.config.config import Config

logger = logging.getLogger("pyclaw.heartbeat")

HEARTBEAT_PATH = Path.home() / ".pyclaw" / "heartbeat.md"


class Heartbeat:
    """Periodic health checker — writes results to heartbeat.md."""

    def __init__(self, cfg: Config) -> None:
        self._cfg = cfg
        self._running = False
        self._last_status: dict[str, Any] = {}

    @property
    def last_status(self) -> dict[str, Any]:
        return dict(self._last_status)

    async def check(self) -> dict[str, Any]:
        """Run a single health check. Returns status dict."""
        status: dict[str, Any] = {
            "timestamp": time.time(),
            "time_str": time.strftime("%Y-%m-%d %H:%M:%S"),
            "ok": True,
            "checks": {},
        }

        # Check 1: Config readable
        try:
            _ = self._cfg.get("agent.model")
            status["checks"]["config"] = "✅ ok"
        except Exception as exc:
            status["checks"]["config"] = f"❌ {exc}"
            status["ok"] = False

        # Check 2: Auth token present
        provider = self._cfg.get("auth.provider", "antigravity")
        if provider == "antigravity":
            token = self._cfg.get("auth.google_token")
            status["checks"]["auth"] = "✅ token present" if token else "❌ no token"
            if not token:
                status["ok"] = False
        elif provider == "openai":
            key = self._cfg.get("auth.openai_api_key")
            status["checks"]["auth"] = "✅ key set" if key else "⚠️ no key"
        elif provider == "anthropic":
            key = self._cfg.get("auth.anthropic_api_key")
            status["checks"]["auth"] = "✅ key set" if key else "⚠️ no key"
        elif provider == "custom":
            base = self._cfg.get("auth.custom_api_base")
            status["checks"]["auth"] = "✅ endpoint set" if base else "⚠️ no endpoint"

        # Check 3: API reachability
        try:
            urls = {
                "antigravity": "https://cloudcode-pa.googleapis.com",
                "openai": "https://api.openai.com",
                "anthropic": "https://api.anthropic.com",
                "custom": self._cfg.get("auth.custom_api_base", ""),
            }
            url = urls.get(provider, "")
            if url:
                async with aiohttp.ClientSession() as session:
                    async with session.head(
                        url, timeout=aiohttp.ClientTimeout(total=5)
                    ) as resp:
                        status["checks"]["api"] = f"✅ reachable ({resp.status})"
            else:
                status["checks"]["api"] = "⏭️ skipped"
        except Exception:
            status["checks"]["api"] = "❌ unreachable"

        # Check 4: Gateway PID
        try:
            from pyclaw.gateway.manager import GatewayManager

            if GatewayManager.is_running():
                pid = GatewayManager.get_pid()
                status["checks"]["gateway"] = f"✅ running (pid {pid})"
            else:
                status["checks"]["gateway"] = "⏹️ stopped"
        except Exception:
            status["checks"]["gateway"] = "❓ unknown"

        # Check 5: Soul file
        from pyclaw.agent.identity import SOUL_PATH

        status["checks"]["soul"] = (
            "✅ configured" if SOUL_PATH.exists() else "⚠️ first boot"
        )

        self._last_status = status
        return status

    async def _write_md(self, status: dict[str, Any]) -> None:
        """Append a status entry to heartbeat.md."""
        HEARTBEAT_PATH.parent.mkdir(parents=True, exist_ok=True)

        overall = "✅ healthy" if status["ok"] else "⚠️ issues detected"

        # Build the entry
        entry = f"\n## {status['time_str']} — {overall}\n\n"
        entry += "| Check | Status |\n|-------|--------|\n"
        for k, v in status["checks"].items():
            entry += f"| {k} | {v} |\n"
        entry += "\n---\n"

        # If file doesn't exist, create with header
        if not HEARTBEAT_PATH.exists():
            header = "# 🫀 PyClaw Heartbeat Log\n\n"
            header += "_Periodic health checks. Latest entries at the bottom._\n\n---\n"
            async with aiofiles.open(HEARTBEAT_PATH, "w") as f:
                await f.write(header + entry)
        else:
            # Keep file from growing too large — last 50 entries
            async with aiofiles.open(HEARTBEAT_PATH, "r") as f:
                content = await f.read()

            sections = content.split("\n## ")
            if len(sections) > 51:  # header + 50 entries
                # Keep header + last 50
                header = sections[0]
                kept = sections[-50:]
                content = header + "\n## " + "\n## ".join(kept)
                async with aiofiles.open(HEARTBEAT_PATH, "w") as f:
                    await f.write(content + entry)
            else:
                async with aiofiles.open(HEARTBEAT_PATH, "a") as f:
                    await f.write(entry)

    async def start(self) -> None:
        """Start the heartbeat loop."""
        interval = self._cfg.get("cron.heartbeat_interval", 300)
        self._running = True
        logger.info("heartbeat started (interval=%ds)", interval)

        HEARTBEAT_PATH.parent.mkdir(parents=True, exist_ok=True)

        while self._running:
            try:
                status = await self.check()
                await self._write_md(status)

                if not status["ok"]:
                    checks_str = " | ".join(
                        f"{k}={v}" for k, v in status["checks"].items()
                    )
                    logger.warning("heartbeat: %s", checks_str)

            except Exception as exc:
                logger.error("heartbeat error: %s", exc)

            await asyncio.sleep(interval)

    def stop(self) -> None:
        """Stop the heartbeat loop."""
        self._running = False
