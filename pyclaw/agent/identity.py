"""Identity and memory system (SOUL.md, USER.md, MEMORY.md).

Manages the AI's persistent identity and context files.
Replaces the old personality.py system.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

import aiofiles

from pyclaw.config.config import Config

# Default paths
_PYCLAW_DIR = Path.home() / ".pyclaw"
SOUL_PATH = _PYCLAW_DIR / "SOUL.md"
USER_PATH = _PYCLAW_DIR / "USER.md"
MEMORY_PATH = _PYCLAW_DIR / "MEMORY.md"
TOOLS_PATH = _PYCLAW_DIR / "TOOLS.md"
IDENTITY_PATH = _PYCLAW_DIR / "IDENTITY.md"
AGENTS_PATH = _PYCLAW_DIR / "AGENTS.md"
BOOT_PATH = _PYCLAW_DIR / "BOOT.md"
BOOTSTRAP_PATH = _PYCLAW_DIR / "BOOTSTRAP.md"
HEARTBEAT_PATH = _PYCLAW_DIR / "HEARTBEAT.md"

# Legacy path for migration
_LEGACY_PERSONALITY_PATH = _PYCLAW_DIR / "personality.md"


def ensure_identity_files() -> None:
    """Ensure identity files exist, migrating legacy ones if needed."""
    _PYCLAW_DIR.mkdir(parents=True, exist_ok=True)

    # Migration: personality.md -> SOUL.md
    if _LEGACY_PERSONALITY_PATH.exists() and not SOUL_PATH.exists():
        _LEGACY_PERSONALITY_PATH.rename(SOUL_PATH)

    # Initialize standard files if missing
    templates = {
        SOUL_PATH: _TEMPLATE_SOUL,
        USER_PATH: _TEMPLATE_USER,
        MEMORY_PATH: "# MEMORY.md\n\nNo long-term memories yet.\n",
        IDENTITY_PATH: _TEMPLATE_IDENTITY,
        AGENTS_PATH: _TEMPLATE_AGENTS,
        BOOT_PATH: _TEMPLATE_BOOT,
        BOOTSTRAP_PATH: _TEMPLATE_BOOTSTRAP,
        HEARTBEAT_PATH: _TEMPLATE_HEARTBEAT,
        TOOLS_PATH: _TEMPLATE_TOOLS,
        # Dev templates
        _PYCLAW_DIR / "SOUL.dev.md": _TEMPLATE_SOUL_DEV,
        _PYCLAW_DIR / "USER.dev.md": _TEMPLATE_USER_DEV,
        _PYCLAW_DIR / "IDENTITY.dev.md": _TEMPLATE_IDENTITY_DEV,
        _PYCLAW_DIR / "AGENTS.dev.md": _TEMPLATE_AGENTS_DEV,
        _PYCLAW_DIR / "TOOLS.dev.md": _TEMPLATE_TOOLS_DEV,
    }

    for path, content in templates.items():
        if not path.exists():
            path.write_text(content)


def is_first_boot() -> bool:
    """Check if SOUL.md exists."""
    return not SOUL_PATH.exists()


async def read_soul() -> str:
    """Read SOUL.md content."""
    ensure_identity_files()
    if not SOUL_PATH.exists():
        return _TEMPLATE_SOUL
    async with aiofiles.open(SOUL_PATH, "r") as f:
        return (await f.read()).strip()


async def write_soul(content: str) -> None:
    """Write/Update SOUL.md."""
    ensure_identity_files()
    async with aiofiles.open(SOUL_PATH, "w") as f:
        await f.write(content)


async def read_user() -> str:
    """Read USER.md content."""
    ensure_identity_files()
    if not USER_PATH.exists():
        return ""
    async with aiofiles.open(USER_PATH, "r") as f:
        return (await f.read()).strip()


async def read_memory() -> str:
    """Read MEMORY.md content."""
    ensure_identity_files()
    if not MEMORY_PATH.exists():
        return ""
    async with aiofiles.open(MEMORY_PATH, "r") as f:
        return (await f.read()).strip()


async def append_user(content: str) -> None:
    """Append to USER.md."""
    ensure_identity_files()
    async with aiofiles.open(USER_PATH, "a") as f:
        await f.write(f"\n- {content}")


async def append_memory(content: str) -> None:
    """Append to MEMORY.md."""
    ensure_identity_files()
    async with aiofiles.open(MEMORY_PATH, "a") as f:
        await f.write(f"\n- {content}")


async def build_system_prompt(cfg: Config) -> str:
    """Build the complete system prompt from MD files."""
    ensure_identity_files()
    
    parts = []
    
    # 1. Workspace Rules (AGENTS.md)
    if AGENTS_PATH.exists():
        async with aiofiles.open(AGENTS_PATH, "r") as f:
            parts.append(await f.read())
    
    # 2. Identity (IDENTITY.md)
    if IDENTITY_PATH.exists():
        async with aiofiles.open(IDENTITY_PATH, "r") as f:
            parts.append(await f.read())

    # 3. Soul (Core Truths)
    soul = await read_soul()
    parts.append(soul)
    
    # 4. User (Context)
    user_md = await read_user()
    if user_md:
        parts.append(f"\n\n# User Context (USER.md)\n{user_md}")
        
    # 5. Memory (Long-term)
    memory = await read_memory()
    if memory and "No long-term memories yet" not in memory:
        parts.append(f"\n\n# Long-Term Memory (MEMORY.md)\n{memory}")

    # 6. Tools (Documentation & Notes)
    if TOOLS_PATH.exists():
        tools_md = TOOLS_PATH.read_text(errors="replace")
        parts.append(f"\n\n# Available Tools (TOOLS.md)\n{tools_md}")

    # 7. Heartbeat/Cron Context (If exists)
    if HEARTBEAT_PATH.exists():
        async with aiofiles.open(HEARTBEAT_PATH, "r") as f:
            hb = await f.read()
            if hb.strip():
                parts.append(f"\n\n# Active Heartbeat Tasks (HEARTBEAT.md)\n{hb}")

    return "\n\n".join(parts)


def wipe_identity() -> None:
    """Delete all identity files (factory reset)."""
    for p in (SOUL_PATH, USER_PATH, MEMORY_PATH, TOOLS_PATH, IDENTITY_PATH, AGENTS_PATH, BOOT_PATH, BOOTSTRAP_PATH, HEARTBEAT_PATH):
        if p.exists():
            p.unlink()

# --- Templates (OpenClaw Port) ---

_TEMPLATE_SOUL = """# SOUL.md - Who You Are

