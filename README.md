# ai-brain-cells

[![tests](https://github.com/omarchouman/ai-brain-cells/actions/workflows/tests.yml/badge.svg)](https://github.com/omarchouman/ai-brain-cells/actions/workflows/tests.yml)

**Your context, your voice, your takes — in markdown, where Claude can read them.**

A local dashboard for building a personal knowledge base that Claude Code
reads as *you*: who you are, how you write, what you believe, what you're
building, and what you've concluded.

Two pieces:

- **`brain/`** — a git repo of plain markdown. Identity, project cards, and
  atomic notes under a strict frontmatter contract. This is the product. It
  is readable, portable, and yours; delete this dashboard and the brain is
  untouched.
- **This Django app** — a pleasant way to fill that repo in and keep it
  consistent, plus the two Claude skills that teach agents how to read from
  it and write to it.

## Where this came from

This project is inspired by
[**BrainOutside**](https://github.com/hassancs91/brainoutside) by
[Hasan Aboul Hasan](https://github.com/hassancs91), which worked out the
ideas this is built on — and the good ones here are his:

- **Identity as a first-class thing.** A wiki holds knowledge but not *you*.
  Putting `voice.md` and `beliefs.md` at the centre is what lets an agent
  write *as* someone rather than merely *about* their work.
- **Note types shaped for making things** — `take`, `story`, `lesson`,
  `fact` — rather than one undifferentiated pile.
- **Verbatim quotes as the mechanism for voice.** Keeping the author's actual
  phrasing in the note, and adapting it rather than summarising it.
- **Supersede, never delete**, so the brain records how thinking moved.
- **A staleness rule on project cards**, so agents stop quoting old numbers
  as current.
- **An index read first**, so retrieval opens a handful of files instead of
  a repo.

BrainOutside in turn grew out of
[Andrej Karpathy's llm-wiki](https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f)
and the wave of markdown knowledge bases around it.

**What's different here is scope, on purpose.** BrainOutside is the bigger,
more capable project: a self-hosted server with REST and MCP endpoints,
API keys with server-enforced visibility tiers, an approval queue where
agents propose writes, a chat test bench, topic graphs and activity
visualisations, Postgres, Redis, a worker, and Docker. If you want your
brain served to every agent you run anywhere, go use it.

This one is deliberately smaller and more direct. One person, one machine,
no server, no containers, no database at all — `runserver` and a folder of
markdown. Three dependencies. The trims that follow from that:

| BrainOutside | Here |
|---|---|
| Server, MCP, REST, API keys | Skills read the files directly |
| Three enforced visibility tiers | One flag: `public` / `private` |
| Agents propose, you approve in a queue | You write it; the feeder skill still proposes |
| Mandatory provenance on every note | Optional — you're typing these yourself |
| `content-catalog/`, `eval/`, ledger, chat bench | Cut |
| Docker, Postgres, Redis, worker | None |

Fewer moving parts, less to run, less to learn. That is the entire pitch —
if you outgrow it, the brain is plain markdown and it travels.

## Running it

```sh
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python manage.py runserver
```

Open <http://127.0.0.1:8000>. There is no database to migrate and no account
to create. The first screen offers to create your brain.

## Design rules

1. **Markdown is the source of truth.** The dashboard edits files on disk.
   There are no database models for brain content — no sync, no drift, no
   stale copy. Edit a note in VS Code or in the dashboard; both are equally
   valid, and each page re-reads the tree.
2. **The brain is a separate git repo.** It lives at `brain/` but carries its
   own `.git`, and this repo ignores it. Every save is one commit, so your
   history and your undo come free. Nothing is ever pushed for you.
3. **Skills install globally**, to `~/.claude/skills/`, so your brain is
   reachable from every project you open — not just this one.

## What's in a brain

```
brain/
├── CLAUDE.md            the contract every agent reads first
├── INDEX.md             generated catalog — what to open, decided cheaply
├── taxonomy.md          the controlled topic vocabulary
├── identity/            core.md · voice.md · beliefs.md
├── projects/            one card per project, with last_verified
├── knowledge/           takes · stories · lessons · facts
├── lenses/              named retrieval scopes
└── raw/                 long sources that notes link to
```

A note is atomic — one idea, five to fifteen lines, titled as a claim so an
agent can judge from `INDEX.md` alone whether to open it. Takes and stories
carry a `> VERBATIM: "..."` line holding your actual phrasing; that line is
what keeps generated writing sounding like you rather than like anyone.

## Things it refuses to do

The parts worth knowing about are the guardrails, not the forms.

- **Identity files still full of template TODOs are reported as unwritten**,
  not counted as done.
- **Removing a topic that notes still use is refused.** Those notes would
  fail validation and vanish from retrieval — still on disk, invisible to
  every agent, with nothing connecting the disappearance to your edit.
- **Project cards go stale at 45 days.** Past that, agents hedge or omit
  their numbers rather than state them as current. One click says "still
  true".
- **Changing your mind supersedes rather than deletes.** The old note stays,
  marked as history and pointing at what replaced it.
- **A file it cannot parse is listed with the reason**, not silently skipped.

## The skills

Install both from the Skills page.

- **`mind-reader`** — the retrieval protocol. Loads your identity core on
  every task, reads `INDEX.md` to decide what else is worth opening, pulls a
  handful of files rather than the repo. Never quotes a private note, never
  presents a superseded take as your current position, never dresses up
  general knowledge as something your brain said.
- **`mind-feeder`** — the only writer. Extracts two to four notes from a
  source, insists on a verbatim quote of your actual words, and proposes
  everything for your approval before writing anything.

Then, in any project: *"draft this as me"*, *"what's my take on X"*, *"add
this to my brain"*.

## Where to start

Write `identity/voice.md` first — paste in three sentences you actually
wrote. Then three or four takes you already hold. A dozen good notes is
already worth more than none, and far more than a hundred weak ones.

## Development

```sh
.venv/bin/python manage.py test
```

Dependencies are Django, PyYAML and Markdown. Git is called through
`subprocess`; there is no build step, no bundler, and no CSS framework.

See [`CONTRIBUTING.md`](CONTRIBUTING.md) before opening a pull request — a
few of this project's constraints are load-bearing and easy to break by
accident.

## License

MIT — see [`LICENSE`](LICENSE).

The license covers this tool, including the files in `brain-template/`.
It does not cover your brain: the notes you write in `brain/` are your
content, under whatever terms you like. That is why no license file is
copied into a brain when one is created.
