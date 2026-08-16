from datetime import date

from django.urls import reverse

from apps.brain.scanner import scan_brain

from .test_views import BrainViewTestCase


class CaptureTestCase(BrainViewTestCase):
    def setUp(self):
        super().setUp()
        self.create_brain()
        self.url = reverse("dashboard:capture")

    def capture(self, text, **overrides):
        data = {"type": "take", "text": text, "topics": [], "verbatim": ""}
        data.update(overrides)
        return self.client.post(self.url, data)

    def notes(self):
        return scan_brain(self.root, use_cache=False).notes


class CaptureTests(CaptureTestCase):
    def test_page_renders(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Get it down")

    def test_first_line_becomes_the_title(self):
        self.capture("Django beats FastAPI\n\nAdmin panels for free.")
        note = self.notes()[0]
        self.assertEqual(note.title, "Django beats FastAPI")
        self.assertEqual(note.body, "Admin panels for free.")

    def test_a_single_line_still_makes_a_valid_note(self):
        self.capture("Django beats FastAPI")
        note = self.notes()[0]
        self.assertEqual(note.title, "Django beats FastAPI")
        self.assertEqual(note.body, "Django beats FastAPI")

    def test_leading_blank_lines_are_ignored(self):
        self.capture("\n\n  Django beats FastAPI\n\nBecause admin.")
        note = self.notes()[0]
        self.assertEqual(note.title, "Django beats FastAPI")
        self.assertEqual(note.body, "Because admin.")

    def test_defaults_are_filled_in(self):
        self.capture("A thought")
        note = self.notes()[0]
        self.assertEqual(note.status, "current")
        self.assertEqual(note.visibility, "public")
        self.assertEqual(note.date, f"{date.today():%Y-%m}")
        self.assertIsNone(note.source_url)

    def test_files_it_under_the_chosen_type(self):
        self.capture("A lesson learned", type="lesson")
        self.assertEqual(self.notes()[0].path.parent.name, "lessons")

    def test_topics_are_optional(self):
        self.capture("A thought")
        self.assertEqual(self.notes()[0].topics, [])

    def test_topics_are_kept_when_given(self):
        self.capture("A thought", topics=["django"])
        self.assertEqual(self.notes()[0].topics, ["django"])

    def test_the_voice_line_is_stored_when_given(self):
        self.capture("A thought", verbatim="This is how I'd say it.")
        self.assertEqual(self.notes()[0].verbatim, "This is how I'd say it.")

    def test_redirects_back_to_capture_with_the_saved_note(self):
        response = self.capture("Django beats FastAPI")
        self.assertEqual(response.status_code, 302)
        self.assertIn("saved=take-", response["Location"])

    def test_the_saved_note_is_offered_for_refining(self):
        self.capture("Django beats FastAPI")
        note = self.notes()[0]

        response = self.client.get(self.url, {"saved": note.id})

        self.assertEqual(response.context["saved"].id, note.id)
        self.assertContains(response, "Saved.")

    def test_capturing_twice_makes_two_notes(self):
        self.capture("First thought")
        self.capture("Second thought")
        self.assertEqual(len(self.notes()), 2)

    def test_the_same_thought_twice_does_not_collide(self):
        self.capture("Same thought")
        self.capture("Same thought")
        ids = sorted(n.id for n in self.notes())
        self.assertEqual(len(set(ids)), 2)

    def test_recent_notes_are_listed(self):
        self.capture("A thought")
        response = self.client.get(self.url)
        self.assertEqual([n.title for n in response.context["recent"]], ["A thought"])


class CaptureValidationTests(CaptureTestCase):
    def test_rejects_empty_text(self):
        response = self.capture("   \n\n  ")
        self.assertEqual(response.status_code, 200)
        self.assertIn("text", response.context["form"].errors)
        self.assertEqual(self.notes(), [])

    def test_rejects_a_first_line_that_cannot_become_a_title(self):
        response = self.capture("!!!\n\nBody here.")
        self.assertIn("text", response.context["form"].errors)
        self.assertEqual(self.notes(), [])

    def test_rejects_an_absurdly_long_first_line(self):
        response = self.capture("word " * 60 + "\n\nBody.")
        self.assertIn("text", response.context["form"].errors)

    def test_rejects_a_topic_outside_the_taxonomy(self):
        response = self.capture("A thought", topics=["invented"])
        self.assertIn("topics", response.context["form"].errors)
        self.assertEqual(self.notes(), [])

    def test_rejects_an_unknown_type(self):
        response = self.capture("A thought", type="rant")
        self.assertIn("type", response.context["form"].errors)
        self.assertEqual(self.notes(), [])

    def test_a_rejected_capture_keeps_what_was_typed(self):
        response = self.capture("A thought", topics=["invented"])
        self.assertEqual(response.context["form"].data["text"], "A thought")
