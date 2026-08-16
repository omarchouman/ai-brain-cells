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


def write_document(path: Path, meta: dict[str, Any], body: str) -> None:
    """Write `meta` as frontmatter above `body`, preserving key order."""
    path.parent.mkdir(parents=True, exist_ok=True)
    front = yaml.safe_dump(
        meta,
        sort_keys=False,
        allow_unicode=True,
        default_flow_style=None,
        width=1000,
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
