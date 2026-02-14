<div align="center">

# 🦞 PyClaw

**your own personal AI assistant — the python claw.**

[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

a fully async, extensible AI assistant that lives in your terminal and telegram.
powered by (Gemini, OpenAI, Anthropic, etc. ) routing.

</div>

---

## ✨ features

- **Telegram bot gateway** — Chat with your AI from anywhere, with photo analysis and file sharing.
- **Terminal chat** — Interactive CLI with streaming responses
- **Tool system** — File operations, shell commands, web search, config management, cron jobs
- **Skills** — Extensible skill system with installable `.md` skill packs
- **Identity** — Persistent personality via `SOUL.md` and `AGENTS.md` templates
- **Memory** — Daily notes + curated long-term memory
- **Reactions** — Auto-reactions and emoji reactions on telegram (minimal/massive modes)
- **Network resilience** — Auto-reconnect with exponential backoff on connection loss
- **Multi-model** — Switch between gemini models on the fly

## 📦 installation

### requirements

- **python 3.11+**
- **pip** (or **pipx** for isolated install)
- a **google AI api key** ([get one here](https://aistudio.google.com/apikey))
- a **telegram bot token** (from [@BotFather](https://t.me/BotFather)) — *optional, for telegram gateway*

### linux / macOS

```bash
git clone https://github.com/9v2/pyclaw.git
cd pyclaw
python -m venv .venv
source .venv/bin/activate
pip install -e .
```

### windows (WSL recommended)

```bash
# install WSL if not already
wsl --install

# then inside WSL:
git clone https://github.com/9v2/pyclaw.git
cd pyclaw
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
```

### windows (native)

```powershell
git clone https://github.com/9v2/pyclaw.git
cd pyclaw
python -m venv .venv
.venv\Scripts\activate
pip install -e .
```

> [!NOTE]
> the telegram gateway uses unix signals for graceful shutdown. on native windows, use WSL for the gateway. the CLI works fine on native windows.

## 🚀 quick start

```bash
# first-time setup — walks you through auth, model selection, telegram, and skills
pyclaw onboard

# start chatting
pyclaw agent

# launch telegram bot
pyclaw gateway
```

## 📋 CLI commands

| command | description |
|---|---|
| `pyclaw onboard` | first-time setup wizard |
| `pyclaw agent` | interactive AI chat in terminal |
| `pyclaw gateway` | telegram bot (interactive menu with start/stop/restart) |
| `pyclaw config show` | display current config |
| `pyclaw config set KEY VALUE` | set a config value |
| `pyclaw config reset` | reset config to defaults |
| `pyclaw models` | list and switch AI models |
| `pyclaw skills list` | list installed skills |
| `pyclaw skills install URL` | install a skill from a `.md` URL |

## ⚙️ configuration

config lives at `~/.pyclaw/config.json`. key sections:

| section | keys | description |
|---|---|---|
| `auth` | `google_api_key` | google AI API key |
| `agent` | `model`, `temperature`, `max_tokens` | model and generation settings |
| `gateway` | `telegram_bot_token`, `allowed_users`, `reaction_mode` | telegram bot settings |
| `search` | `provider`, `perplexity_api_key`, `brave_api_key` | web search provider |
| `workspace` | `path` | workspace directory (default: `~/.pyclaw/workspace`) |

### reaction modes

```bash
# no auto-reactions (default)
pyclaw config set gateway.reaction_mode null

# react on greetings + completion
pyclaw config set gateway.reaction_mode minimal

# react on every message
pyclaw config set gateway.reaction_mode massive
```

## 🧠 skills

skills are markdown files that extend the AI's capabilities. they live in `~/.pyclaw/workspace/skills/<name>/SKILL.md` and are injected into the system prompt.

```bash
# install a skill from a URL
pyclaw skills install https://example.com/skill.md

# list installed skills
pyclaw skills list
```

built-in skills: **tmux**, **shell**, **file_management**

## 🛠 available tools

the AI has access to these tools:

| tool | description |
|---|---|
| `run_command` | execute shell commands |
| `write_file` | create/overwrite files |
| `read_file` | read file contents |
| `list_directory` | list directory contents |
| `web_search` | search the web (brave/perplexity) |
| `read_webpage` | fetch and read a URL |
| `send_reaction` | react to messages with emoji |
| `get_config` / `set_config` | read/write config |
| `update_identity` | update SOUL.md / AGENTS.md |
| `cron` tools | schedule recurring tasks |

## 🏗 architecture

```
~/.pyclaw/
├── config.json          # all settings
├── SOUL.md              # AI personality & rules
├── AGENTS.md            # behavioral guidelines
├── MEMORY.md            # curated long-term memory
├── memory/              # daily notes (YYYY-MM-DD.md)
├── workspace/
│   ├── skills/          # installed skills
│   ├── images/          # generated images
│   ├── files/           # generated files
│   └── temp/            # temporary files
└── gateway.log          # telegram gateway logs
```

```
pyclaw/
├── agent/               # core AI agent, providers, tools, identity
├── auth/                # google OAuth
├── cli/                 # click CLI commands
├── config/              # config management, defaults, models
├── gateway/             # telegram bot gateway
└── skills/              # built-in skill templates
```

## 🔒 security

- **confirmation prompts** for destructive commands (`rm`, `kill`, etc.)
- **blocked patterns** — configurable command blocklist
- **allowed users** — restrict telegram bot to specific user IDs
- **safe commands** — whitelist for auto-approved commands (`ls`, `cat`, `echo`, etc.)

## 🤝 contributing

Contributions are welcome! Feel free to open issues, suggest features, or submit pull requests.

1. Fork the repo
2. Create your branch (`git checkout -b feature/cool-thing`)
3. Commit your changes (`git commit -m 'add cool thing'`)
4. Push to the branch (`git push origin feature/cool-thing`)
5. Open a Pull Request

If you find PyClaw useful, give it a ⭐ — it helps others discover the project!

## 📄 license

[MIT](LICENSE)
