from datetime import date

from django.test import SimpleTestCase

from apps.brain.errors import BrainValidationError
from apps.brain.notes import (
    IdentityDoc,
    Lens,
    Note,
    ProjectCard,
    make_note_id,
    slugify,
)


class SlugifyTests(SimpleTestCase):
    def test_lowercases_and_hyphenates(self):
        self.assertEqual(slugify("Django Beats FastAPI"), "django-beats-fastapi")

    def test_strips_punctuation(self):
        self.assertEqual(
            slugify("Django beats FastAPI: here's why!"),
            "django-beats-fastapi-heres-why",
        )

    def test_collapses_runs_of_separators(self):
        self.assertEqual(slugify("a   --  b"), "a-b")

    def test_trims_leading_and_trailing_separators(self):
        self.assertEqual(slugify("  -- hello --  "), "hello")

    def test_truncates_long_titles_without_leaving_a_trailing_hyphen(self):
        slug = slugify("word " * 40, max_length=40)
        self.assertLessEqual(len(slug), 40)
        self.assertFalse(slug.endswith("-"))

    def test_empty_input_gives_a_usable_fallback(self):
        self.assertEqual(slugify("!!!"), "untitled")


class MakeNoteIdTests(SimpleTestCase):
    def test_builds_type_date_slug(self):
        self.assertEqual(
            make_note_id("take", "2026-08", "Django beats FastAPI"),
            "take-2026-08-django-beats-fastapi",
        )


class NoteTests(SimpleTestCase):
    def valid_meta(self, **overrides):
        meta = {
            "id": "take-2026-08-django-beats-fastapi",
            "type": "take",
            "title": "Django beats FastAPI for solo projects",
            "topics": ["django", "python"],
            "projects": [],
            "status": "current",
            "superseded_by": None,
            "visibility": "public",
            "date": "2026-08",
            "source_url": None,
        }
        meta.update(overrides)
        return meta

    def test_parses_valid_frontmatter(self):
        note = Note.from_meta(self.valid_meta(), body="A body.")
        self.assertEqual(note.type, "take")
        self.assertEqual(note.topics, ["django", "python"])
        self.assertEqual(note.body, "A body.")
        self.assertTrue(note.is_current)

    def test_serializes_keys_in_contract_order(self):
        note = Note.from_meta(self.valid_meta(), body="A body.")
        self.assertEqual(
            list(note.to_meta().keys()),
            [
                "id",
                "type",
                "title",
                "topics",
                "projects",
                "status",
                "superseded_by",
                "visibility",
                "date",
                "source_url",
            ],
        )

    def test_round_trips_through_meta(self):
        note = Note.from_meta(self.valid_meta(), body="A body.")
        again = Note.from_meta(note.to_meta(), body=note.body)
        self.assertEqual(note.to_meta(), again.to_meta())

    def test_rejects_unknown_type(self):
        with self.assertRaises(BrainValidationError):
            Note.from_meta(self.valid_meta(type="rant"), body="")

    def test_rejects_unknown_status(self):
        with self.assertRaises(BrainValidationError):
            Note.from_meta(self.valid_meta(status="draft"), body="")

    def test_rejects_unknown_visibility(self):
        with self.assertRaises(BrainValidationError):
            Note.from_meta(self.valid_meta(visibility="agents-only"), body="")

    def test_rejects_missing_title(self):
        with self.assertRaises(BrainValidationError):
            Note.from_meta(self.valid_meta(title=""), body="")

    def test_rejects_malformed_date(self):
        with self.assertRaises(BrainValidationError):
            Note.from_meta(self.valid_meta(date="August 2026"), body="")

    def test_accepts_a_full_iso_date_and_narrows_it_to_the_month(self):
        note = Note.from_meta(self.valid_meta(date="2026-08-16"), body="")
        self.assertEqual(note.date, "2026-08")

    def test_rejects_more_than_four_topics(self):
        with self.assertRaises(BrainValidationError):
            Note.from_meta(
                self.valid_meta(topics=["a", "b", "c", "d", "e"]), body=""
            )

    def test_rejects_superseded_status_without_a_successor(self):
        with self.assertRaises(BrainValidationError):
            Note.from_meta(
                self.valid_meta(status="superseded", superseded_by=None), body=""
            )

    def test_superseded_note_is_not_current(self):
        note = Note.from_meta(
            self.valid_meta(status="superseded", superseded_by="take-2026-09-x"),
            body="",
        )
        self.assertFalse(note.is_current)

    def test_tolerates_a_missing_optional_list(self):
        meta = self.valid_meta()
        del meta["projects"]
        note = Note.from_meta(meta, body="")
        self.assertEqual(note.projects, [])

    def test_extracts_the_verbatim_line_from_the_body(self):
        body = 'Some prose.\n\n> VERBATIM: "This is how I say it."\n\nMore prose.'
        note = Note.from_meta(self.valid_meta(), body=body)
        self.assertEqual(note.verbatim, "This is how I say it.")

    def test_verbatim_is_none_when_absent(self):
        note = Note.from_meta(self.valid_meta(), body="Just prose.")
        self.assertIsNone(note.verbatim)

    def test_folder_matches_the_pluralised_type(self):
        note = Note.from_meta(self.valid_meta(type="story"), body="")
        self.assertEqual(note.folder, "stories")


