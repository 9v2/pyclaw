"""pyclaw skills — install, list, and remove skills."""

from __future__ import annotations

import asyncio
from pathlib import Path

import click
from rich.console import Console

from pyclaw.config.config import Config
from pyclaw.skills.loader import SkillsManager

console = Console()


async def _list_skills() -> None:
    cfg = await Config.load()
    workspace = Config.workspace_path(cfg.data)
    mgr = SkillsManager(workspace)
    skills = await mgr.load()

    if not skills:
        console.print("[dim]no skills installed.[/dim]")
        return

    console.print(f"[bold]installed skills ({len(skills)}):[/bold]\n")
    for s in skills:
        desc = f" — {s.description}" if s.description else ""
        console.print(f"  [bright_cyan]•[/bright_cyan] [bold]{s.name}[/bold]{desc}")
        console.print(f"    [dim]{s.path}[/dim]")
    console.print()


async def _install_skill(source: str) -> None:
    cfg = await Config.load()
    workspace = Config.workspace_path(cfg.data)
    mgr = SkillsManager(workspace)

    if source.startswith(("http://", "https://")):
        if not source.lower().endswith(".md"):
            console.print("[red]error: skill URL must end in .md[/red]")
            return
        console.print(f"[dim]downloading from {source}…[/dim]")
        skill = await mgr.install_from_url(source)
    else:
        path = Path(source).expanduser().resolve()
        if not path.exists():
            console.print(f"[red]not found: {path}[/red]")
            return
        skill = await mgr.install_from_path(path)

    if skill:
        console.print(f"[green]✓ installed skill: {skill.name}[/green]")
        if skill.description:
            console.print(f"  [dim]{skill.description}[/dim]")
    else:
        console.print("[red]failed to install skill.[/red]")


async def _remove_skill(name: str) -> None:
    cfg = await Config.load()
    workspace = Config.workspace_path(cfg.data)
    mgr = SkillsManager(workspace)

    if mgr.remove(name):
        console.print(f"[green]✓ removed skill: {name}[/green]")
    else:
        console.print(f"[red]skill not found: {name}[/red]")


@click.group("skills")
def skills_cmd() -> None:
    """Manage PyClaw skills."""


@skills_cmd.command("list")
def skills_list() -> None:
    """List installed skills."""
    asyncio.run(_list_skills())


@skills_cmd.command("install")
@click.argument("source")
def skills_install(source: str) -> None:
    """Install a skill from a URL or local path."""
    asyncio.run(_install_skill(source))


@skills_cmd.command("remove")
@click.argument("name")
def skills_remove(name: str) -> None:
    """Remove an installed skill."""
    asyncio.run(_remove_skill(name))
