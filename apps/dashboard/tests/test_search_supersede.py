from django.urls import reverse

from apps.brain.notes import Note
from apps.brain.scanner import scan_brain
from apps.brain.writer import assign_note_id, save_note

from .test_views import BrainViewTestCase


class NoteSeedingTestCase(BrainViewTestCase):
    def setUp(self):
        super().setUp()
        self.create_brain()

    def add(self, title, body="A body.", note_type="take", topics=None):
        note = Note(
            id="", type=note_type, title=title, topics=topics or ["django"],
            projects=[], status="current", superseded_by=None,
            visibility="public", date="2026-08", body=body,
        )
        assign_note_id(self.root, note)
        return save_note(self.root, note)

    def notes(self):
        return scan_brain(self.root, use_cache=False).notes

    def search(self, query, **params):
        params["q"] = query
        return self.client.get(reverse("dashboard:notes"), params)


class SearchTests(NoteSeedingTestCase):
    def setUp(self):
        super().setUp()
        self.add("Django beats FastAPI", body="Admin panels for free.")
        self.add("Vector databases are overrated", body="Grep beat embeddings.",
                 note_type="story", topics=["ai-agents"])

    def test_matches_a_title(self):
        response = self.search("fastapi")
        self.assertEqual([n.title for n in response.context["notes"]], ["Django beats FastAPI"])

    def test_matches_body_text(self):
        response = self.search("embeddings")
        self.assertEqual(
            [n.title for n in response.context["notes"]],
            ["Vector databases are overrated"],
        )

    def test_matches_a_topic(self):
        response = self.search("ai-agents")
        self.assertEqual(len(response.context["notes"]), 1)

    def test_is_case_insensitive(self):
        self.assertEqual(len(self.search("GREP").context["notes"]), 1)

    def test_all_words_must_match(self):
        self.assertEqual(len(self.search("grep embeddings").context["notes"]), 1)
        self.assertEqual(len(self.search("grep fastapi").context["notes"]), 0)

    def test_no_matches_is_an_empty_list_not_an_error(self):
        response = self.search("nothing here")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["notes"], [])

    def test_search_combines_with_a_type_filter(self):
        response = self.search("a", type="story")
        self.assertTrue(all(n.type == "story" for n in response.context["notes"]))

    def test_search_includes_superseded_notes(self):
        old = self.notes()[0]
        new = self.notes()[1]
        self.client.post(
            reverse("dashboard:note_supersede", kwargs={"note_id": old.id}),
            {"successor": new.id},
        )

        found = self.search(old.title.split()[0]).context["notes"]

        self.assertIn(old.id, [n.id for n in found])


class SupersedeTests(NoteSeedingTestCase):
    def setUp(self):
        super().setUp()
        self.add("RAG is the only way")
        self.add("Plain markdown beats RAG")
        self.old, self.new = self.notes()[1], self.notes()[0]

    def supersede(self, successor):
        return self.client.post(
            reverse("dashboard:note_supersede", kwargs={"note_id": self.old.id}),
            {"successor": successor},
        )

    def reload(self, note_id):
        return scan_brain(self.root, use_cache=False).note(note_id)

    def test_marks_the_old_note_as_history(self):
        self.supersede(self.new.id)
        old = self.reload(self.old.id)
        self.assertEqual(old.status, "superseded")
        self.assertEqual(old.superseded_by, self.new.id)

    def test_keeps_the_file(self):
        self.supersede(self.new.id)
        self.assertTrue(self.old.path.exists())

    def test_the_superseded_note_leaves_the_default_list(self):
        self.supersede(self.new.id)
        response = self.client.get(reverse("dashboard:notes"))
        self.assertNotIn(self.old.id, [n.id for n in response.context["notes"]])
        self.assertEqual(response.context["superseded_count"], 1)

    def test_rejects_an_empty_choice(self):
        self.supersede("")
        self.assertEqual(self.reload(self.old.id).status, "current")

    def test_rejects_a_note_superseding_itself(self):
        self.supersede(self.old.id)
        self.assertEqual(self.reload(self.old.id).status, "current")

    def test_rejects_an_unknown_successor(self):
        self.supersede("take-2026-08-does-not-exist")
        self.assertEqual(self.reload(self.old.id).status, "current")

    def test_rejects_a_get(self):
        response = self.client.get(
            reverse("dashboard:note_supersede", kwargs={"note_id": self.old.id})
        )
        self.assertEqual(response.status_code, 405)

    def test_the_edit_page_offers_every_other_current_note(self):
        response = self.client.get(
            reverse("dashboard:note_edit", kwargs={"note_id": self.old.id})
        )
        self.assertEqual(
            [n.id for n in response.context["successors"]], [self.new.id]
        )

    def test_reviving_makes_it_current_again(self):
        self.supersede(self.new.id)

        self.client.post(
            reverse("dashboard:note_revive", kwargs={"note_id": self.old.id})
        )

        revived = self.reload(self.old.id)
        self.assertEqual(revived.status, "current")
        self.assertIsNone(revived.superseded_by)

    def test_the_edit_page_names_what_replaced_it(self):
        self.supersede(self.new.id)
        response = self.client.get(
            reverse("dashboard:note_edit", kwargs={"note_id": self.old.id})
        )
        self.assertEqual(response.context["replaced_by"].id, self.new.id)
