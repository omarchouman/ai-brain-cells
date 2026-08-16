import tempfile
from pathlib import Path

from django.conf import settings
from django.test import SimpleTestCase, override_settings
from django.urls import reverse

from apps.brain.notes import IdentityDoc, Note
from apps.brain.repo import initialize_brain, is_repo
from apps.brain.scanner import clear_cache
from apps.brain.writer import assign_note_id, save_identity, save_note


class BrainViewTestCase(SimpleTestCase):
    """Each test gets a throwaway brain, so nothing touches the real one."""

    databases = set()

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.addCleanup(clear_cache)
        self.root = Path(self._tmp.name) / "brain"
        self._override = override_settings(BRAIN_PATH=self.root)
        self._override.enable()
        self.addCleanup(self._override.disable)

    def create_brain(self):
        return initialize_brain(self.root, settings.BRAIN_TEMPLATE_PATH)


class SetupTests(BrainViewTestCase):
    def test_overview_redirects_to_setup_when_there_is_no_brain(self):
        response = self.client.get(reverse("dashboard:overview"))
        self.assertRedirects(
            response, reverse("dashboard:setup"), fetch_redirect_response=False
        )

    def test_setup_page_names_the_path_it_will_use(self):
        response = self.client.get(reverse("dashboard:setup"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, str(self.root))

    def test_creating_the_brain_writes_the_tree_and_starts_git(self):
        response = self.client.post(reverse("dashboard:create_brain"))

        self.assertRedirects(
            response, reverse("dashboard:overview"), fetch_redirect_response=False
        )
        self.assertTrue((self.root / "CLAUDE.md").is_file())
        self.assertTrue((self.root / "identity" / "voice.md").is_file())
        self.assertTrue(is_repo(self.root))

    def test_setup_redirects_away_once_a_brain_exists(self):
        self.create_brain()
        response = self.client.get(reverse("dashboard:setup"))
        self.assertRedirects(
            response, reverse("dashboard:overview"), fetch_redirect_response=False
        )

    def test_creating_twice_does_not_overwrite(self):
        self.create_brain()
        (self.root / "CLAUDE.md").write_text("mine")
        self.client.post(reverse("dashboard:create_brain"))
        self.assertEqual((self.root / "CLAUDE.md").read_text(), "mine")

    def test_create_rejects_a_get(self):
        response = self.client.get(reverse("dashboard:create_brain"))
        self.assertEqual(response.status_code, 405)


class OverviewTests(BrainViewTestCase):
    def setUp(self):
        super().setUp()
        self.create_brain()

    def add_note(self, title, note_type="take", **overrides):
        note = Note(
            id="",
            type=note_type,
            title=title,
            topics=["django"],
            projects=[],
            status=overrides.get("status", "current"),
            superseded_by=overrides.get("superseded_by"),
            visibility="public",
            date="2026-08",
            body="A body.",
        )
        assign_note_id(self.root, note)
        return save_note(self.root, note)

    def get(self):
        return self.client.get(reverse("dashboard:overview"))

    def test_renders(self):
        response = self.get()
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Your brain")

    def test_a_fresh_brain_reads_as_empty(self):
        self.assertContains(self.get(), "Nothing in it yet")

    def test_counts_notes_by_type(self):
        self.add_note("A take", note_type="take")
        self.add_note("Another take", note_type="take")
        self.add_note("A story", note_type="story")

        response = self.get()

        figures = {f["label"]: f["count"] for f in response.context["figures"]}
        self.assertEqual(figures, {"takes": 2, "stories": 1, "lessons": 0, "facts": 0})

    def test_identity_files_from_the_template_count_as_unwritten(self):
        response = self.get()
        self.assertEqual(len(response.context["identity_todo"]), 3)
        self.assertContains(response, "still a template")

    def test_a_written_identity_file_is_marked_written(self):
        save_identity(
            self.root,
            IdentityDoc(slug="voice", body="Short sentences. No hedging."),
        )
        response = self.get()
        todo = [row["slug"] for row in response.context["identity_todo"]]
        self.assertNotIn("voice", todo)

    def test_surfaces_a_file_it_could_not_read(self):
        (self.root / "knowledge" / "takes" / "broken.md").write_text("not a note\n")
        response = self.get()
        self.assertContains(response, "couldn't be read")
        self.assertEqual(len(response.context["brain"].broken), 1)

    def test_lists_recent_commits(self):
        self.add_note("Django beats FastAPI")
        response = self.get()
        subjects = [c.subject for c in response.context["commits"]]
        self.assertIn("Add take: Django beats FastAPI", subjects)

    def test_warns_when_the_brain_is_not_under_git(self):
        import shutil

        shutil.rmtree(self.root / ".git")
        response = self.get()
        self.assertFalse(response.context["tracked"])
        self.assertContains(response, "isn't a git repository")

    def test_shows_an_edit_made_outside_the_dashboard(self):
        saved = self.add_note("Original title")
        path = saved.path
        path.write_text(path.read_text().replace("Original title", "Edited by hand"))

        response = self.get()

        titles = [n.title for n in response.context["brain"].notes]
        self.assertEqual(titles, ["Edited by hand"])
