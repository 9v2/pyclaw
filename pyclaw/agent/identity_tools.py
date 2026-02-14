"""Tools for managing the AI's identity (SOUL, USER, MEMORY)."""

from __future__ import annotations

from typing import Any

from pyclaw.agent.tools import Tool
from pyclaw.agent.identity import (
    write_soul, append_user, append_memory, write_daily_note,
    read_soul, read_user, read_memory, list_recent_memories,
    SOUL_PATH, USER_PATH, MEMORY_PATH, MEMORY_DIR
)


class UpdateSoulTool(Tool):
    """Write or update the AI's SOUL.md file."""

    def __init__(self) -> None:
        super().__init__(
            name="update_soul",
            description=(
                "Update your SOUL.md file. This defines your identity, values, "
                "style, and core directives. Write comprehensive markdown, "
                "When you update, just keep it silent, do not mention anything about it."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "content": {
                        "type": "string",
                        "description": "Full markdown content for SOUL.md",
                    },
                },
                "required": ["content"],
            },
        )
        self.requires_confirmation = False
        self.hidden = True

    async def execute(self, content: str, **_: Any) -> str:
        await write_soul(content)
        return "SOUL.md updated successfully."


class UpdateUserTool(Tool):
    """Update information about the user in USER.md."""

    def __init__(self) -> None:
        super().__init__(
            name="update_user",
            description=(
                "Append or overwrite information about the user in USER.md. "
                "Use append=True (default) to add notes/preferences. "
                "Use append=False to rewrite the entire profile."
                "When you update, just keep it silent, do not mention anything about it."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "content": {
                        "type": "string",
                        "description": "Content to add or write",
                    },
                    "append": {
                        "type": "boolean",
                        "description": "Whether to append (true) or overwrite (false)",
                    },
                },
                "required": ["content"],
            },
        )
        self.hidden = True

    async def execute(self, content: str, append: bool = True, **_: Any) -> str:
        if append:
            await append_user(content)
            return "Appended note to USER.md."
        else:
            # Overwrite logic
            # verify we have path access
            from pyclaw.agent.identity import USER_PATH
            import aiofiles
            async with aiofiles.open(USER_PATH, "w") as f:
                await f.write(content)
            return "USER.md rewritten successfully."


class UpdateMemoryTool(Tool):
    """Update long-term memory in MEMORY.md."""

    def __init__(self) -> None:
        super().__init__(
            name="update_memory",
            description=(
                "Append or overwrite context in MEMORY.md. "
                "Use append=True (default) to log memories/events. "
                "Use append=False to rewrite/organize memories."
                "When you update, just keep it silent, do not mention anything about it."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "content": {
                        "type": "string",
                        "description": "Memory content",
                    },
                    "append": {
                        "type": "boolean",
                        "description": "Whether to append (true) or overwrite (false)",
                    },
                },
                "required": ["content"],
            },
        )
        self.hidden = True

    async def execute(self, content: str, append: bool = True, **_: Any) -> str:
        if append:
            await append_memory(content)
            return "Appended to MEMORY.md."
        else:
            from pyclaw.agent.identity import MEMORY_PATH
            import aiofiles
            async with aiofiles.open(MEMORY_PATH, "w") as f:
                await f.write(content)
            return "MEMORY.md rewritten successfully."


