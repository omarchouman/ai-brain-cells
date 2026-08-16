import tempfile
from pathlib import Path

from django.test import SimpleTestCase

from apps.brain.errors import BrainFileError
from apps.brain.storage import read_document, unique_path, write_document


class TempBrainTestCase(SimpleTestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)


class WriteDocumentTests(TempBrainTestCase):
    def test_writes_frontmatter_in_the_given_key_order(self):
        path = self.root / "note.md"
        write_document(path, {"id": "x", "type": "take", "topics": ["a"]}, "Body.")
        self.assertEqual(
            path.read_text(),
            "---\nid: x\ntype: take\ntopics: [a]\n---\n\nBody.\n",
        )

    def test_renders_none_as_null_and_empty_lists_inline(self):
        path = self.root / "note.md"
        write_document(path, {"superseded_by": None, "projects": []}, "Body.")
        self.assertIn("superseded_by: null", path.read_text())
        self.assertIn("projects: []", path.read_text())

    def test_creates_missing_parent_directories(self):
        path = self.root / "knowledge" / "takes" / "note.md"
        write_document(path, {"id": "x"}, "Body.")
        self.assertTrue(path.exists())

    def test_ends_the_file_with_exactly_one_newline(self):
        path = self.root / "note.md"
        write_document(path, {"id": "x"}, "Body.\n\n\n")
        self.assertTrue(path.read_text().endswith("Body.\n"))


class ReadDocumentTests(TempBrainTestCase):
    def test_round_trips_meta_and_body(self):
        path = self.root / "note.md"
        meta = {"id": "x", "type": "take", "topics": ["a", "b"], "url": None}
        write_document(path, meta, "Line one.\n\nLine two.")
        read_meta, body = read_document(path)
        self.assertEqual(read_meta, meta)
        self.assertEqual(body, "Line one.\n\nLine two.")

    def test_preserves_a_colon_inside_a_title(self):
        path = self.root / "note.md"
        write_document(path, {"title": "Django: a defence"}, "Body.")
        meta, _ = read_document(path)
        self.assertEqual(meta["title"], "Django: a defence")

    def test_raises_on_a_file_with_no_frontmatter(self):
        path = self.root / "note.md"
        path.write_text("Just a body, no frontmatter.\n")
        with self.assertRaises(BrainFileError):
            read_document(path)

    def test_raises_on_malformed_yaml(self):
        path = self.root / "note.md"
        path.write_text("---\nid: [unclosed\n---\n\nBody.\n")
        with self.assertRaises(BrainFileError):
            read_document(path)

    def test_raises_on_a_missing_file(self):
        with self.assertRaises(BrainFileError):
            read_document(self.root / "nope.md")

    def test_error_carries_the_path(self):
        path = self.root / "note.md"
        path.write_text("no frontmatter\n")
        with self.assertRaises(BrainFileError) as ctx:
            read_document(path)
        self.assertEqual(ctx.exception.path, path)


class UniquePathTests(TempBrainTestCase):
    def test_returns_the_original_when_free(self):
        path = self.root / "take-2026-08-x.md"
        self.assertEqual(unique_path(path), path)

    def test_suffixes_when_taken(self):
        path = self.root / "take-2026-08-x.md"
        path.write_text("taken")
        self.assertEqual(unique_path(path).name, "take-2026-08-x-2.md")

    def test_keeps_counting_past_the_first_collision(self):
        (self.root / "take-2026-08-x.md").write_text("taken")
        (self.root / "take-2026-08-x-2.md").write_text("taken")
        self.assertEqual(
            unique_path(self.root / "take-2026-08-x.md").name,
            "take-2026-08-x-3.md",
        )
