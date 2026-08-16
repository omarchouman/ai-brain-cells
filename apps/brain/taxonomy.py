"""Reading and writing `taxonomy.md`, the controlled topic vocabulary.

The file is prose plus a bullet list. Writing preserves the prose and
replaces only the list, so the explanation of what a taxonomy is for
survives every edit made through the dashboard.
"""

import re
from pathlib import Path

BULLET_RE = re.compile(r"^\s*[-*]\s+(?P<topic>\S.*?)\s*$")

DEFAULT_HEADER = """# Taxonomy

The controlled vocabulary. Every note's `topics` come from this list and
nowhere else.

Keep tags `lowercase-with-hyphens`. Keep the list short — a tag earns its
place when two or more notes need it, and a vocabulary of 60 tags
retrieves worse than one of 20.
"""


def taxonomy_path(root: Path) -> Path:
    return root / "taxonomy.md"


def read_topics(root: Path) -> list[str]:
    """Every bullet in `taxonomy.md`, in file order. Missing file means none."""
    path = taxonomy_path(root)
    if not path.is_file():
        return []
    topics = []
    for line in path.read_text(encoding="utf-8").splitlines():
        match = BULLET_RE.match(line)
        if match:
            topic = match.group("topic").strip()
            if topic and topic not in topics:
                topics.append(topic)
    return topics


def read_header(root: Path) -> str:
    """The prose above the first bullet, so writing can put it back."""
    path = taxonomy_path(root)
    if not path.is_file():
        return DEFAULT_HEADER
    lines = path.read_text(encoding="utf-8").splitlines()
    kept = []
    for line in lines:
        if BULLET_RE.match(line):
            break
        kept.append(line)
    header = "\n".join(kept).strip()
    return header or DEFAULT_HEADER


def write_topics(root: Path, topics: list[str]) -> Path:
    """Replace the bullet list, keeping the prose above it intact."""
    cleaned = []
    for topic in topics:
        topic = topic.strip().lower()
        if topic and topic not in cleaned:
            cleaned.append(topic)
    cleaned.sort()

    path = taxonomy_path(root)
    header = read_header(root)
    bullets = "\n".join(f"- {topic}" for topic in cleaned)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"{header}\n\n{bullets}\n".rstrip() + "\n", encoding="utf-8")
    return path
