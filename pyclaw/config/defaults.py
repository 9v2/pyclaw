"""Default configuration values for PyClaw."""

from __future__ import annotations

DEFAULT_CONFIG: dict = {
    "auth": {
        "provider": "antigravity",  # "antigravity", "openai", "anthropic", "custom"
        # Antigravity (Google)
        "google_token": None,
        "google_refresh_token": None,
        "token_expiry": None,
        "email": None,
        "project_id": None,
        # OpenAI
        "openai_api_key": None,
        # Anthropic
        "anthropic_api_key": None,
        # Custom OpenAI-compatible
        "custom_api_key": None,
        "custom_api_base": None,
        "custom_model": None,
    },
    "agent": {
        "model": "gemini-2.5-flash",
        "model_variant": "",
        "system_prompt": None,  # None = use personality-based prompt
        "temperature": 0.7,
        "max_tokens": 8192,
    },
    "personality": {
        "user_name": None,
        "ai_name": "Claw",
        "ai_purpose": None,
        "ai_style": "friendly, concise, uses lowercase",
        "ai_emoji": "🦞",
        "learned_preferences": [],
    },
    "gateway": {
        "telegram_bot_token": None,
        "auto_start": False,
        "allowed_users": [],
    },
    "safety": {
        "confirm_destructive": True,
        "blocked_patterns": [
            "rm -rf /",
            "mkfs",
            "dd if=",
            ":(){:|:&};:",
            "> /dev/sd",
        ],
    },
    "search": {
        "provider": None,  # "brave" or "perplexity" (optional)
        "brave_api_key": None,
        "perplexity_api_key": None,
    },
    "cron": {
        "jobs": [],
        "heartbeat_interval": 300,  # 5 minutes
        "timezone": "auto",
    },
    "backups": {
        "enabled": True,
        "max_count": 5,
    },
    "workspace": {
        "path": "~/.pyclaw/workspace",
    },
}
