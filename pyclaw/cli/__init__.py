"""PyClaw CLI — main entry point.

Registers all subcommands under the ``pyclaw`` group.
"""

from __future__ import annotations

import click

from pyclaw.cli.agent import agent_cmd
from pyclaw.cli.config_cmd import config_cmd
from pyclaw.cli.models_cmd import models_cmd
from pyclaw.cli.gateway_cmd import gateway_cmd
from pyclaw.cli.onboard import onboard_cmd
from pyclaw.cli.skills_cmd import skills_cmd


@click.group(invoke_without_command=True)
@click.version_option(package_name="pyclaw")
@click.pass_context
def cli(ctx: click.Context) -> None:
    """🦞 pyclaw — your personal AI assistant."""
    if ctx.invoked_subcommand is None:
        click.echo(ctx.get_help())


cli.add_command(agent_cmd, "agent")
cli.add_command(config_cmd, "config")
cli.add_command(models_cmd, "models")
cli.add_command(gateway_cmd, "gateway")
cli.add_command(onboard_cmd, "onboard")
cli.add_command(skills_cmd, "skills")


def main() -> None:
    """Package entry point."""
    cli()
