# Contributing

Thanks for looking. This is a small, opinionated tool, and most of what
follows exists so a pull request doesn't get rejected for a reason nobody
wrote down.

## What this project is

A local, single-user dashboard over a folder of markdown that Claude Code
reads. That is the whole scope.

It is deliberately **not** a hosted service, a multi-user product, a team
knowledge base, or a vector store. Those are all reasonable things to build;
they are not this. A pull request that adds accounts, a server deployment
path, or an embeddings pipeline will be declined, however good the code —
please open an issue first if you think one of those belongs here, so you
don't write it for nothing.

## Getting set up

```sh
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python manage.py test
.venv/bin/python manage.py runserver
```

There is no database to migrate and no account to create. If you want a
throwaway brain to develop against, point the app somewhere else rather than
using your own:

```sh
BRAIN_PATH=/tmp/dev-brain CLAUDE_SKILLS_PATH=/tmp/dev-skills \
  .venv/bin/python manage.py runserver
```

Set `CLAUDE_SKILLS_PATH` whenever you touch anything under `apps/dashboard/skills.py`
or `skills/`. Otherwise the install button writes into your real
`~/.claude/skills/`.

## Constraints that are load-bearing

Break one of these and the pull request will be sent back, so they are worth
reading before you start.

**1. Markdown files are the source of truth. There are no models for brain
content.** No Django model may represent a note, project, lens, identity file
or topic. The filesystem is the index; `scan_brain()` re-reads the tree and
caches parsed files by fingerprint. This is what makes the claim literally
true instead of aspirational — a second representation would only be
something to keep in sync, and every bug where the dashboard shows stale
content would come back with it.

There is no database at all. Sessions ride in signed cookies. If you find
yourself adding `DATABASES`, stop and open an issue.

**2. Parsing is strict; scanning is forgiving.** `from_meta()` raises on
anything violating the contract. `scan_brain()` catches it into a
`BrokenFile` in the snapshot. One hand-edited typo must surface as one item
needing attention, never as a 500 on every page.

**3. The file write is the operation; the commit is best-effort.** Every save
writes the file and *then* commits, in that order. If git is missing, has no
configured identity, or fails for any reason, the note is still on disk and
the UI says so separately. Never restructure this so a git failure can lose
someone's writing.

**4. Nothing writes outside the project without an explicit user action.**
Installing skills touches `~/.claude/skills/`. That only ever happens on a
POST the user initiated. No startup hooks, no implicit installs.

**5. No build step, and dependencies stay small.** Django, PyYAML, Markdown.
Hand-written CSS, no framework, no bundler, no Node. Adding a dependency
needs a reason in the pull request description that survives the question
"what would we write by hand instead?"

## The brain contract

`brain-template/CLAUDE.md` is the contract every agent follows, and existing
brains are copies of it that never auto-update. Changing it is a breaking
change to data that already exists on people's disks.

If you change the schema:

- Say so plainly in the pull request.
- Bump `contract-version` in the template's frontmatter.
- Make the scanner tolerate the old shape, or explain why it can't.
- Update `apps/brain/notes.py`, the forms, and `INDEX.md` generation
  together — they encode the same rules in three places, and they must not
  disagree.

Adding an optional field is usually fine. Renaming or removing one is not,
without a migration story.

## The skills

`skills/*/SKILL.md` are templates: `{{BRAIN_PATH}}` is substituted at install
time. Keep the placeholder.

The `description:` line in the frontmatter is not documentation — it is the
trigger surface that decides when Claude reaches for the skill at all. Edit
it with the same care as code, and say in the pull request what behaviour you
expect to change.

## Tests

```sh
.venv/bin/python manage.py test
```

Tests come first for anything in `apps/brain/`, which is where the real logic
lives. Views can be tested after the fact.

A few habits that this codebase has learned the hard way:

- **Never inherit a test class from another test class that has tests.** The
  child re-runs the parent's whole suite under different setup. Extract a
  base case with fixtures and no test methods.
- **Verify a test actually tests the thing.** If you add a guard, delete the
  guard and confirm the test fails. A test that passes either way is worse
  than no test, because it reads like coverage.
- **Never let a test touch the real `~/.claude/skills` or a real brain.**
  Override `CLAUDE_SKILLS_PATH` and `BRAIN_PATH` onto temp directories, as
  `apps/dashboard/tests/test_views.py` does.

CI runs `manage.py check` and the full suite on every push and pull
request (`.github/workflows/tests.yml`, Python 3.13). Run it locally first
anyway — the feedback is faster than a round trip through Actions.

## Commits

One logical change per commit, and a message that explains *why* rather than
restating the diff. The existing history is the reference — subjects are
imperative and specific ("Generate INDEX.md and commit it with the change
that caused it"), and bodies cover the reasoning, the trade-off taken, and
anything a reviewer would otherwise have to ask about.

If you fixed a bug you caused earlier in the same branch, fold it in rather
than leaving the mistake and the fix as two commits.

## Style

Four-space indent, double quotes, type hints on new function signatures.
Comments explain *why*, not what — the code already says what.

Plain `forms.Form`, never `ModelForm`, because there are no models. Keep
views thin: parse the request, call into `apps/brain/`, render. Anything
that touches files belongs in `apps/brain/`, not in a view.

## Reporting something

For a bug, the useful report includes what you did, what the brain looked
like, and whether the file on disk ended up correct — the file being right
while the UI is wrong is a very different bug from the file being wrong.

For anything touching the contract or the scope rules above, open an issue
before writing code.
