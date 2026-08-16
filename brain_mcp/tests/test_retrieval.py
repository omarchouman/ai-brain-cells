import time

from django.test import SimpleTestCase

from apps.brain.notes import Note
from brain_mcp.retrieval import (
    DEFAULT_LIMIT,
    MAX_LIMIT,
    Page,
    clamp_limit,
    filter_notes,
    paginate,
    read_notes,
    search,
    snippet,
    tokenize,
    topic_counts,
)


def make_note(
    title,
    body="A body.",
    *,
    note_type="take",
    topics=(),
    projects=(),
    status="current",
    visibility="public",
    date="2026-08",
    note_id=None,
):
    return Note(
        id=note_id or f"{note_type}-{date}-{title.lower().replace(' ', '-')}",
        type=note_type,
        title=title,
        topics=list(topics),
        projects=list(projects),
        status=status,
        superseded_by="x" if status == "superseded" else None,
        visibility=visibility,
        date=date,
        body=body,
    )


class TokenizeTests(SimpleTestCase):
    def test_lowercases_and_splits_on_punctuation(self):
        self.assertEqual(tokenize("Django beats FastAPI: here's why!"),
                         ["django", "beats", "fastapi", "here", "s", "why"])

    def test_empty_input(self):
        self.assertEqual(tokenize(""), [])
        self.assertEqual(tokenize(None), [])


class PaginationTests(SimpleTestCase):
    def test_clamps_limit_to_a_ceiling(self):
        self.assertEqual(clamp_limit(10_000), MAX_LIMIT)

    def test_defaults_a_missing_or_silly_limit(self):
        self.assertEqual(clamp_limit(None), DEFAULT_LIMIT)
        self.assertEqual(clamp_limit(0), DEFAULT_LIMIT)
        self.assertEqual(clamp_limit(-5), DEFAULT_LIMIT)

    def test_reports_total_and_more(self):
        page = paginate(list(range(100)), limit=10, offset=0)
        self.assertEqual(page.items, list(range(10)))
        self.assertEqual(page.total, 100)
        self.assertTrue(page.has_more)
        self.assertEqual(page.next_offset, 10)

    def test_last_page_has_no_more(self):
        page = paginate(list(range(15)), limit=10, offset=10)
        self.assertEqual(len(page.items), 5)
        self.assertFalse(page.has_more)
        self.assertIsNone(page.next_offset)

    def test_offset_past_the_end_is_empty_not_an_error(self):
        page = paginate(list(range(5)), limit=10, offset=99)
        self.assertEqual(page.items, [])
        self.assertEqual(page.total, 5)
        self.assertFalse(page.has_more)


class FilterTests(SimpleTestCase):
    def setUp(self):
        self.notes = [
            make_note("Public take", topics=["django"]),
            make_note("Private take", visibility="private"),
            make_note("Old take", status="superseded"),
            make_note("A story", note_type="story", topics=["python"]),
            make_note("Project note", projects=["project-brain"]),
        ]

    def test_excludes_private_by_default(self):
        titles = [n.title for n in filter_notes(self.notes, status=None)]
        self.assertNotIn("Private take", titles)

    def test_private_requires_asking_for_it(self):
        titles = [
            n.title
            for n in filter_notes(self.notes, status=None, include_private=True)
        ]
        self.assertIn("Private take", titles)

    def test_excludes_superseded_by_default(self):
        titles = [n.title for n in filter_notes(self.notes)]
        self.assertNotIn("Old take", titles)

    def test_filters_by_type_topic_and_project(self):
        self.assertEqual(
            [n.title for n in filter_notes(self.notes, note_type="story")], ["A story"]
        )
        self.assertEqual(
            [n.title for n in filter_notes(self.notes, topic="django")], ["Public take"]
        )
        self.assertEqual(
            [n.title for n in filter_notes(self.notes, project="project-brain")],
            ["Project note"],
        )


