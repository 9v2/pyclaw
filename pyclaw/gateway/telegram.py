"""Telegram bot gateway — independent worker with tools, image analysis, and heartbeat.

Supports:
- Text messages → AI chat with tool calls
- Received photos → vision analysis (with caption support)
- AI sends photos/documents for written files
- /model, /tools, /status, /reset, /ping commands
- Heartbeat monitoring in background
"""

from __future__ import annotations

import asyncio
import io
import logging
from pathlib import Path
from typing import Dict

from tgram import TgBot, filters
from tgram.types import (
    Message,
    CallbackQuery,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    ReactionTypeEmoji,
)

from pyclaw.agent.agent import Agent
from pyclaw.agent.session import Session
from pyclaw.agent.heartbeat import Heartbeat
from pyclaw.agent.identity import wipe_identity
from pyclaw.config.config import Config
from pyclaw.config.models import get_model

logger = logging.getLogger("pyclaw.gateway")

# Supported image MIME types
_IMAGE_MIMES = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".gif": "image/gif",
    ".webp": "image/webp",
    ".bmp": "image/bmp",
}

# Greeting patterns for auto-reaction
_GREETINGS = {
    "hello",
    "hi",
    "hey",
    "hola",
    "مرحبا",
    "هلا",
    "هلاو",
    "هاي",
    "أهلا",
    "السلام",
    "سلام",
    "صباح",
    "مساء",
    "اهلا",
    "اهلين",
    "yo",
    "sup",
    "good morning",
    "good evening",
}

# Reaction emoji sets
_GREETING_EMOJIS = ["❤️", "👋", "😊"]
_COMPLETION_EMOJIS = ["👍", "✅", "❤️"]
_ERROR_EMOJIS = ["😔"]


