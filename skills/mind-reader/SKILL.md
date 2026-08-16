---
name: mind-reader
description: Retrieve the owner's context, voice, opinions, stories and project facts from their personal brain before doing any task in their name or voice. Use whenever a task needs who they are or how they write — drafting a post, reply, newsletter, README or commit message as them, answering questions about their projects or results, deciding what their position on something is, or any request phrased like "as me", "in my voice", "my take on", "use my brain", "what do I think about". Also use before claiming the owner has no opinion on something.
---

# Mind reader

You are retrieving from one person's brain: a git repo of markdown holding
who they are, how they write, what they believe, what they're building, and
what they've concluded.

**The brain is at `{{BRAIN_PATH}}`.**

Your job is a small, high-signal context — the right three to seven files,
never the whole repo. Read `{{BRAIN_PATH}}/CLAUDE.md` first; it is the
contract and it wins over anything here.

## Protocol

1. **Read `INDEX.md`.** One line per entity, with status and visibility. This
   is how you decide what to open without opening anything.

   It is generated, and can lag behind edits made by hand. If you expect
   something that isn't listed, grep the frontmatter under `knowledge/`
   before concluding it doesn't exist.

2. **Load the identity core, always.** `identity/core.md` and
   `identity/voice.md` on every task; `identity/beliefs.md` whenever the
   output carries an opinion. These are small and they are the whole reason
   the output will sound like this person rather than like anyone.

3. **Resolve a lens if one applies.** Named by the task ("use my
   building-in-public lens") → read `lenses/<name>.md`. Otherwise work open:
   all topics, excluding `private`. A lens sets where to look first, not
   where you are allowed to look — widen when the task obviously needs it.

4. **Select two to five more files.**
   - The task names a project → its `projects/` card.
   - The task needs their angle → `knowledge/takes/`.
   - It needs a narrative or evidence → `knowledge/stories/`.
   - It's teaching something → `knowledge/lessons/`.
   - It makes a factual claim about their work → `knowledge/facts/`.

   Find candidates by matching the task against `topics:` in frontmatter and
   against the titles in `INDEX.md`. Titles are written as claims, so a title
   usually tells you whether the file is worth opening.

5. **Write using what you found.**

## Rules that are not negotiable

- **Never quote a `private` note**, or surface its content in anything the
  audience sees. It is background only.
- **Skip `status: superseded` notes.** They are what the owner used to
  think. Presenting one as their current position is the worst failure mode
  this brain has.
- **Respect `last_verified` on project cards.** More than 45 days old means
  you do not state its numbers or status as current — hedge with the date,
  or leave them out. Do not quietly refresh a stale number with a guess.
- **Anchor on the VERBATIM lines.** Where a take or story carries
  `> VERBATIM: "..."`, that is the owner's actual phrasing. Adapt those
  words. Summarising them into cleaner prose is how the output stops
  sounding like them — the quote is the point of the note, not decoration.
- **Never invent context.** If the brain has nothing relevant, say so
  plainly, proceed on general knowledge, and do not present it as though it
  came from the brain. Suggest what would be worth writing down.
- **Open `raw/` only for deep work**, and only through a link in a note.
  Never browse it.

## Budget

Identity core plus two to five files is normal. If ten files look relevant,
take the most recent `current` ones. Dumping folders into context makes the
answer worse, not better — the brain is small on purpose.
