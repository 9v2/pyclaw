"""Cron job scheduler for PyClaw.

Jobs are stored in config as a list of dicts:
    {
        "name": "daily-summary",
        "schedule": "0 9 * * *",       # standard cron syntax
        "action": "Give me a daily summary of my system health",
        "enabled": true
    }

The CronManager runs as an asyncio background task and fires jobs
by sending their action as a chat message to the agent.
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Optional

from pyclaw.config.config import Config

logger = logging.getLogger("pyclaw.cron")


@dataclass
class CronJob:
    """A scheduled job."""
    name: str
    schedule: str       # cron expression: "min hour dom mon dow"
    action: str         # prompt to send to agent
    enabled: bool = True


def parse_cron_field(field: str, min_val: int, max_val: int) -> set[int]:
    """Parse a single cron field into a set of matching values."""
    if field == "*":
        return set(range(min_val, max_val + 1))

    values: set[int] = set()

    for part in field.split(","):
        # Handle step: */5 or 1-10/2
        if "/" in part:
            range_part, step_str = part.split("/", 1)
            step = int(step_str)
            if range_part == "*":
                start, end = min_val, max_val
            elif "-" in range_part:
                s, e = range_part.split("-", 1)
                start, end = int(s), int(e)
            else:
                start, end = int(range_part), max_val
            values.update(range(start, end + 1, step))

        elif "-" in part:
            s, e = part.split("-", 1)
            values.update(range(int(s), int(e) + 1))

        else:
            values.add(int(part))

    return values


def cron_matches(schedule: str, dt: datetime) -> bool:
    """Check if a cron expression matches the given datetime."""
    fields = schedule.strip().split()
    if len(fields) != 5:
        return False

    minute = parse_cron_field(fields[0], 0, 59)
    hour = parse_cron_field(fields[1], 0, 23)
    dom = parse_cron_field(fields[2], 1, 31)
    month = parse_cron_field(fields[3], 1, 12)
    dow = parse_cron_field(fields[4], 0, 6)

    return (
        dt.minute in minute
        and dt.hour in hour
        and dt.day in dom
        and dt.month in month
        and dt.weekday() in dow  # Python: Mon=0
    )


class CronManager:
    """Manages and runs scheduled jobs."""

    def __init__(self, cfg: Config) -> None:
        self._cfg = cfg
        self._jobs: list[CronJob] = []
        self._running = False
        self._callback: Any = None  # async callable(str) -> None
        self._last_check: int = 0

    def load_jobs(self) -> list[CronJob]:
        """Load jobs from config."""
        self._jobs.clear()
        raw_jobs = self._cfg.get("cron.jobs", [])
        for j in raw_jobs:
            self._jobs.append(CronJob(
                name=j.get("name", "unnamed"),
                schedule=j.get("schedule", ""),
                action=j.get("action", ""),
                enabled=j.get("enabled", True),
            ))
        return self._jobs

    async def save_jobs(self) -> None:
        """Save current jobs to config."""
        self._cfg.set("cron.jobs", [
            {
                "name": j.name,
                "schedule": j.schedule,
                "action": j.action,
                "enabled": j.enabled,
            }
            for j in self._jobs
        ])
        await self._cfg.save()

    def add_job(self, name: str, schedule: str, action: str) -> CronJob:
        """Add a new cron job."""
        job = CronJob(name=name, schedule=schedule, action=action)
        self._jobs.append(job)
        return job

    def remove_job(self, name: str) -> bool:
        """Remove a job by name."""
        before = len(self._jobs)
        self._jobs = [j for j in self._jobs if j.name != name]
        return len(self._jobs) < before

    def toggle_job(self, name: str) -> Optional[bool]:
        """Toggle a job's enabled state. Returns new state or None if not found."""
        for j in self._jobs:
            if j.name == name:
                j.enabled = not j.enabled
                return j.enabled
        return None

    @property
    def jobs(self) -> list[CronJob]:
        return list(self._jobs)

    async def start(self, callback: Any) -> None:
        """Start the cron loop. Callback receives the action string."""
        self._callback = callback
        self._running = True
        self.load_jobs()
        logger.info("cron manager started with %d jobs", len(self._jobs))

        while self._running:
            now = datetime.now()
            current_minute = int(now.timestamp()) // 60

            if current_minute != self._last_check:
                self._last_check = current_minute
                for job in self._jobs:
                    if job.enabled and cron_matches(job.schedule, now):
                        logger.info("firing cron job: %s", job.name)
                        try:
                            await self._callback(
                                f"[Cron Job: {job.name}] {job.action}"
                            )
                        except Exception as exc:
                            logger.error("cron job %s failed: %s", job.name, exc)

            await asyncio.sleep(30)  # check every 30s

    def stop(self) -> None:
        """Stop the cron loop."""
        self._running = False


# ── Cron Tools (for AI to manage jobs) ──────────────────────────────

from pyclaw.agent.tools import Tool


class ListCronJobsTool(Tool):
    """List all cron jobs."""

    def __init__(self) -> None:
        super().__init__(
            name="list_cron_jobs",
            description="List all scheduled cron jobs with their status.",
            parameters={"type": "object", "properties": {}},
        )
        self._cron: Optional[CronManager] = None

    def bind(self, cron: CronManager) -> None:
        self._cron = cron

    async def execute(self, **_: Any) -> str:
        if not self._cron:
            return "Cron manager not available"
        self._cron.load_jobs()
        if not self._cron.jobs:
            return "No cron jobs configured."
        lines: list[str] = []
        for j in self._cron.jobs:
            status = "✅" if j.enabled else "❌"
            lines.append(f"{status} {j.name}: '{j.schedule}' → {j.action}")
        return "\n".join(lines)


class AddCronJobTool(Tool):
    """Add a new cron job."""

    def __init__(self) -> None:
        super().__init__(
            name="add_cron_job",
            description=(
                "Add a new scheduled cron job. Schedule uses standard cron syntax "
                "(minute hour day-of-month month day-of-week). "
                "Example: '0 9 * * 1-5' runs at 9 AM on weekdays."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "name": {
                        "type": "string",
                        "description": "Unique name for the job",
                    },
                    "schedule": {
                        "type": "string",
                        "description": "Cron schedule expression",
                    },
                    "action": {
                        "type": "string",
                        "description": "What the AI should do when the job fires (a prompt)",
                    },
                },
                "required": ["name", "schedule", "action"],
            },
        )
        self.requires_confirmation = True
        self._cron: Optional[CronManager] = None

    def bind(self, cron: CronManager) -> None:
        self._cron = cron

    async def execute(self, name: str, schedule: str, action: str, **_: Any) -> str:
        if not self._cron:
            return "Cron manager not available"
        self._cron.add_job(name, schedule, action)
        await self._cron.save_jobs()
        return f"Added cron job '{name}': {schedule} → {action}"


class RemoveCronJobTool(Tool):
    """Remove a cron job."""

    def __init__(self) -> None:
        super().__init__(
            name="remove_cron_job",
            description="Remove a scheduled cron job by name.",
            parameters={
                "type": "object",
                "properties": {
                    "name": {
                        "type": "string",
                        "description": "Name of the job to remove",
                    },
                },
                "required": ["name"],
            },
        )
        self._cron: Optional[CronManager] = None

    def bind(self, cron: CronManager) -> None:
        self._cron = cron

    async def execute(self, name: str, **_: Any) -> str:
        if not self._cron:
            return "Cron manager not available"
        if self._cron.remove_job(name):
            await self._cron.save_jobs()
            return f"Removed cron job '{name}'"
        return f"Job '{name}' not found"
