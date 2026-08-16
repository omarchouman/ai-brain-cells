import tempfile
from pathlib import Path

from django.test import override_settings
from django.urls import reverse

from apps.dashboard import skills

from .test_views import BrainViewTestCase


class SkillsTestCase(BrainViewTestCase):
    """Points CLAUDE_SKILLS_PATH at a temp dir. Nothing here may ever touch
    the real ~/.claude/skills."""

    def setUp(self):
        super().setUp()
        self.create_brain()
        self._skills_tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._skills_tmp.cleanup)
        self.skills_dir = Path(self._skills_tmp.name) / "skills"
        self._skills_override = override_settings(CLAUDE_SKILLS_PATH=self.skills_dir)
        self._skills_override.enable()
        self.addCleanup(self._skills_override.disable)

    def installed(self, name):
        return self.skills_dir / name / "SKILL.md"


class RenderTests(SkillsTestCase):
    def test_substitutes_the_brain_path(self):
        text = skills.render("mind-reader", self.root)
        self.assertIn(str(self.root), text)
        self.assertNotIn("{{BRAIN_PATH}}", text)

    def test_both_skills_carry_the_path(self):
        for name in skills.SKILL_NAMES:
            with self.subTest(name=name):
                self.assertNotIn("{{BRAIN_PATH}}", skills.render(name, self.root))

    def test_frontmatter_survives_rendering(self):
        text = skills.render("mind-feeder", self.root)
        self.assertTrue(text.startswith("---\n"))
        self.assertIn("name: mind-feeder", text)
        self.assertIn("description:", text)


class StatusTests(SkillsTestCase):
    def test_reports_not_installed_on_a_clean_machine(self):
        states = {s.name: s.state for s in skills.status(self.root)}
        self.assertEqual(
            states, {"mind-reader": "not-installed", "mind-feeder": "not-installed"}
        )

    def test_reports_installed_after_installing(self):
        skills.install(self.root)
        states = {s.name: s.state for s in skills.status(self.root)}
        self.assertEqual(
            states, {"mind-reader": "installed", "mind-feeder": "installed"}
        )

    def test_reports_stale_when_the_brain_moved(self):
        skills.install(Path("/somewhere/else"))
        states = {s.name: s.state for s in skills.status(self.root)}
        self.assertEqual(states["mind-reader"], "stale")

    def test_reports_stale_when_the_shipped_skill_changed(self):
        skills.install(self.root)
        self.installed("mind-reader").write_text("edited by hand")
        self.assertEqual(skills.status(self.root)[0].state, "stale")

    def test_carries_the_description_for_display(self):
        summary = skills.status(self.root)[0].summary
        self.assertIn("Retrieve", summary)


class InstallTests(SkillsTestCase):
    def test_writes_both_files(self):
        written = skills.install(self.root)
        self.assertEqual(len(written), 2)
        for name in skills.SKILL_NAMES:
            self.assertTrue(self.installed(name).is_file())

    def test_creates_missing_directories(self):
        self.assertFalse(self.skills_dir.exists())
        skills.install(self.root)
        self.assertTrue(self.skills_dir.is_dir())

    def test_reinstalling_overwrites(self):
        skills.install(Path("/old/brain"))
        skills.install(self.root)
        self.assertIn(str(self.root), self.installed("mind-reader").read_text())

    def test_uninstall_removes_the_files_and_empty_folders(self):
        skills.install(self.root)
        removed = skills.uninstall()
        self.assertEqual(len(removed), 2)
        self.assertFalse((self.skills_dir / "mind-reader").exists())

    def test_uninstall_leaves_a_folder_holding_other_files(self):
        skills.install(self.root)
        (self.skills_dir / "mind-reader" / "notes.md").write_text("mine")

        skills.uninstall()

        self.assertFalse(self.installed("mind-reader").exists())
        self.assertTrue((self.skills_dir / "mind-reader" / "notes.md").is_file())

    def test_uninstall_on_a_clean_machine_is_a_no_op(self):
        self.assertEqual(skills.uninstall(), [])


class SkillViewTests(SkillsTestCase):
    def test_page_renders(self):
        response = self.client.get(reverse("dashboard:skills"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "mind-reader")
        self.assertContains(response, "not installed")

    def test_install_button_writes_the_files(self):
        response = self.client.post(reverse("dashboard:skills_install"))
        self.assertRedirects(
            response, reverse("dashboard:skills"), fetch_redirect_response=False
        )
        self.assertTrue(self.installed("mind-feeder").is_file())

    def test_page_reports_installed_afterwards(self):
        self.client.post(reverse("dashboard:skills_install"))
        response = self.client.get(reverse("dashboard:skills"))
        self.assertEqual(
            {s.state for s in response.context["skills"]}, {"installed"}
        )

    def test_uninstall_button_removes_them(self):
        self.client.post(reverse("dashboard:skills_install"))
        self.client.post(reverse("dashboard:skills_uninstall"))
        self.assertFalse(self.installed("mind-reader").exists())

    def test_install_rejects_a_get(self):
        self.assertEqual(
            self.client.get(reverse("dashboard:skills_install")).status_code, 405
        )

    def test_uninstall_rejects_a_get(self):
        self.assertEqual(
            self.client.get(reverse("dashboard:skills_uninstall")).status_code, 405
        )