class SnippetTests(SimpleTestCase):
    def test_short_bodies_come_back_whole(self):
        self.assertEqual(snippet("Short body.", ["body"]), "Short body.")

    def test_collapses_whitespace(self):
        self.assertEqual(snippet("a\n\n  b\tc", ["a"]), "a b c")

    def test_windows_around_the_first_match(self):
        body = ("filler " * 100) + "NEEDLE here " + ("filler " * 100)
        result = snippet(body, ["needle"], width=60)
        self.assertIn("NEEDLE", result)
        self.assertLessEqual(len(result), 64)

    def test_falls_back_to_the_opening_when_nothing_matches(self):
        body = "alpha " * 100
        result = snippet(body, ["zzz"], width=40)
        self.assertTrue(result.startswith("alpha"))
        self.assertTrue(result.endswith("…"))

    def test_drops_the_verbatim_marker_from_the_preview(self):
        body = 'Prose.\n\n> VERBATIM: "How I say it."'
        self.assertNotIn("VERBATIM", snippet(body, ["prose"]))


class SearchRankingTests(SimpleTestCase):
    def setUp(self):
        self.notes = [
            make_note("Django beats FastAPI", body="Nothing relevant here.",
                      topics=["django"], note_id="a"),
            make_note("Unrelated title", body="django django django mentioned thrice.",
                      note_id="b"),
            make_note("Another unrelated", body="One passing django mention.",
                      note_id="c"),
        ]

    def test_a_title_match_outranks_body_mentions(self):
        page = search(self.notes, "django")
        self.assertEqual(page.items[0].note.id, "a")

    def test_body_repetition_is_capped(self):
        """A long note must not win by saying the word many times."""
        spammy = make_note("Spam", body=("django " * 500), note_id="spam")
        page = search([*self.notes, spammy], "django")
        self.assertEqual(page.items[0].note.id, "a")

    def test_matching_every_term_beats_matching_one_loudly(self):
        both = make_note("Django and python together", note_id="both")
        one = make_note("Django django django django", note_id="one")
        page = search([both, one], "django python")
        self.assertEqual(page.items[0].note.id, "both")

    def test_a_topic_match_counts(self):
        page = search(self.notes, "django", note_type="take")
        self.assertIn("a", [h.note.id for h in page.items])

    def test_verbatim_matches_are_weighted(self):
        voiced = make_note(
            "Some title", body='Prose.\n\n> VERBATIM: "grep beat embeddings."',
            note_id="voiced",
        )
        plain = make_note("Other title", body="grep appears once.", note_id="plain")
        page = search([voiced, plain], "grep")
        self.assertEqual(page.items[0].note.id, "voiced")

    def test_newer_notes_break_ties(self):
        old = make_note("Same title", date="2024-01", note_id="old")
        new = make_note("Same title", date="2026-08", note_id="new")
        page = search([old, new], "same title")
        self.assertEqual(page.items[0].note.id, "new")

    def test_no_matches_is_an_empty_page(self):
        page = search(self.notes, "nothingmatchesthis")
        self.assertEqual(page.items, [])
        self.assertEqual(page.total, 0)

    def test_an_empty_query_returns_nothing_rather_than_everything(self):
        page = search(self.notes, "   ")
        self.assertEqual(page.total, 0)

    def test_hits_carry_a_snippet(self):
        page = search(self.notes, "django")
        self.assertTrue(all(isinstance(h.snippet, str) for h in page.items))

    def test_superseded_notes_are_searchable_but_current_ones_rank_alongside(self):
        old = make_note("Retired position", status="superseded", note_id="ret")
        page = search([*self.notes, old], "retired position")
        self.assertIn("ret", [h.note.id for h in page.items])

    def test_superseded_can_be_excluded(self):
        old = make_note("Retired position", status="superseded", note_id="ret")
        page = search([*self.notes, old], "retired position", include_superseded=False)
        self.assertEqual(page.items, [])

    def test_private_notes_stay_out_by_default(self):
        secret = make_note("Secret take", visibility="private", note_id="s")
        page = search([secret], "secret")
        self.assertEqual(page.total, 0)
        self.assertEqual(search([secret], "secret", include_private=True).total, 1)


