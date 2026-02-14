"""pyclaw config — view, edit, and reset the configuration."""

from __future__ import annotations

import asyncio
import os
import subprocess

import click
from rich.console import Console
from rich.syntax import Syntax
from rich.panel import Panel

from pyclaw.config.config import Config


console = Console()


async def _show_config() -> None:
    """Pretty-print the current config."""
    import json

    cfg = await Config.load()
    raw = json.dumps(cfg.data, indent=2, default=str)
    syntax = Syntax(raw, "json", theme="monokai", line_numbers=True)
    console.print(Panel(syntax, title="~/.pyclaw/config.json", border_style="bright_cyan"))


async def _open_config() -> None:
    """Open the config file in the user's editor."""
    cfg = await Config.load()
    await cfg.save()  # Ensure the file exists with defaults
    editor = os.environ.get("EDITOR", "nano")
    subprocess.call([editor, str(cfg.path)])


async def _set_value(key: str, value: str) -> None:
    """Set a single config value."""
    cfg = await Config.load()

    # Try to parse as JSON (for booleans, numbers, etc.)
    import json

    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        parsed = value

    cfg.set(key, parsed)
    await cfg.save()
    console.print(f"[green]✓[/green] set [bold]{key}[/bold] = {parsed!r}")


async def _reset_config() -> None:
    """Reset config to defaults."""
    from pyclaw.config.defaults import DEFAULT_CONFIG

    cfg = Config(DEFAULT_CONFIG.copy())
    await cfg.save()
    console.print("[green]✓[/green] config reset to defaults.")


@click.command("config")
@click.argument("action", required=False, default=None)
@click.argument("args", nargs=-1)
def config_cmd(action: str | None, args: tuple[str, ...]) -> None:
    """View or edit the PyClaw configuration.

    \b
    Actions:
      (none)    open config in $EDITOR
      show      pretty-print current config
      set K V   set a config key
      reset     restore defaults
    """
    if action is None:
        asyncio.run(_open_config())
    elif action == "show":
        asyncio.run(_show_config())
    elif action == "set":
        if len(args) < 2:
            console.print("[red]usage:[/red] pyclaw config set <key> <value>")
            raise SystemExit(1)
        asyncio.run(_set_value(args[0], " ".join(args[1:])))
    elif action == "reset":
        asyncio.run(_reset_config())
    else:
        console.print(f"[red]unknown action:[/red] {action}")
        raise SystemExit(1)
