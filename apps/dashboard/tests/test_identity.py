from django.urls import reverse

from apps.brain.scanner import scan_brain
from apps.brain.storage import read_document

from .test_views import BrainViewTestCase


class IdentityTests(BrainViewTestCase):
    def setUp(self):
        super().setUp()
        self.create_brain()

    def edit_url(self, slug):
        return reverse("dashboard:identity_edit", kwargs={"slug": slug})

    def docs(self):
        return scan_brain(self.root, use_cache=False).identity

    def test_index_lists_all_three(self):
        response = self.client.get(reverse("dashboard:identity"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            [row["slug"] for row in response.context["rows"]],
            ["core", "voice", "beliefs"],
        )

    def test_edit_form_loads_the_shipped_prompts(self):
        response = self.client.get(self.edit_url("voice"))
        self.assertEqual(response.status_code, 200)
        self.assertIn("The shape of my sentences", response.context["form"].initial["body"])

    def test_an_unknown_slug_is_a_404(self):
        self.assertEqual(self.client.get(self.edit_url("vibes")).status_code, 404)

    def test_saving_writes_the_file_and_commits(self):
        response = self.client.post(
            self.edit_url("voice"),
            {"visibility": "private", "body": "Short sentences. No hedging."},
        )
        self.assertRedirects(
            response, self.edit_url("voice"), fetch_redirect_response=False
        )
        meta, body = read_document(self.root / "identity" / "voice.md")
        self.assertEqual(meta, {"visibility": "private"})
        self.assertEqual(body, "Short sentences. No hedging.")

    def test_a_saved_file_counts_as_written(self):
        self.client.post(
            self.edit_url("core"),
            {"visibility": "private", "body": "I build small local tools."},
        )
        self.assertTrue(self.docs()["core"].is_filled_in)

    def test_a_body_still_holding_todos_does_not_count_as_written(self):
        self.client.post(
            self.edit_url("core"), {"visibility": "private", "body": "TODO — later."}
        )
        self.assertFalse(self.docs()["core"].is_filled_in)

    def test_visibility_can_be_changed(self):
        self.client.post(
            self.edit_url("beliefs"), {"visibility": "public", "body": "I believe X."}
        )
        self.assertEqual(self.docs()["beliefs"].visibility, "public")

    def test_rejects_an_empty_body(self):
        response = self.client.post(
            self.edit_url("voice"), {"visibility": "private", "body": ""}
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("body", response.context["form"].errors)

    def test_falls_back_to_the_template_when_the_file_is_gone(self):
        (self.root / "identity" / "voice.md").unlink()
        response = self.client.get(self.edit_url("voice"))
        self.assertEqual(response.status_code, 200)
        self.assertIn("The shape of my sentences", response.context["form"].initial["body"])

    def test_saving_after_deletion_recreates_the_file(self):
        (self.root / "identity" / "voice.md").unlink()
        self.client.post(
            self.edit_url("voice"), {"visibility": "private", "body": "Recreated."}
        )
        self.assertTrue((self.root / "identity" / "voice.md").is_file())