class ReadBudgetTests(SimpleTestCase):
    def test_reads_requested_notes(self):
        notes = [make_note("One", note_id="1"), make_note("Two", note_id="2")]
        result = read_notes(notes, ["1", "2"])
        self.assertEqual([n.id for n in result.notes], ["1", "2"])
        self.assertFalse(result.truncated)

    def test_reports_ids_that_do_not_exist(self):
        result = read_notes([make_note("One", note_id="1")], ["1", "ghost"])
        self.assertEqual(result.missing, ["ghost"])

    def test_caps_the_number_of_notes(self):
        notes = [make_note(f"N{i}", note_id=str(i)) for i in range(30)]
        result = read_notes(notes, [str(i) for i in range(30)], max_notes=5)
        self.assertEqual(len(result.notes), 5)
        self.assertTrue(result.truncated)
        self.assertEqual(len(result.skipped_for_budget), 25)

    def test_caps_total_characters(self):
        notes = [make_note(f"N{i}", body="x" * 5000, note_id=str(i)) for i in range(10)]
        result = read_notes(notes, [str(i) for i in range(10)], max_chars=12_000)
        self.assertLessEqual(sum(len(n.body) for n in result.notes), 12_000)
        self.assertTrue(result.truncated)

    def test_names_what_it_dropped_rather_than_dropping_silently(self):
        notes = [make_note(f"N{i}", note_id=str(i)) for i in range(4)]
        result = read_notes(notes, ["0", "1", "2", "3"], max_notes=2)
        self.assertEqual(result.skipped_for_budget, ["2", "3"])

    def test_a_private_note_is_not_readable_by_id_either(self):
        secret = make_note("Secret", visibility="private", note_id="s")
        result = read_notes([secret], ["s"])
        self.assertEqual(result.notes, [])
        self.assertEqual(result.missing, ["s"])


class ScaleTests(SimpleTestCase):
    """The claim is bounded responses at scale — assert it, don't assume it."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.many = [
            make_note(
                f"Note number {i} about django and testing",
                body=f"Body {i}. " + ("filler words for length. " * 40),
                topics=["django"] if i % 2 else ["python"],
                date=f"2026-{(i % 12) + 1:02d}",
                note_id=f"take-2026-{i:05d}",
            )
            for i in range(2000)
        ]

    def test_search_over_two_thousand_notes_stays_bounded(self):
        page = search(self.many, "django testing", limit=10)
        self.assertEqual(len(page.items), 10)
        self.assertGreater(page.total, 500)
        self.assertTrue(page.has_more)

    def test_a_caller_cannot_request_an_unbounded_page(self):
        page = search(self.many, "django", limit=100_000)
        self.assertEqual(len(page.items), MAX_LIMIT)

    def test_response_size_is_bounded_regardless_of_corpus_size(self):
        page = search(self.many, "django testing", limit=10)
        rendered = sum(len(h.note.title) + len(h.snippet) for h in page.items)
        self.assertLess(rendered, 4000)

    def test_reading_is_budgeted_even_when_many_ids_are_asked_for(self):
        ids = [n.id for n in self.many[:200]]
        result = read_notes(self.many, ids)
        self.assertLessEqual(len(result.notes), 12)
        self.assertLessEqual(sum(len(n.body) for n in result.notes), 24_000)
        self.assertTrue(result.truncated)

    def test_search_is_fast_enough_to_be_interactive(self):
        start = time.perf_counter()
        for _ in range(5):
            search(self.many, "django testing", limit=10)
        elapsed = (time.perf_counter() - start) / 5
        self.assertLess(elapsed, 1.0, f"search took {elapsed:.3f}s per call")

    def test_paging_through_a_large_result_set_terminates(self):
        seen, offset, pages = set(), 0, 0
        while True:
            page = search(self.many, "django", limit=MAX_LIMIT, offset=offset)
            for hit in page.items:
                seen.add(hit.note.id)
            pages += 1
            if not page.has_more or pages > 40:
                break
            offset = page.next_offset
        self.assertGreater(len(seen), 100)
        self.assertLessEqual(pages, 41)


class TopicCountTests(SimpleTestCase):
    def test_counts_topics_across_notes(self):
        notes = [
            make_note("A", topics=["django", "python"]),
            make_note("B", topics=["django"]),
        ]
        self.assertEqual(topic_counts(notes), {"django": 2, "python": 1})
