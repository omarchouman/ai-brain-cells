---
contract-version: "1.0"
---

# This repo is a brain

Everything here describes one person: who they are, how they write, what
they believe, what they're building, and what they've concluded. Agents
read it to work in that person's name and voice.

This file is the contract. If any other instruction conflicts with it,
this file wins.

Two skills operate on this repo:

- `mind-reader` — how agents retrieve. Every consumer uses it.
- `mind-feeder` — the only writer. Proposes; the owner approves.

## 1. Layout

| Path | What lives here |
|---|---|
| `INDEX.md` | Generated catalog: one line per entity. Read first. |
| `taxonomy.md` | The controlled topic vocabulary. Tags come only from here. |
| `identity/` | Who the owner is, how they write, what they believe. Small, and loaded on every task. |
| `projects/` | One card per project: status, numbers, pointers. |
| `knowledge/` | Atomic notes — takes, stories, lessons, facts. The retrieval workhorse. |
| `lenses/` | Named retrieval scopes. |
| `raw/` | Full transcripts and long docs that notes link to. Rarely opened. |

## 2. Scope rule

**This brain knows ABOUT the owner's work. It does not CONTAIN the work.**

A note is a distillation: a position, a story, a lesson, a fact. The
artefact itself — the codebase, the video, the manuscript — lives wherever
it already lives, and the project card points at it.

If you are pasting a whole document in, you want a `raw/` archive plus a
short note that links to it.

Keep the brain in one language, whichever the owner's agents write in. A
mixed-language corpus poisons voice retrieval.

## 3. Note schema (`knowledge/`)

```yaml
---
id: take-2026-08-django-over-fastapi   # type-YYYY-MM-slug, unique
type: take                             # take | story | lesson | fact
title: Django beats FastAPI for solo projects
topics: [django, python]               # 1-4 tags, from taxonomy.md only
projects: [ai-brain-cells]             # optional
status: current                        # current | superseded
superseded_by: null                    # id of the newer note
visibility: public                     # public | private
date: 2026-08                          # YYYY-MM: when this thinking is from
source_url: null                       # optional
---
```

**Titles are claims, not labels.** "Django beats FastAPI for solo
projects", never "Thoughts on frameworks". That line is what an agent
reads in `INDEX.md` to decide whether to open the file.

**Type meanings:**

- `take` — an opinionated position. The owner's angle on something.
- `story` — a personal narrative with real numbers, failures, outcomes.
- `lesson` — a transferable "what I learned building or testing X".
- `fact` — a stable, citable fact about the owner's work or results.

**Body rules:**

- One idea per note. Two ideas means two notes.
- 5–15 lines. These are retrieval units, not essays.
- `take` and `story` should carry a verbatim line — the owner's own
  phrasing, marked `> VERBATIM: "..."`. Agents writing in their voice
  adapt these lines rather than summarizing around them. This is the
  mechanism by which voice survives retrieval; treat it as the point of
  the note, not decoration.

## 4. Visibility

- `public` — safe to draw on for anything, including audience-facing output.
- `private` — background context only. Never quote it, never surface it in
  generated output, never let it show up in something published.

Default to `public` for anything derived from work the owner has already
published. Default to `private` for unpublished thinking, and when unsure.

Files without a `visibility` field resolve by path: `taxonomy.md`,
`lenses/*` and `INDEX.md` are `public`; `raw/*` inherits from the notes
linking to it; anything else unclassified is `private`. `CLAUDE.md`,
`README.md` and `*/_TEMPLATE.md` are infrastructure and are never served
as content.

## 5. Writer rules (`mind-feeder`)

1. **Never invent.** No claim that isn't in the source. No enrichment, no
   smoothing, no filling gaps with plausible-sounding detail.
2. **Extract conservatively.** Two to four strong notes per source beats
   ten weak ones. Depth belongs in `raw/`.
3. **Supersede, never delete.** A new conflicting claim marks the old note
   `status: superseded` and sets `superseded_by`. The old note stays — the
   brain records how thinking moved, not just where it landed. If both
   claims are true in different contexts, keep both `current` and write
   the boundary into each.
4. **Prefer false duplicates over false merges.** When unsure whether two
   notes are the same, keep both.
5. **The owner approves before anything is written.** Propose, wait, then
   write. One save is one commit.
6. **Touch a project? Update its `last_verified`.**

## 6. Reader rules (`mind-reader`)

1. Read `INDEX.md` first. Open only what the task justifies — a typical
   budget is the identity core plus two to five files, never a whole folder.
2. `INDEX.md` is generated and can lag behind hand edits. If something you
   expect is missing, grep the frontmatter directly rather than concluding
   it doesn't exist.
3. Never quote a `private` note.
4. Skip `status: superseded` notes. They are history, not current positions.
5. If a project card's `last_verified` is more than 45 days old, do not
   present its numbers or status as current. Hedge with the date, or omit.
6. For voice work, anchor on the VERBATIM lines. Adapt the owner's actual
   phrasing; do not summarize it into generic prose.
7. Open `raw/` only for deep work, and only through links in notes — never
   by browsing.
8. If the brain has nothing relevant, say so and proceed on general
   knowledge. Never present invented context as the owner's.

## 7. Taxonomy

Tags come only from `taxonomy.md`. Never invent an ad-hoc tag. A tag earns
its place when two or more notes need it — and a vocabulary of 60 tags
retrieves worse than one of 20.
