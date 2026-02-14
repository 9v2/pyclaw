"""pyclaw onboard — first-run setup wizard with multi-provider auth."""

from __future__ import annotations

import asyncio
import time

import click
from rich.console import Console
from rich.panel import Panel
from rich.text import Text

from pyclaw.config.config import Config
from pyclaw.skills.loader import SkillsManager
from pyclaw.auth.google_auth import start_auth_flow
from pyclaw.gateway.manager import GatewayManager


console = Console()

_BANNER = r"""
     ╔═══════════════════════════════╗
     ║       🦞  p y c l a w        ║
     ║   your personal ai assistant  ║
     ╚═══════════════════════════════╝
"""


async def _setup_antigravity(cfg: Config) -> None:
    """Google Antigravity auth flow."""
    # Check if we already have a valid token
    existing_token = cfg.get("auth.google_token")
    existing_email = cfg.get("auth.email")
    expiry_val = cfg.get("auth.token_expiry")
    try:
        expiry = float(expiry_val) if expiry_val is not None else 0.0
    except (ValueError, TypeError):
        expiry = 0.0

    if existing_token and existing_email and expiry > time.time():
        console.print(f"[dim]currently logged in as: {existing_email}[/dim]")
        try:
            skip = (
                console.input("[bold bright_cyan]skip login? (Y/n): [/]")
                .strip()
                .lower()
            )
        except (KeyboardInterrupt, EOFError):
            skip = "y"

        if skip in ("", "y", "yes"):
            cfg.set("auth.provider", "antigravity")
            # Ensure we save to confirm usage
            await cfg.save()
            console.print(
                f"[green]✓ using existing login for {existing_email}[/green]\n"
            )
            return

    console.print("[dim]opening your browser for google sign-in…[/dim]\n")
    result = await start_auth_flow()

    if "error" in result:
        console.print(f"[red]auth failed: {result['error']}[/red]")
        console.print("[dim]you can retry later with `pyclaw onboard`.[/dim]\n")
    else:
        cfg.set("auth.provider", "antigravity")
        cfg.set("auth.google_token", result.get("access_token"))
        cfg.set("auth.google_refresh_token", result.get("refresh_token"))
        cfg.set("auth.token_expiry", str(result.get("expires", 0)))
        cfg.set("auth.email", result.get("email"))
        cfg.set("auth.project_id", result.get("project_id"))
        await cfg.save()
        email = result.get("email") or "unknown"
        console.print(f"[green]✓ authenticated as {email}[/green]\n")


async def _setup_openai(cfg: Config) -> None:
    """OpenAI API key auth."""
    console.print(
        "[dim]get your API key from https://platform.openai.com/api-keys[/dim]\n"
    )
    try:
        key = console.input("[bold bright_cyan]openai api key: [/]").strip()
    except (KeyboardInterrupt, EOFError):
        return

    if key:
        cfg.set("auth.provider", "openai")
        cfg.set("auth.openai_api_key", key)
        cfg.set("agent.model", "gpt-4o")
        await cfg.save()
        console.print("[green]✓ OpenAI configured[/green]\n")


async def _setup_anthropic(cfg: Config) -> None:
    """Anthropic API key auth."""
    console.print(
        "[dim]get your API key from https://console.anthropic.com/settings/keys[/dim]\n"
    )
    try:
        key = console.input("[bold bright_cyan]anthropic api key: [/]").strip()
    except (KeyboardInterrupt, EOFError):
        return

    if key:
        cfg.set("auth.provider", "anthropic")
        cfg.set("auth.anthropic_api_key", key)
        cfg.set("agent.model", "claude-sonnet-4-20250514")
        await cfg.save()
        console.print("[green]✓ Anthropic configured[/green]\n")


