from datetime import date, timedelta

from django.urls import reverse

from apps.brain.notes import STALE_AFTER_DAYS
from apps.brain.scanner import scan_brain
from apps.brain.storage import read_document, write_document

from .test_views import BrainViewTestCase


class ProjectTestCase(BrainViewTestCase):
    def setUp(self):
        super().setUp()
        self.create_brain()

    def payload(self, **overrides):
        data = {
            "title": "AI Brain Cells",
            "status": "active",
            "topics": ["django"],
            "visibility": "public",
            "url": "",
            "body": "## What it is\nA dashboard over a markdown brain.",
        }
        data.update(overrides)
        return data

    def post_new(self, **overrides):
        return self.client.post(
            reverse("dashboard:project_new"), self.payload(**overrides)
        )

    def cards(self):
        return scan_brain(self.root, use_cache=False).projects

    def backdate(self, path, days):
        meta, body = read_document(path)
        meta["last_verified"] = (date.today() - timedelta(days=days)).isoformat()
        write_document(path, meta, body)


class ProjectWriteTests(ProjectTestCase):
    def test_creates_a_card_and_redirects_to_it(self):
        response = self.post_new()
        self.assertRedirects(
            response,
            reverse("dashboard:project_edit", kwargs={"slug": "ai-brain-cells"}),
            fetch_redirect_response=False,
        )
        self.assertEqual([c.title for c in self.cards()], ["AI Brain Cells"])

    def test_dates_a_new_card_today(self):
        self.post_new()
        self.assertEqual(self.cards()[0].last_verified, date.today())

    def test_frontmatter_matches_the_contract(self):
        self.post_new()
        meta, _ = read_document(self.cards()[0].path)
        self.assertEqual(
            list(meta),
            ["id", "type", "title", "status", "topics", "visibility",
             "last_verified", "url"],
        )
        self.assertEqual(meta["type"], "project")

    def test_rejects_an_unknown_status(self):
        response = self.post_new(status="vibing")
        self.assertIn("status", response.context["form"].errors)
        self.assertEqual(self.cards(), [])

    def test_rejects_a_topic_outside_the_taxonomy(self):
        response = self.post_new(topics=["invented"])
        self.assertIn("topics", response.context["form"].errors)

    def test_lists_cards(self):
        self.post_new()
        response = self.client.get(reverse("dashboard:projects"))
        self.assertEqual(len(response.context["projects"]), 1)


class ProjectEditTests(ProjectTestCase):
    def setUp(self):
        super().setUp()
        self.post_new()
        self.card = self.cards()[0]

    def edit_url(self, slug=None):
        return reverse(
            "dashboard:project_edit", kwargs={"slug": slug or self.card.slug}
        )

    def test_edit_form_loads_current_values(self):
        response = self.client.get(self.edit_url())
        self.assertEqual(response.context["form"].initial["title"], "AI Brain Cells")

    def test_renaming_keeps_the_filename_so_note_references_survive(self):
        self.client.post(self.edit_url(), self.payload(title="Brain Cells"))

        cards = self.cards()
        self.assertEqual(len(cards), 1)
        self.assertEqual(cards[0].title, "Brain Cells")
        self.assertEqual(cards[0].id, "project-ai-brain-cells")
        self.assertEqual(cards[0].path.name, "ai-brain-cells.md")

    def test_saving_re_dates_the_card(self):
        self.backdate(self.card.path, days=200)
        self.client.post(self.edit_url(), self.payload(body="Updated numbers."))
        self.assertEqual(self.cards()[0].last_verified, date.today())

    def test_a_missing_card_is_a_404(self):
        self.assertEqual(self.client.get(self.edit_url("ghost")).status_code, 404)

    def test_delete_removes_it(self):
        response = self.client.post(
            reverse("dashboard:project_delete", kwargs={"slug": self.card.slug})
        )
        self.assertRedirects(
            response, reverse("dashboard:projects"), fetch_redirect_response=False
        )
        self.assertEqual(self.cards(), [])


class StalenessTests(ProjectTestCase):
    def setUp(self):
        super().setUp()
        self.post_new()
        self.card = self.cards()[0]

    def test_a_card_past_the_window_is_stale(self):
        self.backdate(self.card.path, days=STALE_AFTER_DAYS + 1)
        response = self.client.get(reverse("dashboard:projects"))
        self.assertEqual(len(response.context["stale"]), 1)

    def test_a_card_inside_the_window_is_not(self):
        self.backdate(self.card.path, days=STALE_AFTER_DAYS - 1)
        response = self.client.get(reverse("dashboard:projects"))
        self.assertEqual(response.context["stale"], [])

    def test_verify_re_dates_without_touching_the_body(self):
        self.backdate(self.card.path, days=200)
        before = self.cards()[0].body

        response = self.client.post(
            reverse("dashboard:project_verify", kwargs={"slug": self.card.slug})
        )

        self.assertRedirects(
            response, reverse("dashboard:projects"), fetch_redirect_response=False
        )
        card = self.cards()[0]
        self.assertEqual(card.last_verified, date.today())
        self.assertEqual(card.body, before)

    def test_verify_rejects_a_get(self):
        response = self.client.get(
            reverse("dashboard:project_verify", kwargs={"slug": self.card.slug})
        )
        self.assertEqual(response.status_code, 405)
