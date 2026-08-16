from django.urls import reverse

from apps.brain.notes import Note
from apps.brain.scanner import scan_brain
from apps.brain.taxonomy import read_topics
from apps.brain.writer import assign_note_id, save_note

from .test_views import BrainViewTestCase


class TaxonomyTests(BrainViewTestCase):
    def setUp(self):
        super().setUp()
        self.create_brain()
        self.url = reverse("dashboard:taxonomy")

    def add_note(self, topics):
        note = Note(
            id="", type="take", title="A take", topics=topics, projects=[],
            status="current", superseded_by=None, visibility="public",
            date="2026-08", body="A body.",
        )
        assign_note_id(self.root, note)
        save_note(self.root, note)

    def test_lists_topics_with_usage_counts(self):
        self.add_note(["django"])
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(dict(response.context["usage"])["django"], 1)
        self.assertIn("python", response.context["unused"])

    def test_saves_a_new_list(self):
        response = self.client.post(self.url, {"topics": "django\npython\nrust"})
        self.assertRedirects(response, self.url, fetch_redirect_response=False)
        self.assertEqual(read_topics(self.root), ["django", "python", "rust"])

    def test_normalises_case_and_stray_bullets(self):
        self.client.post(self.url, {"topics": "- Django\n* PYTHON\n\n  rust  "})
        self.assertEqual(read_topics(self.root), ["django", "python", "rust"])

    def test_rejects_a_tag_with_spaces(self):
        response = self.client.post(self.url, {"topics": "machine learning"})
        self.assertEqual(response.status_code, 200)
        self.assertIn("topics", response.context["form"].errors)

    def test_refuses_to_remove_a_topic_notes_still_use(self):
        self.add_note(["django"])

        response = self.client.post(self.url, {"topics": "python"})

        self.assertEqual(response.status_code, 200)
        self.assertIn("Still in use", str(response.context["form"].errors))
        self.assertIn("django", read_topics(self.root))

    def test_allows_removing_a_topic_nothing_uses(self):
        self.client.post(self.url, {"topics": "django"})
        self.assertEqual(read_topics(self.root), ["django"])

    def test_removing_a_used_topic_would_have_hidden_the_note(self):
        """Why the refusal exists, stated as a test."""
        self.add_note(["django"])
        from apps.brain.taxonomy import write_topics

        write_topics(self.root, ["python"])

        brain = scan_brain(self.root, use_cache=False)
        self.assertEqual(brain.notes, [])
        self.assertEqual(len(brain.broken), 1)


class LensTests(BrainViewTestCase):
    def setUp(self):
        super().setUp()
        self.create_brain()

    def payload(self, **overrides):
        data = {
            "name": "building-in-public",
            "topics": ["django"],
            "types": ["take", "story"],
            "visibility_ceiling": "public",
            "body": "For anything the audience will read.",
        }
        data.update(overrides)
        return data

    def lenses(self):
        return scan_brain(self.root, use_cache=False).lenses

    def test_creates_a_lens(self):
        response = self.client.post(reverse("dashboard:lens_new"), self.payload())
        self.assertRedirects(
            response,
            reverse("dashboard:lens_edit", kwargs={"name": "building-in-public"}),
            fetch_redirect_response=False,
        )
        lens = self.lenses()[0]
        self.assertEqual(lens.types, ["take", "story"])

    def test_refuses_a_duplicate_name(self):
        self.client.post(reverse("dashboard:lens_new"), self.payload())
        response = self.client.post(reverse("dashboard:lens_new"), self.payload())
        self.assertIn("name", response.context["form"].errors)
        self.assertEqual(len(self.lenses()), 1)

    def test_rejects_an_unknown_note_type(self):
        response = self.client.post(
            reverse("dashboard:lens_new"), self.payload(types=["rant"])
        )
        self.assertIn("types", response.context["form"].errors)

    def test_edit_shows_what_the_lens_currently_pulls(self):
        self.client.post(reverse("dashboard:lens_new"), self.payload())
        for title, topics, note_type in [
            ("Matching take", ["django"], "take"),
            ("Wrong topic", ["python"], "take"),
            ("Wrong type", ["django"], "fact"),
        ]:
            note = Note(
                id="", type=note_type, title=title, topics=topics, projects=[],
                status="current", superseded_by=None, visibility="public",
                date="2026-08", body="A body.",
            )
            assign_note_id(self.root, note)
            save_note(self.root, note)

        response = self.client.get(
            reverse("dashboard:lens_edit", kwargs={"name": "building-in-public"})
        )

        self.assertEqual(
            [n.title for n in response.context["matches"]], ["Matching take"]
        )

    def test_a_public_ceiling_excludes_private_notes(self):
        self.client.post(reverse("dashboard:lens_new"), self.payload())
        note = Note(
            id="", type="take", title="Private take", topics=["django"], projects=[],
            status="current", superseded_by=None, visibility="private",
            date="2026-08", body="A body.",
        )
        assign_note_id(self.root, note)
        save_note(self.root, note)

        response = self.client.get(
            reverse("dashboard:lens_edit", kwargs={"name": "building-in-public"})
        )
        self.assertEqual(response.context["matches"], [])

    def test_delete_removes_it(self):
        self.client.post(reverse("dashboard:lens_new"), self.payload())
        response = self.client.post(
            reverse("dashboard:lens_delete", kwargs={"name": "building-in-public"})
        )
        self.assertRedirects(
            response, reverse("dashboard:lenses"), fetch_redirect_response=False
        )
        self.assertEqual(self.lenses(), [])

    def test_a_missing_lens_is_a_404(self):
        response = self.client.get(
            reverse("dashboard:lens_edit", kwargs={"name": "ghost"})
        )
        self.assertEqual(response.status_code, 404)
