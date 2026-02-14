"""Model definitions and dynamic fetching from Antigravity API.

Model IDs match the API spec exactly (no date suffixes):
  https://github.com/NoeFabris/opencode-antigravity-auth/blob/main/docs/ANTIGRAVITY_API_SPEC.md
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass(frozen=True)
class Model:
    """Metadata for an Antigravity model."""

    id: str
    name: str
    provider: str
    description: str
    default: bool = False
    variants: list[str] = field(default_factory=list)
    default_variant: Optional[str] = None


# ── Static fallback models (IDs from API spec) ─────────────────────

MODELS: list[Model] = [
    # Static models removed in favor of dynamic fetching
]


def get_model(model_id: str) -> Optional[Model]:
    """Look up a model by its ID."""
    for m in MODELS:
        if m.id == model_id:
            return m
    return None


def get_default_model() -> Model:
    """Return the default model."""
    for m in MODELS:
        if m.default:
            return m
    return MODELS[0]


# ── Dynamic model fetching ──────────────────────────────────────────

@dataclass
class LiveModel:
    """A model returned by the Antigravity API with quota info."""

    id: str
    display_name: str
    remaining_fraction: float
    remaining_percent: int
    reset_time: Optional[str] = None


async def fetch_live_models(
    access_token: str,
    project_id: str | None = None,
) -> list[LiveModel]:
    """Fetch available models from the Antigravity API."""
    from pyclaw.agent.antigravity import fetch_available_models

    data = await fetch_available_models(access_token, project_id)
    models_data = data.get("models", {})

    result: list[LiveModel] = []
    for model_id, model_info in models_data.items():
        if model_id.startswith("chat_") or model_id.startswith("tab_"):
            continue

        quota = model_info.get("quotaInfo", {})
        remaining = quota.get("remainingFraction", 1.0)
        if isinstance(remaining, str):
            try:
                remaining = float(remaining)
            except ValueError:
                remaining = 1.0

        result.append(LiveModel(
            id=model_id,
            display_name=model_info.get("displayName", model_id),
            remaining_fraction=remaining,
            remaining_percent=round(remaining * 100),
            reset_time=quota.get("resetTime"),
        ))

    result.sort(key=lambda m: m.id)
    return result
