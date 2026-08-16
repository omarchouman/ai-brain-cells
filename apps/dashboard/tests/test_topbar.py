from django.urls import reverse

from .test_views import BrainViewTestCase


class TopbarTests(BrainViewTestCase):
    def setUp(self):
        super().setUp()
        self.create_brain()

    def get(self, name="dashboard:overview"):
        return self.client.get(reverse(name))

    def test_renders_on_a_page(self):
        self.assertContains(self.get(), 'class="topbar"')

    def test_shows_the_page_as_context(self):
        self.assertContains(self.get(), "Overview")

    def test_appears_across_pages_not_just_one(self):
        for name in ("dashboard:overview", "dashboard:notes", "dashboard:skills"):
            with self.subTest(page=name):
                self.assertContains(self.get(name), 'class="topbar"')


class ThemeToggleTests(BrainViewTestCase):
    def setUp(self):
        super().setUp()
        self.create_brain()

    def test_the_toggle_is_present_and_labelled(self):
        response = self.get_overview()
        self.assertContains(response, 'id="theme-toggle"')
        self.assertContains(response, "Switch between light and dark")

    def test_theme_resolves_before_first_paint(self):
        """The inline head script is what prevents a white flash for a
        dark-theme user; a deferred bundle would run too late."""
        html = self.get_overview().content.decode()
        head = html.split("</head>")[0]
        self.assertIn("abc-theme", head)
        self.assertIn("data-theme", head)
        self.assertLess(head.index("abc-theme"), head.index("css/app.css"))

    def test_no_stored_choice_means_no_attribute_so_the_os_decides(self):
        html = self.get_overview().content.decode()
        self.assertNotIn('<html lang="en" data-theme', html)

    def get_overview(self):
        return self.client.get(reverse("dashboard:overview"))


class AccountMenuTests(BrainViewTestCase):
    def setUp(self):
        super().setUp()
        self.create_brain()
        self.html = self.client.get(reverse("dashboard:overview")).content.decode()

    def test_the_trigger_declares_its_menu(self):
        self.assertIn('aria-haspopup="menu"', self.html)
        self.assertIn('aria-controls="account-menu"', self.html)

    def test_the_menu_starts_closed(self):
        self.assertIn('aria-expanded="false"', self.html)
        self.assertIn('id="account-menu"', self.html)
        self.assertIn("hidden>", self.html)

    def test_it_offers_profile_and_sign_out(self):
        self.assertIn("Profile", self.html)
        self.assertIn("Sign out", self.html)

    def test_unwired_items_say_so_rather_than_silently_doing_nothing(self):
        """A control that looks live and isn't reads as broken. These are
        marked until they are real."""
        self.assertIn('aria-disabled="true"', self.html)
        self.assertIn("soon", self.html)

    def test_the_menu_header_shows_something_true(self):
        self.assertIn("This brain", self.html)
        self.assertIn(str(self.root), self.html)


class TopbarIsConsistentEverywhereTests(BrainViewTestCase):
    """The bar is on every page, so it must not depend on what a given view
    remembered to pass into its context."""

    def setUp(self):
        super().setUp()
        self.create_brain()

    def test_the_brain_path_shows_on_pages_whose_view_never_passes_it(self):
        for name in ("dashboard:notes", "dashboard:identity", "dashboard:taxonomy"):
            with self.subTest(page=name):
                html = self.client.get(reverse(name)).content.decode()
                self.assertIn(str(self.root), html)
