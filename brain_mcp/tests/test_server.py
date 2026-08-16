"""Tests drive the real MCP server through `call_tool`, so tool registration,
generated schemas, and argument coercion are exercised rather than assumed."""

import asyncio
import tempfile
from datetime import date, timedelta
from pathlib import Path

from django.conf import settings
from django.test import SimpleTestCase

from apps.brain.notes import IdentityDoc, Lens, Note, ProjectCard
from apps.brain.repo import initialize_brain
from apps.brain.scanner import clear_cache
from apps.brain.storage import read_document, write_document
from apps.brain.writer import (
    assign_note_id,
    save_identity,
    save_lens,
    save_note,
    save_project,
    supersede_note,
)
from brain_mcp.__main__ import resolve_brain_path
from brain_mcp.server import build_server


class ServerTestCase(SimpleTestCase):
    databases = set()

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.addCleanup(clear_cache)
        self.root = Path(self._tmp.name) / "brain"
        initialize_brain(self.root, settings.BRAIN_TEMPLATE_PATH)
        self.server = build_server(self.root)

    def call(self, tool, **arguments):
        result = asyncio.run(self.server.call_tool(tool, arguments))
        return "\n".join(
            block.text for block in result.content if getattr(block, "text", None)
        )

    def add_note(self, title, **overrides):
        note = Note(
            id="",
            type=overrides.get("type", "take"),
            title=title,
            topics=overrides.get("topics", ["django"]),
            projects=overrides.get("projects", []),
            status="current",
            superseded_by=None,
            visibility=overrides.get("visibility", "public"),
            date=overrides.get("date", "2026-08"),
            body=overrides.get("body", "A body about frameworks."),
        )
        assign_note_id(self.root, note)
        save_note(self.root, note)
        return note


class ToolRegistrationTests(ServerTestCase):
    def test_every_expected_tool_is_registered(self):
        names = {t.name for t in asyncio.run(self.server.list_tools())}
        self.assertEqual(
            names,
            {
                "brain_overview",
                "search_brain",
                "read_notes",
                "get_identity",
                "list_notes",
                "list_projects",
                "get_project",
                "list_lenses",
                "read_index",
            },
        )

    def test_no_write_tool_is_exposed(self):
        """Read-only is a safety property, not an oversight — pin it."""
        names = {t.name for t in asyncio.run(self.server.list_tools())}
        for forbidden in ("save", "write", "create", "delete", "edit", "update"):
            self.assertFalse(
                any(forbidden in name for name in names),
                f"a tool matching '{forbidden}' is exposed: {names}",
            )

    def test_tools_carry_descriptions_and_schemas(self):
        for tool in asyncio.run(self.server.list_tools()):
            with self.subTest(tool=tool.name):
                self.assertTrue(tool.description)
                self.assertIn("properties", tool.input_schema)

    def test_the_contract_rules_travel_with_the_server(self):
        instructions = self.server.instructions
        for rule in ("private", "superseded", "VERBATIM", "45 days"):
            self.assertIn(rule, instructions)


class OverviewTests(ServerTestCase):
    def test_reports_counts_and_identity_state(self):
        self.add_note("Django beats FastAPI")
        out = self.call("brain_overview")
        self.assertIn("1 takes", out)
        self.assertIn("core: still a template", out)

    def test_marks_a_written_identity_file(self):
        save_identity(self.root, IdentityDoc(slug="voice", body="Short sentences."))
        self.assertIn("voice: written", self.call("brain_overview"))

    def test_flags_unparseable_files(self):
        (self.root / "knowledge" / "takes" / "broken.md").write_text("no frontmatter\n")
        self.assertIn("could not be parsed", self.call("brain_overview"))

    def test_a_missing_brain_explains_where_it_looked(self):
        server = build_server(self.root.parent / "nope")
        out = asyncio.run(server.call_tool("brain_overview", {}))
        self.assertIn("No brain found", out.content[0].text)


class SearchTests(ServerTestCase):
    def setUp(self):
        super().setUp()
        self.add_note("Django beats FastAPI for solo projects")
        self.add_note("Vector databases are overrated", topics=["ai-agents"],
                      body="Grep beat embeddings.", type="story")

    def test_finds_by_title(self):
        out = self.call("search_brain", query="fastapi")
        self.assertIn("Django beats FastAPI", out)
        self.assertNotIn("Vector databases", out)

    def test_returns_ids_for_follow_up_reads(self):
        self.assertIn("id: take-2026-08-django", self.call("search_brain", query="fastapi"))

    def test_returns_snippets_not_whole_bodies(self):
        long_body = "unique-marker " + ("padding " * 400)
        self.add_note("Long one", body=long_body)
        out = self.call("search_brain", query="unique-marker")
        self.assertLess(len(out), 1500)

    def test_narrows_by_type(self):
        out = self.call("search_brain", query="databases", type="story")
        self.assertIn("Vector databases", out)

    def test_no_match_says_so_rather_than_inventing(self):
        out = self.call("search_brain", query="quantum tunnelling")
        self.assertIn("No notes match", out)
        self.assertIn("rather than answering as though it did", out)

    def test_private_notes_are_withheld_by_default(self):
        self.add_note("Secret position", visibility="private", body="Confidential.")
        self.assertIn("No notes match", self.call("search_brain", query="secret position"))

    def test_private_notes_are_labelled_when_explicitly_requested(self):
        self.add_note("Secret position", visibility="private", body="Confidential.")
        out = self.call("search_brain", query="secret position", include_private=True)
        self.assertIn("PRIVATE", out)

    def test_superseded_notes_are_labelled_as_history(self):
        old = self.add_note("Old position")
        new = self.add_note("New position")
        from apps.brain.scanner import scan_brain

        stored = scan_brain(self.root, use_cache=False).note(old.id)
        supersede_note(self.root, stored, new.id)

        out = self.call("search_brain", query="old position")
        self.assertIn("SUPERSEDED", out)

    def test_a_voice_line_is_flagged(self):
        self.add_note("Voiced take", body='Prose.\n\n> VERBATIM: "How I say it."')
        self.assertIn("voice", self.call("search_brain", query="voiced take"))

    def test_pagination_is_reported(self):
        for i in range(30):
            self.add_note(f"Framework note {i}")
        out = self.call("search_brain", query="framework note", limit=5)
        self.assertIn("showing 5", out)
        self.assertIn("offset=5", out)


