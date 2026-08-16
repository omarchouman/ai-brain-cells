from django.conf import settings
from django.contrib import messages
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.views.decorators.http import require_POST

from apps.brain.notes import IDENTITY_SLUGS, NOTE_TYPES, IdentityDoc
from apps.brain.repo import initialize_brain, is_repo, recent_commits

from .access import brain_exists, brain_root, current_brain

TYPE_LABELS = {
    "take": "takes",
    "story": "stories",
    "lesson": "lessons",
    "fact": "facts",
}


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


def overview(request: HttpRequest) -> HttpResponse:
    if not brain_exists():
        return redirect("dashboard:setup")

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
            "brain_path": root,
            "figures": [
                {"label": TYPE_LABELS[t], "count": len(brain.notes_of_type(t))}
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
