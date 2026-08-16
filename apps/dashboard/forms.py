"""Forms over markdown files.

These are plain `forms.Form` subclasses, not ModelForms — there are no
models. Each one validates against the same contract `apps.brain.notes`
enforces, then hands back a dataclass for the writer to serialise.

Choices for topics and projects are built from the brain itself, so the
taxonomy is a real constraint in the UI rather than a rule you can only
break and then read about on the overview page.
"""

import re
from datetime import date

from django import forms

from apps.brain.notes import (
    MAX_TOPICS,
    NOTE_TYPES,
    PROJECT_STATUSES,
    VISIBILITIES,
    Lens,
    Note,
    ProjectCard,
    slugify,
)

from .rendering import join_verbatim

MONTH_RE = re.compile(r"^\d{4}-\d{2}$")


class BaselineForm(forms.Form):
    """Carries the fingerprint of the file as it was when the form loaded.

    Compared against the file on save so an edit made in an editor, in
    another tab, or by an agent can't be silently overwritten by a form
    that was rendered before it happened.
    """

    baseline = forms.CharField(required=False, widget=forms.HiddenInput)


TYPE_HELP = {
    "take": "An opinionated position — your angle on something.",
    "story": "A narrative with real numbers, failures and outcomes.",
    "lesson": "Something transferable you learned building or testing.",
    "fact": "A stable, citable fact about your work or results.",
}

VERBATIM_HELP = (
    "The sentence as you would actually say it out loud. Agents writing in "
    "your voice adapt this line rather than summarising around it — it is "
    "the single thing that keeps generated text sounding like you. Stored in "
    "the body as a VERBATIM quote, at the end."
)


class TopicsField(forms.MultipleChoiceField):
    def validate(self, value):
        super().validate(value)
        if len(value) > MAX_TOPICS:
            raise forms.ValidationError(
                f"Pick at most {MAX_TOPICS} topics. A note that needs more is "
                f"usually two notes."
            )


