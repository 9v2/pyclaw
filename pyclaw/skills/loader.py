"""Async skill loader with install/remove support.

Each skill lives in ``<workspace>/skills/<name>/SKILL.md``.  Skills can be
installed from URLs, local paths, or the bundled defaults.
"""

from __future__ import annotations

import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import aiohttp
import aiofiles


@dataclass(slots=True)
class Skill:
    """A loaded skill."""

    name: str
    description: Optional[str]
    content: str
    path: Path


class SkillsManager:
    """Discovers, loads, installs, and removes skills.

    Usage::

        mgr = SkillsManager(workspace_path)
        await mgr.load()
        prompt_block = mgr.as_prompt()
        await mgr.install_from_url("https://example.com/skills/browser.tar.gz")
    """

    __slots__ = ("_workspace", "_skills")

    def __init__(self, workspace: Path) -> None:
        self._workspace = workspace
        self._skills: list[Skill] = []

    # ── Public API ──────────────────────────────────────────────────

    async def load(self) -> list[Skill]:
        """Scan the workspace skills directory and load all SKILL.md files."""
        self._skills.clear()
        skills_dir = self._workspace / "skills"

        if not skills_dir.is_dir():
            return self._skills

        for child in sorted(skills_dir.iterdir()):
            if not child.is_dir():
                continue
            skill_file = child / "SKILL.md"
            if not skill_file.is_file():
                continue
            skill = await self._parse_skill(child.name, skill_file)
            if skill:
                self._skills.append(skill)

        return self._skills

    @property
    def skills(self) -> list[Skill]:
        return list(self._skills)

    def as_prompt(self) -> str:
        """Build the skills block to inject into the system prompt."""
        if not self._skills:
            return ""

        parts: list[str] = ["<skills>"]
        for skill in self._skills:
            parts.append(f"\n## Skill: {skill.name}")
            if skill.description:
                parts.append(f"_{skill.description}_\n")
            parts.append(skill.content)
        parts.append("\n</skills>")
        return "\n".join(parts)

    # ── Install ─────────────────────────────────────────────────────

    async def install_from_path(self, source: Path, name: str | None = None) -> Skill | None:
        """Install a skill from a local directory or SKILL.md file."""
        skills_dir = self._workspace / "skills"
        skills_dir.mkdir(parents=True, exist_ok=True)

        if source.is_file() and source.name == "SKILL.md":
            skill_name = name or source.parent.name
            target = skills_dir / skill_name
            target.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target / "SKILL.md")
        elif source.is_dir():
            skill_name = name or source.name
            target = skills_dir / skill_name
            if target.exists():
                shutil.rmtree(target)
            shutil.copytree(source, target)
        else:
            return None

        # Reload and return the newly installed skill
        skill_file = skills_dir / skill_name / "SKILL.md"
        if skill_file.exists():
            return await self._parse_skill(skill_name, skill_file)
        return None

    async def install_from_url(self, url: str) -> Skill | None:
        """Install a skill from a URL.

        Supports:
        - Direct SKILL.md URL
        - .tar.gz / .zip archives containing a skill directory
        """
        skills_dir = self._workspace / "skills"
        skills_dir.mkdir(parents=True, exist_ok=True)

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    url,
                    timeout=aiohttp.ClientTimeout(total=30),
                ) as resp:
                    if resp.status != 200:
                        return None
                    content = await resp.read()
                    content_type = resp.headers.get("Content-Type", "")

            # Determine type
            if url.endswith(".md") or "text/" in content_type:
                # Direct SKILL.md
                name = url.rsplit("/", 2)[-2] if "/" in url else "downloaded"
                target = skills_dir / name
                target.mkdir(parents=True, exist_ok=True)
                (target / "SKILL.md").write_bytes(content)
                return await self._parse_skill(name, target / "SKILL.md")

            elif url.endswith(".tar.gz") or url.endswith(".tgz"):
                import tarfile
                with tempfile.TemporaryDirectory() as tmp:
                    archive = Path(tmp) / "skill.tar.gz"
                    archive.write_bytes(content)
                    with tarfile.open(archive, "r:gz") as tar:
                        tar.extractall(tmp)
                    # Find SKILL.md
                    for md in Path(tmp).rglob("SKILL.md"):
                        skill_dir = md.parent
                        return await self.install_from_path(skill_dir)

            elif url.endswith(".zip"):
                import zipfile
                with tempfile.TemporaryDirectory() as tmp:
                    archive = Path(tmp) / "skill.zip"
                    archive.write_bytes(content)
                    with zipfile.ZipFile(archive, "r") as zf:
                        zf.extractall(tmp)
                    for md in Path(tmp).rglob("SKILL.md"):
                        skill_dir = md.parent
                        return await self.install_from_path(skill_dir)

        except Exception:
            return None
        return None

    def remove(self, name: str) -> bool:
        """Remove an installed skill by name."""
        target = self._workspace / "skills" / name
        if target.exists():
            shutil.rmtree(target)
            self._skills = [s for s in self._skills if s.name != name]
            return True
        return False

    def list_names(self) -> list[str]:
        """List installed skill names."""
        skills_dir = self._workspace / "skills"
        if not skills_dir.is_dir():
            return []
        return sorted(
            d.name for d in skills_dir.iterdir()
            if d.is_dir() and (d / "SKILL.md").exists()
        )

    # ── Install defaults ────────────────────────────────────────────

    async def install_defaults(self) -> None:
        """Copy bundled default skills into the workspace if absent."""
        skills_dir = self._workspace / "skills"
        skills_dir.mkdir(parents=True, exist_ok=True)

        defaults_root = Path(__file__).parent / "defaults"
        if not defaults_root.is_dir():
            return

        for skill_dir in sorted(defaults_root.iterdir()):
            if not skill_dir.is_dir():
                continue
            target = skills_dir / skill_dir.name
            if target.exists():
                continue
            shutil.copytree(skill_dir, target)

    # ── Internals ───────────────────────────────────────────────────

    @staticmethod
    async def _parse_skill(name: str, path: Path) -> Skill | None:
        """Read a SKILL.md and extract optional YAML front-matter."""
        async with aiofiles.open(path, "r") as f:
            raw = await f.read()

        description: str | None = None
        content = raw

        if raw.startswith("---"):
            parts = raw.split("---", 2)
            if len(parts) >= 3:
                frontmatter = parts[1].strip()
                content = parts[2].strip()
                for line in frontmatter.splitlines():
                    if line.startswith("description:"):
                        description = line.split(":", 1)[1].strip().strip("\"'")
                    elif line.startswith("name:"):
                        name = line.split(":", 1)[1].strip().strip("\"'")

        return Skill(name=name, description=description, content=content, path=path)