async def _setup_custom(cfg: Config) -> None:
    """Custom OpenAI-compatible endpoint."""
    console.print("[dim]set up a custom OpenAI-compatible API endpoint.[/dim]\n")

    try:
        api_base = console.input(
            "[bold bright_cyan]api base url (e.g. http://localhost:11434/v1): [/]"
        ).strip()
    except (KeyboardInterrupt, EOFError):
        return
    if not api_base:
        return

    try:
        api_key = console.input(
            "[bold bright_cyan]api key (enter 'secret' for empty, or press enter to skip): [/]"
        ).strip()
    except (KeyboardInterrupt, EOFError):
        api_key = ""

    # If "secret", we'll pass "" to the API
    if api_key == "secret":
        cfg.set("auth.custom_api_key", "secret")
    elif api_key:
        cfg.set("auth.custom_api_key", api_key)

    cfg.set("auth.provider", "custom")
    cfg.set("auth.custom_api_base", api_base)

    # Try to fetch models
    console.print("\n[dim]fetching available models…[/dim]")
    try:
        from pyclaw.agent.providers import OpenAICompatProvider

        provider = OpenAICompatProvider(
            api_key="" if api_key == "secret" else api_key,
            api_base=api_base,
        )
        models = await provider.fetch_models()

        if models:
            console.print(f"[dim]found {len(models)} models:[/dim]")
            for i, m in enumerate(models[:20], 1):
                console.print(f"  [bright_cyan]{i}[/bright_cyan]  {m['id']}")
            console.print()

            try:
                choice = console.input(
                    "[bold bright_cyan]select model number (or type model name): [/]"
                ).strip()
            except (KeyboardInterrupt, EOFError):
                choice = ""

            if choice:
                try:
                    idx = int(choice) - 1
                    if 0 <= idx < len(models):
                        model_id = models[idx]["id"]
                    else:
                        model_id = choice
                except ValueError:
                    model_id = choice
                cfg.set("auth.custom_model", model_id)
                cfg.set("agent.model", model_id)
        else:
            console.print("[dim]couldn't fetch models list.[/dim]")
            try:
                model_name = console.input(
                    "[bold bright_cyan]default model name: [/]"
                ).strip()
            except (KeyboardInterrupt, EOFError):
                model_name = ""
            if model_name:
                cfg.set("auth.custom_model", model_name)
                cfg.set("agent.model", model_name)

    except Exception as exc:
        console.print(f"[dim]couldn't connect: {exc}[/dim]")
        try:
            model_name = console.input(
                "[bold bright_cyan]default model name: [/]"
            ).strip()
        except (KeyboardInterrupt, EOFError):
            model_name = ""
        if model_name:
            cfg.set("auth.custom_model", model_name)
            cfg.set("agent.model", model_name)

    await cfg.save()
    console.print("[green]✓ custom provider configured[/green]\n")


