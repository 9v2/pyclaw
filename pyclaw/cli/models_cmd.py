"""pyclaw models — list and select available AI models."""

from __future__ import annotations

import asyncio

import click
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.text import Text

from pyclaw.config.config import Config
from pyclaw.config.models import MODELS, get_model


console = Console()


async def _list_and_select() -> None:
    """Interactive model selector."""
    from pyclaw.config.models import fetch_live_models
    from pyclaw.auth.google_auth import refresh_token_if_needed

    cfg = await Config.load()
    current = cfg.get("agent.model", "")
    
    # Refresh token for fetching
    console.print("[dim]fetching available models...[/dim]")
    token = await refresh_token_if_needed(cfg)
    if not token:
        console.print("[red]not authenticated. run `pyclaw onboard` first.[/red]")
        return

    try:
        models = await fetch_live_models(token, cfg.get("auth.project_id"))
    except Exception as exc:
        console.print(f"[red]failed to fetch models: {exc}[/red]")
        return

    if not models:
        console.print("[yellow]no models found available to your account.[/yellow]")
        return

    # Build table
    table = Table(
        title="Available Models (Antigravity)",
        border_style="bright_cyan",
        header_style="bold bright_cyan",
        row_styles=["", "dim"],
    )
    table.add_column("#", style="dim", width=3, justify="right")
    table.add_column("Model ID", style="bold")
    table.add_column("Display Name")
    table.add_column("Quota", justify="right")
    table.add_column("Reset", style="dim")
    table.add_column("", width=3)

    for i, model in enumerate(models, 1):
        is_current = model.id == current
        marker = "→" if is_current else ""
        style = "bold bright_green" if is_current else ""
        
        quota_str = f"{model.remaining_percent}%"
        if model.remaining_fraction < 0.2:
            quota_str = f"[red]{quota_str}[/red]"
        elif model.remaining_fraction < 0.5:
            quota_str = f"[yellow]{quota_str}[/yellow]"
        else:
            quota_str = f"[green]{quota_str}[/green]"

        table.add_row(
            str(i),
            model.id,
            model.display_name,
            quota_str,
            model.reset_time or "—",
            marker,
            style=style,
        )

    console.print()
    console.print(table)
    console.print()
    current_display = f"[dim]current: [bold]{current}[/bold][/dim]"
    console.print(current_display)
    console.print()

    # Prompt for selection
    try:
        choice = console.input(
            "[bold bright_cyan]select model number (or enter to keep current): [/]"
        ).strip()
    except (KeyboardInterrupt, EOFError):
        console.print("\n[dim]cancelled.[/dim]")
        return

    if not choice:
        console.print("[dim]no change.[/dim]")
        return

    try:
        idx = int(choice) - 1
        if idx < 0 or idx >= len(models):
            raise ValueError
    except ValueError:
        console.print("[red]invalid selection.[/red]")
        return

    selected = models[idx]
    cfg.set("agent.model", selected.id)
    # Clear variant as we are selecting a new base model from API list
    cfg.set("agent.model_variant", "")
    
    await cfg.save()
    console.print(f"\n[green]✓[/green] model set to [bold]{selected.id}[/bold]")


@click.command("models")
def models_cmd() -> None:
    """List and select available AI models."""
    asyncio.run(_list_and_select())
