"""One place that knows where the brain is and hands out snapshots.

Views never touch `settings.BRAIN_PATH` directly. Keeping it here means the
tests can point at a temporary brain by overriding one setting, and there is
a single seam if the path ever becomes configurable at runtime.
"""

from pathlib import Path

from django.conf import settings

from apps.brain.scanner import Brain, scan_brain


def brain_root() -> Path:
    return Path(settings.BRAIN_PATH)


def brain_exists() -> bool:
    return brain_root().is_dir()


def current_brain() -> Brain:
    return scan_brain(brain_root())
