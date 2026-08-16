import tempfile
from datetime import date
from pathlib import Path

from django.test import SimpleTestCase

from apps.brain.index import index_path, refresh_index, render_index
from apps.brain.notes import IdentityDoc, Lens, Note, ProjectCard
from apps.brain.repo import init_repo, recent_commits
from apps.brain.scanner import scan_brain
from apps.brain.writer import (
    assign_note_id,
    delete_note,
    save_identity,
    save_lens,
    save_note,
    save_project,
)


class IndexTestCase(SimpleTestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        init_repo(self.root)
        (self.root / "taxonomy.md").write_text("- django\n- python\n")

    def add_note(self, title, note_type="take", **overrides):
        note = Note(
            id="",
            type=note_type,
            title=title,
            topics=["django"],
            projects=[],
            status=overrides.get("status", "current"),
            superseded_by=overrides.get("superseded_by"),
            visibility=overrides.get("visibility", "public"),
            date=overrides.get("date", "2026-08"),
            body="A body.",
        )
        assign_note_id(self.root, note)
        return save_note(self.root, note)

    def index_text(self):
        return index_path(self.root).read_text()


class RenderIndexTests(IndexTestCase):
    def test_an_empty_brain_renders_every_section_as_empty(self):
        text = render_index(scan_brain(self.root, use_cache=False))
        self.assertIn("## identity", text)
        self.assertIn("## projects", text)
        self.assertIn("## knowledge", text)
        self.assertIn("## lenses", text)
        self.assertEqual(text.count("_Empty._"), 4)

    def test_lists_a_note_with_its_status_and_visibility(self):
        self.add_note("Django beats FastAPI")
        text = self.index_text()
        self.assertIn(
            "- `take-2026-08-django-beats-fastapi` — Django beats FastAPI "
            "[current] [public]",
            text,
        )

    def test_groups_notes_under_their_type(self):
        self.add_note("A take", note_type="take")
        self.add_note("A story", note_type="story")
        text = self.index_text()
        self.assertIn("### takes", text)
        self.assertIn("### stories", text)
        self.assertLess(text.index("### takes"), text.index("### stories"))

    def test_omits_a_type_with_no_notes(self):
        self.add_note("A take")
        self.assertNotIn("### facts", self.index_text())

    def test_marks_a_superseded_note_as_history(self):
        self.add_note(
            "An old view", status="superseded", superseded_by="take-2026-09-new"
        )
        self.assertIn("[superseded]", self.index_text())

    def test_lists_projects_with_their_status(self):
        save_project(
            self.root,
            ProjectCard(
                id="project-brain",
                title="Brain",
                status="active",
                topics=["django"],
                last_verified=date(2026, 8, 16),
                body="What it is.",
            ),
        )
        self.assertIn("- `project-brain` — Brain [active] [public]", self.index_text())

    def test_marks_identity_files_still_full_of_todos(self):
        save_identity(
            self.root, IdentityDoc(slug="core", body="TODO — write this.")
        )
        self.assertIn("[todo]", self.index_text())

    def test_marks_a_written_identity_file(self):
        save_identity(
            self.root, IdentityDoc(slug="core", body="I build small tools.")
        )
        self.assertIn("`identity-core`", self.index_text())
        self.assertIn("[written]", self.index_text())

    def test_lists_lenses_by_their_opening_line(self):
        save_lens(
            self.root,
            Lens(
                name="public-writing",
                topics=["django"],
                body="For anything the audience will read.",
            ),
        )
        self.assertIn(
            "- `lens-public-writing` — For anything the audience will read [public]",
            self.index_text(),
        )

    def test_says_it_is_generated(self):
        text = render_index(scan_brain(self.root, use_cache=False))
        self.assertIn("do not edit by hand", text)


class IndexStaysInSyncTests(IndexTestCase):
    def test_saving_a_note_lands_it_and_the_index_in_one_commit(self):
        self.add_note("Django beats FastAPI")
        commits = recent_commits(self.root)
        self.assertEqual(commits[0].subject, "Add take: Django beats FastAPI")
        self.assertIn("django-beats-fastapi", self.index_text())

    def test_deleting_a_note_removes_its_line(self):
        saved = self.add_note("Django beats FastAPI")
        note = scan_brain(self.root, use_cache=False).notes[0]
        note.path = saved.path

        delete_note(self.root, note)

        self.assertNotIn("django-beats-fastapi", self.index_text())

    def test_retitling_replaces_the_line_rather_than_adding_one(self):
        first = self.add_note("Django beats FastAPI")
        note = scan_brain(self.root, use_cache=False).notes[0]
        note.title = "FastAPI is fine, actually"
        note.id = "take-2026-08-fastapi-is-fine-actually"
        save_note(self.root, note, previous_path=first.path)

        text = self.index_text()
        self.assertNotIn("django-beats-fastapi", text)
        self.assertIn("fastapi-is-fine-actually", text)

    def test_refresh_on_a_missing_directory_does_nothing(self):
        self.assertIsNone(refresh_index(self.root / "nope"))
