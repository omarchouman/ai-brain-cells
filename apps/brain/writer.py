"""Saving and deleting brain entities.

Every function here does the same two things in the same order: write the
file, then commit. The write is what must not fail; the commit is reported
back so the dashboard can mention it, and a git problem never costs you the
note you just wrote.

Renames are handled explicitly. A note's filename comes from its id, which
comes from its title — so retitling moves the file, and the old path has to
go in the same commit or the brain ends up holding both.
"""

from dataclasses import dataclass
from datetime import date
from pathlib import Path

from .index import refresh_index
from .notes import (
    FOLDER_BY_TYPE,
    IdentityDoc,
    Lens,
    Note,
    ProjectCard,
    make_note_id,
    slugify,
)
from .repo import GitResult, commit_all
from .storage import unique_path, write_document
from .taxonomy import write_topics


@dataclass
class SaveResult:
    path: Path
    git: GitResult

    @property
    def committed(self) -> bool:
        return self.git.ok


def note_path(root: Path, note: Note) -> Path:
    return Path(root) / "knowledge" / FOLDER_BY_TYPE[note.type] / f"{note.id}.md"


def project_path(root: Path, card: ProjectCard) -> Path:
    return Path(root) / "projects" / f"{card.slug}.md"


def lens_path(root: Path, lens: Lens) -> Path:
    return Path(root) / "lenses" / f"{lens.name}.md"


def identity_path(root: Path, doc: IdentityDoc) -> Path:
    return Path(root) / "identity" / f"{doc.slug}.md"


def assign_note_id(root: Path, note: Note) -> Note:
    """Give a new note an id, disambiguating if that filename is taken."""
    note.id = make_note_id(note.type, note.date, note.title)
    target = unique_path(note_path(root, note))
    note.id = target.stem
    return note


def _reindex_and_commit(root: Path, message: str) -> GitResult:
    """Regenerate INDEX.md, then commit it together with whatever changed.

    Same commit on purpose: a note and its catalog line should never arrive
    separately, or an agent reading the index sees a brain that doesn't
    match the files.
    """
    refresh_index(root)
    return commit_all(root, message)


def _write_and_commit(
    root: Path, path: Path, meta: dict, body: str, message: str, previous: Path | None
) -> SaveResult:
    write_document(path, meta, body)
    if previous and previous.resolve() != path.resolve() and previous.exists():
        previous.unlink()
    return SaveResult(path=path, git=_reindex_and_commit(root, message))


def save_note(root: Path, note: Note, previous_path: Path | None = None) -> SaveResult:
    root = Path(root)
    path = note_path(root, note)
    verb = "Edit" if previous_path else "Add"
    return _write_and_commit(
        root, path, note.to_meta(), note.body, f"{verb} {note.type}: {note.title}",
        previous_path,
    )


def save_project(
    root: Path, card: ProjectCard, previous_path: Path | None = None
) -> SaveResult:
    root = Path(root)
    card.id = f"project-{slugify(card.title)}" if not card.id else card.id
    path = project_path(root, card)
    verb = "Edit" if previous_path else "Add"
    return _write_and_commit(
        root, path, card.to_meta(), card.body, f"{verb} project: {card.title}",
        previous_path,
    )


def save_lens(root: Path, lens: Lens, previous_path: Path | None = None) -> SaveResult:
    root = Path(root)
    path = lens_path(root, lens)
    verb = "Edit" if previous_path else "Add"
    return _write_and_commit(
        root, path, lens.to_meta(), lens.body, f"{verb} lens: {lens.name}",
        previous_path,
    )


def save_identity(root: Path, doc: IdentityDoc) -> SaveResult:
    root = Path(root)
    path = identity_path(root, doc)
    return _write_and_commit(
        root, path, doc.to_meta(), doc.body, f"Edit identity: {doc.slug}.md", None
    )


def save_taxonomy(root: Path, topics: list[str]) -> SaveResult:
    root = Path(root)
    path = write_topics(root, topics)
    return SaveResult(path=path, git=_reindex_and_commit(root, "Update taxonomy"))


def delete_entity(root: Path, path: Path, message: str) -> SaveResult:
    root, path = Path(root), Path(path)
    if path.exists():
        path.unlink()
    return SaveResult(path=path, git=_reindex_and_commit(root, message))


def delete_note(root: Path, note: Note) -> SaveResult:
    return delete_entity(
        root, note.path or note_path(root, note), f"Delete {note.type}: {note.title}"
    )


def supersede_note(
    root: Path, old: Note, successor_id: str, today: date | None = None
) -> SaveResult:
    """Mark a note as history rather than deleting it.

    The contract's rule is supersede-never-delete: the brain should record
    how thinking moved, not just where it landed.
    """
    old.status = "superseded"
    old.superseded_by = successor_id
    path = old.path or note_path(root, old)
    write_document(path, old.to_meta(), old.body)
    return SaveResult(
        path=path,
        git=_reindex_and_commit(Path(root), f"Supersede {old.type}: {old.title}"),
    )
