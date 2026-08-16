"""Bounded, ranked retrieval over a brain.

The scaling limit for a tool an agent calls is not CPU — a few thousand
markdown notes match in microseconds once parsed. It is the context window.
A tool that returns everything it matched is unusable at a hundred notes and
actively harmful at a thousand, because the useful answer arrives buried in
the useless ones.

So everything here is bounded by construction:

- results are **ranked**, so a limit of ten returns the best ten rather than
  the first ten;
- list results carry **snippets**, never whole bodies;
- every listing is **paginated** and reports its total, so the caller can ask
  for more instead of being handed it;
- reading full notes is **budgeted** in both count and characters.

Nothing here imports Django or MCP. It is plain functions over the dataclasses
in `apps.brain`, which makes it testable without a server and reusable by
anything else that needs retrieval.
"""

import re
from dataclasses import dataclass, field
from typing import Any, Iterable, Sequence

from apps.brain.notes import Note, ProjectCard

WORD_RE = re.compile(r"[a-z0-9]+")

# Defaults chosen to keep a single response comfortably small. A caller that
# genuinely needs more asks for the next page.
DEFAULT_LIMIT = 10
MAX_LIMIT = 50
SNIPPET_WIDTH = 180

# Ceilings for reading full note bodies in one call.
MAX_NOTES_PER_READ = 12
MAX_CHARS_PER_READ = 24_000

# Scoring weights. Titles are written as claims and topics are a controlled
# vocabulary, so both are far stronger evidence of relevance than a body
# mention — which is why body matches are also capped: a long note should not
# outrank a precise one by repeating a word.
WEIGHT_TITLE_PHRASE = 12.0
WEIGHT_TITLE_TERM = 6.0
WEIGHT_TOPIC_TERM = 5.0
WEIGHT_VERBATIM_TERM = 4.0
WEIGHT_ID_TERM = 3.0
WEIGHT_BODY_TERM = 2.0
MAX_BODY_HITS_COUNTED = 3


def tokenize(text: str) -> list[str]:
    return WORD_RE.findall((text or "").lower())


@dataclass
class Hit:
    note: Note
    score: float
    snippet: str


@dataclass
class Page:
    """One slice of a result set, plus what it took to produce it."""

    items: list[Any] = field(default_factory=list)
    total: int = 0
    offset: int = 0
    limit: int = DEFAULT_LIMIT

    @property
    def has_more(self) -> bool:
        return self.offset + len(self.items) < self.total

    @property
    def next_offset(self) -> int | None:
        return self.offset + len(self.items) if self.has_more else None


def clamp_limit(limit: int | None) -> int:
    """Callers cannot opt out of the bound, only choose a smaller one."""
    if not limit or limit < 1:
        return DEFAULT_LIMIT
    return min(int(limit), MAX_LIMIT)


def paginate(items: Sequence[Any], limit: int | None = None, offset: int = 0) -> Page:
    limit = clamp_limit(limit)
    offset = max(0, int(offset or 0))
    return Page(
        items=list(items[offset : offset + limit]),
        total=len(items),
        offset=offset,
        limit=limit,
    )


def filter_notes(
    notes: Iterable[Note],
    *,
    note_type: str | None = None,
    topic: str | None = None,
    project: str | None = None,
    status: str | None = "current",
    include_private: bool = False,
) -> list[Note]:
    """Apply the retrieval filters, with the safe defaults up front.

    Private notes are excluded unless asked for by name. The contract says an
    agent must never quote one, and a default that silently includes them
    invites exactly that mistake — the caller has to say so deliberately.
    """
    result = []
    for note in notes:
        if note_type and note.type != note_type:
            continue
        if topic and topic not in note.topics:
            continue
        if project and project not in note.projects:
            continue
        if status and note.status != status:
            continue
        if not include_private and note.visibility == "private":
            continue
        result.append(note)
    return result


