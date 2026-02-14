"""Core agent — orchestrates AI model, tools, personality, and sessions.

Uses the Provider abstraction for multi-backend support (Antigravity,
OpenAI, Anthropic, Custom).  Supports tool/function calling with an
automatic execute → respond loop, personality system, and safety
confirmations.
"""

from __future__ import annotations

from typing import Any, AsyncIterator, Callable, Awaitable, Optional

from pyclaw.agent.session import Session
from pyclaw.agent.providers import Provider
from pyclaw.agent.tools import (
    ToolRegistry,
    create_default_registry,
)

# from pyclaw.agent.identity import (
#     build_system_prompt, is_first_boot, FIRST_BOOT_SYSTEM, TOOLS_PATH,
# )
from pyclaw.config.config import Config
from pyclaw.skills.loader import SkillsManager


# Max rounds of tool calls before forcing a final answer
MAX_TOOL_ROUNDS = 15

# Safe commands that don"t need confirmation (read-only)
SAFE_COMMANDS = (
    "ls",
    "cat",
    "grep",
    "find",
    "pwd",
    "echo",
    "print",
    "printf",
    "whoami",
    "date",
    "uptime",
    "df",
    "du",
    "free",
    "top",
    "ps",
    "head",
    "tail",
    "wc",
    "sort",
    "uniq",
    "awk",
    "sed",
    "git status",
    "git log",
    "git diff",
    "git show",
    "stat",
    "file",
    "readlink",
    "whereis",
    "which",
)


