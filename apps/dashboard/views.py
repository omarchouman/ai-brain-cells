import functools
from datetime import date

from django.conf import settings
from django.contrib import messages
from django.http import Http404, HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import redirect, render
from django.views.decorators.http import require_POST

from apps.brain.notes import IDENTITY_SLUGS, NOTE_TYPES, IdentityDoc
from apps.brain.repo import initialize_brain, is_repo, recent_commits
from apps.brain.writer import (
    assign_note_id,
    delete_entity,
    delete_note,
    save_identity,
    save_lens,
    save_note,
    save_project,
    save_taxonomy,
)

from .access import brain_exists, brain_root, current_brain
from .forms import (
    TYPE_HELP,
    IdentityForm,
    LensForm,
    NoteForm,
    ProjectForm,
    TaxonomyForm,
)
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


# ---------------------------------------------------------------- projects


PROJECT_STARTER = """## What it is

## Where it stands

## Why I'm building it

## Where it lives
"""


def _project_or_404(brain, slug):
    card = brain.project(slug)
    if card is None:
        raise Http404("No project with that slug.")
    return card


@needs_brain
def projects(request: HttpRequest) -> HttpResponse:
    brain = current_brain()
    return render(
        request,
        "dashboard/projects.html",
        {
            "nav": "projects",
            "page_title": "Projects",
            "brain": brain,
            "counts": _nav_counts(brain),
            "projects": brain.projects,
            "stale": brain.stale_projects(),
        },
    )


@needs_brain
def project_new(request: HttpRequest) -> HttpResponse:
    brain = current_brain()
    if request.method == "POST":
        form = ProjectForm(request.POST, brain=brain)
        if form.is_valid():
            card = form.to_card()
            result = save_project(brain_root(), card)
            _report(request, result, f"Saved project: {card.title}")
            return redirect("dashboard:project_edit", slug=card.slug)
    else:
        form = ProjectForm(
            brain=brain,
            initial={"status": "active", "visibility": "public", "body": PROJECT_STARTER},
        )
    return render(
        request,
        "dashboard/project_form.html",
        {
            "nav": "projects",
            "page_title": "New project",
            "brain": brain,
            "counts": _nav_counts(brain),
            "form": form,
            "card": None,
        },
    )


@needs_brain
def project_edit(request: HttpRequest, slug: str) -> HttpResponse:
    brain = current_brain()
    card = _project_or_404(brain, slug)

    if request.method == "POST":
        form = ProjectForm(request.POST, brain=brain)
        if form.is_valid():
            updated = form.to_card(existing=card)
            result = save_project(brain_root(), updated, previous_path=card.path)
            _report(request, result, f"Saved project: {updated.title}")
            return redirect("dashboard:project_edit", slug=updated.slug)
    else:
        form = ProjectForm(
            brain=brain,
            initial={
                "title": card.title,
                "status": card.status,
                "topics": card.topics,
                "visibility": card.visibility,
                "url": card.url or "",
                "body": card.body,
            },
        )

    return render(
        request,
        "dashboard/project_form.html",
        {
            "nav": "projects",
            "page_title": card.title,
            "brain": brain,
            "counts": _nav_counts(brain),
            "form": form,
            "card": card,
        },
    )


@require_POST
@needs_brain
def project_verify(request: HttpRequest, slug: str) -> HttpResponse:
    """Re-date a card you have just read and found still true.

    The staleness rule is only useful if clearing it is one click. Making
    people re-save the whole card to say "still accurate" is how cards go
    stale and stay that way.
    """
    brain = current_brain()
    card = _project_or_404(brain, slug)
    card.last_verified = date.today()
    result = save_project(brain_root(), card, previous_path=card.path)
    _report(request, result, f"Marked {card.title} verified today")
    return redirect("dashboard:projects")


@require_POST
@needs_brain
def project_delete(request: HttpRequest, slug: str) -> HttpResponse:
    brain = current_brain()
    card = _project_or_404(brain, slug)
    result = delete_entity(
        brain_root(), card.path, f"Delete project: {card.title}"
    )
    _report(request, result, f"Deleted project: {card.title}")
    return redirect("dashboard:projects")


# ---------------------------------------------------------- taxonomy, lenses


def _topic_usage(brain) -> dict[str, int]:
    usage = {topic: 0 for topic in brain.topics}
    for item in [*brain.notes, *brain.projects]:
        for topic in item.topics:
            usage[topic] = usage.get(topic, 0) + 1
    return usage


@needs_brain
def taxonomy(request: HttpRequest) -> HttpResponse:
    brain = current_brain()
    usage = _topic_usage(brain)

    if request.method == "POST":
        form = TaxonomyForm(request.POST)
        if form.is_valid():
            kept = form.cleaned_data["topics"]
            orphaned = sorted(
                topic
                for topic in brain.topics
                if topic not in kept and usage.get(topic)
            )
            if orphaned:
                # Removing a tag that notes still carry would make every one
                # of those notes fail validation and vanish from retrieval.
                # Refusing is kinder than letting the brain quietly shrink.
                form.add_error(
                    "topics",
                    "Still in use: "
                    + ", ".join(f"{t} ({usage[t]})" for t in orphaned)
                    + ". Retag those notes first, or keep the topic.",
                )
            else:
                result = save_taxonomy(brain_root(), kept)
                _report(request, result, "Saved taxonomy")
                return redirect("dashboard:taxonomy")
    else:
        form = TaxonomyForm(initial={"topics": "\n".join(brain.topics)})

    return render(
        request,
        "dashboard/taxonomy.html",
        {
            "nav": "taxonomy",
            "page_title": "Taxonomy",
            "brain": brain,
            "counts": _nav_counts(brain),
            "form": form,
            "usage": sorted(usage.items()),
            "unused": sorted(t for t, n in usage.items() if not n),
        },
    )


