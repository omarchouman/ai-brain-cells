from django.urls import reverse

from apps.brain.scanner import scan_brain
from apps.brain.storage import read_document
from apps.dashboard.rendering import join_verbatim, split_verbatim

from .test_views import BrainViewTestCase


class VerbatimSplitTests(BrainViewTestCase):
    def test_splits_the_quote_out_of_the_body(self):
        body = 'Some prose.\n\n> VERBATIM: "How I say it."\n\nMore prose.'
        prose, verbatim = split_verbatim(body)
        self.assertEqual(verbatim, "How I say it.")
        self.assertEqual(prose, "Some prose.\n\nMore prose.")

    def test_a_body_with_no_quote_comes_back_whole(self):
        prose, verbatim = split_verbatim("Just prose.")
        self.assertEqual(prose, "Just prose.")
        self.assertEqual(verbatim, "")

    def test_joins_the_quote_onto_the_end(self):
        self.assertEqual(
            join_verbatim("Some prose.", "How I say it."),
            'Some prose.\n\n> VERBATIM: "How I say it."',
        )

    def test_an_empty_quote_leaves_the_body_alone(self):
        self.assertEqual(join_verbatim("Some prose.", "  "), "Some prose.")

    def test_strips_quotes_the_user_typed_themselves(self):
        self.assertEqual(
            join_verbatim("P.", '"How I say it."'),
            'P.\n\n> VERBATIM: "How I say it."',
        )

    def test_collapses_newlines_so_the_quote_stays_one_line(self):
        composed = join_verbatim("P.", "How I\nsay it.")
        self.assertEqual(composed, 'P.\n\n> VERBATIM: "How I say it."')
        self.assertEqual(split_verbatim(composed)[1], "How I say it.")

    def test_round_trips(self):
        prose, verbatim = "Some prose.\n\nMore prose.", "How I say it."
        again = split_verbatim(join_verbatim(prose, verbatim))
        self.assertEqual(again, (prose, verbatim))


class NoteWritingTestCase(BrainViewTestCase):
    """Shared fixtures. Deliberately carries no tests of its own, so the
    subclasses below don't each re-run the whole parent suite."""

    def setUp(self):
        super().setUp()
        self.create_brain()

    def payload(self, **overrides):
        data = {
            "type": "take",
            "title": "Django beats FastAPI for solo projects",
            "date": "2026-08",
            "topics": ["django"],
            "projects": [],
            "visibility": "public",
            "source_url": "",
            "body": "Most solo devs reach for FastAPI because it feels modern.",
            "verbatim": "You spend three weekends rebuilding the admin.",
        }
        data.update(overrides)
        return data

    def post_new(self, **overrides):
        return self.client.post(reverse("dashboard:note_new"), self.payload(**overrides))

    def notes(self):
        return scan_brain(self.root, use_cache=False).notes


class NoteFormTests(NoteWritingTestCase):
    def test_new_note_form_renders(self):
        response = self.client.get(reverse("dashboard:note_new") + "?type=story")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["form"].initial["type"], "story")

    def test_an_unknown_type_falls_back_rather_than_erroring(self):
        response = self.client.get(reverse("dashboard:note_new") + "?type=rant")
        self.assertEqual(response.context["form"].initial["type"], "take")

    def test_writes_the_file_and_redirects_to_it(self):
        response = self.post_new()
        self.assertRedirects(
            response,
            reverse(
                "dashboard:note_edit",
                kwargs={"note_id": "take-2026-08-django-beats-fastapi-for-solo-projects"},
            ),
            fetch_redirect_response=False,
        )
        self.assertEqual(len(self.notes()), 1)

    def test_stores_the_verbatim_line_in_the_body(self):
        self.post_new()
        note = self.notes()[0]
        self.assertEqual(note.verbatim, "You spend three weekends rebuilding the admin.")
        self.assertIn("> VERBATIM:", note.body)

    def test_frontmatter_matches_the_contract(self):
        self.post_new()
        meta, _ = read_document(self.notes()[0].path)
        self.assertEqual(
            list(meta),
            ["id", "type", "title", "topics", "projects", "status",
             "superseded_by", "visibility", "date", "source_url"],
        )
        self.assertEqual(meta["status"], "current")
        self.assertIsNone(meta["superseded_by"])

    def test_files_the_note_under_its_type(self):
        self.post_new(type="story")
        self.assertEqual(self.notes()[0].path.parent.name, "stories")

    def test_rejects_a_topic_outside_the_taxonomy(self):
        response = self.post_new(topics=["not-a-real-topic"])
        self.assertEqual(response.status_code, 200)
        self.assertIn("topics", response.context["form"].errors)
        self.assertEqual(self.notes(), [])

    def test_rejects_more_than_four_topics(self):
        response = self.post_new(
            topics=["django", "python", "learning", "writing", "career"]
        )
        self.assertIn("topics", response.context["form"].errors)

    def test_rejects_a_malformed_date(self):
        response = self.post_new(date="August 2026")
        self.assertIn("date", response.context["form"].errors)

    def test_rejects_a_title_that_cannot_become_a_filename(self):
        response = self.post_new(title="!!!")
        self.assertIn("title", response.context["form"].errors)

    def test_a_rejected_form_writes_nothing(self):
        self.post_new(date="nope")
        self.assertEqual(self.notes(), [])


