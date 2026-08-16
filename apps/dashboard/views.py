import functools

from django.conf import settings
from django.contrib import messages
from django.http import Http404, HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import redirect, render
from django.views.decorators.http import require_POST

from apps.brain.notes import IDENTITY_SLUGS, NOTE_TYPES, IdentityDoc
from apps.brain.repo import initialize_brain, is_repo, recent_commits
from apps.brain.writer import assign_note_id, delete_note, save_note

from .access import brain_exists, brain_root, current_brain
from .forms import TYPE_HELP, NoteForm
from .rendering import render_markdown, split_verbatim

TYPE_LABELS = {
    "take": "takes",
    "story": "stories",
    "lesson": "lessons",
    "fact": "facts",
}


def needs_brain(view):
    """Send anyone without a brain to the first-run screen."""

    @functools.wraps(view)
    def wrapper(request, *args, **kwargs):
        if not brain_exists():
            return redirect("dashboard:setup")
        return view(request, *args, **kwargs)

    return wrapper


def _nav_counts(brain) -> dict[str, int]:
    return {t: len(brain.notes_of_type(t)) for t in NOTE_TYPES}


# --------------------------------------------------------------- first run


def setup(request: HttpRequest) -> HttpResponse:
    if brain_exists():
        return redirect("dashboard:overview")
    return render(
        request,
        "dashboard/setup.html",
        {
            "nav": "setup",
            "page_title": "Set up",
            "brain_path": brain_root(),
            "template_path": settings.BRAIN_TEMPLATE_PATH,
        },
    )


@require_POST
def create_brain(request: HttpRequest) -> HttpResponse:
    if brain_exists():
        return redirect("dashboard:overview")

    result = initialize_brain(brain_root(), settings.BRAIN_TEMPLATE_PATH)
    if not result.ok:
        messages.error(request, result.detail)
        return redirect("dashboard:setup")

    messages.success(request, result.detail)
    return redirect("dashboard:overview")


# ---------------------------------------------------------------- overview


def _identity_rows(brain) -> list[dict]:
    """One row per identity file, present or not.

    A file that still holds its template TODOs counts as unwritten. Calling
    a half-filled brain finished is the one thing the overview must not do.
    """
    rows = []
    for slug in IDENTITY_SLUGS:
        doc = brain.identity.get(slug)
        labels = IdentityDoc(slug=slug, body="")
        rows.append(
            {
                "slug": slug,
                "title": labels.title,
                "blurb": labels.blurb,
                "exists": doc is not None,
                "written": bool(doc and doc.is_filled_in),
            }
        )
    return rows


@needs_brain
def overview(request: HttpRequest) -> HttpResponse:
    root = brain_root()
    brain = current_brain()
    identity = _identity_rows(brain)

    return render(
        request,
        "dashboard/overview.html",
        {
            "nav": "overview",
            "page_title": "Overview",
            "brain": brain,
            "counts": _nav_counts(brain),
            "brain_path": root,
            "figures": [
                {
                    "type": t,
                    "label": TYPE_LABELS[t],
                    "count": len(brain.notes_of_type(t)),
                }
                for t in NOTE_TYPES
            ],
            "note_total": len(brain.notes),
            "identity": identity,
            "identity_todo": [row for row in identity if not row["written"]],
            "stale": brain.stale_projects(),
            "commits": recent_commits(root, limit=8),
            "tracked": is_repo(root),
        },
    )


# ------------------------------------------------------------------- notes


@needs_brain
def notes(request: HttpRequest) -> HttpResponse:
    brain = current_brain()
    selected = request.GET.get("type", "")
    topic = request.GET.get("topic", "")
    status = request.GET.get("status", "current")

    visible = brain.notes
    if selected in NOTE_TYPES:
        visible = [n for n in visible if n.type == selected]
    if topic:
        visible = [n for n in visible if topic in n.topics]
    if status in ("current", "superseded"):
        visible = [n for n in visible if n.status == status]

    return render(
        request,
        "dashboard/notes.html",
        {
            "nav": "notes",
            "page_title": "Notes",
            "brain": brain,
            "counts": _nav_counts(brain),
            "notes": visible,
            "heading": TYPE_LABELS[selected].title() if selected in NOTE_TYPES else "Notes",
            "selected_type": selected,
            "selected_topic": topic,
            "selected_status": status,
            "type_labels": TYPE_LABELS,
            "superseded_count": len(
                [n for n in brain.notes if n.status == "superseded"]
            ),
        },
    )


