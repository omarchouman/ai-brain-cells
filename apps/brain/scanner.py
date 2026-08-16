"""Walking the brain directory and turning it into one in-memory snapshot.

The filesystem is the index. Every request re-walks the tree, but parsed
files are cached by (mtime, size) so the work is a `stat()` per file rather
than a parse. A brain of a few hundred notes scans in single-digit
milliseconds, and in exchange there is no second copy of your content to
fall out of sync with the files.

Nothing here raises on a bad file. A file that cannot be parsed becomes a
`BrokenFile` in the snapshot, so one typo shows up as one item needing
attention instead of a 500.
"""

from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any, Callable

from .errors import BrainError
from .notes import (
    IDENTITY_SLUGS,
    NOTE_TYPES,
    TYPE_BY_FOLDER,
    IdentityDoc,
    Lens,
    Note,
    ProjectCard,
)
from .storage import read_document
from .taxonomy import read_topics

# path -> (mtime_ns, size, parsed entity or BrokenFile)
_CACHE: dict[str, tuple[int, int, Any]] = {}


def clear_cache() -> None:
    _CACHE.clear()


@dataclass
class BrokenFile:
    path: Path
    message: str

    @property
    def name(self) -> str:
        return self.path.name


@dataclass
class Brain:
    root: Path
    exists: bool = False
    notes: list[Note] = field(default_factory=list)
    projects: list[ProjectCard] = field(default_factory=list)
    lenses: list[Lens] = field(default_factory=list)
    identity: dict[str, IdentityDoc] = field(default_factory=dict)
    topics: list[str] = field(default_factory=list)
    broken: list[BrokenFile] = field(default_factory=list)

    def note(self, note_id: str) -> Note | None:
        return next((n for n in self.notes if n.id == note_id), None)

    def project(self, slug: str) -> ProjectCard | None:
        return next((p for p in self.projects if p.slug == slug), None)

    def lens(self, name: str) -> Lens | None:
        return next((lens for lens in self.lenses if lens.name == name), None)

    def notes_of_type(self, note_type: str) -> list[Note]:
        return [n for n in self.notes if n.type == note_type]

    def counts_by_type(self) -> dict[str, int]:
        return {t: len(self.notes_of_type(t)) for t in NOTE_TYPES}

    def stale_projects(self, today: date | None = None) -> list[ProjectCard]:
        return [p for p in self.projects if p.is_stale(today)]

    @property
    def is_empty(self) -> bool:
        return not (self.notes or self.projects)


def _load(path: Path, loader: Callable[[Path], Any], use_cache: bool) -> Any:
    """Parse `path`, reusing the cached result while mtime and size hold."""
    try:
        stat = path.stat()
    except OSError as exc:
        return BrokenFile(path, f"Could not stat the file: {exc}")

    key = str(path)
    fingerprint = (stat.st_mtime_ns, stat.st_size)
    if use_cache:
        cached = _CACHE.get(key)
        if cached and cached[:2] == fingerprint:
            return cached[2]

    try:
        result = loader(path)
    except BrainError as exc:
        result = BrokenFile(path, getattr(exc, "message", str(exc)))

    _CACHE[key] = (*fingerprint, result)
    return result


def _is_content(path: Path) -> bool:
    """Templates and folder READMEs are infrastructure, not content."""
    return not (path.name.startswith("_") or path.name == "README.md")


def _markdown_files(directory: Path) -> list[Path]:
    if not directory.is_dir():
        return []
    return sorted(p for p in directory.glob("*.md") if p.is_file() and _is_content(p))


def _load_note(path: Path) -> Note:
    meta, body = read_document(path)
    return Note.from_meta(meta, body, path=path)


def _load_project(path: Path) -> ProjectCard:
    meta, body = read_document(path)
    return ProjectCard.from_meta(meta, body, path=path)


def _load_lens(path: Path) -> Lens:
    meta, body = read_document(path)
    return Lens.from_meta(meta, body, path=path)


def _load_identity(path: Path) -> IdentityDoc:
    meta, body = read_document(path)
    return IdentityDoc.from_meta(meta, body, slug=path.stem, path=path)


def scan_brain(root: Path, use_cache: bool = True) -> Brain:
    """Walk `root` and return a snapshot of everything in it."""
    root = Path(root)
    brain = Brain(root=root)
    if not root.is_dir():
        return brain

    brain.exists = True
    brain.topics = read_topics(root)
    seen: set[str] = set()

    def collect(path: Path, loader) -> Any:
        seen.add(str(path))
        result = _load(path, loader, use_cache)
        if isinstance(result, BrokenFile):
            brain.broken.append(result)
            return None
        return result

    for folder, note_type in TYPE_BY_FOLDER.items():
        for path in _markdown_files(root / "knowledge" / folder):
            note = collect(path, _load_note)
            if note is None:
                continue
            if note.type != note_type:
                brain.broken.append(
                    BrokenFile(
                        path,
                        f"A '{note.type}' note is filed under knowledge/{folder}/. "
                        f"Move it, or change its type.",
                    )
                )
                continue
            brain.notes.append(note)

    for path in _markdown_files(root / "projects"):
        card = collect(path, _load_project)
        if card is not None:
            brain.projects.append(card)

    for path in _markdown_files(root / "lenses"):
        lens = collect(path, _load_lens)
        if lens is not None:
            brain.lenses.append(lens)

    for slug in IDENTITY_SLUGS:
        path = root / "identity" / f"{slug}.md"
        if path.is_file():
            doc = collect(path, _load_identity)
            if doc is not None:
                brain.identity[slug] = doc

    _reject_unknown_topics(brain)

    brain.notes.sort(key=lambda n: n.title.lower())
    brain.notes.sort(key=lambda n: n.date, reverse=True)
    brain.projects.sort(key=lambda p: p.title.lower())
    brain.lenses.sort(key=lambda lens: lens.name)
    brain.broken.sort(key=lambda b: str(b.path))

    _prune_cache(root, seen)
    return brain


def _reject_unknown_topics(brain: Brain) -> None:
    """Tags come only from taxonomy.md — an ad-hoc tag is a broken file.

    Skipped entirely when the taxonomy is empty, so a brain that hasn't set
    one up yet isn't reported as entirely broken.
    """
    if not brain.topics:
        return
    vocabulary = set(brain.topics)

    def partition(items):
        kept = []
        for item in items:
            unknown = [t for t in item.topics if t not in vocabulary]
            if unknown:
                brain.broken.append(
                    BrokenFile(
                        item.path,
                        f"Topic(s) not in taxonomy.md: {', '.join(unknown)}. "
                        f"Add them to the taxonomy, or fix the note.",
                    )
                )
            else:
                kept.append(item)
        return kept

    brain.notes = partition(brain.notes)
    brain.projects = partition(brain.projects)


def _prune_cache(root: Path, seen: set[str]) -> None:
    prefix = str(root)
    for key in [k for k in _CACHE if k.startswith(prefix) and k not in seen]:
        del _CACHE[key]
