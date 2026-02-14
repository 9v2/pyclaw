"""Self-config tools — let the AI read and modify its own config.

The AI can change models, update personality, manage preferences, and
create backups of the config.  All writes auto-backup first.
"""

from __future__ import annotations

import json
from typing import Any

from pyclaw.agent.tools import Tool


class GetConfigTool(Tool):
    """Read a config value."""

    def __init__(self) -> None:
        super().__init__(
            name="get_config",
            description=(
                "Read a PyClaw configuration value by its dotted key path. "
                "Example keys: 'agent.model', 'personality.ai_name', "
                "'search.provider', 'cron.jobs'."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "key": {
                        "type": "string",
                        "description": "Dotted config key, e.g. 'agent.model'",
                    },
                },
                "required": ["key"],
            },
        )
        self._cfg = None

    def bind(self, cfg: Any) -> None:
        self._cfg = cfg

    async def execute(self, key: str, **_: Any) -> str:
        if not self._cfg:
            return "Error: config not bound"
        value = self._cfg.get(key)
        return json.dumps(value, default=str)


class SetConfigTool(Tool):
    """Set a config value (auto-backups before writing)."""

    def __init__(self) -> None:
        super().__init__(
            name="set_config",
            description=(
                "Set a PyClaw configuration value. Auto-creates a backup before "
                "writing. Use dotted keys like 'agent.model', 'personality.ai_name', etc."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "key": {
                        "type": "string",
                        "description": "Dotted config key",
                    },
                    "value": {
                        "type": "string",
                        "description": "Value to set (JSON-encoded for complex types)",
                    },
                },
                "required": ["key", "value"],
            },
        )
        self.requires_confirmation = True
        self._cfg = None

    def bind(self, cfg: Any) -> None:
        self._cfg = cfg

    async def execute(self, key: str, value: str, **_: Any) -> str:
        if not self._cfg:
            return "Error: config not bound"

        # Auto-backup
        await self._cfg.backup()

        # Try to parse as JSON, fall back to string
        try:
            parsed = json.loads(value)
        except (json.JSONDecodeError, TypeError):
            parsed = value

        self._cfg.set(key, parsed)
        await self._cfg.save()
        return f"Set {key} = {json.dumps(parsed, default=str)}"


class ChangeModelTool(Tool):
    """Switch the active AI model."""

    def __init__(self) -> None:
        super().__init__(
            name="change_model",
            description=(
                "Switch to a different AI model. The change takes effect on the "
                "next message. Examples: 'gemini-2.5-flash', 'claude-sonnet-4-5', 'gpt-4o'."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "model_id": {
                        "type": "string",
                        "description": "Model ID to switch to",
                    },
                },
                "required": ["model_id"],
            },
        )
        self._cfg = None
        self._agent = None

    def bind(self, cfg: Any, agent: Any = None) -> None:
        self._cfg = cfg
        self._agent = agent

    async def execute(self, model_id: str, **_: Any) -> str:
        if not self._cfg:
            return "Error: config not bound"

        await self._cfg.backup()
        self._cfg.set("agent.model", model_id)
        await self._cfg.save()

        if self._agent:
            self._agent.model_id = model_id

        return f"Model switched to {model_id}. Will take effect on next message."


class BackupConfigTool(Tool):
    """Manually create a config backup."""

    def __init__(self) -> None:
        super().__init__(
            name="backup_config",
            description="Create a manual backup of the current PyClaw configuration.",
            parameters={
                "type": "object",
                "properties": {},
            },
        )
        self._cfg = None

    def bind(self, cfg: Any) -> None:
        self._cfg = cfg

    async def execute(self, **_: Any) -> str:
        if not self._cfg:
            return "Error: config not bound"
        path = await self._cfg.backup()
        return f"Backup created at {path}"
