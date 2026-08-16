import os
import tempfile
import time
from pathlib import Path

from django.test import SimpleTestCase

from apps.brain.scanner import scan_brain
from apps.brain.storage import write_document


class ScannerTests(SimpleTestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        (self.root / "taxonomy.md").write_text("# Taxonomy\n\n- django\n- python\n")

    def write_note(self, note_type, folder, slug, **overrides):
        meta = {
            "id": f"{note_type}-2026-08-{slug}",
            "type": note_type,
            "title": slug.replace("-", " ").title(),
            "topics": ["django"],
            "projects": [],
            "status": "current",
            "superseded_by": None,
            "visibility": "public",
            "date": "2026-08",
            "source_url": None,
        }
        meta.update(overrides)
        path = self.root / "knowledge" / folder / f"{meta['id']}.md"
        write_document(path, meta, "A body.")
        return path

    def test_finds_notes_across_all_four_folders(self):
        self.write_note("take", "takes", "a")
        self.write_note("story", "stories", "b")
        self.write_note("lesson", "lessons", "c")
        self.write_note("fact", "facts", "d")

        brain = scan_brain(self.root, use_cache=False)

        self.assertEqual(len(brain.notes), 4)
        self.assertEqual(
            sorted(n.type for n in brain.notes),
            ["fact", "lesson", "story", "take"],
        )

    def test_ignores_template_files(self):
        (self.root / "knowledge" / "takes").mkdir(parents=True)
        (self.root / "knowledge" / "takes" / "_TEMPLATE.md").write_text(
            "---\nid: take-YYYY-MM-slug\n---\n\nBody.\n"
        )
        brain = scan_brain(self.root, use_cache=False)
        self.assertEqual(brain.notes, [])
        self.assertEqual(brain.broken, [])

    def test_collects_broken_files_instead_of_raising(self):
        self.write_note("take", "takes", "good")
        bad = self.root / "knowledge" / "takes" / "take-2026-08-bad.md"
        bad.write_text("no frontmatter at all\n")

        brain = scan_brain(self.root, use_cache=False)

        self.assertEqual(len(brain.notes), 1)
        self.assertEqual(len(brain.broken), 1)
        self.assertEqual(brain.broken[0].path, bad)
        self.assertTrue(brain.broken[0].message)

    def test_a_note_in_the_wrong_folder_is_reported_as_broken(self):
        self.write_note("take", "stories", "misfiled")
        brain = scan_brain(self.root, use_cache=False)
        self.assertEqual(brain.notes, [])
        self.assertEqual(len(brain.broken), 1)

    def test_reports_a_topic_outside_the_taxonomy_as_broken(self):
        self.write_note("take", "takes", "a", topics=["not-in-taxonomy"])
        brain = scan_brain(self.root, use_cache=False)
        self.assertEqual(brain.notes, [])
        self.assertEqual(len(brain.broken), 1)
        self.assertIn("not-in-taxonomy", brain.broken[0].message)

    def test_notes_are_sorted_newest_first(self):
        self.write_note("take", "takes", "older", date="2025-01")
        self.write_note("take", "takes", "newer", date="2026-08")
        brain = scan_brain(self.root, use_cache=False)
        self.assertEqual([n.date for n in brain.notes], ["2026-08", "2025-01"])

    def test_finds_identity_projects_and_lenses(self):
        write_document(
            self.root / "identity" / "core.md", {"visibility": "private"}, "Me."
        )
        write_document(
            self.root / "projects" / "thing.md",
            {
                "id": "project-thing",
                "type": "project",
                "title": "Thing",
                "status": "active",
                "topics": [],
                "visibility": "public",
                "last_verified": "2026-08-16",
                "url": None,
            },
            "What it is.",
        )
        write_document(
            self.root / "lenses" / "public-writing.md",
            {"name": "public-writing", "topics": ["django"], "types": ["take"]},
            "When writing publicly.",
        )

        brain = scan_brain(self.root, use_cache=False)

        self.assertEqual(list(brain.identity), ["core"])
        self.assertEqual(len(brain.projects), 1)
        self.assertEqual(brain.projects[0].slug, "thing")
        self.assertEqual(len(brain.lenses), 1)
        self.assertEqual(brain.lenses[0].name, "public-writing")

    def test_reads_the_taxonomy(self):
        brain = scan_brain(self.root, use_cache=False)
        self.assertEqual(brain.topics, ["django", "python"])

    def test_missing_brain_directory_scans_as_empty(self):
        brain = scan_brain(self.root / "nonexistent", use_cache=False)
        self.assertFalse(brain.exists)
        self.assertEqual(brain.notes, [])

    def test_lookup_by_id(self):
        self.write_note("take", "takes", "findme")
        brain = scan_brain(self.root, use_cache=False)
        self.assertIsNotNone(brain.note("take-2026-08-findme"))
        self.assertIsNone(brain.note("take-2026-08-nope"))


class ScannerCacheTests(SimpleTestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        (self.root / "taxonomy.md").write_text("- django\n")
        self.path = self.root / "knowledge" / "takes" / "take-2026-08-a.md"
        write_document(
            self.path,
            {
                "id": "take-2026-08-a",
                "type": "take",
                "title": "First title",
                "topics": ["django"],
                "projects": [],
                "status": "current",
                "superseded_by": None,
                "visibility": "public",
                "date": "2026-08",
                "source_url": None,
            },
            "A body.",
        )

    def test_picks_up_an_edit_made_outside_the_dashboard(self):
        first = scan_brain(self.root)
        self.assertEqual(first.notes[0].title, "First title")

        self.path.write_text(
            self.path.read_text().replace("First title", "Other title")
        )

        second = scan_brain(self.root)
        self.assertEqual(second.notes[0].title, "Other title")

    def _retitle_keeping_fingerprint(self, new_title: str, mtime_ns: int) -> None:
        """Rewrite the title and restore the file's exact (mtime, size).

        "First title" and "Other title" are the same length, so after putting
        the timestamp back the fingerprint is byte-for-byte what the cache
        already holds. This is the state a naive cache cannot distinguish
        from "nothing happened".
        """
        self.path.write_text(
            self.path.read_text().replace("First title", new_title)
        )
        os.utime(self.path, ns=(mtime_ns, mtime_ns))

    def test_picks_up_a_recent_edit_hidden_behind_an_identical_fingerprint(self):
        scan_brain(self.root)
        just_now = self.path.stat().st_mtime_ns

        self._retitle_keeping_fingerprint("Other title", just_now)

        # Modified within the racy window, so the fingerprint is not trusted.
        self.assertEqual(scan_brain(self.root).notes[0].title, "Other title")

    def test_trusts_the_fingerprint_once_a_file_has_settled(self):
        """The optimisation has to actually optimise, or this is a slow scan."""
        long_ago = time.time_ns() - 600 * 1_000_000_000
        os.utime(self.path, ns=(long_ago, long_ago))
        scan_brain(self.root)

        self._retitle_keeping_fingerprint("Other title", long_ago)

        # Outside the racy window with an unchanged fingerprint, so the file
        # is not re-read. Missing this edit is the trade the cache makes.
        self.assertEqual(scan_brain(self.root).notes[0].title, "First title")

    def test_notices_a_deleted_file(self):
        scan_brain(self.root)
        self.path.unlink()
        self.assertEqual(scan_brain(self.root).notes, [])

    def test_notices_a_new_file(self):
        self.assertEqual(len(scan_brain(self.root).notes), 1)
        write_document(
            self.root / "knowledge" / "facts" / "fact-2026-08-b.md",
            {
                "id": "fact-2026-08-b",
                "type": "fact",
                "title": "Second",
                "topics": ["django"],
                "projects": [],
                "status": "current",
                "superseded_by": None,
                "visibility": "public",
                "date": "2026-08",
                "source_url": None,
            },
            "A body.",
        )
        self.assertEqual(len(scan_brain(self.root).notes), 2)