async def _run_onboard() -> None:
    """Full onboarding wizard."""
    console.print(
        Panel(
            Text(_BANNER, style="bright_cyan"),
            border_style="bright_cyan",
            padding=(0, 2),
        )
    )

    cfg = await Config.load()

    # ── Step 1: Welcome
    console.print("\n[bold]welcome to pyclaw![/bold]")
    console.print("[dim]let's get you set up. this will only take a minute.[/dim]\n")

    # ── Step 2: Auth Provider Selection
    console.print(
        "[bold bright_cyan]step 1/4[/bold bright_cyan] — choose your AI provider\n"
    )
    console.print(
        "  [bright_cyan]1[/bright_cyan]  Google Antigravity (free, requires Google account)"
    )
    console.print("  [bright_cyan]2[/bright_cyan]  OpenAI (requires API key)")
    console.print("  [bright_cyan]3[/bright_cyan]  Anthropic (requires API key)")
    console.print(
        "  [bright_cyan]4[/bright_cyan]  Custom OpenAI-compatible (local/self-hosted)"
    )
    console.print()

    try:
        provider_choice = console.input(
            "[bold bright_cyan]select provider (1-4, default 1): [/]"
        ).strip()
    except (KeyboardInterrupt, EOFError):
        provider_choice = "1"

    if provider_choice == "2":
        await _setup_openai(cfg)
    elif provider_choice == "3":
        await _setup_anthropic(cfg)
    elif provider_choice == "4":
        await _setup_custom(cfg)
    else:
        await _setup_antigravity(cfg)

    # ── Step 3: Model Selection (only for Antigravity)
    # ── Step 3: Model Selection (only for Antigravity)
    if cfg.get("auth.provider") == "antigravity":
        console.print(
            "[bold bright_cyan]step 2/4[/bold bright_cyan] — choose your default model\n"
        )
        console.print("[dim]fetching available models...[/dim]")

        from pyclaw.config.models import fetch_live_models

        token = cfg.get("auth.google_token")
        project_id = cfg.get("auth.project_id")

        live_models = []
        try:
            if token:
                live_models = await fetch_live_models(token, project_id)
        except Exception as exc:
            console.print(f"[red]failed to fetch models: {exc}[/red]")

        if live_models:
            for i, model in enumerate(live_models, 1):
                meta = ""
                if model.remaining_percent is not None:
                    meta = f" [dim]({model.remaining_percent}% quota)[/dim]"
                console.print(
                    f"  [bright_cyan]{i}[/bright_cyan]  {model.display_name} — {model.id}{meta}"
                )

            console.print()
            try:
                choice = console.input(
                    "[bold bright_cyan]select model (enter for default): [/]"
                ).strip()
            except (KeyboardInterrupt, EOFError):
                choice = ""

            if choice:
                try:
                    idx = int(choice) - 1
                    if 0 <= idx < len(live_models):
                        selected = live_models[idx]
                        cfg.set("agent.model", selected.id)
                        # Clear variant as dynamic models usually include variant in ID or we don't know it
                        cfg.set("agent.model_variant", "")
                        console.print(f"[green]✓ model → {selected.id}[/green]\n")
                except ValueError:
                    console.print("[dim]keeping default.[/dim]\n")
            else:
                # Default to first available or gemini-2.5-flash if present?
                # Or just keep what was set or default
                console.print("[dim]keeping default model.[/dim]\n")
        else:
            console.print(
                "[yellow]could not list models. you can set one manually later via `pyclaw config`.[/yellow]\n"
            )
    else:
        console.print("[dim]step 2/4 — model already set by provider.[/dim]\n")

    # ── Step 4: Telegram Bot
    console.print(
        "[bold bright_cyan]step 3/4[/bold bright_cyan] — telegram gateway (optional)\n"
    )
    console.print("[dim]set up a telegram bot to chat with pyclaw via telegram.[/dim]")
    console.print("[dim]get a bot token from @BotFather on telegram.[/dim]\n")

    existing_token = cfg.get("gateway.telegram_bot_token")
    use_existing_token = False

    if existing_token:
        masked = existing_token[:6] + "..." + existing_token[-4:]
        console.print(f"[dim]existing token: {masked}[/dim]")
        try:
            choice = (
                console.input("[bold bright_cyan]keep existing? (Y/n): [/]")
                .strip()
                .lower()
            )
        except (KeyboardInterrupt, EOFError):
            choice = "y"
        if choice in ("", "y", "yes"):
            use_existing_token = True
            token = existing_token

    if not use_existing_token:
        try:
            token = console.input(
                "[bold bright_cyan]bot token (enter to skip): [/]"
            ).strip()
        except (KeyboardInterrupt, EOFError):
            token = ""

    if token:
        cfg.set("gateway.telegram_bot_token", token)
        await cfg.save()
        if not use_existing_token:
            console.print("[green]✓ telegram bot token saved.[/green]\n")
        else:
            console.print("[green]✓ using existing token.[/green]\n")

        # User ID
        existing_uids = cfg.get("gateway.allowed_users", [])
        existing_uid = existing_uids[0] if existing_uids else None
        use_existing_uid = False

        if existing_uid:
            console.print(f"[dim]existing allowed user: {existing_uid}[/dim]")
            try:
                choice = (
                    console.input("[bold bright_cyan]keep existing? (Y/n): [/]")
                    .strip()
                    .lower()
                )
            except (KeyboardInterrupt, EOFError):
                choice = "y"
            if choice in ("", "y", "yes"):
                use_existing_uid = True

        if not use_existing_uid:
            try:
                tg_user_id = console.input(
                    "[bold bright_cyan]your telegram user id (enter to skip): [/]"
                ).strip()
            except (KeyboardInterrupt, EOFError):
                tg_user_id = ""

            if tg_user_id:
                try:
                    uid = int(tg_user_id)
                    cfg.set("gateway.allowed_users", [uid])
                    console.print(f"[green]✓ user {uid} added to allow list.[/green]\n")
                except ValueError:
                    console.print("[dim]invalid id, skipping.[/dim]\n")
        else:
            console.print("[green]✓ keeping existing user.[/green]\n")

    else:
        console.print("[dim]skipped — configure later via `pyclaw config`.[/dim]\n")

    # ── Step 5: Workspace + Skills
    console.print(
        "[bold bright_cyan]step 4/4[/bold bright_cyan] — setting up workspace\n"
    )

    workspace = Config.workspace_path(cfg.data)
    workspace.mkdir(parents=True, exist_ok=True)

    skills_mgr = SkillsManager(workspace)
    await skills_mgr.install_defaults()
    skills = await skills_mgr.load()

    console.print(f"[dim]workspace: {workspace}[/dim]")
    console.print(f"[dim]installed {len(skills)} default skills:[/dim]")
    for s in skills:
        console.print(f"  [bright_cyan]•[/bright_cyan] {s.name}")

    # ── Done
    await cfg.save()

    # ── Gateway Lifecycle
    pid = GatewayManager.get_pid() if GatewayManager.is_running() else None

    console.print("\n[bold bright_cyan]gateway management[/bold bright_cyan]")
    if pid:
        console.print(f"  status: [green]RUNNING[/green] (pid {pid})")
        options = r"\[R]estart / \[S]top / \[I]gnore"
    else:
        console.print("  status: [dim]STOPPED[/dim]")
        options = r"\[S]tart / \[I]gnore"

    try:
        gw_action = console.input(f"  action ({options}): [/]").strip().lower()
    except (KeyboardInterrupt, EOFError):
        gw_action = "i"

    if gw_action in ("r", "restart") and pid:
        ok, msg = GatewayManager.restart()
        color = "green" if ok else "red"
        console.print(f"  {msg}", style=color)
    elif gw_action in ("s", "stop") and pid:
        ok, msg = GatewayManager.stop()
        color = "green" if ok else "red"
        console.print(f"  {msg}", style=color)
    elif gw_action in ("s", "start") and not pid:
        if not cfg.get("gateway.telegram_bot_token"):
            console.print(
                "  [yellow]warning: no bot token set. gateway may fail.[/yellow]"
            )
        ok, msg = GatewayManager.start()
        color = "green" if ok else "red"
        console.print(f"  {msg}", style=color)

    provider_name = cfg.get("auth.provider", "antigravity")
    model_name = cfg.get("agent.model", "unknown")

    console.print()
    console.print(
        Panel(
            Text.from_markup(
                "[bold green]✓ setup complete![/bold green]\n\n"
                f"[dim]provider: {provider_name} · model: {model_name}[/dim]\n\n"
                "[dim]get started:[/dim]\n"
                "  [bright_cyan]pyclaw agent[/bright_cyan]    — chat with your ai\n"
                "  [bright_cyan]pyclaw config[/bright_cyan]   — edit settings\n"
                "  [bright_cyan]pyclaw models[/bright_cyan]   — switch models\n"
                "  [bright_cyan]pyclaw gateway[/bright_cyan]  — manage telegram\n"
                "  [bright_cyan]pyclaw skills[/bright_cyan]   — manage skills"
            ),
            border_style="green",
            padding=(1, 2),
        )
    )


@click.command("onboard")
def onboard_cmd() -> None:
    """Run the first-time setup wizard."""
    asyncio.run(_run_onboard())
