"""pyclaw gateway — manage the Telegram gateway process."""

from __future__ import annotations

import asyncio

import click
from rich.console import Console
from rich.panel import Panel
from rich.text import Text

from pyclaw.config.config import Config
from pyclaw.gateway.manager import GatewayManager


console = Console()


async def _ensure_token() -> bool:
    """Check if token exists, prompt if not."""
    cfg = await Config.load()
    token = cfg.get("gateway.telegram_bot_token")
    if token:
        return True

    console.print("[yellow]⚠️ telegram bot token not configured.[/yellow]")
    try:
        should_setup = (
            console.input("[bold]setup a telegram bot now? (Y/n): [/]").strip().lower()
        )
    except (KeyboardInterrupt, EOFError):
        should_setup = "n"

    if should_setup not in ("", "y", "yes"):
        return False

    console.print("[dim]get a token from @BotFather on telegram[/dim]")
    try:
        token = console.input("[bold bright_cyan]bot token: [/]").strip()
    except (KeyboardInterrupt, EOFError):
        return False

    if token:
        cfg.set("gateway.telegram_bot_token", token)
        await cfg.save()
        console.print("[green]✓ token saved.[/green]\n")
        return True

    return False


def _show_status() -> None:
    """Display current gateway status."""
    running = GatewayManager.is_running()
    pid = GatewayManager.get_pid()

    if running:
        status = Text.from_markup(
            f"[bold green]● running[/bold green]  [dim]pid {pid}[/dim]"
        )
    else:
        status = Text.from_markup("[bold red]● stopped[/bold red]")

    console.print(
        Panel(
            status,
            title="telegram gateway",
            border_style="bright_cyan",
            padding=(0, 2),
        )
    )

    if running:
        log_path = GatewayManager.log_path()
        console.print(f"  [dim]logs: {log_path}[/dim]")


async def _interactive_menu() -> None:
    """Interactive gateway management screen."""
    while True:
        console.print()
        _show_status()
        console.print()

        running = GatewayManager.is_running()

        options = []
        if not running:
            options.append(("1", "start"))
        else:
            options.append(("1", "restart"))
            options.append(("2", "stop"))

        options.append(("s", "status"))
        options.append(("l", "view logs"))
        options.append(("q", "quit"))

        for key, label in options:
            console.print(f"  [bright_cyan]{key}[/bright_cyan]  {label}")

        console.print()

        try:
            choice = console.input("[bold bright_cyan]❯ [/]").strip().lower()
        except (KeyboardInterrupt, EOFError):
            break

        if choice == "q":
            break
        elif choice == "s":
            continue  # Re-display status
        elif choice == "l":
            log_path = GatewayManager.log_path()
            if log_path.exists():
                content = log_path.read_text()
                # Show last 50 lines
                lines = content.strip().splitlines()
                tail = "\n".join(lines[-50:])
                console.print(
                    Panel(tail or "[dim]no logs yet[/dim]", title="gateway logs")
                )
            else:
                console.print("[dim]no logs yet.[/dim]")
        elif choice == "1":
            # Check token before start/restart
            if not await _ensure_token():
                console.print("[red]cannot start without a bot token.[/red]")
                continue

            if running:
                ok, msg = GatewayManager.restart()
            else:
                ok, msg = GatewayManager.start()
            style = "green" if ok else "red"
            console.print(f"[{style}]{msg}[/{style}]")
        elif choice == "2" and running:
            ok, msg = GatewayManager.stop()
            style = "green" if ok else "red"
            console.print(f"[{style}]{msg}[/{style}]")
        else:
            console.print("[dim]invalid option.[/dim]")


async def _run_gateway(action: str | None) -> None:
    """Async wrapper for gateway commands."""
    if action is None:
        await _interactive_menu()
    elif action == "start":
        if not await _ensure_token():
            console.print("[red]cannot start without a bot token.[/red]")
            return
        ok, msg = GatewayManager.start()
        style = "green" if ok else "yellow"
        console.print(f"[{style}]{msg}[/{style}]")
    elif action == "stop":
        ok, msg = GatewayManager.stop()
        style = "green" if ok else "yellow"
        console.print(f"[{style}]{msg}[/{style}]")
    elif action == "restart":
        if not await _ensure_token():
            console.print("[red]cannot restart without a bot token.[/red]")
            return
        ok, msg = GatewayManager.restart()
        style = "green" if ok else "yellow"
        console.print(f"[{style}]{msg}[/{style}]")
    elif action == "status":
        _show_status()
    else:
        console.print(f"[red]unknown action:[/red] {action}")
        raise SystemExit(1)


@click.command("gateway")
@click.argument("action", required=False, default=None)
def gateway_cmd(action: str | None) -> None:
    """Manage the Telegram gateway.

    \b
    Actions:
      (none)    interactive management screen
      start     start the gateway
      stop      stop the gateway
      restart   restart the gateway
      status    show gateway status
    """
    asyncio.run(_run_gateway(action))
