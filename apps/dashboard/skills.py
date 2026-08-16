"""Installing the two skills into `~/.claude/skills/`.

Installing globally rather than into the brain folder is what makes the
brain available from every project you open, instead of only when Claude
Code happens to be pointed at the brain itself. The cost is that the skill
files have to carry an absolute path, which is why they are templates with
`{{BRAIN_PATH}}` in them rather than files that can just be copied.

Nothing here runs on its own. Writing outside the project is always an
explicit action the user takes.
"""

from dataclasses import dataclass
from pathlib import Path

from django.conf import settings

SKILL_NAMES = ("mind-reader", "mind-feeder")
PLACEHOLDER = "{{BRAIN_PATH}}"

NOT_INSTALLED = "not-installed"
INSTALLED = "installed"
STALE = "stale"


@dataclass
class SkillStatus:
    name: str
    state: str
    path: Path
    summary: str

    @property
    def is_installed(self) -> bool:
        return self.state in (INSTALLED, STALE)


def source_dir() -> Path:
    return Path(settings.SKILLS_SOURCE_PATH)


def install_dir() -> Path:
    return Path(settings.CLAUDE_SKILLS_PATH)


def render(name: str, brain_path: Path) -> str:
    """The skill file with the brain's real location substituted in."""
    text = (source_dir() / name / "SKILL.md").read_text(encoding="utf-8")
    return text.replace(PLACEHOLDER, str(brain_path))


def _summary(name: str) -> str:
    """The `description:` line, which is what decides when Claude reaches for it."""
    for line in (source_dir() / name / "SKILL.md").read_text().splitlines():
        if line.startswith("description:"):
            return line.removeprefix("description:").strip()
    return ""


def status(brain_path: Path) -> list[SkillStatus]:
    results = []
    for name in SKILL_NAMES:
        target = install_dir() / name / "SKILL.md"
        if not target.is_file():
            state = NOT_INSTALLED
        else:
            try:
                current = target.read_text(encoding="utf-8")
            except OSError:
                current = ""
            state = INSTALLED if current == render(name, brain_path) else STALE
        results.append(
            SkillStatus(name=name, state=state, path=target, summary=_summary(name))
        )
    return results


def install(brain_path: Path) -> list[Path]:
    """Write both skills, overwriting whatever is there. Returns the paths."""
    written = []
    for name in SKILL_NAMES:
        target = install_dir() / name / "SKILL.md"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(render(name, brain_path), encoding="utf-8")
        written.append(target)
    return written


def uninstall() -> list[Path]:
    """Remove the two SKILL.md files, and their folders if now empty.

    Deliberately narrow: only the files this tool wrote, and a folder is
    only removed if nothing else is in it.
    """
    removed = []
    for name in SKILL_NAMES:
        target = install_dir() / name / "SKILL.md"
        if target.is_file():
            target.unlink()
            removed.append(target)
        folder = target.parent
        if folder.is_dir() and not any(folder.iterdir()):
            folder.rmdir()
    return removed
