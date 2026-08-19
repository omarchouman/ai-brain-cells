"""The theme toggle is CSS, not Python, and the way it broke was invisible to
every browser test run on a light-OS machine: the light palette lived only
inside `@media (prefers-color-scheme: light)`, so on a dark-OS machine
`data-theme="light"` set an attribute that matched nothing. These parse the
stylesheet directly so the guarantee does not depend on what OS the test
runner happens to prefer."""

import re

from django.conf import settings
from django.test import SimpleTestCase

CSS = (settings.BASE_DIR / "static" / "css" / "app.css").read_text()

TOKEN_RE = re.compile(r"(--[a-z0-9-]+)\s*:\s*([^;]+);")


def block_after(marker: str) -> str:
    """The declaration block following a selector, to its closing brace."""
    start = CSS.index(marker) + len(marker)
    depth, out = 1, []
    for char in CSS[start:]:
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                break
        out.append(char)
    return "".join(out)


def tokens(block: str) -> dict[str, str]:
    return {name: value.strip() for name, value in TOKEN_RE.findall(block)}


def strip_media_blocks(css: str) -> str:
    """Remove every @media rule and its body, leaving top-level rules only."""
    out, i = [], 0
    while i < len(css):
        at = css.find("@media", i)
        if at == -1:
            out.append(css[i:])
            break
        out.append(css[i:at])
        brace = css.index("{", at)
        depth, j = 1, brace + 1
        while depth and j < len(css):
            if css[j] == "{":
                depth += 1
            elif css[j] == "}":
                depth -= 1
            j += 1
        i = j
    return "".join(out)


class ThemeOverrideTests(SimpleTestCase):
    def test_an_explicit_light_choice_applies_without_a_media_query(self):
        """The bug: with dark on bare :root, a light override that only exists
        inside prefers-color-scheme:light never fires on a dark-OS machine."""
        self.assertIn(':root[data-theme="light"] {', CSS)
        self.assertIn(
            ':root[data-theme="light"] {',
            strip_media_blocks(CSS),
            "the light override only exists inside a media query",
        )

    def test_the_explicit_override_defines_the_whole_palette(self):
        """Every colour the OS-driven block themes, the explicit choice must
        theme too. Typography and radii are not theme-dependent and are
        deliberately absent."""
        from_media = set(tokens(block_after(':root:not([data-theme="dark"]) {')))
        explicit = set(tokens(block_after(':root[data-theme="light"] {')))
        self.assertEqual(from_media - explicit, set())

    def test_the_two_light_blocks_stay_identical(self):
        """They are duplicated because CSS cannot share a block between a media
        rule and a plain selector. Nothing but this stops them drifting."""
        from_media = tokens(block_after(':root:not([data-theme="dark"]) {'))
        explicit = tokens(block_after(':root[data-theme="light"] {'))
        self.assertEqual(from_media, explicit)

    def test_dark_is_the_base_so_it_needs_no_media_query(self):
        base = tokens(block_after(":root {"))
        self.assertEqual(base["--bg"], "#14101c")

    def test_both_directions_are_reachable_from_either_os_preference(self):
        """What the toggle actually promises: whichever way the OS leans, both
        explicit choices repaint."""
        base_dark = tokens(block_after(":root {"))
        explicit_light = tokens(block_after(':root[data-theme="light"] {'))
        self.assertNotEqual(base_dark["--bg"], explicit_light["--bg"])
        # data-theme="dark" reaches the base palette by failing the
        # :not([data-theme="dark"]) guard on the media block.
        self.assertIn(':root:not([data-theme="dark"])', CSS)
