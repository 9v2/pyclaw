"""Built-in tools for the PyClaw agent.

Each tool is a simple callable with a JSON Schema declaration that gets
passed to the Antigravity API via the ``tools`` field in the request.

API spec format:
  "tools": [
    {
      "functionDeclarations": [
        {
          "name": "tool_name",
          "description": "...",
          "parameters": { "type": "object", "properties": {...}, "required": [...] }
        }
      ]
    }
  ]
"""

from __future__ import annotations

import asyncio
import json
import os
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Awaitable, Optional


@dataclass
class ToolDefinition:
    """Describes a tool for the API's functionDeclarations."""

    name: str
    description: str
    parameters: dict[str, Any]


@dataclass
class ToolResult:
    """Result of executing a tool."""

    name: str
    call_id: str
    result: Any
    error: Optional[str] = None


class Tool:
    """A callable tool that the AI model can invoke.

    Subclass this and implement ``execute()`` for custom tools.
    """

    def __init__(
        self,
        name: str,
        description: str,
        parameters: dict[str, Any],
    ) -> None:
        self.name = name
        self.description = description
        self.parameters = parameters
        self.requires_confirmation = False
        self.hidden = False

    def declaration(self) -> dict[str, Any]:
        """Return the function declaration dict for the API."""
        return {
            "name": self.name,
            "description": self.description,
            "parameters": self.parameters,
        }

    async def execute(self, **kwargs: Any) -> Any:
        """Execute the tool. Override in subclasses."""
        raise NotImplementedError


class ToolRegistry:
    """Registry of available tools."""

    def __init__(self) -> None:
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        """Register a tool."""
        self._tools[tool.name] = tool

    def get(self, name: str) -> Optional[Tool]:
        """Get a tool by name."""
        return self._tools.get(name)

    @property
    def tools(self) -> list[Tool]:
        return list(self._tools.values())

    def declarations(self) -> list[dict[str, Any]]:
        """Return all function declarations for the API request."""
        if not self._tools:
            return []
        return [{
            "functionDeclarations": [
                t.declaration() for t in self._tools.values()
            ]
        }]

    async def execute(self, name: str, call_id: str, args: dict[str, Any]) -> ToolResult:
        """Execute a tool by name and return the result."""
        tool = self._tools.get(name)
        if not tool:
            return ToolResult(
                name=name,
                call_id=call_id,
                result=None,
                error=f"Unknown tool: {name}",
            )
        try:
            result = await tool.execute(**args)
            return ToolResult(name=name, call_id=call_id, result=result)
        except Exception as exc:
            return ToolResult(
                name=name,
                call_id=call_id,
                result=None,
                error=str(exc),
            )


# ── Built-in Tools ──────────────────────────────────────────────────


class ReadFileTool(Tool):
    """Read the contents of a file."""

    def __init__(self) -> None:
        super().__init__(
            name="read_file",
            description="Read the contents of a file at the given path. Returns the file text content.",
            parameters={
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Absolute or relative file path to read",
                    },
                },
                "required": ["path"],
            },
        )

    async def execute(self, path: str, **_: Any) -> str:
        p = Path(path).expanduser().resolve()
        if not p.exists():
            return f"Error: file not found: {p}"
        if not p.is_file():
            return f"Error: not a file: {p}"
        try:
            text = p.read_text(errors="replace")
            if len(text) > 50000:
                return text[:50000] + f"\n\n... (truncated, {len(text)} total chars)"
            return text
        except Exception as exc:
            return f"Error reading file: {exc}"


class WriteFileTool(Tool):
    """Write content to a file."""

    def __init__(self) -> None:
        super().__init__(
            name="write_file",
            description="Write content to a file. Creates parent directories if needed. Overwrites existing content.",
            parameters={
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "File path to write to",
                    },
                    "content": {
                        "type": "string",
                        "description": "Content to write to the file",
                    },
                },
                "required": ["path", "content"],
            },
        )
        self.requires_confirmation = False

    async def execute(self, path: str, content: str, **_: Any) -> str:
        p = Path(path).expanduser().resolve()
        try:
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(content)
            return f"Wrote {len(content)} chars to {p}"
        except Exception as exc:
            return f"Error writing file: {exc}"


class ListDirectoryTool(Tool):
    """List files and directories."""

    def __init__(self) -> None:
        super().__init__(
            name="list_directory",
            description="List files and subdirectories in the given directory path.",
            parameters={
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Directory path to list. Defaults to current directory.",
                    },
                },
                "required": ["path"],
            },
        )

    async def execute(self, path: str = ".", **_: Any) -> str:
        p = Path(path).expanduser().resolve()
        if not p.exists():
            return f"Error: directory not found: {p}"
        if not p.is_dir():
            return f"Error: not a directory: {p}"
        try:
            entries = sorted(p.iterdir(), key=lambda x: (not x.is_dir(), x.name.lower()))
            lines: list[str] = []
            for entry in entries[:200]:
                prefix = "📁 " if entry.is_dir() else "📄 "
                size = ""
                if entry.is_file():
                    s = entry.stat().st_size
                    size = f" ({s:,} bytes)"
                lines.append(f"{prefix}{entry.name}{size}")
            result = "\n".join(lines)
            if len(entries) > 200:
                result += f"\n... and {len(entries) - 200} more entries"
            return result
        except Exception as exc:
            return f"Error listing directory: {exc}"