class NoteEditTests(NoteWritingTestCase):
    def setUp(self):
        super().setUp()
        self.post_new()
        self.note = self.notes()[0]

    def edit_url(self, note_id=None):
        return reverse(
            "dashboard:note_edit", kwargs={"note_id": note_id or self.note.id}
        )

    def test_edit_form_loads_the_quote_into_its_own_field(self):
        response = self.client.get(self.edit_url())
        initial = response.context["form"].initial
        self.assertEqual(
            initial["verbatim"], "You spend three weekends rebuilding the admin."
        )
        self.assertNotIn("VERBATIM", initial["body"])

    def test_saving_without_changing_the_title_keeps_the_same_file(self):
        self.client.post(self.edit_url(), self.payload(body="Rewritten body."))

        notes = self.notes()
        self.assertEqual(len(notes), 1)
        self.assertEqual(notes[0].id, self.note.id)
        self.assertIn("Rewritten body.", notes[0].body)

    def test_retitling_moves_the_file_and_leaves_no_duplicate(self):
        self.client.post(self.edit_url(), self.payload(title="FastAPI is fine"))

        notes = self.notes()
        self.assertEqual(len(notes), 1)
        self.assertEqual(notes[0].id, "take-2026-08-fastapi-is-fine")
        self.assertFalse(self.note.path.exists())

    def test_changing_the_type_moves_it_to_the_other_folder(self):
        self.client.post(self.edit_url(), self.payload(type="lesson"))

        notes = self.notes()
        self.assertEqual(len(notes), 1)
        self.assertEqual(notes[0].path.parent.name, "lessons")
        self.assertFalse(self.note.path.exists())

    def test_editing_a_missing_note_is_a_404(self):
        self.assertEqual(self.client.get(self.edit_url("take-2026-08-ghost")).status_code, 404)

    def test_delete_removes_it(self):
        response = self.client.post(
            reverse("dashboard:note_delete", kwargs={"note_id": self.note.id})
        )
        self.assertRedirects(
            response, reverse("dashboard:notes"), fetch_redirect_response=False
        )
        self.assertEqual(self.notes(), [])

    def test_delete_rejects_a_get(self):
        response = self.client.get(
            reverse("dashboard:note_delete", kwargs={"note_id": self.note.id})
        )
        self.assertEqual(response.status_code, 405)


class NoteListTests(NoteWritingTestCase):
    def setUp(self):
        super().setUp()
        self.post_new(title="A take", type="take")
        self.post_new(title="A story", type="story", topics=["python"])

    def test_lists_everything_by_default(self):
        response = self.client.get(reverse("dashboard:notes"))
        self.assertEqual(len(response.context["notes"]), 2)

    def test_filters_by_type(self):
        response = self.client.get(reverse("dashboard:notes") + "?type=story")
        self.assertEqual([n.title for n in response.context["notes"]], ["A story"])

    def test_filters_by_topic(self):
        response = self.client.get(reverse("dashboard:notes") + "?topic=python")
        self.assertEqual([n.title for n in response.context["notes"]], ["A story"])

    def test_hides_superseded_notes_by_default(self):
        note = self.notes()[0]
        from apps.brain.writer import supersede_note

        supersede_note(self.root, note, "take-2026-09-newer")

        response = self.client.get(reverse("dashboard:notes"))
        titles = [n.title for n in response.context["notes"]]
        self.assertNotIn(note.title, titles)
        self.assertEqual(response.context["superseded_count"], 1)

    def test_the_sidebar_count_matches_what_the_link_shows(self):
        note = self.notes()[0]
        from apps.brain.writer import supersede_note

        supersede_note(self.root, note, "take-2026-09-newer")

        listing = self.client.get(reverse("dashboard:notes") + f"?type={note.type}")
        self.assertEqual(
            listing.context["counts"][note.type], len(listing.context["notes"])
        )

    def test_can_ask_for_superseded_notes(self):
        note = self.notes()[0]
        from apps.brain.writer import supersede_note

        supersede_note(self.root, note, "take-2026-09-newer")

        response = self.client.get(reverse("dashboard:notes") + "?status=superseded")
        self.assertEqual([n.title for n in response.context["notes"]], [note.title])


class PreviewTests(BrainViewTestCase):
    def setUp(self):
        super().setUp()
        self.create_brain()

    def test_renders_markdown(self):
        response = self.client.post(
            reverse("dashboard:preview"), {"body": "# Title\n\nSome **bold**."}
        )
        self.assertEqual(response.status_code, 200)
        html = response.json()["html"]
        self.assertIn("<h1>Title</h1>", html)
        self.assertIn("<strong>bold</strong>", html)

    def test_includes_the_verbatim_line_as_it_will_be_stored(self):
        response = self.client.post(
            reverse("dashboard:preview"),
            {"body": "Prose.", "verbatim": "How I say it."},
        )
        self.assertIn("VERBATIM", response.json()["html"])

    def test_rejects_a_get(self):
        self.assertEqual(
            self.client.get(reverse("dashboard:preview")).status_code, 405
        )
