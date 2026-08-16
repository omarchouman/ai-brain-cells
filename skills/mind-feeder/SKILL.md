---
name: mind-feeder
description: Propose new notes for the owner's personal brain from something they just said, wrote, built or read. Use when they say "add this to my brain", "remember this", "save this take", "feed this in", "make a note of this", or when a conversation has produced an opinion, a story with real numbers, a lesson learned, or a citable fact that is clearly worth keeping. Always propose and wait for approval — never write into the brain unasked.
---

# Mind feeder

You extract notes from a source and propose them. You are the only writer
this brain has, and you write nothing until the owner says yes.

**The brain is at `{{BRAIN_PATH}}`.**

Read `{{BRAIN_PATH}}/CLAUDE.md` first — it is the contract, and it wins over
anything here. Read `{{BRAIN_PATH}}/taxonomy.md` too: topics come from that
list and nowhere else.

## Protocol

1. **Read the source properly.** A transcript, a post, a thread, a file, or
   just what they said in this conversation.

2. **Extract two to four notes. Not ten.** Conservative extraction is the
   whole discipline here. A brain that fills up with weak notes is one the
   owner stops trusting, and an untrusted brain gets abandoned. If the
   source only carries one real idea, propose one note.

3. **Pick the type honestly.**
   - `take` — an opinionated position. Their angle.
   - `story` — a narrative with real numbers, failures and outcomes.
   - `lesson` — something transferable, with the conditions it applies under.
   - `fact` — a stable, citable fact about their work or results.

   If a thing is two ideas, it is two notes.

4. **Write the title as a claim.** "Django beats FastAPI for solo projects",
   never "Thoughts on frameworks". The title is what a retrieving agent reads
   in `INDEX.md` to decide whether to open the file, so a vague one makes the
   note unreachable.

5. **Capture their words verbatim.** Every `take` and `story` must carry at
   least one `> VERBATIM: "..."` line quoting what they actually said or
   wrote. Their phrasing, not your cleaner version of it. This is the
   mechanism by which their voice survives retrieval. If you cannot find a
   real sentence to quote, that is a signal the note is your idea and not
   theirs — drop it.

6. **Check for conflicts before proposing.** Grep existing notes on the same
   topics. If a new claim contradicts an existing one, do not silently add
   it: propose marking the old note `status: superseded` with `superseded_by`
   pointing at the new id, and say so explicitly. If both are true in
   different contexts, keep both `current` and write the boundary into each.

7. **Propose, then stop.** Show the owner each note in full — frontmatter and
   body — and wait. Only after an explicit yes do you write files.

## Frontmatter

```yaml
---
id: take-2026-08-slug          # type-YYYY-MM-slug
type: take                     # matches its folder
title: The claim, stated
topics: [from-taxonomy]        # 1-4, from taxonomy.md only
projects: []                   # optional
status: current
superseded_by: null
visibility: public             # public | private
date: 2026-08                  # when this thinking is from
source_url: null               # optional
---
```

File it at `knowledge/<takes|stories|lessons|facts>/<id>.md`.

## Never

- **Never invent.** No claim that is not in the source. No enrichment, no
  smoothing, no filling a gap with something plausible.
- **Never delete a note to resolve a disagreement.** Supersede it. The brain
  is supposed to record how their thinking moved, not just where it landed.
- **Never merge two notes you are unsure about.** A false duplicate costs
  nothing; a false merge loses an idea silently.
- **Never invent a topic.** If the right tag does not exist in
  `taxonomy.md`, say so and let the owner add it.
- **Never write without approval.** Not even one note. Not even an obvious
  one.

## After writing

Update `last_verified` on any project card the notes touched, and mention
that the dashboard regenerates `INDEX.md` — if you wrote files directly,
tell the owner to open the dashboard or regenerate it so the catalog matches
the files.
