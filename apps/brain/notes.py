"""The entities a brain holds, and the rules that make a file one of them.

Everything here is a plain dataclass over a markdown file. There are no
Django models on purpose: the files are the source of truth, so a second
representation would only be something to keep in sync.

Parsing is strict (`from_meta` raises) and the scanner is forgiving (it
catches). That way a malformed file is one visible problem rather than a
silently wrong note.
"""

import re
import unicodedata
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Any

from .errors import BrainValidationError

NOTE_TYPES = ("take", "story", "lesson", "fact")
FOLDER_BY_TYPE = {
    "take": "takes",
    "story": "stories",
    "lesson": "lessons",
    "fact": "facts",
}
TYPE_BY_FOLDER = {folder: note_type for note_type, folder in FOLDER_BY_TYPE.items()}

NOTE_STATUSES = ("current", "superseded")
PROJECT_STATUSES = ("active", "paused", "shipped", "archived")
VISIBILITIES = ("public", "private")
IDENTITY_SLUGS = ("core", "voice", "beliefs")

MAX_TOPICS = 4
STALE_AFTER_DAYS = 45

VERBATIM_RE = re.compile(r'^>\s*VERBATIM:\s*"(?P<quote>.*)"\s*$', re.MULTILINE)


# --------------------------------------------------------------------------
# helpers


def slugify(text: str, max_length: int = 60) -> str:
    """Turn a title into a filename-safe slug."""
    value = unicodedata.normalize("NFKD", str(text))
    value = value.encode("ascii", "ignore").decode("ascii").lower()
    # Drop apostrophes rather than turning them into separators, so
    # "here's why" slugs to "heres-why" and not "here-s-why".
    value = value.replace("'", "").replace("’", "")
    value = re.sub(r"[^a-z0-9]+", "-", value).strip("-")
    if len(value) > max_length:
        value = value[:max_length].rstrip("-")
    return value or "untitled"


def make_note_id(note_type: str, month: str, title: str) -> str:
    return f"{note_type}-{month}-{slugify(title)}"


def _choice(meta: dict[str, Any], key: str, choices: tuple[str, ...], default=None):
    value = meta.get(key, default)
    if value is None:
        raise BrainValidationError(f"'{key}' is required.", key)
    value = str(value).strip()
    if value not in choices:
        raise BrainValidationError(
            f"'{key}' must be one of {', '.join(choices)} (got '{value}').", key
        )
    return value


def _text(meta: dict[str, Any], key: str, required: bool = True) -> str:
    value = meta.get(key)
    value = "" if value is None else str(value).strip()
    if required and not value:
        raise BrainValidationError(f"'{key}' is required.", key)
    return value


def _optional_text(meta: dict[str, Any], key: str) -> str | None:
    value = meta.get(key)
    value = "" if value is None else str(value).strip()
    return value or None


def _string_list(meta: dict[str, Any], key: str) -> list[str]:
    value = meta.get(key) or []
    if isinstance(value, str):
        value = [part.strip() for part in value.split(",")]
    if not isinstance(value, (list, tuple)):
        raise BrainValidationError(f"'{key}' must be a list.", key)
    return [str(item).strip() for item in value if str(item).strip()]


def _month(meta: dict[str, Any], key: str) -> str:
    """Accept `YYYY-MM` or a full date, and narrow both to `YYYY-MM`."""
    value = meta.get(key)
    if isinstance(value, (date, datetime)):
        return f"{value.year:04d}-{value.month:02d}"
    text = _text(meta, key)
    if not re.fullmatch(r"\d{4}-\d{2}(-\d{2})?", text):
        raise BrainValidationError(
            f"'{key}' must look like 2026-08 (got '{text}').", key
        )
    return text[:7]


def _date(meta: dict[str, Any], key: str) -> date:
    value = meta.get(key)
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = _text(meta, key)
    try:
        return datetime.strptime(text, "%Y-%m-%d").date()
    except ValueError:
        raise BrainValidationError(
            f"'{key}' must look like 2026-08-16 (got '{text}').", key
        ) from None


def extract_verbatim(body: str) -> str | None:
    match = VERBATIM_RE.search(body)
    return match.group("quote").strip() if match else None


# --------------------------------------------------------------------------
# entities


