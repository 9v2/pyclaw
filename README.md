# 🦞 PyClaw

> Your own personal AI assistant — the Python claw.

A fully async Python implementation inspired by [OpenClaw](https://github.com/openclaw/openclaw).
Chat with AI via your terminal or Telegram, powered by Antigravity model routing.

## Install

```bash
# clone and install in dev mode
git clone <repo-url> && cd my-own-claw
pip install -e .
```

## Quick Start

```bash
# first-run setup (auth, model, telegram, skills)
pyclaw onboard

# chat with your AI
pyclaw agent

# manage models
pyclaw models

# edit config
pyclaw config

# telegram gateway
pyclaw gateway
```

## CLI Commands

| Command | Description |
|---|---|
| `pyclaw agent` | Interactive AI chat session |
| `pyclaw config` | Open/view/edit config (`show`, `set K V`, `reset`) |
| `pyclaw models` | List and select Antigravity models |
| `pyclaw gateway` | Manage Telegram bot (interactive or `start`/`stop`/`restart`) |
| `pyclaw onboard` | First-time setup wizard |

## Skills

Skills live in `~/.pyclaw/workspace/skills/<name>/SKILL.md` and are
automatically injected into the agent's system prompt. Add your own
by creating a new directory with a `SKILL.md` file.

Built-in skills: **tmux**, **shell**, **file_management**.

## Config

Config lives at `~/.pyclaw/config.json`. Key sections:

- `auth` — Google OAuth tokens
- `agent` — model, system prompt, temperature
- `gateway` — Telegram bot token, allowed users
- `workspace` — workspace path

## License

MIT
