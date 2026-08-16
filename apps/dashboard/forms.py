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


class NoteForm(forms.Form):
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


class ProjectForm(forms.Form):
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


class IdentityForm(forms.Form):
    visibility = forms.ChoiceField(choices=[(v, v) for v in VISIBILITIES])
    body = forms.CharField(widget=forms.Textarea(attrs={"rows": 26}))


class LensForm(forms.Form):
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


class TaxonomyForm(forms.Form):
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
