"""Generating `INDEX.md`, the catalog an agent reads before opening anything.

Every line has one job: give an agent enough to decide whether this file is
worth opening, and nothing more. That is why note titles are written as
claims — the title *is* the index entry.

The index is regenerated on every save and committed alongside the change
that caused it, so a note and its catalog line never arrive separately.
"""

from pathlib import Path

from .notes import IDENTITY_SLUGS, NOTE_TYPES

PREAMBLE = """One line per entity. This is the catalog agents read first to
decide what to open, so a line says enough to make that decision and no more.

Format: `` `id` — title [status] [visibility] ``

**Generated file — do not edit by hand.** The dashboard rewrites it whenever
the brain changes."""

SECTION_TITLES = {
    "take": "takes",
    "story": "stories",
    "lesson": "lessons",
    "fact": "facts",
}

EMPTY = "_Empty._"


def _first_sentence(text: str) -> str:
    """The opening line of a body, for entities with no title field."""
    for line in text.splitlines():
        line = line.strip()
        if line and not line.startswith(("#", "<!--", ">")):
            return line.rstrip(".")
    return ""


def _line(entity_id: str, description: str, *tags: str) -> str:
    suffix = "".join(f" [{tag}]" for tag in tags if tag)
    return f"- `{entity_id}` — {description}{suffix}"


def render_index(brain) -> str:
    parts = ["# INDEX", "", PREAMBLE, "", "## identity", ""]

    identity_lines = [
        _line(doc.id, doc.blurb, "written" if doc.is_filled_in else "todo", doc.visibility)
        for slug in IDENTITY_SLUGS
        if (doc := brain.identity.get(slug))
    ]
    parts += identity_lines or [EMPTY]

    parts += ["", "## projects", ""]
    project_lines = [
        _line(card.id, card.title, card.status, card.visibility)
        for card in brain.projects
    ]
    parts += project_lines or [EMPTY]

    parts += ["", "## knowledge", ""]
    if not brain.notes:
        parts.append(EMPTY)
    else:
        for note_type in NOTE_TYPES:
            notes = brain.notes_of_type(note_type)
            if not notes:
                continue
            parts += [f"### {SECTION_TITLES[note_type]}", ""]
            parts += [
                _line(note.id, note.title, note.status, note.visibility)
                for note in notes
            ]
            parts.append("")
        parts.pop()

    parts += ["", "## lenses", ""]
    lens_lines = [
        _line(f"lens-{lens.name}", _first_sentence(lens.body) or lens.name,
              lens.visibility_ceiling)
        for lens in brain.lenses
    ]
    parts += lens_lines or [EMPTY]

    return "\n".join(parts).strip() + "\n"


def index_path(root: Path) -> Path:
    return Path(root) / "INDEX.md"


def refresh_index(root: Path) -> Path | None:
    """Rewrite `INDEX.md` from what is currently on disk."""
    from .scanner import scan_brain

    root = Path(root)
    if not root.is_dir():
        return None
    path = index_path(root)
    path.write_text(render_index(scan_brain(root)), encoding="utf-8")
    return path