class ProjectCardTests(SimpleTestCase):
    def valid_meta(self, **overrides):
        meta = {
            "id": "project-ai-brain-cells",
            "type": "project",
            "title": "AI Brain Cells",
            "status": "active",
            "topics": ["django"],
            "visibility": "public",
            "last_verified": date(2026, 8, 16),
            "url": None,
        }
        meta.update(overrides)
        return meta

    def test_parses_valid_frontmatter(self):
        card = ProjectCard.from_meta(self.valid_meta(), body="What it is.")
        self.assertEqual(card.slug, "ai-brain-cells")
        self.assertEqual(card.last_verified, date(2026, 8, 16))

    def test_accepts_last_verified_as_a_string(self):
        card = ProjectCard.from_meta(
            self.valid_meta(last_verified="2026-08-16"), body=""
        )
        self.assertEqual(card.last_verified, date(2026, 8, 16))

    def test_rejects_unknown_status(self):
        with self.assertRaises(BrainValidationError):
            ProjectCard.from_meta(self.valid_meta(status="vibing"), body="")

    def test_is_stale_after_the_staleness_window(self):
        card = ProjectCard.from_meta(
            self.valid_meta(last_verified=date(2026, 1, 1)), body=""
        )
        self.assertTrue(card.is_stale(today=date(2026, 8, 16)))

    def test_is_not_stale_inside_the_window(self):
        card = ProjectCard.from_meta(
            self.valid_meta(last_verified=date(2026, 8, 1)), body=""
        )
        self.assertFalse(card.is_stale(today=date(2026, 8, 16)))


class LensTests(SimpleTestCase):
    def test_parses_valid_frontmatter(self):
        lens = Lens.from_meta(
            {
                "name": "building-in-public",
                "topics": ["building-in-public"],
                "types": ["take", "story"],
                "visibility_ceiling": "public",
            },
            body="For audience-facing writing.",
        )
        self.assertEqual(lens.name, "building-in-public")
        self.assertEqual(lens.types, ["take", "story"])

    def test_rejects_a_type_outside_the_note_types(self):
        with self.assertRaises(BrainValidationError):
            Lens.from_meta(
                {"name": "x", "topics": [], "types": ["rant"]}, body=""
            )

    def test_defaults_types_to_all_note_types(self):
        lens = Lens.from_meta({"name": "x", "topics": []}, body="")
        self.assertEqual(lens.types, ["take", "story", "lesson", "fact"])


class IdentityDocTests(SimpleTestCase):
    def test_parses_and_titles_itself(self):
        doc = IdentityDoc.from_meta(
            {"visibility": "private"}, body="# How I write", slug="voice"
        )
        self.assertEqual(doc.slug, "voice")
        self.assertEqual(doc.id, "identity-voice")
        self.assertEqual(doc.visibility, "private")

    def test_defaults_to_private_when_unmarked(self):
        doc = IdentityDoc.from_meta({}, body="", slug="core")
        self.assertEqual(doc.visibility, "private")

    def test_rejects_an_unknown_slug(self):
        with self.assertRaises(BrainValidationError):
            IdentityDoc.from_meta({}, body="", slug="vibes")
