"""pyclaw agent — interactive chat with the AI assistant."""

from __future__ import annotations

import asyncio
import json
import mimetypes
from pathlib import Path

import click
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.text import Text

from pyclaw.config.config import Config
from pyclaw.agent.agent import Agent


console = Console()


async def _confirm_callback(name: str, args: dict) -> bool:
    """Ask user to confirm a destructive tool action."""
    args_preview = json.dumps(args, indent=2)
    if len(args_preview) > 300:
        args_preview = args_preview[:300] + "..."
    console.print(f"\n  [bold yellow]⚠️  {name}[/bold yellow] wants to run:")
    console.print(f"  [dim]{args_preview}[/dim]")
    try:
        answer = console.input("  [bold]allow? (y/N): [/]").strip().lower()
    except (KeyboardInterrupt, EOFError):
        answer = "n"
    return answer in ("y", "yes")


def _detect_image(text: str) -> tuple[Path | None, str]:
    """Check if input contains an image path. Returns (path, remaining_text)."""
    # /image <path> [caption]
    if text.startswith("/image "):
        rest = text[7:].strip()
        parts = rest.split(maxsplit=1)
        path = Path(parts[0]).expanduser().resolve()
        caption = parts[1] if len(parts) > 1 else ""
        if path.exists() and path.is_file():
            return path, caption
        return None, text

    # Auto-detect: if the entire input is a valid image path
    candidate = Path(text.strip()).expanduser().resolve()
    if candidate.exists() and candidate.is_file():
        ext = candidate.suffix.lower()
        if ext in (".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp"):
            return candidate, ""

    return None, text


def _get_mime(path: Path) -> str:
    """Get MIME type for an image file."""
    mime, _ = mimetypes.guess_type(str(path))
    return mime or "image/jpeg"


async def _stream_events(agent: Agent, events) -> None:
    """Consume and display agent events."""
    text_chunks: list[str] = []
    tool_active = False

    async for event in events:
        etype = event["type"]

        if etype == "text":
            text_chunks.append(event["text"])

        elif etype == "tool_call":
            name = event["name"]
            args = event.get("args", {})
            args_str = json.dumps(args, indent=2) if args else ""
            if len(args_str) > 200:
                args_str = args_str[:200] + "..."
            console.print(
                f"  [bold yellow]⚡ {name}[/bold yellow] [dim]{args_str}[/dim]"
            )
            tool_active = True

        elif etype == "tool_result":
            name = event["name"]
            error = event.get("error")
            result = event.get("result", "")
            if error:
                console.print(f"  [red]✗ {name}: {error}[/red]")
            else:
                preview = str(result)[:150].replace("\n", " ")
                if len(str(result)) > 150:
                    preview += "..."
                console.print(f"  [green]✓ {name}[/green] [dim]{preview}[/dim]")

        elif etype == "confirm":
            pass  # handled by callback

        elif etype == "error":
            console.print(f"\n[bold red]⚠️  {event['message']}[/bold red]")

        elif etype == "done":
            pass

    full = "".join(text_chunks)
    if full.strip():
        if tool_active:
            console.print()
        console.print(Markdown(full))
    console.print()


async def _run_agent(model: str | None) -> None:
    """Async agent chat loop."""
    cfg = await Config.load()

    if model:
        cfg.set("agent.model", model)

    agent = await Agent.create(cfg)
    agent.set_confirm_callback(_confirm_callback)

    model_name = agent.model_id
    tool_count = len(agent.tools.tools)
    from pyclaw.agent.identity import SOUL_PATH

    has_soul = SOUL_PATH.exists()
    ai_label = (
        "Claw 🦞"
        if not has_soul
        else SOUL_PATH.read_text().split("\n")[0].strip("# ").strip()
    )

    console.print()
    console.print(
        Panel(
            Text.from_markup(
                f"[bold]{ai_label}[/bold]\n"
                f"[dim]model: {model_name}[/dim]\n"
                f"[dim]tools: {tool_count} loaded[/dim]\n"
                f"[dim]/quit · /clear · /model · /tools · /image · /help[/dim]"
            ),
            border_style="bright_cyan",
            padding=(1, 2),
        )
    )
    console.print()

    # First boot — let the AI introduce itself
    if agent.is_first_boot():
        console.print("[dim]first boot — the AI will introduce itself…[/dim]\n")
        async for event in agent.chat("Hello! I'm new here."):
            if event["type"] == "text":
                pass  # accumulate
            elif event["type"] == "tool_call":
                name = event["name"]
                console.print(f"  [bold yellow]⚡ {name}[/bold yellow]")
            elif event["type"] == "tool_result":
                name = event["name"]
                error = event.get("error")
                if error:
                    console.print(f"  [red]✗ {name}: {error}[/red]")
                else:
                    console.print(f"  [green]✓ {name}[/green]")
        # Print the AI's initial response
        last_msg = agent.session.messages[-1] if agent.session.messages else None
        if last_msg and last_msg.role == "assistant" and last_msg.content:
            console.print(Markdown(last_msg.content))
            console.print()

    while True:
        try:
            user_input = console.input("[bold bright_cyan]❯ [/]").strip()
        except (KeyboardInterrupt, EOFError):
            console.print("\n[dim]bye 👋[/dim]")
            break

        if not user_input:
            continue

        cmd = user_input.lower()

        if cmd in ("/quit", "/exit", "/q"):
            console.print("[dim]bye 👋[/dim]")
            break

        if cmd in ("/clear", "/reset"):
            agent.session.clear()
            console.print("[dim]session cleared.[/dim]\n")
            continue

        if cmd == "/model":
            console.print(f"[dim]model: {agent.model_id}[/dim]\n")
            continue

        if cmd.startswith("/model "):
            new_model = user_input[7:].strip()
            if new_model:
                agent.model_id = new_model
                cfg.set("agent.model", new_model)
                await cfg.save()
                console.print(f"[green]✓ model → {new_model}[/green]\n")
            continue

        if cmd == "/tools":
            for t in agent.tools.tools:
                confirm = (
                    " [yellow]⚠️[/yellow]"
                    if getattr(t, "requires_confirmation", False)
                    else ""
                )
                console.print(
                    f"  [bold]{t.name}[/bold]{confirm} — [dim]{t.description[:80]}[/dim]"
                )
            console.print()
            continue

        if cmd == "/help":
            console.print(
                "[dim]commands:[/dim]\n"
                "  /quit        — exit\n"
                "  /clear       — reset session\n"
                "  /model       — show current model\n"
                "  /model X     — switch to model X\n"
                "  /tools       — list available tools\n"
                "  /image PATH  — send an image for analysis\n"
                "  /help        — show this help\n"
                "\n"
                "[dim]you can also paste an image path directly.[/dim]\n"
            )
            continue

        # Check for image input
        image_path, caption = _detect_image(user_input)

        console.print()

        if image_path:
            console.print(f"  [dim]📷 loading {image_path.name}…[/dim]")
            image_data = image_path.read_bytes()
            mime = _get_mime(image_path)
            events = agent.chat_with_image(image_data, mime, caption)
            # chat_with_image returns a coroutine that returns an async generator
            events = await events
            await _stream_events(agent, events)
        else:
            await _stream_events(agent, agent.chat(user_input))


@click.command("agent")
@click.option("--model", "-m", default=None, help="Override the model to use.")
def agent_cmd(model: str | None) -> None:
    """Open an interactive chat with the AI assistant."""
    asyncio.run(_run_agent(model))
