"""Gateway runner — entry point for the background process.

Invoked via ``python -m pyclaw.gateway._runner``.
"""

from __future__ import annotations

import asyncio
import logging
import signal
import sys

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("pyclaw.gateway.runner")


async def _main() -> None:
    from pyclaw.config.config import Config
    from pyclaw.gateway.telegram import TelegramGateway

    cfg = await Config.load()

    token = cfg.get("gateway.telegram_bot_token")
    if not token:
        logger.error("no telegram bot token — set it via `pyclaw config`")
        sys.exit(1)

    gw = await TelegramGateway.create(cfg)

    # Graceful shutdown on SIGTERM
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, lambda: sys.exit(0))

    logger.info("gateway process running — waiting for telegram messages…")
    await gw.run()


def main() -> None:
    """Top-level entry with crash recovery."""
    max_crashes = 5
    crash_count = 0

    while crash_count < max_crashes:
        try:
            asyncio.run(_main())
            break  # clean exit
        except SystemExit:
            break
        except KeyboardInterrupt:
            break
        except Exception:
            crash_count += 1
            logger.exception(
                "gateway crashed (%d/%d), restarting…",
                crash_count,
                max_crashes,
            )
            if crash_count >= max_crashes:
                logger.error("too many crashes, giving up.")
                sys.exit(1)


if __name__ == "__main__":
    main()