def _lens_or_404(brain, name):
    lens = brain.lens(name)
    if lens is None:
        raise Http404("No lens with that name.")
    return lens


@needs_brain
def lenses(request: HttpRequest) -> HttpResponse:
    brain = current_brain()
    return render(
        request,
        "dashboard/lenses.html",
        {
            "nav": "lenses",
            "page_title": "Lenses",
            "brain": brain,
            "counts": _nav_counts(brain),
            "lenses": brain.lenses,
        },
    )


@needs_brain
def lens_new(request: HttpRequest) -> HttpResponse:
    brain = current_brain()
    if request.method == "POST":
        form = LensForm(request.POST, brain=brain)
        if form.is_valid():
            lens = form.to_lens()
            if brain.lens(lens.name):
                form.add_error("name", "You already have a lens with that name.")
            else:
                result = save_lens(brain_root(), lens)
                _report(request, result, f"Saved lens: {lens.name}")
                return redirect("dashboard:lens_edit", name=lens.name)
    else:
        form = LensForm(
            brain=brain,
            initial={"visibility_ceiling": "public", "types": list(NOTE_TYPES)},
        )
    return render(
        request,
        "dashboard/lens_form.html",
        {
            "nav": "lenses",
            "page_title": "New lens",
            "brain": brain,
            "counts": _nav_counts(brain),
            "form": form,
            "lens": None,
        },
    )


@needs_brain
def lens_edit(request: HttpRequest, name: str) -> HttpResponse:
    brain = current_brain()
    lens = _lens_or_404(brain, name)

    if request.method == "POST":
        form = LensForm(request.POST, brain=brain)
        if form.is_valid():
            updated = form.to_lens(existing=lens)
            result = save_lens(brain_root(), updated, previous_path=lens.path)
            _report(request, result, f"Saved lens: {updated.name}")
            return redirect("dashboard:lens_edit", name=updated.name)
    else:
        form = LensForm(
            brain=brain,
            initial={
                "name": lens.name,
                "topics": lens.topics,
                "types": lens.types,
                "visibility_ceiling": lens.visibility_ceiling,
                "body": lens.body,
            },
        )

    return render(
        request,
        "dashboard/lens_form.html",
        {
            "nav": "lenses",
            "page_title": lens.name,
            "brain": brain,
            "counts": _nav_counts(brain),
            "form": form,
            "lens": lens,
            "matches": _lens_matches(brain, lens),
        },
    )


def _lens_matches(brain, lens) -> list:
    """What this lens would actually pull, so it isn't written blind."""
    return [
        note
        for note in brain.notes
        if note.status == "current"
        and note.type in lens.types
        and (not lens.topics or set(note.topics) & set(lens.topics))
        and not (lens.visibility_ceiling == "public" and note.visibility == "private")
    ]


@require_POST
@needs_brain
def lens_delete(request: HttpRequest, name: str) -> HttpResponse:
    brain = current_brain()
    lens = _lens_or_404(brain, name)
    result = delete_entity(brain_root(), lens.path, f"Delete lens: {lens.name}")
    _report(request, result, f"Deleted lens: {lens.name}")
    return redirect("dashboard:lenses")


# ---------------------------------------------------------------- identity


IDENTITY_INTROS = {
    "core": (
        "Ten honest lines beat a page of positioning. Agents load this on every "
        "task, so keep it short and true."
    ),
    "voice": (
        "The highest-leverage file in the brain. What makes it work is real "
        "sentences you actually wrote — rules describe a voice, examples "
        "transmit one. Two paragraphs of your own writing beat a page of "
        "adjectives about it."
    ),
    "beliefs": (
        "The positions that cut across everything you make. A belief specific "
        "to one subject is a take, and belongs in your notes instead."
    ),
}


@needs_brain
def identity(request: HttpRequest) -> HttpResponse:
    brain = current_brain()
    return render(
        request,
        "dashboard/identity.html",
        {
            "nav": "identity",
            "page_title": "Identity",
            "brain": brain,
            "counts": _nav_counts(brain),
            "rows": _identity_rows(brain),
            "intros": IDENTITY_INTROS,
        },
    )


@needs_brain
def identity_edit(request: HttpRequest, slug: str) -> HttpResponse:
    if slug not in IDENTITY_SLUGS:
        raise Http404("No such identity file.")

    brain = current_brain()
    doc = brain.identity.get(slug) or _identity_from_template(slug)

    if request.method == "POST":
        form = IdentityForm(request.POST)
        if form.is_valid():
            doc.visibility = form.cleaned_data["visibility"]
            doc.body = form.cleaned_data["body"].strip()
            result = save_identity(brain_root(), doc)
            _report(request, result, f"Saved {slug}.md")
            return redirect("dashboard:identity_edit", slug=slug)
    else:
        form = IdentityForm(
            initial={"visibility": doc.visibility, "body": doc.body}
        )

    return render(
        request,
        "dashboard/identity_form.html",
        {
            "nav": "identity",
            "page_title": doc.title,
            "brain": brain,
            "counts": _nav_counts(brain),
            "form": form,
            "doc": doc,
            "intro": IDENTITY_INTROS[slug],
        },
    )


def _identity_from_template(slug: str) -> IdentityDoc:
    """Fall back to the shipped prompts if the file was deleted.

    Better to hand someone the questions again than an empty box.
    """
    from apps.brain.storage import read_document

    doc = IdentityDoc(slug=slug, body="")
    source = settings.BRAIN_TEMPLATE_PATH / "identity" / f"{slug}.md"
    if source.is_file():
        try:
            meta, body = read_document(source)
        except Exception:
            return doc
        doc.visibility = meta.get("visibility", "private")
        doc.body = body
    return doc


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