class Agent:
    """Async AI agent with streaming, tools, and personality.

    Usage::

        agent = await Agent.create(cfg)
        async for event in agent.chat("Hello!"):
            if event["type"] == "text":
                print(event["text"], end="", flush=True)
    """

    __slots__ = (
        "_cfg",
        "_session",
        "_skills",
        "_model_id",
        "_model_variant",
        "_tools",
        "_provider",
        "_confirm_callback",
        "_cancelled",
    )

    def __init__(
        self,
        cfg: Config,
        session: Optional[Session] = None,
        tools: Optional[ToolRegistry] = None,
        provider: Optional[Provider] = None,
    ) -> None:
        self._cfg = cfg
        self._session = session or Session()
        self._skills: Optional[SkillsManager] = None
        self._model_id: str = cfg.get("agent.model", "gemini-2.5-flash")
        self._model_variant: str = cfg.get("agent.model_variant", "")
        self._tools = tools or self._create_full_registry(cfg, self._session)
        self._generate_tools_md()
        self._provider = provider or Provider.from_config(cfg)
        self._confirm_callback: Optional[Callable[[str, dict], Awaitable[bool]]] = None
        self._cancelled = False

    # ── Factory ─────────────────────────────────────────────────────

    @classmethod
    async def create(
        cls,
        cfg: Config,
        session: Optional[Session] = None,
    ) -> "Agent":
        """Create an agent, loading skills from the workspace."""
        agent = cls(cfg, session)
        workspace = Config.workspace_path(cfg.data)
        agent._skills = SkillsManager(workspace)
        await agent._skills.load()
        return agent

    @staticmethod
    def _create_full_registry(cfg: Config, session: Session) -> ToolRegistry:
        """Create tool registry with all available tools."""
        registry = create_default_registry()

        # Config tools
        # Config tools
        from pyclaw.agent.config_tool import (
            GetConfigTool,
            SetConfigTool,
            ChangeModelTool,
            BackupConfigTool,
        )

        for ToolCls in (
            GetConfigTool,
            SetConfigTool,
            ChangeModelTool,
            BackupConfigTool,
        ):
            tool = ToolCls()
            tool.bind(cfg)
            registry.register(tool)

        # Identity tools (OpenClaw Port)
        from pyclaw.agent.identity_tools import (
            UpdateIdentityTool,
            ReadIdentityTool,
        )

        registry.register(UpdateIdentityTool())
        registry.register(ReadIdentityTool())

        # Cron tools
        from pyclaw.agent.cron import (
            ListCronJobsTool,
            AddCronJobTool,
            RemoveCronJobTool,
            CronManager,
        )

        cron = CronManager(cfg)
        cron.load_jobs()
        for ToolCls in (ListCronJobsTool, AddCronJobTool, RemoveCronJobTool):
            tool = ToolCls()
            tool.bind(cron)
            registry.register(tool)

        # Search tools (only if provider is configured)
        search_provider = cfg.get("search.provider")
        if search_provider:
            from pyclaw.agent.search import WebSearchTool

            if search_provider == "brave":
                api_key = cfg.get("search.brave_api_key", "")
                if api_key:
                    registry.register(WebSearchTool("brave", api_key))
            elif search_provider == "perplexity":
                api_key = cfg.get("search.perplexity_api_key", "")
                if api_key:
                    registry.register(WebSearchTool("perplexity", api_key))

        # Webpage reader (always available)
        try:
            from pyclaw.agent.search import ReadWebpageTool

            registry.register(ReadWebpageTool())
        except ImportError:
            pass

        return registry

    # ── Properties ──────────────────────────────────────────────────

    @property
    def session(self) -> Session:
        return self._session

    @property
    def model_id(self) -> str:
        return self._model_id

    @model_id.setter
    def model_id(self, value: str) -> None:
        self._model_id = value

    @property
    def model_variant(self) -> str:
        return self._model_variant

    @model_variant.setter
    def model_variant(self, value: str) -> None:
        self._model_variant = value

    @property
    def tools(self) -> ToolRegistry:
        return self._tools

    @property
    def provider(self) -> Provider:
        return self._provider

    @property
    def cfg(self) -> Config:
        return self._cfg

    def set_confirm_callback(self, cb: Callable[[str, dict], Awaitable[bool]]) -> None:
        """Set the confirmation callback for destructive actions."""
        self._confirm_callback = cb

    def is_first_boot(self) -> bool:
        """Check if this is the first boot (no SOUL.md yet)."""
        from pyclaw.agent.identity import is_first_boot

        return is_first_boot()

    def cancel(self) -> None:
        """Cancel the current operation."""
        self._cancelled = True

    @property
    def is_cancelled(self) -> bool:
        return self._cancelled

    # ── Chat with image ─────────────────────────────────────────────

    async def chat_with_image(
        self,
        image_data: bytes,
        mime_type: str = "image/jpeg",
        caption: str = "",
    ) -> "AsyncIterator[dict[str, Any]]":
        """Send an image (with optional caption) and stream events."""
        self._session.add_image("user", image_data, mime_type, caption)

        prompt = caption or "What do you see in this image?"
        # We need to go through chat() but the image is already in session
        # So we do the generation directly without re-adding
        return self._chat_from_session()

    async def _chat_from_session(self) -> "AsyncIterator[dict[str, Any]]":
        """Run the generation loop from current session state (no new message added)."""
        tool_declarations = self._tools.declarations() if self._tools.tools else None
        full_text: list[str] = []
        self._cancelled = False

        for round_num in range(MAX_TOOL_ROUNDS):
            if self._cancelled:
                yield {"type": "text", "text": "⛔ stopped."}
                break

            contents = self._build_contents()
            text_chunks: list[str] = []
            function_calls: list[dict[str, Any]] = []

            model_id = self._model_id
            if self._model_variant:
                model_id = f"{model_id}-{self._model_variant}"

            async for candidate in self._provider.stream(
                model=model_id,
                contents=contents,
                system_instruction=await self._build_system_prompt(),
                temperature=self._cfg.get("agent.temperature", 0.7),
                max_output_tokens=self._cfg.get("agent.max_tokens", 1000),
                tools=tool_declarations,
            ):
                if self._cancelled:
                    break
                if "error" in candidate:
                    yield {"type": "error", "message": candidate["error"]}
                    return

                content = candidate.get("content", {})
                parts = content.get("parts", [])

                for part in parts:
                    if "text" in part and not part.get("thought"):
                        text = part["text"]
                        text_chunks.append(text)
                    elif "functionCall" in part:
                        function_calls.append(part["functionCall"])

            if self._cancelled:
                yield {"type": "text", "text": "⛔ stopped."}
                break

            # Only yield text on the final round (no more tool calls)
            if not function_calls:
                for t in text_chunks:
                    full_text.append(t)
                    yield {"type": "text", "text": t}
                break

            model_parts: list[dict[str, Any]] = []
            if text_chunks:
                model_parts.append({"text": "".join(text_chunks)})
            for fc in function_calls:
                model_parts.append({"functionCall": fc})
            self._session.add_raw("model", model_parts)

            tool_response_parts: list[dict[str, Any]] = []
            for fc in function_calls:
                name = fc.get("name", "unknown")
                args = fc.get("args", {})
                call_id = fc.get("id", "")

                tool = self._tools.get(name)
                needs_confirm = getattr(tool, "requires_confirmation", False)

                if needs_confirm and self._cfg.get("safety.confirm_destructive", True):
                    if name == "run_command":
                        cmd = args.get("command", "").strip()

                        blocked = self._cfg.get("safety.blocked_patterns", [])
                        for pattern in blocked:
                            if pattern in cmd:
                                yield {
                                    "type": "tool_result",
                                    "name": name,
                                    "result": None,
                                    "error": f"Blocked: '{pattern}'",
                                }
                                tool_response_parts.append(
                                    {
                                        "functionResponse": {
                                            "name": name,
                                            "id": call_id,
                                            "response": {
                                                "error": f"Blocked: '{pattern}'"
                                            },
                                        }
                                    }
                                )
                                continue

                        is_safe = False
                        for safe_cmd in SAFE_COMMANDS:
                            if cmd == safe_cmd or cmd.startswith(safe_cmd + " "):
                                is_safe = True
                                break
                        if is_safe:
                            needs_confirm = False

                if needs_confirm and self._cfg.get("safety.confirm_destructive", True):
                    yield {"type": "confirm", "name": name, "args": args, "id": call_id}
                    if self._confirm_callback:
                        confirmed = await self._confirm_callback(name, args)
                        if not confirmed:
                            tool_response_parts.append(
                                {
                                    "functionResponse": {
                                        "name": name,
                                        "id": call_id,
                                        "response": {"error": "User denied"},
                                    }
                                }
                            )
                            yield {
                                "type": "tool_result",
                                "name": name,
                                "result": None,
                                "error": "User denied",
                            }
                            continue

                yield {"type": "tool_call", "name": name, "args": args, "id": call_id}
                result = await self._tools.execute(name, call_id, args)
                yield {
                    "type": "tool_result",
                    "name": name,
                    "result": str(result.result) if result.result else None,
                    "error": result.error,
                }

                response_data = (
                    {"error": result.error}
                    if result.error
                    else {"result": result.result}
                )
                tool_response_parts.append(
                    {
                        "functionResponse": {
                            "name": name,
                            "id": call_id,
                            "response": response_data,
                        }
                    }
                )

            self._session.add_raw("user", tool_response_parts)
            text_chunks = []

        final_text = "".join(full_text)
        if final_text:
            self._session.add("assistant", final_text)
        yield {"type": "done"}

    # ── Chat (simple text-only, backward compat) ────────────────────

    async def chat_text(self, message: str) -> AsyncIterator[str]:
        """Stream back text only (no tool events)."""
        async for event in self.chat(message):
            if event["type"] == "text":
                yield event["text"]

    async def chat_complete(self, message: str) -> str:
        """Send a message and return full response text."""
        chunks: list[str] = []
        async for event in self.chat(message):
            if event["type"] == "text":
                chunks.append(event["text"])
        return "".join(chunks)

    # ── Chat (full event stream) ────────────────────────────────────

    async def chat(self, message: str) -> AsyncIterator[dict[str, Any]]:
        """Send a user message and stream back events.

        Event types:
          - {"type": "text", "text": "..."}
          - {"type": "tool_call", "name": ..., "args": ..., "id": ...}
          - {"type": "tool_result", "name": ..., "result": ..., "error": ...}
          - {"type": "confirm", "name": ..., "args": ..., "id": ...}
          - {"type": "error", "message": ...}
          - {"type": "done"}
        """
        self._session.add("user", message)

        tool_declarations = self._tools.declarations() if self._tools.tools else None
        full_text: list[str] = []
        self._cancelled = False

        for round_num in range(MAX_TOOL_ROUNDS):
            if self._cancelled:
                yield {"type": "text", "text": "⛔ stopped."}
                break

            contents = self._build_contents()

            text_chunks: list[str] = []
            function_calls: list[dict[str, Any]] = []

            model_id = self._model_id
            if self._model_variant:
                model_id = f"{model_id}-{self._model_variant}"

            async for candidate in self._provider.stream(
                model=model_id,
                contents=contents,
                system_instruction=await self._build_system_prompt(),
                temperature=self._cfg.get("agent.temperature", 0.7),
                max_output_tokens=self._cfg.get("agent.max_tokens", 1000),
                tools=tool_declarations,
            ):
                if self._cancelled:
                    break
                if "error" in candidate:
                    yield {"type": "error", "message": candidate["error"]}
                    return

                content = candidate.get("content", {})
                parts = content.get("parts", [])

                for part in parts:
                    if "text" in part and not part.get("thought"):
                        text = part["text"]
                        text_chunks.append(text)
                    elif "functionCall" in part:
                        function_calls.append(part["functionCall"])

            if self._cancelled:
                yield {"type": "text", "text": "⛔ stopped."}
                break

            # Only yield text on the final round (no more tool calls)
            if not function_calls:
                for t in text_chunks:
                    full_text.append(t)
                    yield {"type": "text", "text": t}
                break

            # Add model response with function calls
            model_parts: list[dict[str, Any]] = []
            if text_chunks:
                model_parts.append({"text": "".join(text_chunks)})
            for fc in function_calls:
                model_parts.append({"functionCall": fc})
            self._session.add_raw("model", model_parts)

            # Execute each function call
            tool_response_parts: list[dict[str, Any]] = []
            for fc in function_calls:
                name = fc.get("name", "unknown")
                args = fc.get("args", {})
                call_id = fc.get("id", "")

                # Safety check
                tool = self._tools.get(name)
                needs_confirm = getattr(tool, "requires_confirmation", False)

                if needs_confirm and self._cfg.get("safety.confirm_destructive", True):
                    # Check for blocked patterns
                    if name == "run_command":
                        cmd = args.get("command", "").strip()

                        # Check blocked patterns
                        blocked = self._cfg.get("safety.blocked_patterns", [])
                        for pattern in blocked:
                            if pattern in cmd:
                                yield {
                                    "type": "tool_result",
                                    "name": name,
                                    "result": None,
                                    "error": f"Blocked: command contains '{pattern}'",
                                }
                                tool_response_parts.append(
                                    {
                                        "functionResponse": {
                                            "name": name,
                                            "id": call_id,
                                            "response": {
                                                "error": f"Blocked: '{pattern}'"
                                            },
                                        }
                                    }
                                )
                                continue

                        # Check if command is safe (starts with whitelisted prefix)
                        is_safe = False
                        for safe_cmd in SAFE_COMMANDS:
                            if cmd == safe_cmd or cmd.startswith(safe_cmd + " "):
                                is_safe = True
                                break

                        if is_safe:
                            needs_confirm = False

                if needs_confirm and self._cfg.get("safety.confirm_destructive", True):
                    # Ask for confirmation
                    yield {
                        "type": "confirm",
                        "name": name,
                        "args": args,
                        "id": call_id,
                    }

                    # Check confirmation callback
                    if self._confirm_callback:
                        confirmed = await self._confirm_callback(name, args)
                        if not confirmed:
                            tool_response_parts.append(
                                {
                                    "functionResponse": {
                                        "name": name,
                                        "id": call_id,
                                        "response": {"error": "User denied the action"},
                                    }
                                }
                            )
                            yield {
                                "type": "tool_result",
                                "name": name,
                                "result": None,
                                "error": "User denied",
                            }
                            continue

                yield {
                    "type": "tool_call",
                    "name": name,
                    "args": args,
                    "id": call_id,
                }

                result = await self._tools.execute(name, call_id, args)

                yield {
                    "type": "tool_result",
                    "name": name,
                    "result": str(result.result) if result.result else None,
                    "error": result.error,
                }

                response_data = {}
                if result.error:
                    response_data["error"] = result.error
                else:
                    response_data["result"] = result.result

                tool_response_parts.append(
                    {
                        "functionResponse": {
                            "name": name,
                            "id": call_id,
                            "response": response_data,
                        }
                    }
                )

            self._session.add_raw("user", tool_response_parts)
            text_chunks = []

        final_text = "".join(full_text)
        if final_text:
            self._session.add("assistant", final_text)

        yield {"type": "done"}

    # ── System prompt ───────────────────────────────────────────────

    async def _build_system_prompt(self) -> str:
        """Build system prompt from personality.md + skills.

        On first boot, uses the special FIRST_BOOT_SYSTEM prompt
        that instructs the AI to generate its own personality.
        """
        from pyclaw.agent.identity import FIRST_BOOT_SYSTEM, build_system_prompt

        if self.is_first_boot():
            base = FIRST_BOOT_SYSTEM
        else:
            base = await build_system_prompt(self._cfg)

        if self._skills:
            skills_block = self._skills.as_prompt()

        parts = [base]
        if skills_block:
            parts.append(skills_block)

        # Tools are now documented in TOOLS.md which is included by build_system_prompt
        # But we still want the specific "Available tools" list for quick reference?
        # build_system_prompt in identity.py includes TOOLS.md content.
        # But we also have "Use them proactively..." instruction.

        if self._tools.tools:
            tool_names = [t.name for t in self._tools.tools]
            parts.append(
                f"Active Tools: {', '.join(tool_names)}.\n"
                "Use them proactively when asked. "
                "Use read_file, grep, list_directory to understand code. "
                "Use run_command for shell operations. "
                "Use get_config/set_config to manage your settings. "
                "Use update_identity to evolve your soul, remember things about the human, or update workspace rules. "
                "IMPORTANT: If you lack a specific tool for a task (e.g., 'take a screenshot', 'check weather'), "
                "do NOT refuse. Instead, try to use `run_command` with standard Linux utilities "
                "(e.g., `scrot`, `curl`, `date`) or use `search` to find the right command."
            )

        return "\n\n".join(parts)

    def _generate_tools_md(self) -> None:
        """Generate TOOLS.md from registered tools."""
        content = "# Available Tools (TOOLS.md)\n\n"
        content += "This file lists the tools currently available to the AI agent.\n\n"

        for tool in sorted(self._tools.tools, key=lambda t: t.name):
            content += f"## `{tool.name}`\n"
            content += f"{tool.description}\n\n"

            # Add parameters schema simplified
            params = tool.parameters.get("properties", {})
            if params:
                content += "### Parameters\n"
                for name, details in params.items():
                    req = (
                        " (required)"
                        if name in tool.parameters.get("required", [])
                        else ""
                    )
                    desc = details.get("description", "")
                    content += f"- **{name}**{req}: {desc}\n"
            content += "\n---\n\n"

        try:
            from pyclaw.agent.identity import TOOLS_PATH

            TOOLS_PATH.parent.mkdir(parents=True, exist_ok=True)
            TOOLS_PATH.write_text(content)
        except Exception:
            pass  # Non-fatal if we can't write docs

    # ── Build contents ──────────────────────────────────────────────

    def _build_contents(self) -> list[dict[str, Any]]:
        """Convert session messages to Gemini-style content dicts."""
        contents: list[dict[str, Any]] = []
        for msg in self._session.messages:
            if msg.role == "system":
                continue
            role = "user" if msg.role == "user" else "model"

            if msg.raw_parts:
                contents.append({"role": role, "parts": msg.raw_parts})
            else:
                contents.append(
                    {
                        "role": role,
                        "parts": [{"text": msg.content}],
                    }
                )
        return contents