@dataclass
class Note:
    id: str
    type: str
    title: str
    topics: list[str] = field(default_factory=list)
    projects: list[str] = field(default_factory=list)
    status: str = "current"
    superseded_by: str | None = None
    visibility: str = "public"
    date: str = ""
    source_url: str | None = None
    body: str = ""
    path: Path | None = None

    @classmethod
    def from_meta(cls, meta: dict[str, Any], body: str, path: Path | None = None):
        note_type = _choice(meta, "type", NOTE_TYPES)
        status = _choice(meta, "status", NOTE_STATUSES, default="current")
        superseded_by = _optional_text(meta, "superseded_by")
        if status == "superseded" and not superseded_by:
            raise BrainValidationError(
                "A superseded note must name its successor in 'superseded_by'.",
                "superseded_by",
            )

        topics = _string_list(meta, "topics")
        if len(topics) > MAX_TOPICS:
            raise BrainValidationError(
                f"A note carries at most {MAX_TOPICS} topics (got {len(topics)}).",
                "topics",
            )

        return cls(
            id=_text(meta, "id"),
            type=note_type,
            title=_text(meta, "title"),
            topics=topics,
            projects=_string_list(meta, "projects"),
            status=status,
            superseded_by=superseded_by,
            visibility=_choice(meta, "visibility", VISIBILITIES, default="public"),
            date=_month(meta, "date"),
            source_url=_optional_text(meta, "source_url"),
            body=body,
            path=path,
        )

    def to_meta(self) -> dict[str, Any]:
        """Frontmatter in the order the contract documents it."""
        return {
            "id": self.id,
            "type": self.type,
            "title": self.title,
            "topics": list(self.topics),
            "projects": list(self.projects),
            "status": self.status,
            "superseded_by": self.superseded_by,
            "visibility": self.visibility,
            "date": self.date,
            "source_url": self.source_url,
        }

    @property
    def folder(self) -> str:
        return FOLDER_BY_TYPE[self.type]

    @property
    def is_current(self) -> bool:
        return self.status == "current"

    @property
    def verbatim(self) -> str | None:
        return extract_verbatim(self.body)


@dataclass
class ProjectCard:
    id: str
    title: str
    status: str = "active"
    topics: list[str] = field(default_factory=list)
    visibility: str = "public"
    last_verified: date | None = None
    url: str | None = None
    body: str = ""
    path: Path | None = None

    @classmethod
    def from_meta(cls, meta: dict[str, Any], body: str, path: Path | None = None):
        return cls(
            id=_text(meta, "id"),
            title=_text(meta, "title"),
            status=_choice(meta, "status", PROJECT_STATUSES, default="active"),
            topics=_string_list(meta, "topics"),
            visibility=_choice(meta, "visibility", VISIBILITIES, default="public"),
            last_verified=_date(meta, "last_verified"),
            url=_optional_text(meta, "url"),
            body=body,
            path=path,
        )

    def to_meta(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "type": "project",
            "title": self.title,
            "status": self.status,
            "topics": list(self.topics),
            "visibility": self.visibility,
            "last_verified": self.last_verified.isoformat()
            if self.last_verified
            else None,
            "url": self.url,
        }

    @property
    def slug(self) -> str:
        return self.id.removeprefix("project-")

    def is_stale(self, today: date | None = None) -> bool:
        """True once the card's numbers are too old to quote as current."""
        if self.last_verified is None:
            return True
        today = today or date.today()
        return (today - self.last_verified).days > STALE_AFTER_DAYS

    def days_since_verified(self, today: date | None = None) -> int | None:
        if self.last_verified is None:
            return None
        return ((today or date.today()) - self.last_verified).days


@dataclass
class Lens:
    name: str
    topics: list[str] = field(default_factory=list)
    types: list[str] = field(default_factory=lambda: list(NOTE_TYPES))
    visibility_ceiling: str = "public"
    body: str = ""
    path: Path | None = None

    @classmethod
    def from_meta(cls, meta: dict[str, Any], body: str, path: Path | None = None):
        types = _string_list(meta, "types") or list(NOTE_TYPES)
        unknown = [t for t in types if t not in NOTE_TYPES]
        if unknown:
            raise BrainValidationError(
                f"Unknown note type(s) in 'types': {', '.join(unknown)}.", "types"
            )
        return cls(
            name=_text(meta, "name"),
            topics=_string_list(meta, "topics"),
            types=types,
            visibility_ceiling=_choice(
                meta, "visibility_ceiling", VISIBILITIES, default="public"
            ),
            body=body,
            path=path,
        )

    def to_meta(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "topics": list(self.topics),
            "types": list(self.types),
            "visibility_ceiling": self.visibility_ceiling,
        }


@dataclass
class IdentityDoc:
    slug: str
    visibility: str = "private"
    body: str = ""
    path: Path | None = None

    TITLES = {
        "core": "Who I am",
        "voice": "How I write",
        "beliefs": "What I believe",
    }
    BLURBS = {
        "core": "who I am and what I'm working toward",
        "voice": "how I write; an instruction manual for agents",
        "beliefs": "positions that cut across everything",
    }

    @classmethod
    def from_meta(
        cls, meta: dict[str, Any], body: str, slug: str, path: Path | None = None
    ):
        if slug not in IDENTITY_SLUGS:
            raise BrainValidationError(
                f"Identity files are {', '.join(IDENTITY_SLUGS)} (got '{slug}').",
                "slug",
            )
        return cls(
            slug=slug,
            visibility=_choice(meta, "visibility", VISIBILITIES, default="private"),
            body=body,
            path=path,
        )

    def to_meta(self) -> dict[str, Any]:
        return {"visibility": self.visibility}

    @property
    def id(self) -> str:
        return f"identity-{self.slug}"

    @property
    def title(self) -> str:
        return self.TITLES[self.slug]

    @property
    def blurb(self) -> str:
        return self.BLURBS[self.slug]

    @property
    def is_filled_in(self) -> bool:
        """A template still full of TODOs isn't an answer yet."""
        stripped = re.sub(r"<!--.*?-->", "", self.body, flags=re.DOTALL)
        return bool(stripped.strip()) and "TODO" not in stripped