class ReadNotesTests(ServerTestCase):
    def test_returns_full_bodies(self):
        note = self.add_note("Django beats FastAPI", body="The whole argument here.")
        out = self.call("read_notes", ids=[note.id])
        self.assertIn("The whole argument here.", out)

    def test_unknown_ids_are_reported(self):
        self.assertIn("ghost", self.call("read_notes", ids=["ghost"]))

    def test_private_notes_are_not_readable_by_id_by_default(self):
        note = self.add_note("Secret", visibility="private", body="Confidential text.")
        out = self.call("read_notes", ids=[note.id])
        self.assertNotIn("Confidential text.", out)

    def test_budget_overflow_names_what_it_skipped(self):
        ids = [self.add_note(f"Note {i}", body="x" * 3000).id for i in range(20)]
        out = self.call("read_notes", ids=ids)
        self.assertIn("Skipped to stay within the response budget", out)


class IdentityTests(ServerTestCase):
    def test_returns_all_three_by_default(self):
        out = self.call("get_identity")
        for slug in ("core", "voice", "beliefs"):
            self.assertIn(f"identity/{slug}.md", out)

    def test_can_ask_for_one(self):
        out = self.call("get_identity", files=["voice"])
        self.assertIn("identity/voice.md", out)
        self.assertNotIn("identity/beliefs.md", out)

    def test_an_unwritten_file_is_labelled_not_presented_as_an_answer(self):
        self.assertIn("STILL A TEMPLATE", self.call("get_identity", files=["core"]))

    def test_a_written_file_is_not_labelled(self):
        save_identity(self.root, IdentityDoc(slug="voice", body="Short sentences."))
        out = self.call("get_identity", files=["voice"])
        self.assertIn("Short sentences.", out)
        self.assertNotIn("STILL A TEMPLATE", out)


class ProjectTests(ServerTestCase):
    def make_card(self, days_old=0):
        card = ProjectCard(
            id="project-brain",
            title="AI Brain Cells",
            status="active",
            topics=["django"],
            visibility="public",
            last_verified=date.today() - timedelta(days=days_old),
            body="## What it is\nA dashboard over a markdown brain.\n\n## Where it stands\n1,200 users.",
        )
        return save_project(self.root, card).path

    def test_lists_cards(self):
        self.make_card()
        self.assertIn("AI Brain Cells", self.call("list_projects"))

    def test_a_fresh_card_is_not_marked_stale(self):
        self.make_card(days_old=3)
        self.assertNotIn("UNVERIFIED", self.call("list_projects"))

    def test_a_stale_card_carries_the_hedging_instruction(self):
        path = self.make_card()
        meta, body = read_document(path)
        meta["last_verified"] = (date.today() - timedelta(days=200)).isoformat()
        write_document(path, meta, body)

        out = self.call("list_projects")
        self.assertIn("UNVERIFIED 200d", out)
        self.assertIn("do not present its numbers", out)

    def test_reads_one_card_in_full(self):
        self.make_card()
        out = self.call("get_project", slug="brain")
        self.assertIn("1,200 users", out)

    def test_an_unknown_slug_lists_the_known_ones(self):
        self.make_card()
        out = self.call("get_project", slug="nope")
        self.assertIn("Known slugs: brain", out)


class ListingTests(ServerTestCase):
    def test_lists_notes_newest_first_with_totals(self):
        for i in range(15):
            self.add_note(f"Note {i}")
        out = self.call("list_notes", limit=5)
        self.assertIn("15 total", out)
        self.assertIn("showing 5", out)

    def test_hides_private_notes(self):
        self.add_note("Secret", visibility="private")
        self.assertNotIn("Secret", self.call("list_notes"))

    def test_lenses_are_listed(self):
        save_lens(self.root, Lens(name="public-writing", topics=["django"], types=["take"]))
        out = self.call("list_lenses")
        self.assertIn("public-writing", out)

    def test_no_lenses_explains_the_default_scope(self):
        self.assertIn("Work open", self.call("list_lenses"))

    def test_index_is_readable(self):
        self.add_note("Django beats FastAPI")
        self.assertIn("django-beats-fastapi", self.call("read_index"))


class BrainPathResolutionTests(SimpleTestCase):
    def test_flag_wins(self):
        self.assertEqual(
            resolve_brain_path(["--brain", "/tmp/somewhere"]),
            Path("/tmp/somewhere").resolve(),
        )

    def test_env_var_is_used_when_no_flag(self):
        import os

        original = os.environ.get("BRAIN_PATH")
        os.environ["BRAIN_PATH"] = "/tmp/from-env"
        try:
            self.assertEqual(resolve_brain_path([]), Path("/tmp/from-env").resolve())
        finally:
            if original is None:
                del os.environ["BRAIN_PATH"]
            else:
                os.environ["BRAIN_PATH"] = original

    def test_falls_back_to_the_project_brain(self):
        import os

        original = os.environ.pop("BRAIN_PATH", None)
        try:
            self.assertEqual(resolve_brain_path([]).name, "brain")
        finally:
            if original is not None:
                os.environ["BRAIN_PATH"] = original
