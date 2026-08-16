"""Creating the brain repo, and committing to it.

Git here is best-effort by design. The file write is the operation that
matters; the commit is history on top of it. If git is missing, or has no
identity configured, or the working tree is in some state we did not
anticipate, the note is still on disk and the dashboard says so. Losing
someone's writing because a subprocess exited non-zero would be a bad
trade for a tidier log.
"""

import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

FALLBACK_IDENTITY = ("ai-brain-cells", "brain@localhost")
GIT_TIMEOUT_SECONDS = 15


@dataclass
class GitResult:
    ok: bool
    sha: str | None = None
    detail: str = ""

    def __bool__(self) -> bool:
        return self.ok


@dataclass
class CommitEntry:
    sha: str
    subject: str
    when: str


def _run(root: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", "-C", str(root), *args],
        capture_output=True,
        text=True,
        timeout=GIT_TIMEOUT_SECONDS,
    )


def git_available() -> bool:
    try:
        return (
            subprocess.run(
                ["git", "--version"], capture_output=True, timeout=GIT_TIMEOUT_SECONDS
            ).returncode
            == 0
        )
    except (OSError, subprocess.SubprocessError):
        return False


def is_repo(root: Path) -> bool:
    """True only if `root` is the top level of a repo, not merely inside one.

    The distinction matters here: the brain lives inside this project's own
    repo. Asking git "are you in a repository" from an uninitialised brain/
    answers yes — about the parent — and commits would be aimed at the wrong
    history. Comparing against the toplevel is the question we actually mean.
    """
    root = Path(root)
    if not root.is_dir():
        return False
    try:
        result = _run(root, "rev-parse", "--show-toplevel")
    except (OSError, subprocess.SubprocessError):
        return False
    if result.returncode != 0:
        return False
    try:
        return Path(result.stdout.strip()).resolve() == root.resolve()
    except OSError:
        return False


def _identity_args(root: Path) -> list[str]:
    """Fall back to a local identity when git has no configured author.

    A fresh machine with no `git config --global user.email` would otherwise
    fail every commit, which is a confusing first-run experience for
    something that isn't really about git.
    """
    try:
        if _run(root, "var", "GIT_AUTHOR_IDENT").returncode == 0:
            return []
    except (OSError, subprocess.SubprocessError):
        return []
    name, email = FALLBACK_IDENTITY
    return ["-c", f"user.name={name}", "-c", f"user.email={email}"]


def init_repo(root: Path) -> GitResult:
    root = Path(root)
    if is_repo(root):
        return GitResult(True, detail="Already a git repository.")
    if not git_available():
        return GitResult(False, detail="git is not installed.")
    try:
        result = _run(root, "init", "-q", "-b", "main")
    except (OSError, subprocess.SubprocessError) as exc:
        return GitResult(False, detail=str(exc))
    if result.returncode != 0:
        return GitResult(False, detail=result.stderr.strip())
    return GitResult(True, detail="Initialised a git repository.")


def commit_all(root: Path, message: str) -> GitResult:
    """Stage everything and commit. A clean tree is success, not failure."""
    root = Path(root)
    if not is_repo(root):
        return GitResult(False, detail="Not a git repository, so nothing was committed.")
    try:
        staged = _run(root, "add", "-A")
        if staged.returncode != 0:
            return GitResult(False, detail=staged.stderr.strip())

        if _run(root, "diff", "--cached", "--quiet").returncode == 0:
            return GitResult(True, detail="No changes to commit.")

        committed = _run(root, *_identity_args(root), "commit", "-m", message)
        if committed.returncode != 0:
            return GitResult(
                False, detail=(committed.stderr or committed.stdout).strip()
            )

        head = _run(root, "rev-parse", "--short", "HEAD")
        sha = head.stdout.strip() if head.returncode == 0 else None
        return GitResult(True, sha=sha, detail=message)
    except (OSError, subprocess.SubprocessError) as exc:
        return GitResult(False, detail=str(exc))


def recent_commits(root: Path, limit: int = 10) -> list[CommitEntry]:
    root = Path(root)
    if not is_repo(root):
        return []
    try:
        result = _run(
            root, "log", f"-{limit}", "--format=%h\x1f%s\x1f%cr", "--no-merges"
        )
    except (OSError, subprocess.SubprocessError):
        return []
    if result.returncode != 0:
        return []
    entries = []
    for line in result.stdout.splitlines():
        parts = line.split("\x1f")
        if len(parts) == 3:
            entries.append(CommitEntry(*parts))
    return entries


def initialize_brain(root: Path, template: Path) -> GitResult:
    """Create the brain from the shipped template and make its first commit."""
    root, template = Path(root), Path(template)
    if root.exists() and any(root.iterdir()):
        return GitResult(False, detail=f"{root} already exists and is not empty.")
    if not template.is_dir():
        return GitResult(False, detail=f"Template not found at {template}.")

    shutil.copytree(template, root, dirs_exist_ok=True)

    init = init_repo(root)
    if not init:
        return GitResult(
            True,
            detail=(
                f"Created the brain at {root}, but could not start its git "
                f"history: {init.detail}"
            ),
        )
    commit = commit_all(root, "Start this brain from the template")
    if not commit:
        return GitResult(
            True,
            detail=(
                f"Created the brain at {root}, but the first commit failed: "
                f"{commit.detail}"
            ),
        )
    return GitResult(True, sha=commit.sha, detail=f"Created the brain at {root}.")
