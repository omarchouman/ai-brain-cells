"""The dashboard and an editor are both meant to be valid ways to change a
file. That only holds if neither can silently discard the other's work."""

from django.urls import reverse

from apps.brain.notes import Lens, Note, ProjectCard
from apps.brain.scanner import scan_brain
from apps.brain.storage import content_fingerprint, read_document, write_document
from apps.brain.writer import assign_note_id, save_lens, save_note, save_project

from .test_views import BrainViewTestCase


class ConflictTestCase(BrainViewTestCase):
    def setUp(self):
        super().setUp()
        self.create_brain()

    def edit_on_disk(self, path, old, new):
        """Stand in for someone editing the file in VS Code."""
        path.write_text(path.read_text().replace(old, new))


class FingerprintTests(ConflictTestCase):
    def test_changes_when_content_changes(self):
        path = self.root / "taxonomy.md"
        before = content_fingerprint(path)
        path.write_text(path.read_text() + "\n- extra\n")
        self.assertNotEqual(before, content_fingerprint(path))

    def test_catches_an_edit_of_identical_length(self):
        """The case (mtime, size) cannot see."""
        path = self.root / "taxonomy.md"
        path.write_text("- aaaa\n")
        before = content_fingerprint(path)
        path.write_text("- bbbb\n")
        self.assertNotEqual(before, content_fingerprint(path))

    def test_a_missing_file_fingerprints_as_empty(self):
        self.assertEqual(content_fingerprint(self.root / "nope.md"), "")


class NoteConflictTests(ConflictTestCase):
    def setUp(self):
        super().setUp()
        note = Note(
            id="", type="take", title="Django beats FastAPI", topics=["django"],
            projects=[], status="current", superseded_by=None, visibility="public",
            date="2026-08", body="Original body.",
        )
        assign_note_id(self.root, note)
        save_note(self.root, note)
        self.note = scan_brain(self.root, use_cache=False).note(note.id)
        self.assertIsNotNone(self.note, "fixture note was not written")
        self.url = reverse("dashboard:note_edit", kwargs={"note_id": self.note.id})

    def payload(self, baseline, **overrides):
        data = {
            "baseline": baseline,
            "type": "take",
            "title": "Django beats FastAPI",
            "date": "2026-08",
            "topics": ["django"],
            "projects": [],
            "visibility": "public",
            "source_url": "",
            "body": "Body typed in the dashboard.",
            "verbatim": "",
        }
        data.update(overrides)
        return data

    def current_baseline(self):
        return self.client.get(self.url).context["form"].initial["baseline"]

    def test_the_form_carries_a_baseline(self):
        self.assertTrue(self.current_baseline())

    def test_an_uncontested_save_goes_through(self):
        response = self.client.post(self.url, self.payload(self.current_baseline()))
        self.assertEqual(response.status_code, 302)
        _, body = read_document(self.note.path)
        self.assertEqual(body, "Body typed in the dashboard.")

    def test_a_save_is_refused_when_the_file_changed_underneath(self):
        baseline = self.current_baseline()
        self.edit_on_disk(self.note.path, "Original body.", "Edited in my editor.")

        response = self.client.post(self.url, self.payload(baseline))

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context["form"].non_field_errors())

    def test_the_editor_edit_survives_the_refusal(self):
        baseline = self.current_baseline()
        self.edit_on_disk(self.note.path, "Original body.", "Edited in my editor.")

        self.client.post(self.url, self.payload(baseline))

        _, body = read_document(self.note.path)
        self.assertEqual(body, "Edited in my editor.")

    def test_the_refusal_shows_what_is_on_disk(self):
        baseline = self.current_baseline()
        self.edit_on_disk(self.note.path, "Original body.", "Edited in my editor.")

        response = self.client.post(self.url, self.payload(baseline))

        self.assertIn(
            "Edited in my editor.", response.context["form"].conflict_disk_text
        )
        self.assertContains(response, "On disk right now")

    def test_saving_again_after_seeing_the_conflict_overwrites(self):
        baseline = self.current_baseline()
        self.edit_on_disk(self.note.path, "Original body.", "Edited in my editor.")

        refused = self.client.post(self.url, self.payload(baseline))
        refreshed = refused.context["form"].data["baseline"]
        accepted = self.client.post(self.url, self.payload(refreshed))

        self.assertEqual(accepted.status_code, 302)
        _, body = read_document(self.note.path)
        self.assertEqual(body, "Body typed in the dashboard.")

    def test_a_conflicting_save_writes_nothing_at_all(self):
        baseline = self.current_baseline()
        self.edit_on_disk(self.note.path, "Django beats FastAPI", "Retitled by hand")

        self.client.post(self.url, self.payload(baseline, title="Retitled in form"))

        titles = [n.title for n in scan_brain(self.root, use_cache=False).notes]
        self.assertEqual(titles, ["Retitled by hand"])

    def test_a_missing_baseline_does_not_block_saving(self):
        """Older bookmarked forms, and anything posting without the field."""
        response = self.client.post(self.url, self.payload(""))
        self.assertEqual(response.status_code, 302)


class OtherEditorsCarryTheGuardTests(ConflictTestCase):
    """A guard on only some editors is worse than none — you'd trust it."""

    def assert_guarded(self, url, payload_builder, path, old, new):
        baseline = self.client.get(url).context["form"].initial["baseline"]
        self.assertTrue(baseline)
        self.edit_on_disk(path, old, new)

        response = self.client.post(url, payload_builder(baseline))

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context["form"].non_field_errors())
        self.assertIn(new, path.read_text())

    def test_identity(self):
        self.assert_guarded(
            reverse("dashboard:identity_edit", kwargs={"slug": "core"}),
            lambda b: {"baseline": b, "visibility": "private", "body": "From form."},
            self.root / "identity" / "core.md",
            "# Who I am",
            "# Who I am, edited by hand",
        )

    def test_taxonomy(self):
        self.assert_guarded(
            reverse("dashboard:taxonomy"),
            lambda b: {"baseline": b, "topics": "django\npython"},
            self.root / "taxonomy.md",
            "- django",
            "- django-edited-by-hand",
        )

    def test_project(self):
        from datetime import date

        card = ProjectCard(
            id="project-brain", title="Brain", status="active", topics=["django"],
            visibility="public", last_verified=date(2026, 8, 16), body="## What it is\nOriginal.",
        )
        path = save_project(self.root, card).path
        self.assert_guarded(
            reverse("dashboard:project_edit", kwargs={"slug": "brain"}),
            lambda b: {
                "baseline": b, "title": "Brain", "status": "active",
                "topics": ["django"], "visibility": "public", "url": "",
                "body": "## What it is\nFrom form.",
            },
            path,
            "Original.",
            "Edited by hand.",
        )

    def test_lens(self):
        path = save_lens(
            self.root,
            Lens(name="public-writing", topics=["django"], types=["take"],
                 body="Original."),
        ).path
        self.assert_guarded(
            reverse("dashboard:lens_edit", kwargs={"name": "public-writing"}),
            lambda b: {
                "baseline": b, "name": "public-writing", "topics": ["django"],
                "types": ["take"], "visibility_ceiling": "public",
                "body": "From form.",
            },
            path,
            "Original.",
            "Edited by hand.",
        )
