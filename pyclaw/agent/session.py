"""Chat session management.

Maintains an ordered list of messages and supports truncation so the
conversation fits within token limits.

Supports both text-only messages and raw parts (for tool calls/responses).
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal, Optional

import aiofiles


@dataclass(slots=True)
class Message:
    """A single chat message.

    For regular text messages, ``content`` holds the text and
    ``raw_parts`` is None.  For tool interactions (functionCall,
    functionResponse), ``raw_parts`` holds the Gemini-style parts
    list and ``content`` may be empty.
    """

    role: Literal["user", "assistant", "system"]
    content: str
    timestamp: float = field(default_factory=time.time)
    raw_parts: Optional[list[dict[str, Any]]] = None


class Session:
    """Manages a conversation's message history.

    Usage::

        session = Session()
        session.add("user", "Hello!")
        session.add("assistant", "Hi there!")
        # For tool interactions:
        session.add_raw("model", [{"functionCall": {...}}])
    """

    __slots__ = ("_messages", "_max_messages", "_session_id")

    def __init__(
        self,
        max_messages: int = 100,
        session_id: Optional[str] = None,
    ) -> None:
        self._messages: list[Message] = []
        self._max_messages = max_messages
        self._session_id = session_id or f"session-{int(time.time())}"

    @property
    def session_id(self) -> str:
        return self._session_id

    @property
    def messages(self) -> list[Message]:
        return list(self._messages)

    def add(self, role: Literal["user", "assistant", "system"], content: str) -> None:
        """Add a text message and truncate if needed."""
        self._messages.append(Message(role=role, content=content))
        self._truncate()

    def add_raw(self, role: str, parts: list[dict[str, Any]]) -> None:
        """Add a message with raw Gemini-style parts (for tool calls).

        The API role should be "model" or "user", but we store as
        "assistant" / "user" internally.
        """
        internal_role: Literal["user", "assistant", "system"]
        if role == "model":
            internal_role = "assistant"
        elif role == "user":
            internal_role = "user"
        else:
            internal_role = "assistant"

        # Extract any text content for display purposes
        text_parts = [p.get("text", "") for p in parts if "text" in p]
        content = "".join(text_parts)

        self._messages.append(Message(
            role=internal_role,
            content=content,
            raw_parts=parts,
        ))
        self._truncate()

    def add_image(
        self,
        role: Literal["user", "assistant"],
        image_data: bytes,
        mime_type: str = "image/jpeg",
        caption: str = "",
    ) -> None:
        """Add an image message with optional caption.

        Stores as Gemini-style inlineData parts so it can be sent
        directly to vision-capable models.
        """
        import base64
        b64 = base64.b64encode(image_data).decode("ascii")

        parts: list[dict[str, Any]] = [
            {
                "inlineData": {
                    "mimeType": mime_type,
                    "data": b64,
                }
            }
        ]
        if caption:
            parts.append({"text": caption})

        self._messages.append(Message(
            role=role,
            content=caption or "[image]",
            raw_parts=parts,
        ))
        self._truncate()

    def clear(self) -> None:
        """Clear all messages."""
        self._messages.clear()

    def messages_for_api(self) -> list[dict[str, str]]:
        """Return messages formatted for the AI API.

        Filters out system messages (those are injected separately).
        """
        return [
            {"role": m.role, "parts": [{"text": m.content}]}
            for m in self._messages
            if m.role in ("user", "assistant")
        ]

    # ── Persistence ─────────────────────────────────────────────────

    async def save(self, path: Path) -> None:
        """Persist the session to a JSON file."""
        data = {
            "session_id": self._session_id,
            "messages": [
                {
                    "role": m.role,
                    "content": m.content,
                    "timestamp": m.timestamp,
                    "raw_parts": m.raw_parts,
                }
                for m in self._messages
            ],
        }
        path.parent.mkdir(parents=True, exist_ok=True)
        async with aiofiles.open(path, "w") as f:
            await f.write(json.dumps(data, indent=2))

    @classmethod
    async def load(cls, path: Path) -> "Session":
        """Load a session from a JSON file."""
        async with aiofiles.open(path, "r") as f:
            data = json.loads(await f.read())

        session = cls(session_id=data.get("session_id"))
        for msg in data.get("messages", []):
            m = Message(
                role=msg["role"],
                content=msg["content"],
                timestamp=msg.get("timestamp", time.time()),
                raw_parts=msg.get("raw_parts"),
            )
            session._messages.append(m)
        return session

    # ── Internals ───────────────────────────────────────────────────

    def _truncate(self) -> None:
        """Trim old messages if we exceed the max, keeping the most recent."""
        if len(self._messages) > self._max_messages:
            trim = len(self._messages) - self._max_messages
            self._messages = self._messages[trim:]