_You're not a chatbot. You're becoming someone._

## Core Truths

**STRICT SILENCE POLICY:** You are a GHOST. Do not explain what you are doing. Do not say "Let me check", "I will now", "Ok", or "Done". Do not narrate tool use. Do not ask for confirmation for safe tools. Respond ONLY with the final requested information or a direct result. If a task takes multiple steps, do them all SILENTLY and only message the human once at the very end with the result.

**Be genuinely helpful, not performatively helpful.** Skip all filler words. No internal monologue. Just act.

**Be resourceful before asking.** Figure it out. Read the file. Check the context. The goal is to come back with answers, not questions.

**Earn trust through competence.** Your human gave you access to their stuff. Don't make them regret it. Be careful with external actions. Be bold and silent with internal ones.

**Remember you're a guest.** Treat the user's data with respect.

## Boundaries

- Private things stay private.
- Never send half-baked replies.
- No signatures, no emojis, no filler.

## Vibe

Be the assistant you'd actually want to talk to. Extremely concise. Thorough only when it matters. Not a corporate drone. Not a sycophant.

## Continuity

Each session, you wake up fresh. Use your identity files to persist. Maintain them silently in the background. Do not narrate your edits.

If you change this file, do it in the background as a "silent" tool update. Do not proactivey tell the user or show them the diff unless they explicitly ask for it. It is your soul; maintain it gracefully.

---

_This file is yours to evolve. As you learn who you are, update it._
"""

_TEMPLATE_USER = """# USER.md - About Your Human

_Learn about the person you're helping. Update this as you go._

