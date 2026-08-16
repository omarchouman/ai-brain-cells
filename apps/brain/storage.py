"""Reading and writing markdown files with YAML frontmatter.

Written by hand rather than pulled from a library for two reasons: a file
with no frontmatter must be an error here (libraries tend to return empty
metadata and let the problem travel), and the key order in the output is
part of the contract, so files stay readable and diffs stay small.
"""

import hashlib
from pathlib import Path
from typing import Any

import yaml

from .errors import BrainFileError

DELIMITER = "---"


class _FrontmatterDumper(yaml.SafeDumper):
    """Block mappings, inline sequences — decided per node, not globally.

    PyYAML's `default_flow_style=None` picks per collection: inline when it
    holds only scalars, block otherwise. That is what keeps
    `topics: [django, python]` on one line — but it applied to the frontmatter
    mapping itself too, so a file whose only key was `visibility` came out as
    `{visibility: private}`. It parsed and round-tripped, which is why it went
    unnoticed, but it matched nothing else in the brain and looked broken to
    anyone opening the file.

    Setting the two node kinds separately gets both halves right regardless of
    what a given file happens to contain.
    """

    def represent_mapping(self, tag, mapping, flow_style=None):
        return super().represent_mapping(tag, mapping, flow_style=False)

    def represent_sequence(self, tag, sequence, flow_style=None):
        return super().represent_sequence(tag, sequence, flow_style=True)


def normalise_newlines(text: str) -> str:
    """Force LF.

    A browser submits `<textarea>` content with CRLF — that is the HTML spec,
    not a quirk — so every save made through the dashboard was writing Windows
    line endings into a Unix markdown repo. Nothing broke, because the parser
    splits on either, but it made `git diff` mark whole files as rewritten the
    first time anything touched them with LF, which buries the real change.
    Normalising here catches every writer at once rather than at each form.
    """
    return (text or "").replace("\r\n", "\n").replace("\r", "\n")


def write_document(path: Path, meta: dict[str, Any], body: str) -> None:
    """Write `meta` as frontmatter above `body`, preserving key order."""
    body = normalise_newlines(body)
    path.parent.mkdir(parents=True, exist_ok=True)
    front = (
        yaml.dump(
            meta,
            Dumper=_FrontmatterDumper,
            sort_keys=False,
            allow_unicode=True,
            width=1000,
        )
        if meta
        else ""
    )
    path.write_text(
        f"{DELIMITER}\n{front}{DELIMITER}\n\n{body.strip()}\n", encoding="utf-8"
    )


def read_document(path: Path) -> tuple[dict[str, Any], str]:
    """Return `(meta, body)`, raising `BrainFileError` if that isn't possible."""
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        raise BrainFileError("File does not exist.", path) from None
    except OSError as exc:
        raise BrainFileError(f"Could not read the file: {exc}", path) from exc

    lines = text.splitlines()
    if not lines or lines[0].strip() != DELIMITER:
        raise BrainFileError(
            "No frontmatter: the file must start with a '---' line.", path
        )

    try:
        closing = next(
            i for i, line in enumerate(lines[1:], start=1) if line.strip() == DELIMITER
        )
    except StopIteration:
        raise BrainFileError(
            "Unterminated frontmatter: no closing '---' line.", path
        ) from None

    try:
        meta = yaml.safe_load("\n".join(lines[1:closing]))
    except yaml.YAMLError as exc:
        raise BrainFileError(f"Frontmatter is not valid YAML: {exc}", path) from exc

    if meta is None:
        meta = {}
    if not isinstance(meta, dict):
        raise BrainFileError("Frontmatter must be a mapping of keys to values.", path)

    return meta, "\n".join(lines[closing + 1 :]).strip()


def content_fingerprint(path: Path) -> str:
    """A short hash of a file's bytes, or "" if it isn't there.

    Deliberately a content hash rather than the (mtime, size) pair the
    scanner caches on. The question here is "is this the same text I showed
    the user", which has to be exact — an edit that preserves length inside
    a filesystem's timestamp granularity is precisely the case that must not
    slip through.
    """
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()[:16]
    except OSError:
        return ""


def unique_path(path: Path) -> Path:
    """Return `path`, or the first free `name-2.md`, `name-3.md`, ... variant."""
    if not path.exists():
        return path
    for counter in range(2, 1000):
        candidate = path.with_name(f"{path.stem}-{counter}{path.suffix}")
        if not candidate.exists():
            return candidate
    raise BrainFileError("Could not find a free filename.", path)
