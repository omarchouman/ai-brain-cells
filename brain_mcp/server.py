"""An MCP server that serves one brain, read-only, over stdio.

Claude Desktop launches this as a subprocess on the same machine as the
brain, so nothing is hosted and nothing is exposed — the files never leave
the disk they live on.

**Read-only on purpose.** The contract's rule is that agents propose and the
owner approves; a write tool here would hand an agent silent, unreviewed
write access to the one artefact this project exists to keep trustworthy.
Writing stays in the dashboard and in mind-feeder, where a human sees the
change before it lands.

The retrieval rules that keep an agent honest — never quote a private note,
never present a superseded take as current, hedge on stale project numbers,
anchor on the owner's own words — are carried in the server instructions and
repeated in the tool descriptions, so the server behaves correctly for a
client that has never seen the mind-reader skill.
"""

from pathlib import Path

from mcp.server import MCPServer

from apps.brain.index import render_index
from apps.brain.notes import IDENTITY_SLUGS, NOTE_TYPES
from apps.brain.scanner import scan_brain

from . import formatting
from .retrieval import (
    DEFAULT_LIMIT,
    filter_notes,
    paginate,
    search,
    topic_counts,
)
from .retrieval import read_notes as read_notes_budgeted

SERVER_NAME = "ai-brain-cells"
SERVER_VERSION = "1.0.0"

# "storys" is not a word; the note types don't pluralise uniformly.
TYPE_PLURALS = {"take": "takes", "story": "stories", "lesson": "lessons", "fact": "facts"}

INSTRUCTIONS = """\
This server serves one person's brain: a git repo of markdown holding who
they are, how they write, what they believe, what they're building, and what
they have concluded. Use it before writing anything in their name or voice,
answering questions about their work, or stating what their position on
something is.

How to retrieve well:

1. Call `brain_overview` once to see what is in there.
2. Call `get_identity` before any task that writes in their voice. It is
   small, and it is the reason output sounds like them rather than like
   anyone.
3. Use `search_brain` to find candidates, then `read_notes` on the few ids
   worth opening. A typical answer needs the identity core plus two to five
   notes — not the whole brain.

Rules that are not negotiable:

- Never quote a `private` note or surface its content in anything the
  audience sees. It is background only, and it is excluded from results
  unless explicitly requested.
- Never present a `superseded` note as a current position. It is what they
  used to think, and results label it.
- If a project card is marked unverified past 45 days, do not state its
  numbers or status as current — hedge with the date, or leave them out.
- Where a note carries a `> VERBATIM: "..."` line, that is their actual
  phrasing. Adapt those words rather than summarising them into cleaner
  prose; the quote is the point of the note.
- If the brain has nothing relevant, say so plainly and answer from general
  knowledge without implying it came from the brain.

This server is read-only. To add or change a note, the owner uses their
dashboard — propose the text and let them approve it.
"""