class NoteForm(BaselineForm):
    type = forms.ChoiceField(choices=[(t, t) for t in NOTE_TYPES])
    title = forms.CharField(
        max_length=180,
        help_text=(
            "Write it as a claim, not a label — “Django beats FastAPI for solo "
            "projects”, not “Thoughts on frameworks”. This line is what an "
            "agent reads in INDEX.md to decide whether to open the file."
        ),
    )
    date = forms.CharField(
        label="When this thinking is from",
        help_text="YYYY-MM. A take from two years ago is different evidence.",
    )
    topics = TopicsField(
        required=False,
        widget=forms.CheckboxSelectMultiple,
        help_text="From your taxonomy. One to four.",
    )
    projects = forms.MultipleChoiceField(
        required=False, widget=forms.CheckboxSelectMultiple
    )
    visibility = forms.ChoiceField(
        choices=[(v, v) for v in VISIBILITIES],
        help_text=(
            "“private” means background context only — never quoted, never "
            "surfaced in anything generated."
        ),
    )
    source_url = forms.URLField(
        required=False,
        assume_scheme="https",
        label="Source link",
        help_text="Optional. Only if this came from something published.",
    )
    body = forms.CharField(
        widget=forms.Textarea(attrs={"rows": 10}),
        help_text="Five to fifteen lines. One idea. This is a retrieval unit, not an essay.",
    )
    verbatim = forms.CharField(
        required=False,
        label="In my words",
        widget=forms.Textarea(attrs={"rows": 3}),
        help_text=VERBATIM_HELP,
    )

    def __init__(self, *args, brain=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.brain = brain
        topics = brain.topics if brain else []
        projects = brain.projects if brain else []
        self.fields["topics"].choices = [(t, t) for t in topics]
        self.fields["projects"].choices = [(p.id, p.title) for p in projects]
        self.fields["type"].widget.attrs["class"] = "type-select"
        if not topics:
            self.fields["topics"].help_text = (
                "Your taxonomy is empty. Add a few topics first — without them "
                "nothing can be retrieved by subject."
            )

    def clean_date(self):
        value = self.cleaned_data["date"].strip()
        if not MONTH_RE.match(value):
            raise forms.ValidationError("Use YYYY-MM, for example 2026-08.")
        return value

    def clean_title(self):
        title = self.cleaned_data["title"].strip()
        if not slugify(title, max_length=200) or slugify(title) == "untitled":
            raise forms.ValidationError(
                "That title has no letters or numbers in it, so it cannot "
                "become a filename."
            )
        return title

    def to_note(self, existing: Note | None = None) -> Note:
        data = self.cleaned_data
        return Note(
            id=existing.id if existing else "",
            type=data["type"],
            title=data["title"],
            topics=list(data["topics"]),
            projects=list(data["projects"]),
            status=existing.status if existing else "current",
            superseded_by=existing.superseded_by if existing else None,
            visibility=data["visibility"],
            date=data["date"],
            source_url=data["source_url"] or None,
            body=join_verbatim(data["body"], data["verbatim"]),
            path=existing.path if existing else None,
        )


class ProjectForm(BaselineForm):
    title = forms.CharField(max_length=180)
    status = forms.ChoiceField(choices=[(s, s) for s in PROJECT_STATUSES])
    topics = TopicsField(required=False, widget=forms.CheckboxSelectMultiple)
    visibility = forms.ChoiceField(choices=[(v, v) for v in VISIBILITIES])
    url = forms.URLField(
        required=False,
        assume_scheme="https",
        label="Where it lives",
        help_text="Repo, site, docs — the artefact itself. The brain points at your work rather than containing it.",
    )
    body = forms.CharField(
        widget=forms.Textarea(attrs={"rows": 12}),
        help_text=(
            "What it is, where it stands, why you're building it. Put real "
            "numbers in the “where it stands” part — that is what goes stale, "
            "and what the 45-day rule protects agents from quoting."
        ),
    )

    def __init__(self, *args, brain=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["topics"].choices = [(t, t) for t in (brain.topics if brain else [])]

    def to_card(self, existing: ProjectCard | None = None) -> ProjectCard:
        data = self.cleaned_data
        slug = existing.slug if existing else slugify(data["title"])
        return ProjectCard(
            id=f"project-{slug}",
            title=data["title"],
            status=data["status"],
            topics=list(data["topics"]),
            visibility=data["visibility"],
            last_verified=date.today(),
            url=data["url"] or None,
            body=data["body"].strip(),
            path=existing.path if existing else None,
        )


class IdentityForm(BaselineForm):
    visibility = forms.ChoiceField(choices=[(v, v) for v in VISIBILITIES])
    body = forms.CharField(widget=forms.Textarea(attrs={"rows": 26}))


class LensForm(BaselineForm):
    name = forms.SlugField(
        max_length=60,
        help_text="lowercase-with-hyphens. This is how you'll invoke it: “use my building-in-public lens”.",
    )
    topics = forms.MultipleChoiceField(
        required=False, widget=forms.CheckboxSelectMultiple
    )
    types = forms.MultipleChoiceField(
        choices=[(t, t) for t in NOTE_TYPES],
        widget=forms.CheckboxSelectMultiple,
        initial=list(NOTE_TYPES),
    )
    visibility_ceiling = forms.ChoiceField(choices=[(v, v) for v in VISIBILITIES])
    body = forms.CharField(
        widget=forms.Textarea(attrs={"rows": 6}),
        help_text="When to reach for this lens, and what it deliberately leaves out.",
    )

    def __init__(self, *args, brain=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["topics"].choices = [(t, t) for t in (brain.topics if brain else [])]

    def to_lens(self, existing: Lens | None = None) -> Lens:
        data = self.cleaned_data
        return Lens(
            name=data["name"],
            topics=list(data["topics"]),
            types=list(data["types"]),
            visibility_ceiling=data["visibility_ceiling"],
            body=data["body"].strip(),
            path=existing.path if existing else None,
        )


class CaptureForm(forms.Form):
    """The smallest form that can still produce a valid note.

    Most notes die as ideas because the full editor asks eight questions of
    a thought that took four seconds to have. Here the first line becomes
    the title and the rest becomes the body, which removes the field people
    stall on, and everything else takes a default you can fix later.
    """

    type = forms.ChoiceField(
        choices=[(t, t) for t in NOTE_TYPES], widget=forms.RadioSelect
    )
    text = forms.CharField(
        label="What's the thought?",
        widget=forms.Textarea(attrs={"rows": 8, "autofocus": "autofocus"}),
        help_text=(
            "First line becomes the title — write it as a claim. Everything "
            "after it becomes the body."
        ),
    )
    topics = TopicsField(required=False, widget=forms.CheckboxSelectMultiple)
    verbatim = forms.CharField(
        required=False,
        label="In my words",
        widget=forms.Textarea(attrs={"rows": 2}),
        help_text="Optional now, and worth adding before this note gets used.",
    )

    def __init__(self, *args, brain=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["topics"].choices = [(t, t) for t in (brain.topics if brain else [])]

    def clean_text(self):
        lines = self.cleaned_data["text"].strip().splitlines()
        title = next((line.strip() for line in lines if line.strip()), "")
        if not title:
            raise forms.ValidationError("Write something first.")
        if slugify(title) == "untitled":
            raise forms.ValidationError(
                "The first line has no letters or numbers in it, so it can't "
                "become a title."
            )
        if len(title) > 180:
            raise forms.ValidationError(
                "That first line is very long for a title. Put the claim on "
                "line one and the detail underneath."
            )

        index = lines.index(next(line for line in lines if line.strip()))
        self.cleaned_data["title"] = title
        # A one-line thought is a real note. Rather than reject it or leave
        # the body empty, the claim stands as its own body.
        self.cleaned_data["body"] = "\n".join(lines[index + 1 :]).strip() or title
        return self.cleaned_data["text"]

    def to_note(self, today: date | None = None) -> Note:
        data = self.cleaned_data
        today = today or date.today()
        return Note(
            id="",
            type=data["type"],
            title=data["title"],
            topics=list(data["topics"]),
            projects=[],
            status="current",
            superseded_by=None,
            visibility="public",
            date=f"{today.year:04d}-{today.month:02d}",
            source_url=None,
            body=join_verbatim(data["body"], data["verbatim"]),
        )


class RemoteForm(forms.Form):
    url = forms.CharField(
        label="Backup remote",
        max_length=400,
        help_text=(
            "An SSH or HTTPS git URL — git@github.com:you/my-brain.git. "
            "Make the repository private."
        ),
    )

    def clean_url(self):
        url = self.cleaned_data["url"].strip()
        looks_like_git = (
            url.startswith(("https://", "ssh://", "git@", "file://", "/"))
            or url.startswith(".")
        )
        if not looks_like_git:
            raise forms.ValidationError(
                "That doesn't look like a git remote. Use an SSH URL "
                "(git@host:you/repo.git) or an HTTPS one."
            )
        return url


class TaxonomyForm(BaselineForm):
    topics = forms.CharField(
        widget=forms.Textarea(attrs={"rows": 14}),
        help_text=(
            "One per line, lowercase-with-hyphens. Keep it short — a tag earns "
            "its place when two notes need it, and 60 tags retrieve worse than 20."
        ),
    )

    def clean_topics(self):
        seen = []
        for line in self.cleaned_data["topics"].splitlines():
            topic = line.strip().lstrip("-*").strip().lower()
            if not topic:
                continue
            if not re.fullmatch(r"[a-z0-9]+(-[a-z0-9]+)*", topic):
                raise forms.ValidationError(
                    f"“{topic}” isn't a usable tag. Use lowercase letters, "
                    f"numbers and hyphens."
                )
            if topic not in seen:
                seen.append(topic)
        return seen
