"""Entry point: `python -m brain_mcp`.

Claude Desktop launches this as a subprocess and speaks MCP over stdio, so
**stdout is the protocol channel**. Anything printed there that is not a
protocol message corrupts the session — diagnostics go to stderr, which
Claude Desktop captures into its logs.
"""

import os
import sys
from pathlib import Path

from .server import build_server

DEFAULT_BRAIN = Path(__file__).resolve().parent.parent / "brain"


def resolve_brain_path(argv: list[str] | None = None) -> Path:
    """Where the brain lives: `--brain PATH`, then BRAIN_PATH, then ./brain."""
    argv = list(argv if argv is not None else sys.argv[1:])
    if "--brain" in argv:
        index = argv.index("--brain")
        if index + 1 < len(argv):
            return Path(argv[index + 1]).expanduser().resolve()
    env = os.environ.get("BRAIN_PATH")
    if env:
        return Path(env).expanduser().resolve()
    return DEFAULT_BRAIN


def main(argv: list[str] | None = None) -> int:
    brain_path = resolve_brain_path(argv)

    # A missing brain is not fatal: the server still starts and every tool
    # explains where it looked. Exiting instead would show up in Claude
    # Desktop as a server that failed to launch, which is a much harder
    # thing to debug than a tool that tells you the path was wrong.
    if not brain_path.is_dir():
        print(
            f"[ai-brain-cells] warning: no brain directory at {brain_path}. "
            f"Set BRAIN_PATH or pass --brain.",
            file=sys.stderr,
        )
    else:
        print(f"[ai-brain-cells] serving brain at {brain_path}", file=sys.stderr)

    build_server(brain_path).run("stdio")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
