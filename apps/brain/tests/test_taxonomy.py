import tempfile
from pathlib import Path

from django.test import SimpleTestCase

from apps.brain.taxonomy import read_topics, write_topics


class TaxonomyTests(SimpleTestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        self.path = self.root / "taxonomy.md"

    def test_reads_bullets(self):
        self.path.write_text("# Taxonomy\n\nSome prose.\n\n- django\n- python\n")
        self.assertEqual(read_topics(self.root), ["django", "python"])

    def test_reads_asterisk_bullets_too(self):
        self.path.write_text("* django\n* python\n")
        self.assertEqual(read_topics(self.root), ["django", "python"])

    def test_missing_file_has_no_topics(self):
        self.assertEqual(read_topics(self.root), [])

    def test_ignores_duplicates(self):
        self.path.write_text("- django\n- django\n")
        self.assertEqual(read_topics(self.root), ["django"])

    def test_writing_preserves_the_prose_above_the_list(self):
        self.path.write_text("# Taxonomy\n\nKeep this sentence.\n\n- django\n")
        write_topics(self.root, ["django", "python"])
        text = self.path.read_text()
        self.assertIn("Keep this sentence.", text)
        self.assertEqual(read_topics(self.root), ["django", "python"])

    def test_writing_sorts_lowercases_and_deduplicates(self):
        write_topics(self.root, ["Python", "django", "python", " AI-Agents "])
        self.assertEqual(read_topics(self.root), ["ai-agents", "django", "python"])

    def test_writing_to_a_fresh_brain_supplies_a_header(self):
        write_topics(self.root, ["django"])
        self.assertIn("# Taxonomy", self.path.read_text())

    def test_writing_an_empty_list_leaves_a_usable_file(self):
        self.path.write_text("# Taxonomy\n\nProse.\n\n- django\n")
        write_topics(self.root, [])
        self.assertEqual(read_topics(self.root), [])
        self.assertIn("Prose.", self.path.read_text())