def build_server(brain_root: Path, name: str = SERVER_NAME) -> MCPServer:
    """Wire the tools against one brain directory."""
    brain_root = Path(brain_root)
    server = MCPServer(
        name=name,
        version=SERVER_VERSION,
        title="AI Brain Cells",
        description="Read one person's markdown brain: identity, voice, takes, stories, lessons, facts, projects.",
        instructions=INSTRUCTIONS,
    )

    def load():
        """Re-read the brain.

        Every call re-scans, so an edit made in the dashboard or an editor is
        visible immediately. The scanner caches parsed files by fingerprint,
        so in practice this costs a stat() per file rather than a parse.
        """
        return scan_brain(brain_root)

    def _missing() -> str:
        return (
            f"No brain found at {brain_root}. The owner has not created one yet, "
            f"or this server is pointed at the wrong path."
        )

    @server.tool()
    def brain_overview() -> str:
        """Orient yourself in this brain before retrieving from it.

        Returns how many notes of each kind exist, which topics are in use,
        whether the identity files are actually written, and anything needing
        attention. Cheap — call it first when you don't know what is in here.
        """
        brain = load()
        if not brain.exists:
            return _missing()

        current = [n for n in brain.notes if n.is_current]
        counts = {t: len([n for n in current if n.type == t]) for t in NOTE_TYPES}
        lines = [
            f"Brain at {brain_root}",
            "Notes: " + ", ".join(f"{n} {TYPE_PLURALS[t]}" for t, n in counts.items()),
        ]

        superseded = len(brain.notes) - len(current)
        if superseded:
            lines.append(f"Plus {superseded} superseded note(s) — history, not positions.")

        private = len([n for n in brain.notes if n.visibility == "private"])
        if private:
            lines.append(
                f"{private} note(s) are private: background only, never quoted, "
                f"and excluded from results unless explicitly requested."
            )

        identity_state = []
        for slug in IDENTITY_SLUGS:
            doc = brain.identity.get(slug)
            if doc is None:
                identity_state.append(f"{slug}: missing")
            elif doc.is_filled_in:
                identity_state.append(f"{slug}: written")
            else:
                identity_state.append(f"{slug}: still a template")
        lines.append("Identity — " + "; ".join(identity_state))

        used = topic_counts(current)
        if used:
            ranked = sorted(used.items(), key=lambda kv: -kv[1])[:20]
            lines.append("Topics in use: " + ", ".join(f"{t} ({n})" for t, n in ranked))
        if brain.projects:
            lines.append(f"Projects: {len(brain.projects)} card(s) — call list_projects.")
        if brain.lenses:
            lines.append(f"Lenses: {', '.join(l.name for l in brain.lenses)}")
        if brain.broken:
            lines.append(
                f"{len(brain.broken)} file(s) could not be parsed and are invisible "
                f"to retrieval: " + ", ".join(b.name for b in brain.broken)
            )
        return "\n".join(lines)

    @server.tool()
    def search_brain(
        query: str,
        type: str = "",
        topic: str = "",
        project: str = "",
        limit: int = DEFAULT_LIMIT,
        offset: int = 0,
        include_private: bool = False,
        include_superseded: bool = True,
    ) -> str:
        """Find the notes most relevant to a query. Start here.

        Returns ranked matches with a short snippet each — ids and previews,
        not full bodies. Follow up with `read_notes` on the few ids worth
        opening; a good answer usually needs two to five.

        Matches on titles, topics, ids, the owner's verbatim lines, and body
        text, weighted in that order. Optionally narrow by `type`
        (take/story/lesson/fact), `topic`, or `project` id.

        Private notes are excluded unless `include_private` is true — and if
        you do request them, they are still background only and must never be
        quoted. Superseded notes are included and clearly labelled; treat
        them as history, never as a current position.
        """
        brain = load()
        if not brain.exists:
            return _missing()
        page = search(
            brain.notes,
            query,
            limit=limit,
            offset=offset,
            note_type=type or None,
            topic=topic or None,
            project=project or None,
            include_private=include_private,
            include_superseded=include_superseded,
        )
        return formatting.render_hits(page, query)

    @server.tool()
    def read_notes(ids: list[str], include_private: bool = False) -> str:
        """Read the full text of specific notes, by id.

        Pass several ids in one call rather than calling repeatedly. The
        response is capped in both note count and total size; anything
        dropped for budget is named so you can ask again.

        Where a note carries a `> VERBATIM: "..."` line, that is the owner's
        actual phrasing — adapt those words rather than paraphrasing them.
        """
        brain = load()
        if not brain.exists:
            return _missing()
        result = read_notes_budgeted(
            brain.notes, ids, include_private=include_private
        )
        return formatting.render_full_notes(result)

    @server.tool()
    def get_identity(files: list[str] | None = None) -> str:
        """Read who this person is and how they write.

        Load this before producing anything in their voice — it is small and
        it is what makes the output sound like them. `core` is who they are,
        `voice` is an instruction manual for writing as them, `beliefs` is
        the positions that cut across everything. Defaults to all three.

        A file still full of template TODOs is labelled as such: treat it as
        unwritten rather than as an answer.
        """
        brain = load()
        if not brain.exists:
            return _missing()
        wanted = [f for f in (files or list(IDENTITY_SLUGS)) if f in IDENTITY_SLUGS]
        docs = [brain.identity[s] for s in wanted if s in brain.identity]
        return formatting.render_identity(docs)

    @server.tool()
    def list_notes(
        type: str = "",
        topic: str = "",
        project: str = "",
        limit: int = DEFAULT_LIMIT,
        offset: int = 0,
        include_private: bool = False,
        include_superseded: bool = False,
    ) -> str:
        """Browse notes newest-first without a query.

        Use this to see what exists in a category; use `search_brain` when
        you know what you are looking for. Paginated — the response reports
        the total and the next offset.
        """
        brain = load()
        if not brain.exists:
            return _missing()
        notes = filter_notes(
            brain.notes,
            note_type=type or None,
            topic=topic or None,
            project=project or None,
            status=None if include_superseded else "current",
            include_private=include_private,
        )
        heading = " ".join(filter(None, [type or "notes", f"on {topic}" if topic else ""]))
        return formatting.render_note_list(paginate(notes, limit, offset), heading.strip())

    @server.tool()
    def list_projects() -> str:
        """List what this person is building, with how fresh each card is.

        A card past 45 days unverified is marked: do not present its numbers
        or status as current — hedge with the date, or omit them.
        """
        brain = load()
        if not brain.exists:
            return _missing()
        return formatting.render_projects(brain.projects)

    @server.tool()
    def get_project(slug: str) -> str:
        """Read one project card in full, by slug (see `list_projects`)."""
        brain = load()
        if not brain.exists:
            return _missing()
        card = brain.project(slug)
        if card is None:
            known = ", ".join(c.slug for c in brain.projects) or "none"
            return f"No project '{slug}'. Known slugs: {known}"
        return formatting.render_project(card)

    @server.tool()
    def list_lenses() -> str:
        """List the owner's named retrieval scopes.

        A lens is a saved filter — topics plus note types — they may invoke
        by name ("use my building-in-public lens"). Lenses are defaults, not
        walls: widen past one when the task obviously needs it.
        """
        brain = load()
        if not brain.exists:
            return _missing()
        return formatting.render_lenses(brain.lenses)

    @server.tool()
    def read_index() -> str:
        """Read the generated catalog of every entity in the brain.

        One line each. Useful for a whole-brain overview on a small brain; on
        a large one prefer `search_brain`, which is bounded.
        """
        brain = load()
        if not brain.exists:
            return _missing()
        return render_index(brain)

    return server
