"""Telegram gateway — tgram-based bot bridge."""

from pyclaw.gateway.manager import GatewayManager

__all__ = ["TelegramGateway", "GatewayManager"]


def __getattr__(name: str):
    """Lazy import TelegramGateway to avoid importing tgram at CLI startup."""
    if name == "TelegramGateway":
        from pyclaw.gateway.telegram import TelegramGateway

        return TelegramGateway
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
