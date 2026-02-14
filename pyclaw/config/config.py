"""Async config manager with file-based persistence.

Config is stored as JSON at ``~/.pyclaw/config.json``.  The manager
deep-merges user values over defaults and provides typed helpers.
"""

from __future__ import annotations

import asyncio
import copy
import json
import os
import shutil
from pathlib import Path
from typing import Any

import aiofiles

from pyclaw.config.defaults import DEFAULT_CONFIG

_PYCLAW_DIR = Path.home() / ".pyclaw"
_CONFIG_PATH = _PYCLAW_DIR / "config.json"

# Reentrant lock protects concurrent reads/writes.
_lock = asyncio.Lock()


def _deep_merge(base: dict, override: dict) -> dict:
    """Recursively merge *override* into a copy of *base*."""
    result = copy.deepcopy(base)
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = copy.deepcopy(value)
    return result


class Config:
    """Async configuration manager for PyClaw.

    Usage::

        cfg = await Config.load()
        model = cfg.get("agent.model")
        cfg.set("agent.model", "antigravity-gemini-3-pro")
        await cfg.save()
    """

    __slots__ = ("_data", "_path")

    def __init__(self, data: dict, path: Path = _CONFIG_PATH) -> None:
        self._data = data
        self._path = path

    # ── Factory ─────────────────────────────────────────────────────

    @classmethod
    async def load(cls, path: Path | None = None) -> "Config":
        """Load config from disk, creating defaults if absent."""
        path = path or _CONFIG_PATH
        if path.exists():
            async with _lock:
                async with aiofiles.open(path, "r") as f:
                    raw = await f.read()
            try:
                user_data = json.loads(raw)
            except json.JSONDecodeError:
                user_data = {}
            data = _deep_merge(DEFAULT_CONFIG, user_data)
        else:
            data = copy.deepcopy(DEFAULT_CONFIG)
        return cls(data, path)

    # ── Persistence ─────────────────────────────────────────────────

    async def save(self) -> None:
        """Write the current config to disk."""
        self._path.parent.mkdir(parents=True, exist_ok=True)
        payload = json.dumps(self._data, indent=2, default=str)
        async with _lock:
            async with aiofiles.open(self._path, "w") as f:
                await f.write(payload)

    # ── Accessors ───────────────────────────────────────────────────

    def get(self, dotted_key: str, default: Any = None) -> Any:
        """Get a value via dotted key, e.g. ``agent.model``."""
        keys = dotted_key.split(".")
        node: Any = self._data
        for k in keys:
            if isinstance(node, dict) and k in node:
                node = node[k]
            else:
                return default
        return node

    def set(self, dotted_key: str, value: Any) -> None:
        """Set a value via dotted key."""
        keys = dotted_key.split(".")
        node = self._data
        for k in keys[:-1]:
            if k not in node or not isinstance(node[k], dict):
                node[k] = {}
            node = node[k]
        node[keys[-1]] = value

    @property
    def data(self) -> dict:
        """Return the raw config dict (read-only view)."""
        return self._data

    @property
    def path(self) -> Path:
        return self._path

    # ── Helpers ─────────────────────────────────────────────────────

    @staticmethod
    def config_dir() -> Path:
        return _PYCLAW_DIR

    @staticmethod
    def config_path() -> Path:
        return _CONFIG_PATH

    @staticmethod
    def workspace_path(cfg_data: dict | None = None) -> Path:
        raw = (
            (cfg_data or DEFAULT_CONFIG)
            .get("workspace", {})
            .get("path", "~/.pyclaw/workspace")
        )
        return Path(os.path.expanduser(raw))

    # ── Backup / Restore ────────────────────────────────────────────

    async def backup(self) -> Path:
        """Create a timestamped backup of the config file."""
        import time

        ts = int(time.time())
        backup_path = self._path.parent / f"config.backup.{ts}.json"
        if self._path.exists():
            shutil.copy2(self._path, backup_path)

        # Prune old backups
        max_count = self.get("backups.max_count", 5)
        backups = sorted(self.list_backups(), reverse=True)
        for old in backups[max_count:]:
            old.unlink(missing_ok=True)

        return backup_path

    @staticmethod
    def list_backups() -> list[Path]:
        """List all config backup files."""
        return sorted(_PYCLAW_DIR.glob("config.backup.*.json"))

    async def restore(self, backup_path: Path) -> None:
        """Restore config from a backup file."""
        if not backup_path.exists():
            raise FileNotFoundError(f"Backup not found: {backup_path}")
        shutil.copy2(backup_path, self._path)
        # Reload
        async with _lock:
            async with aiofiles.open(self._path, "r") as f:
                raw = await f.read()
        self._data = _deep_merge(DEFAULT_CONFIG, json.loads(raw))
