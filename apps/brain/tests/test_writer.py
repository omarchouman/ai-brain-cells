import tempfile
from datetime import date
from pathlib import Path

from django.test import SimpleTestCase

from apps.brain.notes import IdentityDoc, Lens, Note, ProjectCard
from apps.brain.repo import init_repo, recent_commits
from apps.brain.scanner import scan_brain
from apps.brain.storage import read_document
from apps.brain.taxonomy import read_topics
from apps.brain.writer import (
    assign_note_id,
    delete_note,
    save_identity,
    save_lens,
    save_note,
    save_project,
    save_taxonomy,
    supersede_note,
)


class WriterTestCase(SimpleTestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        init_repo(self.root)
        (self.root / "taxonomy.md").write_text("- django\n- python\n")

    def make_note(self, title="Django beats FastAPI", **overrides):
        meta = {
            "id": "",
            "type": "take",
            "title": title,
            "topics": ["django"],
            "projects": [],
            "status": "current",
            "superseded_by": None,
            "visibility": "public",
            "date": "2026-08",
            "source_url": None,
        }
        meta.update(overrides)
        note = Note(
            id=meta["id"],
            type=meta["type"],
            title=meta["title"],
            topics=meta["topics"],
            projects=meta["projects"],
            status=meta["status"],
            superseded_by=meta["superseded_by"],
            visibility=meta["visibility"],
            date=meta["date"],
            source_url=meta["source_url"],
            body="A body.",
        )
        return assign_note_id(self.root, note)


class SaveNoteTests(WriterTestCase):
    def test_writes_to_the_folder_matching_its_type(self):
        note = self.make_note()
        result = save_note(self.root, note)
        self.assertEqual(
            result.path,
            self.root / "knowledge" / "takes" / "take-2026-08-django-beats-fastapi.md",
        )

    def test_commits_with_a_readable_message(self):
        save_note(self.root, self.make_note())
        self.assertEqual(
            recent_commits(self.root)[0].subject,
            "Add take: Django beats FastAPI",
        )

    def test_an_edit_commits_as_an_edit(self):
        note = self.make_note()
        first = save_note(self.root, note)
        note.body = "A different body."
        save_note(self.root, note, previous_path=first.path)
        self.assertEqual(
            recent_commits(self.root)[0].subject,
            "Edit take: Django beats FastAPI",
        )

    def test_retitling_moves_the_file_and_leaves_no_duplicate(self):
        note = self.make_note()
        first = save_note(self.root, note)

        note.title = "FastAPI is fine, actually"
        note.id = "take-2026-08-fastapi-is-fine-actually"
        second = save_note(self.root, note, previous_path=first.path)

        self.assertFalse(first.path.exists())
        self.assertTrue(second.path.exists())
        self.assertEqual(len(scan_brain(self.root, use_cache=False).notes), 1)

    def test_a_second_note_with_the_same_title_gets_its_own_file(self):
        save_note(self.root, self.make_note())
        second = save_note(self.root, self.make_note())
        self.assertTrue(second.path.name.endswith("-2.md"))
        self.assertEqual(len(scan_brain(self.root, use_cache=False).notes), 2)

    def test_the_saved_file_scans_back_as_the_same_note(self):
        note = self.make_note()
        save_note(self.root, note)
        scanned = scan_brain(self.root, use_cache=False).notes[0]
        self.assertEqual(scanned.to_meta(), note.to_meta())

    def test_saving_still_succeeds_outside_a_git_repository(self):
        plain = Path(self._tmp.name) / "plain"
        plain.mkdir()
        note = self.make_note()
        result = save_note(plain, note)
        self.assertTrue(result.path.exists())
        self.assertFalse(result.committed)


class DeleteAndSupersedeTests(WriterTestCase):
    def test_delete_removes_the_file_and_commits(self):
        note = self.make_note()
        saved = save_note(self.root, note)
        note.path = saved.path

        delete_note(self.root, note)

        self.assertFalse(saved.path.exists())
        self.assertEqual(
            recent_commits(self.root)[0].subject,
            "Delete take: Django beats FastAPI",
        )

    def test_supersede_keeps_the_file_and_marks_it_history(self):
        note = self.make_note()
        saved = save_note(self.root, note)
        note.path = saved.path

        supersede_note(self.root, note, "take-2026-09-newer")

        meta, _ = read_document(saved.path)
        self.assertEqual(meta["status"], "superseded")
        self.assertEqual(meta["superseded_by"], "take-2026-09-newer")
        self.assertTrue(saved.path.exists())


class SaveOtherEntitiesTests(WriterTestCase):
    def test_saves_a_project_card(self):
        card = ProjectCard(
            id="project-ai-brain-cells",
            title="AI Brain Cells",
            status="active",
            topics=["django"],
            visibility="public",
            last_verified=date(2026, 8, 16),
            body="What it is.",
        )
        result = save_project(self.root, card)
        self.assertEqual(result.path, self.root / "projects" / "ai-brain-cells.md")
        self.assertEqual(
            recent_commits(self.root)[0].subject, "Add project: AI Brain Cells"
        )
        self.assertEqual(
            scan_brain(self.root, use_cache=False).projects[0].last_verified,
            date(2026, 8, 16),
        )

    def test_saves_a_lens(self):
        lens = Lens(name="public-writing", topics=["django"], types=["take"])
        result = save_lens(self.root, lens)
        self.assertEqual(result.path, self.root / "lenses" / "public-writing.md")
        self.assertEqual(
            scan_brain(self.root, use_cache=False).lenses[0].types, ["take"]
        )

    def test_saves_an_identity_document(self):
        doc = IdentityDoc(slug="voice", visibility="private", body="# How I write")
        result = save_identity(self.root, doc)
        self.assertEqual(result.path, self.root / "identity" / "voice.md")
        self.assertEqual(
            recent_commits(self.root)[0].subject, "Edit identity: voice.md"
        )

    def test_saves_the_taxonomy(self):
        save_taxonomy(self.root, ["python", "django", "ai-agents"])
        self.assertEqual(read_topics(self.root), ["ai-agents", "django", "python"])
        self.assertEqual(recent_commits(self.root)[0].subject, "Update taxonomy")
