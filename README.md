# ai-brain-cells

**Your context, your voice, your takes — in markdown, where Claude can read them.**

A local dashboard for building and maintaining a personal knowledge base
that Claude Code reads as *you*: who you are, how you write, what you
believe, what you're building, and what you've concluded.

Two pieces:

- **`brain/`** — a git repo of plain markdown. Your identity, project
  cards, and atomic notes (takes, stories, lessons, facts) under a strict
  frontmatter contract. This is the product. It is readable, portable, and
  yours; delete this dashboard and the brain is untouched.
- **This Django app** — a pleasant way to fill that repo in and keep it
  consistent, plus the two Claude skills that teach agents how to read
  from it and write to it.

## Design rules

1. **Markdown is the source of truth.** The dashboard edits files on disk.
   There are no database models for brain content — no sync, no drift, no
   stale copy. Edit a note in VS Code or in the dashboard; both are equally
   valid.
2. **The brain is a separate git repo.** It lives at `brain/` inside this
   folder but carries its own `.git`, and this repo ignores it. Every save
   in the dashboard is one commit, so your history and your undo come free.
3. **Skills are global.** They install to `~/.claude/skills/`, so your
   brain is available in every project you open — not just this one.

## Running it

```sh
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python manage.py runserver
```

Then open <http://127.0.0.1:8000>. There is no database to migrate and no
account to create.
