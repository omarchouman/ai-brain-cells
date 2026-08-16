"""Backup uses a local bare repo as the remote, so nothing here needs a
network and nothing can accidentally publish anything."""

import subprocess
import tempfile
from pathlib import Path

from django.urls import reverse

from apps.brain.notes import Note
from apps.brain.repo import (
    current_branch,
    get_remote,
    push,
    set_remote,
    unpushed_count,
)
from apps.brain.writer import assign_note_id, save_note

from .test_views import BrainViewTestCase


class BackupTestCase(BrainViewTestCase):
    def setUp(self):
        super().setUp()
        self.create_brain()
        self._remote_tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._remote_tmp.cleanup)
        self.remote = Path(self._remote_tmp.name) / "brain.git"
        subprocess.run(
            ["git", "init", "--bare", "-q", str(self.remote)], check=True
        )

    def add_note(self, title="A take"):
        note = Note(
            id="", type="take", title=title, topics=["django"], projects=[],
            status="current", superseded_by=None, visibility="public",
            date="2026-08", body="A body.",
        )
        assign_note_id(self.root, note)
        save_note(self.root, note)

    def remote_log(self):
        result = subprocess.run(
            ["git", "-C", str(self.remote), "log", "--format=%s"],
            capture_output=True, text=True,
        )
        return result.stdout.splitlines()


class RemoteTests(BackupTestCase):
    def test_a_fresh_brain_has_no_remote(self):
        self.assertIsNone(get_remote(self.root))

    def test_sets_and_reads_back_a_remote(self):
        self.assertTrue(set_remote(self.root, str(self.remote)))
        self.assertEqual(get_remote(self.root), str(self.remote))

    def test_setting_twice_updates_rather_than_failing(self):
        set_remote(self.root, str(self.remote))
        second = Path(self._remote_tmp.name) / "other.git"
        subprocess.run(["git", "init", "--bare", "-q", str(second)], check=True)

        self.assertTrue(set_remote(self.root, str(second)))
        self.assertEqual(get_remote(self.root), str(second))

    def test_unpushed_is_none_before_the_first_push(self):
        set_remote(self.root, str(self.remote))
        self.assertIsNone(unpushed_count(self.root))

    def test_branch_is_reported(self):
        self.assertEqual(current_branch(self.root), "main")


class PushTests(BackupTestCase):
    def test_push_sends_the_history(self):
        set_remote(self.root, str(self.remote))
        self.add_note("Django beats FastAPI")

        result = push(self.root)

        self.assertTrue(result, result.detail)
        self.assertIn("Add take: Django beats FastAPI", self.remote_log())

    def test_unpushed_counts_commits_made_since(self):
        set_remote(self.root, str(self.remote))
        push(self.root)
        self.assertEqual(unpushed_count(self.root), 0)

        self.add_note("Another take")

        self.assertEqual(unpushed_count(self.root), 1)

    def test_pushing_again_clears_the_count(self):
        set_remote(self.root, str(self.remote))
        push(self.root)
        self.add_note("Another take")
        push(self.root)
        self.assertEqual(unpushed_count(self.root), 0)

    def test_push_without_a_remote_fails_cleanly(self):
        result = push(self.root)
        self.assertFalse(result)
        self.assertIn("No backup remote", result.detail)

    def test_push_to_an_unreachable_remote_fails_rather_than_hanging(self):
        """Git must never sit waiting for a credential nobody can type."""
        set_remote(self.root, str(Path(self._remote_tmp.name) / "does-not-exist.git"))
        result = push(self.root)
        self.assertFalse(result)
        self.assertTrue(result.detail)


class BackupViewTests(BackupTestCase):
    def test_page_renders_without_a_remote(self):
        response = self.client.get(reverse("dashboard:backup"))
        self.assertEqual(response.status_code, 200)
        self.assertIsNone(response.context["remote"])

    def test_page_warns_that_pushing_publishes_private_notes(self):
        response = self.client.get(reverse("dashboard:backup"))
        self.assertContains(response, "Pushing publishes everything")
        self.assertContains(response, "private repository")

    def test_counts_private_notes_for_the_warning(self):
        note = Note(
            id="", type="take", title="Private thought", topics=["django"],
            projects=[], status="current", superseded_by=None,
            visibility="private", date="2026-08", body="A body.",
        )
        assign_note_id(self.root, note)
        save_note(self.root, note)

        response = self.client.get(reverse("dashboard:backup"))

        self.assertEqual(response.context["private_notes"], 1)

    def test_setting_a_remote_through_the_form(self):
        response = self.client.post(
            reverse("dashboard:backup_set_remote"), {"url": str(self.remote)}
        )
        self.assertRedirects(
            response, reverse("dashboard:backup"), fetch_redirect_response=False
        )
        self.assertEqual(get_remote(self.root), str(self.remote))

    def test_rejects_something_that_is_not_a_git_url(self):
        self.client.post(
            reverse("dashboard:backup_set_remote"), {"url": "not a url"}
        )
        self.assertIsNone(get_remote(self.root))

    def test_pushing_through_the_view(self):
        set_remote(self.root, str(self.remote))
        self.add_note("Django beats FastAPI")

        response = self.client.post(reverse("dashboard:backup_push"))

        self.assertRedirects(
            response, reverse("dashboard:backup"), fetch_redirect_response=False
        )
        self.assertIn("Add take: Django beats FastAPI", self.remote_log())

    def test_removing_the_remote(self):
        set_remote(self.root, str(self.remote))
        self.client.post(reverse("dashboard:backup_remove_remote"))
        self.assertIsNone(get_remote(self.root))

    def test_push_rejects_a_get(self):
        self.assertEqual(
            self.client.get(reverse("dashboard:backup_push")).status_code, 405
        )

    def test_set_remote_rejects_a_get(self):
        self.assertEqual(
            self.client.get(reverse("dashboard:backup_set_remote")).status_code, 405
        )
