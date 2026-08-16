"""Compact text renderings of brain entities.

Tool results are read by a model, so the format is optimised for information
per token rather than for looking like a document: one line per entity, the
identifier the caller needs to fetch it, and the flags that change how it may
be used. No headings, no framing prose, no repetition of what the tool
already said it was returning.
"""

from apps.brain.notes import STALE_AFTER_DAYS, IdentityDoc, Lens, Note, ProjectCard

from .retrieval import Hit, Page, ReadResult


def _flags(note: Note) -> str:
    flags = [note.type, note.date]
    if note.verbatim:
        flags.append("voice")
    if note.visibility == "private":
        flags.append("PRIVATE")
    if note.status == "superseded":
        flags.append(f"SUPERSEDED→{note.superseded_by}")
    return " · ".join(flags)


def note_line(note: Note) -> str:
    line = f"[{_flags(note)}] {note.title}\n  id: {note.id}"
    if note.topics:
        line += f"\n  topics: {', '.join(note.topics)}"
    return line


def render_hits(page: Page, query: str) -> str:
    if not page.items:
        return (
            f'No notes match "{query}". The brain may simply not cover this — '
            f"say so rather than answering as though it did."
        )

    lines = [
        f'{page.total} note(s) match "{query}"; showing {len(page.items)} '
        f"from offset {page.offset}."
    ]
    for hit in page.items:
        entry = note_line(hit.note)
        if hit.snippet:
            entry += f"\n  {hit.snippet}"
        lines.append(entry)

    if page.has_more:
        lines.append(
            f"More available — call again with offset={page.next_offset}. "
            f"Prefer refining the query over paging blindly."
        )
    return "\n\n".join(lines)


def render_note_list(page: Page, heading: str) -> str:
    if not page.items:
        return f"{heading}: nothing found."
    lines = [f"{heading}: {page.total} total, showing {len(page.items)} from offset {page.offset}."]
    lines += [note_line(note) for note in page.items]
    if page.has_more:
        lines.append(f"More available — call again with offset={page.next_offset}.")
    return "\n\n".join(lines)


def render_full_notes(result: ReadResult) -> str:
    blocks = []
    for note in result.notes:
        header = f"--- {note.id} [{_flags(note)}] ---\n{note.title}"
        if note.topics:
            header += f"\ntopics: {', '.join(note.topics)}"
        if note.source_url:
            header += f"\nsource: {note.source_url}"
        blocks.append(f"{header}\n\n{note.body}")

    if result.missing:
        blocks.append(
            "Not returned (unknown id, or private and not requested): "
            + ", ".join(result.missing)
        )
    if result.skipped_for_budget:
        blocks.append(
            "Skipped to stay within the response budget — request these in a "
            "follow-up call if you still need them: "
            + ", ".join(result.skipped_for_budget)
        )
    return "\n\n".join(blocks) if blocks else "Nothing to return."


def render_identity(docs: list[IdentityDoc]) -> str:
    if not docs:
        return "This brain has no identity files yet."
    blocks = []
    for doc in docs:
        state = "" if doc.is_filled_in else "  [STILL A TEMPLATE — do not treat as written]"
        blocks.append(f"--- identity/{doc.slug}.md{state} ---\n{doc.body}")
    return "\n\n".join(blocks)


def render_projects(cards: list[ProjectCard]) -> str:
    if not cards:
        return "No project cards."
    lines = []
    for card in cards:
        days = card.days_since_verified()
        stale = card.is_stale()
        marker = (
            f" · UNVERIFIED {days}d — do not present its numbers or status as "
            f"current; hedge with the date or omit"
            if stale
            else f" · verified {card.last_verified}"
        )
        entry = f"[{card.status}{marker}] {card.title}\n  id: {card.id} (slug: {card.slug})"
        if card.topics:
            entry += f"\n  topics: {', '.join(card.topics)}"
        if card.url:
            entry += f"\n  lives at: {card.url}"
        lines.append(entry)
    return "\n\n".join(lines)


def render_project(card: ProjectCard) -> str:
    days = card.days_since_verified()
    header = f"--- {card.id} [{card.status}] ---\n{card.title}"
    if card.url:
        header += f"\nlives at: {card.url}"
    header += f"\nlast verified: {card.last_verified} ({days} days ago)"
    if card.is_stale():
        header += (
            f"\nSTALE: past {STALE_AFTER_DAYS} days. Do not state its numbers or "
            f"status as current — hedge with the date, or leave them out."
        )
    return f"{header}\n\n{card.body}"


def render_lenses(lenses: list[Lens]) -> str:
    if not lenses:
        return "No lenses defined. Work open: all topics, excluding private notes."
    lines = []
    for lens in lenses:
        entry = f"{lens.name}\n  types: {', '.join(lens.types)}"
        entry += f"\n  topics: {', '.join(lens.topics) if lens.topics else 'all'}"
        entry += f"\n  visibility ceiling: {lens.visibility_ceiling}"
        if lens.body:
            entry += f"\n  {lens.body.splitlines()[0]}"
        lines.append(entry)
    return "\n\n".join(lines)
