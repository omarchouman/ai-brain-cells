"""Turning note bodies into HTML, and splitting the voice line back out.

The VERBATIM line is stored in the body — it is part of the markdown file
and stays readable in any editor — but the dashboard edits it as its own
field, so that the one thing that makes a note sound like you is a box you
have to look at rather than a convention you forget.
"""

import re

import markdown as markdown_lib
from django.utils.safestring import mark_safe

from apps.brain.notes import VERBATIM_RE

_RENDERER = markdown_lib.Markdown(extensions=["extra", "sane_lists"])


def render_markdown(text: str) -> str:
    _RENDERER.reset()
    return mark_safe(_RENDERER.convert(text or ""))


def split_verbatim(body: str) -> tuple[str, str]:
    """Return `(prose, verbatim)` for editing them as separate fields."""
    match = VERBATIM_RE.search(body or "")
    if not match:
        return (body or "").strip(), ""
    prose = VERBATIM_RE.sub("", body, count=1)
    return re.sub(r"\n{3,}", "\n\n", prose).strip(), match.group("quote").strip()


def join_verbatim(prose: str, verbatim: str) -> str:
    """Compose the stored body from the two fields.

    The quote is appended rather than woven back into wherever it sat. A
    hand-written note with the quote in the middle therefore has it moved to
    the end the first time it is saved here — normalising, not destructive,
    and the form says so.
    """
    prose = (prose or "").strip()
    verbatim = " ".join((verbatim or "").split()).strip().strip('"')
    if not verbatim:
        return prose
    block = f'> VERBATIM: "{verbatim}"'
    return f"{prose}\n\n{block}".strip()