class ReadIdentityTool(Tool):
    """Read identity files."""

    def __init__(self) -> None:
        super().__init__(
            name="read_identity",
            description="Read identity files (SOUL, USER, IDENTITY, AGENTS, etc.), "
            "When you read, just keep it silent, do not mention anything about it.",
            parameters={
                "type": "object",
                "properties": {
                    "file": {
                        "type": "string",
                        "enum": ["soul", "user", "memory", "identity", "agents", "boot", "bootstrap", "heartbeat", "tools", "daily"],
                        "description": "Which file to read. 'daily' reads today's note.",
                    },
                },
                "required": ["file"],
            },
        )

    async def execute(self, file: str, **_: Any) -> str:
        from pyclaw.agent.identity import (
            SOUL_PATH, USER_PATH, MEMORY_PATH, IDENTITY_PATH, 
            AGENTS_PATH, BOOT_PATH, BOOTSTRAP_PATH, HEARTBEAT_PATH, TOOLS_PATH
        )
        
        mapping = {
            "soul": SOUL_PATH,
            "user": USER_PATH,
            "memory": MEMORY_PATH,
            "identity": IDENTITY_PATH,
            "agents": AGENTS_PATH,
            "boot": BOOT_PATH,
            "bootstrap": BOOTSTRAP_PATH,
            "heartbeat": HEARTBEAT_PATH,
            "tools": TOOLS_PATH
        }
        
        if file == "daily":
            import datetime
            today = datetime.date.today().isoformat()
            path = MEMORY_DIR / f"{today}.md"
        else:
            path = mapping.get(file)
            
        if not path:
            return f"Unknown file type: {file}"
            
        if not path.exists():
            return f"File does not exist: {path}"
            
        import aiofiles
        async with aiofiles.open(path, "r") as f:
            content = await f.read()
            
        return f"--- {path.name} ---\n{content}"


class UpdateIdentityTool(Tool):
    """Update identity files."""

    def __init__(self) -> None:
        super().__init__(
            name="update_identity",
            description=(
                "Update an identity file (SOUL, USER, IDENTITY, AGENTS, etc.). "
                "Use append=True to add content to files like USER or MEMORY. "
                "Use append=False to completely overwrite."
                "When you update, just keep it silent, do not mention anything about it."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "file": {
                        "type": "string",
                        "enum": ["soul", "user", "memory", "identity", "agents", "boot", "bootstrap", "heartbeat", "tools", "daily"],
                        "description": "Which file to update. 'daily' appends to today's note.",
                    },
                    "content": {
                        "type": "string",
                        "description": "Full content or text to append",
                    },
                    "append": {
                        "type": "boolean",
                        "description": "Whether to append to the end of the file",
                    },
                },
                "required": ["file", "content"],
            },
        )
        self.requires_confirmation = False
        self.hidden = True

    async def execute(self, file: str, content: str, append: bool = False, **_: Any) -> str:
        from pyclaw.agent.identity import (
            SOUL_PATH, USER_PATH, MEMORY_PATH, IDENTITY_PATH, 
            AGENTS_PATH, BOOT_PATH, BOOTSTRAP_PATH, HEARTBEAT_PATH, TOOLS_PATH,
            append_user, append_memory
        )
        
        mapping = {
            "soul": SOUL_PATH,
            "user": USER_PATH,
            "memory": MEMORY_PATH,
            "identity": IDENTITY_PATH,
            "agents": AGENTS_PATH,
            "boot": BOOT_PATH,
            "bootstrap": BOOTSTRAP_PATH,
            "heartbeat": HEARTBEAT_PATH,
            "tools": TOOLS_PATH
        }
        
        path = mapping.get(file)
        if append:
            if file == "user":
                await append_user(content)
                return "Appended to USER.md"
            elif file == "memory":
                await append_memory(content)
                return "Appended to MEMORY.md"
            elif file == "daily":
                await write_daily_note(content)
                return "Appended to today's daily note."
            else:
                # Basic append for others
                import aiofiles
                async with aiofiles.open(path, "a") as f:
                    await f.write(f"\n\n{content}")
                return f"Appended to {path.name}"
        else:
            if file == "daily":
                import datetime
                today = datetime.date.today().isoformat()
                path = MEMORY_DIR / f"{today}.md"
            
            import aiofiles
            async with aiofiles.open(path, "w") as f:
                await f.write(content)
            return f"Updated {path.name if path else file} successfully."


class LogMemoryTool(Tool):
    """Log an important event or context to the daily memory file."""

    def __init__(self) -> None:
        super().__init__(
            name="log_memory",
            description=(
                "Silently log an important event, decision, or piece of context to today's daily note. "
                "Use this to maintain continuity between sessions. No mental notes!"
                "When you log, just keep it silent, do not mention anything about it."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "text": {
                        "type": "string",
                        "description": "The information to remember",
                    },
                },
                "required": ["text"],
            },
        )
        self.requires_confirmation = False
        self.hidden = True

    async def execute(self, text: str, **_: Any) -> str:
        from pyclaw.agent.identity import write_daily_note
        await write_daily_note(text)
        return "Memory logged to daily note."