def _note_or_404(brain, note_id):
    note = brain.note(note_id)
    if note is None:
        raise Http404("No note with that id.")
    return note


@needs_brain
def note_new(request: HttpRequest) -> HttpResponse:
    brain = current_brain()
    note_type = request.GET.get("type")
    note_type = note_type if note_type in NOTE_TYPES else "take"

    if request.method == "POST":
        form = NoteForm(request.POST, brain=brain)
        if form.is_valid():
            note = form.to_note()
            assign_note_id(brain_root(), note)
            result = save_note(brain_root(), note)
            _report(request, result, f"Saved {note.type}: {note.title}")
            return redirect("dashboard:note_edit", note_id=note.id)
    else:
        form = NoteForm(
            brain=brain,
            initial={
                "type": note_type,
                "date": _default_month(),
                "visibility": "public",
            },
        )

    return render(
        request,
        "dashboard/note_form.html",
        {
            "nav": "notes",
            "page_title": f"New {note_type}",
            "brain": brain,
            "counts": _nav_counts(brain),
            "form": form,
            "note": None,
            "type_help": TYPE_HELP,
        },
    )


@needs_brain
def note_edit(request: HttpRequest, note_id: str) -> HttpResponse:
    brain = current_brain()
    note = _note_or_404(brain, note_id)

    if request.method == "POST":
        form = NoteForm(request.POST, brain=brain)
        if form.is_valid():
            updated = form.to_note(existing=note)
            assign_note_id(brain_root(), updated, keep_id=note.id)
            result = save_note(brain_root(), updated, previous_path=note.path)
            _report(request, result, f"Saved {updated.type}: {updated.title}")
            return redirect("dashboard:note_edit", note_id=updated.id)
    else:
        prose, verbatim = split_verbatim(note.body)
        form = NoteForm(
            brain=brain,
            initial={
                "type": note.type,
                "title": note.title,
                "date": note.date,
                "topics": note.topics,
                "projects": note.projects,
                "visibility": note.visibility,
                "source_url": note.source_url or "",
                "body": prose,
                "verbatim": verbatim,
            },
        )

    return render(
        request,
        "dashboard/note_form.html",
        {
            "nav": "notes",
            "page_title": note.title,
            "brain": brain,
            "counts": _nav_counts(brain),
            "form": form,
            "note": note,
            "type_help": TYPE_HELP,
        },
    )


@require_POST
@needs_brain
def note_delete(request: HttpRequest, note_id: str) -> HttpResponse:
    brain = current_brain()
    note = _note_or_404(brain, note_id)
    result = delete_note(brain_root(), note)
    _report(request, result, f"Deleted {note.type}: {note.title}")
    return redirect("dashboard:notes")


@require_POST
@needs_brain
def preview(request: HttpRequest) -> JsonResponse:
    """Render the body being typed, so you see the note as an agent will."""
    from .rendering import join_verbatim

    body = join_verbatim(
        request.POST.get("body", ""), request.POST.get("verbatim", "")
    )
    return JsonResponse({"html": render_markdown(body)})


# ----------------------------------------------------------------- helpers


def _default_month() -> str:
    from datetime import date

    today = date.today()
    return f"{today.year:04d}-{today.month:02d}"


def _report(request: HttpRequest, result, success: str) -> None:
    """Say what happened to the file, and separately what happened to git.

    The write is the operation. A failed commit is worth knowing about but
    must never read as though the note was lost.
    """
    if result.committed:
        messages.success(request, success)
    else:
        messages.success(request, f"{success} — written to disk.")
        messages.warning(
            request, f"Not committed: {result.git.detail}"
        )