def _score(note: Note, terms: Sequence[str], phrase: str) -> float:
    if not terms:
        return 0.0

    title_tokens = tokenize(note.title)
    topic_tokens = {t for topic in note.topics for t in tokenize(topic)}
    id_tokens = set(tokenize(note.id))
    verbatim_tokens = set(tokenize(note.verbatim or ""))
    body_tokens = tokenize(note.body)

    matched = 0
    score = 0.0
    for term in terms:
        hit = False
        if term in title_tokens:
            score += WEIGHT_TITLE_TERM
            hit = True
        if term in topic_tokens:
            score += WEIGHT_TOPIC_TERM
            hit = True
        if term in verbatim_tokens:
            score += WEIGHT_VERBATIM_TERM
            hit = True
        if term in id_tokens:
            score += WEIGHT_ID_TERM
            hit = True
        body_hits = min(body_tokens.count(term), MAX_BODY_HITS_COUNTED)
        if body_hits:
            score += WEIGHT_BODY_TERM * body_hits
            hit = True
        if hit:
            matched += 1

    if not matched:
        return 0.0

    if phrase and phrase in note.title.lower():
        score += WEIGHT_TITLE_PHRASE

    # Every term matching somewhere beats a single term matching loudly.
    score *= matched / len(terms)
    return score


def snippet(body: str, terms: Sequence[str], width: int = SNIPPET_WIDTH) -> str:
    """A short window of the body around the first matching term."""
    text = re.sub(r"\s+", " ", (body or "").replace("> VERBATIM:", "")).strip()
    if not text:
        return ""
    if len(text) <= width:
        return text

    lowered = text.lower()
    position = -1
    for term in terms:
        found = lowered.find(term)
        if found != -1 and (position == -1 or found < position):
            position = found

    if position == -1:
        return text[:width].rstrip() + "…"

    start = max(0, position - width // 3)
    excerpt = text[start : start + width].strip()
    return ("…" if start else "") + excerpt + ("…" if start + width < len(text) else "")


def search(
    notes: Iterable[Note],
    query: str,
    *,
    limit: int | None = None,
    offset: int = 0,
    note_type: str | None = None,
    topic: str | None = None,
    project: str | None = None,
    include_private: bool = False,
    include_superseded: bool = True,
) -> Page:
    """Rank notes against a query and return one bounded page of hits.

    Superseded notes are searchable by default and labelled in the result.
    Hiding them means someone searching an exact phrase they remember writing
    is told it does not exist — the default list view is the right place to
    keep history out of the way, not the search.
    """
    candidates = filter_notes(
        notes,
        note_type=note_type,
        topic=topic,
        project=project,
        status=None if include_superseded else "current",
        include_private=include_private,
    )

    terms = tokenize(query)
    phrase = " ".join(terms)
    if not terms:
        return Page(items=[], total=0, offset=offset, limit=clamp_limit(limit))

    hits = []
    for note in candidates:
        score = _score(note, terms, phrase)
        if score > 0:
            hits.append(Hit(note=note, score=score, snippet=snippet(note.body, terms)))

    # Best first; newest breaks ties so equally-relevant notes surface the
    # current thinking rather than the oldest.
    hits.sort(key=lambda h: (h.score, h.note.date), reverse=True)
    return paginate(hits, limit=limit, offset=offset)


@dataclass
class ReadResult:
    notes: list[Note] = field(default_factory=list)
    missing: list[str] = field(default_factory=list)
    skipped_for_budget: list[str] = field(default_factory=list)
    truncated: bool = False


def read_notes(
    notes: Iterable[Note],
    ids: Sequence[str],
    *,
    include_private: bool = False,
    max_notes: int = MAX_NOTES_PER_READ,
    max_chars: int = MAX_CHARS_PER_READ,
) -> ReadResult:
    """Fetch full bodies for specific notes, under a hard budget.

    Reading is where a caller can blow its own context in one call, so both
    the count and the total size are capped. Anything dropped is named in the
    result rather than silently omitted, so the caller can ask again.
    """
    by_id = {note.id: note for note in notes}
    result = ReadResult()
    used = 0

    for note_id in ids:
        note = by_id.get(note_id)
        if note is None:
            result.missing.append(note_id)
            continue
        if not include_private and note.visibility == "private":
            result.missing.append(note_id)
            continue
        if len(result.notes) >= max_notes or used + len(note.body) > max_chars:
            result.skipped_for_budget.append(note_id)
            result.truncated = True
            continue
        result.notes.append(note)
        used += len(note.body)

    return result


def stale_projects(cards: Iterable[ProjectCard], today=None) -> list[ProjectCard]:
    return [card for card in cards if card.is_stale(today)]


def topic_counts(notes: Iterable[Note]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for note in notes:
        for topic in note.topics:
            counts[topic] = counts.get(topic, 0) + 1
    return counts