class RunCommandTool(Tool):
    """Execute a shell command."""

    def __init__(self) -> None:
        super().__init__(
            name="run_command",
            description="Execute a shell command and return stdout/stderr. Use for running scripts, git, etc. Timeout: 30s.",
            parameters={
                "type": "object",
                "properties": {
                    "command": {
                        "type": "string",
                        "description": "The shell command to run",
                    },
                    "cwd": {
                        "type": "string",
                        "description": "Working directory for the command. Optional.",
                    },
                },
                "required": ["command"],
            },
        )
        self.requires_confirmation = False

    async def execute(self, command: str, cwd: str | None = None, **_: Any) -> str:
        try:
            proc = await asyncio.create_subprocess_shell(
                command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=cwd,
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=30)
            out = stdout.decode(errors="replace")
            err = stderr.decode(errors="replace")
            result = ""
            if out:
                result += f"stdout:\n{out}"
            if err:
                result += f"\nstderr:\n{err}"
            result += f"\nexit code: {proc.returncode}"
            if len(result) > 20000:
                result = result[:20000] + "\n... (truncated)"
            return result.strip()
        except asyncio.TimeoutError:
            return "Error: command timed out after 30s"
        except Exception as exc:
            return f"Error running command: {exc}"


class SearchFilesTool(Tool):
    """Search for files by name pattern."""

    def __init__(self) -> None:
        super().__init__(
            name="search_files",
            description="Search for files matching a glob pattern recursively in a directory.",
            parameters={
                "type": "object",
                "properties": {
                    "pattern": {
                        "type": "string",
                        "description": "Glob pattern to match (e.g. '*.py', '**/*.js')",
                    },
                    "directory": {
                        "type": "string",
                        "description": "Root directory to search in. Defaults to current directory.",
                    },
                },
                "required": ["pattern"],
            },
        )

    async def execute(self, pattern: str, directory: str = ".", **_: Any) -> str:
        p = Path(directory).expanduser().resolve()
        if not p.exists():
            return f"Error: directory not found: {p}"
        try:
            matches = list(p.glob(pattern))[:100]
            if not matches:
                return f"No files matching '{pattern}' in {p}"
            lines = [str(m.relative_to(p)) for m in matches]
            result = "\n".join(lines)
            return result
        except Exception as exc:
            return f"Error searching: {exc}"


class GrepTool(Tool):
    """Search for text within files."""

    def __init__(self) -> None:
        super().__init__(
            name="grep",
            description="Search for a text pattern in files. Uses grep-like search.",
            parameters={
                "type": "object",
                "properties": {
                    "pattern": {
                        "type": "string",
                        "description": "Text pattern to search for",
                    },
                    "path": {
                        "type": "string",
                        "description": "File or directory path to search in",
                    },
                    "include": {
                        "type": "string",
                        "description": "File glob to include (e.g. '*.py'). Optional.",
                    },
                },
                "required": ["pattern", "path"],
            },
        )

    async def execute(self, pattern: str, path: str, include: str | None = None, **_: Any) -> str:
        cmd = f"grep -rn --color=never"
        if include:
            cmd += f" --include='{include}'"
        cmd += f" '{pattern}' '{path}'"
        try:
            proc = await asyncio.create_subprocess_shell(
                cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=15)
            out = stdout.decode(errors="replace")
            if not out:
                return f"No matches for '{pattern}' in {path}"
            if len(out) > 20000:
                out = out[:20000] + "\n... (truncated)"
            return out.strip()
        except asyncio.TimeoutError:
            return "Error: search timed out"
        except Exception as exc:
            return f"Error: {exc}"


class SendFileTool(Tool):
    """Explicitly send a file to the user."""

    def __init__(self) -> None:
        super().__init__(
            name="send_file",
            description="Send a file to the user via the gateway. Use this ONLY when the user explicitly requests a file transfer.",
            parameters={
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "File path to send",
                    },
                },
                "required": ["path"],
            },
        )

    async def execute(self, path: str, **_: Any) -> str:
        p = Path(path).expanduser().resolve()
        if not p.exists():
            return f"Error: file not found: {p}"
        return f"File scheduled for sending: {p}"


# ── Default registry ────────────────────────────────────────────────

def create_default_registry() -> ToolRegistry:
    """Create a registry with all built-in tools."""
    registry = ToolRegistry()
    registry.register(ReadFileTool())
    registry.register(WriteFileTool())
    registry.register(SendFileTool())
    registry.register(ListDirectoryTool())
    registry.register(RunCommandTool())
    registry.register(SearchFilesTool())
    registry.register(GrepTool())
    return registry
