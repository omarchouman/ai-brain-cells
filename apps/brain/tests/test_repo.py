import tempfile
from pathlib import Path

from django.conf import settings
from django.test import SimpleTestCase

from apps.brain.repo import (
    commit_all,
    init_repo,
    initialize_brain,
    is_repo,
    recent_commits,
)
from apps.brain.scanner import scan_brain


class TempDirTestCase(SimpleTestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)


class InitRepoTests(TempDirTestCase):
    def test_creates_a_repository(self):
        self.assertFalse(is_repo(self.root))
        self.assertTrue(init_repo(self.root))
        self.assertTrue(is_repo(self.root))

    def test_is_idempotent(self):
        init_repo(self.root)
        self.assertTrue(init_repo(self.root))

    def test_a_plain_directory_is_not_a_repo(self):
        self.assertFalse(is_repo(self.root / "nope"))

    def test_a_subdirectory_of_a_repo_is_not_itself_a_repo(self):
        # The brain lives inside this project's own repo, so "am I in a
        # repository" is the wrong question — commits would land in the
        # parent's history.
        init_repo(self.root)
        nested = self.root / "brain"
        nested.mkdir()
        self.assertFalse(is_repo(nested))
        self.assertTrue(init_repo(nested))
        self.assertTrue(is_repo(nested))


class CommitTests(TempDirTestCase):
    def setUp(self):
        super().setUp()
        init_repo(self.root)

    def test_commits_a_new_file(self):
        (self.root / "note.md").write_text("hello")
        result = commit_all(self.root, "Add note")
        self.assertTrue(result)
        self.assertTrue(result.sha)

    def test_a_clean_tree_is_success_not_failure(self):
        (self.root / "note.md").write_text("hello")
        commit_all(self.root, "Add note")
        result = commit_all(self.root, "Add note again")
        self.assertTrue(result)
        self.assertIsNone(result.sha)

    def test_commits_a_deletion(self):
        path = self.root / "note.md"
        path.write_text("hello")
        commit_all(self.root, "Add note")
        path.unlink()
        self.assertTrue(commit_all(self.root, "Delete note"))

    def test_reports_failure_outside_a_repository(self):
        plain = self.root / "plain"
        plain.mkdir()
        result = commit_all(plain, "Add note")
        self.assertFalse(result)
        self.assertIn("Not a git repository", result.detail)

    def test_recent_commits_are_newest_first(self):
        for i in range(3):
            (self.root / f"note{i}.md").write_text("x")
            commit_all(self.root, f"Add note {i}")
        subjects = [c.subject for c in recent_commits(self.root)]
        self.assertEqual(subjects[:3], ["Add note 2", "Add note 1", "Add note 0"])

    def test_recent_commits_outside_a_repository_is_empty(self):
        self.assertEqual(recent_commits(self.root / "nope"), [])


class InitializeBrainTests(TempDirTestCase):
    def test_copies_the_shipped_template_and_commits_it(self):
        brain = self.root / "brain"
        result = initialize_brain(brain, settings.BRAIN_TEMPLATE_PATH)

        self.assertTrue(result)
        self.assertTrue((brain / "CLAUDE.md").is_file())
        self.assertTrue((brain / "identity" / "voice.md").is_file())
        self.assertTrue((brain / "knowledge" / "takes" / "_TEMPLATE.md").is_file())
        self.assertTrue(is_repo(brain))
        self.assertEqual(
            [c.subject for c in recent_commits(brain)],
            ["Start this brain from the template"],
        )

    def test_the_new_brain_scans_clean(self):
        brain = self.root / "brain"
        initialize_brain(brain, settings.BRAIN_TEMPLATE_PATH)

        scanned = scan_brain(brain, use_cache=False)

        self.assertTrue(scanned.exists)
        self.assertEqual(scanned.broken, [])
        self.assertEqual(scanned.notes, [])
        self.assertEqual(sorted(scanned.identity), ["beliefs", "core", "voice"])
        self.assertIn("django", scanned.topics)

    def test_refuses_to_overwrite_an_existing_brain(self):
        brain = self.root / "brain"
        brain.mkdir()
        (brain / "CLAUDE.md").write_text("mine")

        result = initialize_brain(brain, settings.BRAIN_TEMPLATE_PATH)

        self.assertFalse(result)
        self.assertEqual((brain / "CLAUDE.md").read_text(), "mine")

    def test_reports_a_missing_template(self):
        result = initialize_brain(self.root / "brain", self.root / "no-template")
        self.assertFalse(result)
        self.assertIn("Template not found", result.detail)
