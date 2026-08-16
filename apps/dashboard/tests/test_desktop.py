import json
import sys

from django.urls import reverse

from apps.dashboard.desktop import SERVER_KEY, describe

from .test_views import BrainViewTestCase


class DesktopConfigTests(BrainViewTestCase):
    def setUp(self):
        super().setUp()
        self.create_brain()

    def config(self):
        return json.loads(describe(self.root).config_json)

    def test_names_one_server_under_mcp_servers(self):
        self.assertEqual(list(self.config()["mcpServers"]), [SERVER_KEY])

    def test_uses_the_running_interpreter(self):
        """The venv's python, not whatever `python` resolves to on PATH."""
        self.assertEqual(self.config()["mcpServers"][SERVER_KEY]["command"], sys.executable)

    def test_passes_the_brain_path_explicitly(self):
        args = self.config()["mcpServers"][SERVER_KEY]["args"]
        self.assertEqual(args[:2], ["-m", "brain_mcp"])
        self.assertIn(str(self.root.resolve()), args)

    def test_sets_pythonpath_rather_than_relying_on_cwd(self):
        """Not every MCP client honours cwd; PYTHONPATH always works."""
        entry = self.config()["mcpServers"][SERVER_KEY]
        self.assertIn("PYTHONPATH", entry["env"])
        self.assertNotIn("cwd", entry)

    def test_every_path_is_absolute(self):
        entry = self.config()["mcpServers"][SERVER_KEY]
        self.assertTrue(entry["command"].startswith("/"))
        self.assertTrue(entry["env"]["PYTHONPATH"].startswith("/"))
        self.assertTrue(entry["args"][-1].startswith("/"))

    def test_reports_whether_the_brain_exists(self):
        self.assertTrue(describe(self.root).brain_exists)
        self.assertFalse(describe(self.root / "nope").brain_exists)

    def test_the_command_line_mirrors_the_config(self):
        connection = describe(self.root)
        command = connection.command_line
        self.assertIn(connection.python, command)
        self.assertIn(connection.brain_path, command)
        self.assertIn("PYTHONPATH=", command)


class DesktopPageTests(BrainViewTestCase):
    def setUp(self):
        super().setUp()
        self.create_brain()

    def test_the_skills_page_carries_the_desktop_config(self):
        response = self.client.get(reverse("dashboard:skills"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Claude Desktop")
        self.assertContains(response, "mcpServers")

    def test_the_rendered_config_is_valid_json(self):
        """It is copy-pasted verbatim into a config file — it must parse."""
        response = self.client.get(reverse("dashboard:skills"))
        rendered = response.context["desktop"].config_json
        self.assertEqual(list(json.loads(rendered)["mcpServers"]), [SERVER_KEY])

    def test_names_the_config_file_location(self):
        response = self.client.get(reverse("dashboard:skills"))
        self.assertContains(response, "claude_desktop_config.json")

    def test_without_a_brain_the_page_redirects_to_setup(self):
        """Why the template carries no missing-brain branch: it is unreachable."""
        import shutil

        shutil.rmtree(self.root)
        response = self.client.get(reverse("dashboard:skills"))
        self.assertRedirects(
            response, reverse("dashboard:setup"), fetch_redirect_response=False
        )