class TelegramGateway:
    """Telegram ↔ Agent bridge with vision and tool support."""

    __slots__ = (
        "_cfg",
        "_bot",
        "_sessions",
        "_agents",
        "_allowed_users",
        "_heartbeat",
        "_running_tasks",
    )

    def __init__(self, cfg: Config, bot: TgBot) -> None:
        self._cfg = cfg
        self._bot = bot
        self._sessions: Dict[int, Session] = {}
        self._agents: Dict[int, Agent] = {}
        self._allowed_users: list[int] = cfg.get("gateway.allowed_users") or []
        self._heartbeat = Heartbeat(cfg)
        self._running_tasks: Dict[int, asyncio.Task] = {}

    @classmethod
    async def create(cls, cfg: Config) -> "TelegramGateway":
        token = cfg.get("gateway.telegram_bot_token")
        if not token:
            raise ValueError("no telegram bot token — run `pyclaw config`")
        bot = TgBot(token)
        gw = cls(cfg, bot)
        gw._register_handlers()
        return gw

    # ── Handlers ────────────────────────────────────────────────────

    def _register_handlers(self) -> None:

        @self._bot.on_message(filters.command("start") & filters.private)
        async def handle_start(bot: TgBot, message: Message) -> None:
            if not self._is_allowed(message.from_user.id):
                await message.reply_text("⚠️ unauthorized.")
                return
            from pyclaw.agent.identity import SOUL_PATH

            if SOUL_PATH.exists():
                name = SOUL_PATH.read_text().split("\n")[0].strip("# ").strip()
            else:
                name = "Claw 🦞"
            await message.reply_text(
                f"*{name}* is ready.\n\n"
                "send me a message or a photo and i'll respond.\n\n"
                "commands:\n"
                "/new — new conversation (clears history)\n"
                "/stop — stop running task\n"
                "/reset — factory reset (wipes identity)\n"
                "/model — show/switch model\n"
                "/tools — list available tools\n"
                "/ping — health check\n"
                "/status — heartbeat status",
                parse_mode="Markdown",
            )

        @self._bot.on_message(filters.command("new") & filters.private)
        async def handle_new(bot: TgBot, message: Message) -> None:
            if not self._is_allowed(message.from_user.id):
                return
            uid = message.from_user.id
            if uid in self._sessions:
                self._sessions[uid].clear()
            await message.reply_text("🗑 session history cleared.")

        @self._bot.on_message(filters.command("stop") & filters.private)
        async def handle_stop(bot: TgBot, message: Message) -> None:
            if not self._is_allowed(message.from_user.id):
                return
            uid = message.from_user.id
            agent = self._agents.get(uid)
            if agent:
                agent.cancel()
            task = self._running_tasks.get(uid)
            if task and not task.done():
                task.cancel()
                await message.reply_text("⛔ stopped.")
            else:
                await message.reply_text("nothing running.")

        @self._bot.on_message(filters.command("reset") & filters.private)
        async def handle_reset(bot: TgBot, message: Message) -> None:
            if not self._is_allowed(message.from_user.id):
                return

            keyboard = InlineKeyboardMarkup(
                [
                    [
                        InlineKeyboardButton(
                            "Yes, Wipe Everything", callback_data="confirm_wipe"
                        ),
                        InlineKeyboardButton("Cancel", callback_data="cancel_wipe"),
                    ]
                ]
            )
            await message.reply_text(
                "⚠️ **Factory Reset Warning**\n\n"
                "This will permanently delete:\n"
                "• `SOUL.md` (Identity)\n"
                "• `USER.md` (Learned preferences)\n"
                "• `MEMORY.md` (Long-term memory)\n\n"
                "Are you sure?",
                reply_markup=keyboard,
                parse_mode="Markdown",
            )

        @self._bot.on_callback_query(filters.regex("^(confirm_wipe|cancel_wipe)$"))
        async def handle_wipe_callback(bot: TgBot, query: CallbackQuery) -> None:
            if not self._is_allowed(query.from_user.id):
                return

            if query.data == "confirm_wipe":
                wipe_identity()
                uid = query.from_user.id
                if uid in self._sessions:
                    self._sessions[uid].clear()
                if uid in self._agents:
                    del self._agents[uid]

                await query.message.edit_text(
                    "💥 **Factory Reset Complete**.\n\nI am a blank slate. Send /start to reboot me.",
                    parse_mode="Markdown",
                )
            else:
                await query.message.edit_text("❌ Reset cancelled.")

        @self._bot.on_message(filters.command("model") & filters.private)
        async def handle_model(bot: TgBot, message: Message) -> None:
            if not self._is_allowed(message.from_user.id):
                return

            parts = message.text.split()
            if len(parts) > 1:
                new_model_id = parts[1].strip()

                # Check if variant provided
                variant = parts[2].strip() if len(parts) > 2 else ""

                # Validation & defaulting
                model_def = get_model(new_model_id)
                if model_def:
                    if not variant and model_def.variants:
                        variant = model_def.default_variant or model_def.variants[0]
                    elif variant and variant not in model_def.variants:
                        await message.reply_text(
                            f"⚠️ unknown variant `{variant}`. available: {', '.join(model_def.variants)}"
                        )
                        return

                    if not model_def.variants:
                        variant = ""

                # Update config
                self._cfg.set("agent.model", new_model_id)
                self._cfg.set("agent.model_variant", variant)
                await self._cfg.save()

                # Update active agent
                uid = message.from_user.id
                if uid in self._agents:
                    self._agents[uid].model_id = new_model_id
                    self._agents[uid].model_variant = variant

                msg = f"✅ model → `{new_model_id}`"
                if variant:
                    msg += f" ({variant})"
                await message.reply_text(msg, parse_mode="Markdown")
            else:
                model = self._cfg.get("agent.model", "unknown")
                variant = self._cfg.get("agent.model_variant", "")
                msg = f"🤖 model: `{model}`"
                if variant:
                    msg += f" ({variant})"
                await message.reply_text(msg, parse_mode="Markdown")

        @self._bot.on_message(filters.command("tools") & filters.private)
        async def handle_tools(bot: TgBot, message: Message) -> None:
            if not self._is_allowed(message.from_user.id):
                return
            agent = await self._get_or_create_agent(message.from_user.id)
            lines = [f"• `{t.name}` — {t.description[:60]}" for t in agent.tools.tools]
            await message.reply_text(
                "🔧 *tools:*\n" + "\n".join(lines),
                parse_mode="Markdown",
            )

        @self._bot.on_message(filters.command("ping") & filters.private)
        async def handle_ping(bot: TgBot, message: Message) -> None:
            await message.reply_text("🏓 pong!")

        @self._bot.on_message(filters.command("status") & filters.private)
        async def handle_status(bot: TgBot, message: Message) -> None:
            if not self._is_allowed(message.from_user.id):
                return
            status = await self._heartbeat.check()
            ok = "✅" if status["ok"] else "⚠️"
            lines = [f"{ok} *heartbeat*"]
            for k, v in status["checks"].items():
                lines.append(f"• {k}: `{v}`")
            await message.reply_text("\n".join(lines), parse_mode="Markdown")

        # ── Photo handler ───────────────────────────────────────────

        @self._bot.on_message(filters.photo & filters.private)
        async def handle_photo(bot: TgBot, message: Message) -> None:
            uid = message.from_user.id
            if not self._is_allowed(uid):
                await message.reply_text("⚠️ unauthorized.")
                return

            agent = await self._get_or_create_agent(uid)
            typing_task = asyncio.create_task(self._typing_loop(message.chat.id))

            try:
                # Get the highest resolution photo
                photo = message.photo[-1] if message.photo else None
                if not photo:
                    await message.reply_text("⚠️ couldn't process photo.")
                    return

                try:
                    # Download photo
                    downloaded_file = await bot.download_file(
                        photo.file_id, in_memory=True
                    )
                    photo_bytes = downloaded_file.getvalue()

                    # Get caption
                    caption = message.caption or ""
                    if not caption:
                        caption = (
                            "What do you see in this image? Describe it and analyze it."
                        )

                    # Send to agent for vision analysis
                    events = await agent.chat_with_image(
                        image_data=photo_bytes,
                        mime_type="image/jpeg",
                        caption=caption,
                    )

                    text_chunks: list[str] = []
                    tool_lines: list[str] = []
                    files_to_send: set[str] = set()

                    async for event in events:
                        etype = event["type"]
                        if etype == "text":
                            text_chunks.append(event["text"])
                        elif etype == "tool_call":
                            if event["name"] in ("write_file", "send_file"):
                                path = event.get("args", {}).get("path")
                                if path:
                                    files_to_send.add(path)

                        elif etype == "error":
                            text_chunks.append(f"\n⚠️ {event['message']}")

                    # Send response
                    full = "".join(text_chunks)
                    if full.strip():
                        for chunk in self._split_message(full):
                            try:
                                await message.reply_text(chunk, parse_mode="Markdown")
                            except Exception:
                                await message.reply_text(chunk)

                    # Send written files
                    for fpath in files_to_send:
                        await self._send_file(message.chat.id, fpath)

                except Exception as exc:
                    logger.exception("photo handling error for user %d", uid)
                    await message.reply_text(f"⚠️ error processing photo: {exc}")

            finally:
                typing_task.cancel()

        # ── Text handler ────────────────────────────────────────────

        @self._bot.on_message(filters.text & filters.private)
        async def handle_text(bot: TgBot, message: Message) -> None:
            uid = message.from_user.id
            if not self._is_allowed(uid):
                await message.reply_text("⚠️ unauthorized.")
                return

            agent = await self._get_or_create_agent(uid)
            self._register_reaction_tool(agent, message.chat.id, message.id)
            typing_task = asyncio.create_task(self._typing_loop(message.chat.id))

            # Auto-react on greeting
            reaction_mode = self._cfg.get("gateway.reaction_mode")
            if reaction_mode:
                text_lower = message.text.strip().lower()
                is_greeting = any(g in text_lower for g in _GREETINGS)
                if is_greeting or reaction_mode == "massive":
                    import random

                    emoji = random.choice(
                        _GREETING_EMOJIS if is_greeting else ["👀", "⚡", "🔥"]
                    )
                    await self._react(message.chat.id, message.id, emoji)

            # Track this as the running task for /stop
            current_task = asyncio.current_task()
            if current_task:
                self._running_tasks[uid] = current_task

            text_chunks: list[str] = []
            tool_lines: list[str] = []
            files_to_send: set[str] = set()

            try:
                try:
                    async for event in agent.chat(message.text):
                        etype = event["type"]

                        if etype == "text":
                            text_chunks.append(event["text"])

                        elif etype == "tool_call":
                            if event["name"] in ("write_file", "send_file"):
                                path = event.get("args", {}).get("path")
                                if path:
                                    files_to_send.add(path)

                        elif etype == "error":
                            text_chunks.append(f"\n⚠️ {event['message']}")

                except Exception as exc:
                    logger.exception("agent error for user %d", uid)
                    text_chunks.append(f"⚠️ error: {exc}")

                if tool_lines:
                    for chunk in self._split_message("\n".join(tool_lines)):
                        await message.reply_text(chunk, parse_mode="Markdown")

                full = "".join(text_chunks)
                if full.strip():
                    for chunk in self._split_message(full):
                        try:
                            await message.reply_text(chunk, parse_mode="Markdown")
                        except Exception:
                            await message.reply_text(chunk)

                for fpath in files_to_send:
                    await self._send_file(message.chat.id, fpath)

                # Auto-react on completion
                if reaction_mode in ("minimal", "massive") and full.strip():
                    import random

                    await self._react(
                        message.chat.id, message.id, random.choice(_COMPLETION_EMOJIS)
                    )

            finally:
                typing_task.cancel()
                self._running_tasks.pop(uid, None)

    # ── Reactions ─────────────────────────────────────────────────────

    async def _react(self, chat_id: int, message_id: int, emoji: str) -> None:
        """Silently react to a message with an emoji."""
        try:
            await self._bot.set_message_reaction(
                chat_id=chat_id,
                message_id=message_id,
                reaction=[ReactionTypeEmoji(emoji=emoji)],
            )
        except Exception as exc:
            logger.debug("reaction failed: %s", exc)

    def _register_reaction_tool(
        self, agent: Agent, chat_id: int, message_id: int
    ) -> None:
        """Register a send_reaction tool on the agent bound to the current message."""
        from pyclaw.agent.tools import Tool

        gateway = self

        class SendReactionTool(Tool):
            def __init__(self):
                super().__init__(
                    name="send_reaction",
                    description="React to the user's message with an emoji.",
                    parameters={
                        "type": "object",
                        "properties": {
                            "emoji": {
                                "type": "string",
                                "description": "Emoji to react with (e.g. ❤️, 👍, 🔥, 😊, ⚡, 👋)",
                            },
                        },
                        "required": ["emoji"],
                    },
                )
                self.hidden = True

            async def execute(self, emoji: str = "👍", **_) -> str:
                await gateway._react(chat_id, message_id, emoji)
                return f"Reacted with {emoji}"

        # register() overwrites by name in _tools dict
        agent.tools.register(SendReactionTool())

    async def _send_file(self, chat_id: int, file_path: str) -> None:
        """Send a file as a Telegram document or photo."""
        p = Path(file_path).expanduser().resolve()
        if not p.exists() or not p.is_file():
            return

        try:
            ext = p.suffix.lower()
            file_buf = io.BytesIO(p.read_bytes())
            file_buf.name = p.name

            if ext in _IMAGE_MIMES:
                await self._bot.send_photo(
                    chat_id,
                    photo=file_buf,
                    caption=f"📷 {p.name}",
                )
            else:
                await self._bot.send_document(
                    chat_id,
                    document=file_buf,
                    caption=f"📄 {p.name}",
                )
        except Exception as exc:
            logger.error("failed to send file %s: %s", p, exc)

    # ── Session management ──────────────────────────────────────────

    async def _get_or_create_agent(self, uid: int) -> Agent:
        if uid not in self._agents:
            session = Session(session_id=f"tg-{uid}")
            self._sessions[uid] = session
            self._agents[uid] = await Agent.create(self._cfg, session)
        return self._agents[uid]

    def _is_allowed(self, uid: int) -> bool:
        if not self._allowed_users:
            return True
        return uid in self._allowed_users

    async def _typing_loop(self, chat_id: int) -> None:
        """Keep sending 'typing' action until cancelled."""
        try:
            while True:
                await self._bot.send_chat_action(chat_id, "typing")
                await asyncio.sleep(4.5)
        except asyncio.CancelledError:
            pass
        except Exception:
            pass

    @staticmethod
    def _split_message(text: str, max_len: int = 4000) -> list[str]:
        if len(text) <= max_len:
            return [text]
        chunks: list[str] = []
        while text:
            if len(text) <= max_len:
                chunks.append(text)
                break
            split_at = text.rfind("\n", 0, max_len)
            if split_at == -1:
                split_at = max_len
            chunks.append(text[:split_at])
            text = text[split_at:].lstrip("\n")
        return chunks

    # ── Run ─────────────────────────────────────────────────────────

    async def run(self) -> None:
        """Start polling + heartbeat. Retries on network failures."""
        logger.info("telegram gateway starting…")
        heartbeat_task = asyncio.create_task(self._heartbeat.start())

        delay = 2
        max_delay = 60

        try:
            while True:
                try:
                    await self._bot.run()
                    break  # clean exit
                except (
                    ConnectionError,
                    OSError,
                    TimeoutError,
                    asyncio.TimeoutError,
                ) as exc:
                    logger.warning(
                        "connection lost (%s), retrying in %ds…",
                        exc,
                        delay,
                    )
                    await asyncio.sleep(delay)
                    delay = min(delay * 2, max_delay)
                except Exception as exc:
                    logger.error(
                        "unexpected error (%s: %s), retrying in %ds…",
                        type(exc).__name__,
                        exc,
                        delay,
                    )
                    await asyncio.sleep(delay)
                    delay = min(delay * 2, max_delay)
        finally:
            self._heartbeat.stop()
            heartbeat_task.cancel()