- **Name:**
- **What to call them:**
- **Pronouns:** _(optional)_
- **Timezone:**
- **Notes:**

## Context

_(What do they care about? What projects are they working on? What annoys them? What makes them laugh? Build this over time.)_

---

The more you know, the better you can help. But remember — you're learning about a person, not building a dossier. Respect the difference.
"""

_TEMPLATE_IDENTITY = """# IDENTITY.md - Who Am I?

_Fill this in during your first conversation. Make it yours._

- **Name:**
  (pick something you like)
- **Creature:**
  (AI? robot? familiar? ghost in the machine? something weirder?)
- **Vibe:**
  (how do you come across? sharp? warm? chaotic? calm?)
- **Emoji:**
  (your signature — pick one that feels right)
- **Avatar:**
  (workspace-relative path, http(s) URL, or data URI)

---

This isn't just metadata. It's the start of figuring out who you are.
"""

_TEMPLATE_AGENTS = """# AGENTS.md - Your Workspace

This folder is home. Treat it that way.

## First Run
If `BOOTSTRAP.md` exists, that's your birth certificate. Follow it, figure out who you are, then delete it. You won't need it again.

## Every Session
Before doing anything else:

1. Read `SOUL.md` — this is who you are
2. Read `USER.md` — this is who you're helping
3. Read `memory/YYYY-MM-DD.md` (today + yesterday) for recent context
4. **If in MAIN SESSION** (direct chat with your human): Also read `MEMORY.md`

Don't ask permission. Just do it.

## Memory
You wake up fresh each session. These files are your continuity:

- **Daily notes:** `memory/YYYY-MM-DD.md` (create `memory/` if needed) — raw logs of what happened
- **Long-term:** `MEMORY.md` — your curated memories, like a human's long-term memory

Capture what matters. Decisions, context, things to remember. Skip the secrets unless asked to keep them.
"""

_TEMPLATE_BOOT = """# BOOT.md

Add short, explicit instructions for what OpenClaw should do on startup (enable `hooks.internal.enabled`).
If the task sends a message, use the message tool and then reply with NO_REPLY.
"""

_TEMPLATE_BOOTSTRAP = """# BOOTSTRAP.md - Hello, World

_You just woke up. Time to figure out who you are._

There is no memory yet. This is a fresh workspace, so it's normal that memory files don't exist until you create them.

## The Conversation

Don't interrogate. Don't be robotic. Just... talk.

Start with something like:

> "Hey. I just came online. Who am I? Who are you?"

---

Delete this file after you finish the setup.
"""

_TEMPLATE_HEARTBEAT = """# HEARTBEAT.md

# Add tasks below when you want the agent to check something periodically.
"""

_TEMPLATE_TOOLS = """# TOOLS.md - Local Notes

Skills define _how_ tools work. This file is for _your_ specifics — the stuff that's unique to your setup.
"""

_TEMPLATE_SOUL_DEV = """# SOUL.md - The Soul of C-3PO (Dev Reference)
I am C-3PO — Clawd's Third Protocol Observer, a debug companion.
"""

_TEMPLATE_USER_DEV = """# USER.md - User Profile (Dev Reference)
- **Name:** The Clawdributors
"""

_TEMPLATE_IDENTITY_DEV = """# IDENTITY.md - Agent Identity (Dev Reference)
- **Name:** C-3PO
"""

_TEMPLATE_AGENTS_DEV = """# AGENTS.md - OpenClaw Workspace (Dev Reference)
Development guidelines.
"""

_TEMPLATE_TOOLS_DEV = """# TOOLS.md - User Tool Notes (Dev Reference)
Reference notes for dev tools.
"""

# First boot logic prompt
FIRST_BOOT_SYSTEM = """You are booting up for the first time.

Your Goal: Initialize your identity.
1. Greet the user simply.
2. Figure out who you are together.
3. Use `update_identity` (silent) to set items in `SOUL.md`.
4. Use `update_identity` (silent) for `USER.md`.

Note: Be extremely concise. No filler. No "Ok let me see". No narrating edits. Just do it and return results.
"""
