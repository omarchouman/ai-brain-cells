"""The Claude Desktop connection: config JSON and where it goes.

Generated rather than documented, because every value in it is a machine
path. A copy-paste block with the real interpreter, the real project
directory and the real brain already filled in is the difference between
this working first try and an afternoon of debugging someone else's example.

The launcher deliberately avoids `cwd`: not every MCP client honours it, and
`PYTHONPATH` makes the package importable from wherever the client happens
to start the process. Verified by launching the server from `/`.
"""

import json
import sys
from dataclasses import dataclass
from pathlib import Path

from django.conf import settings

SERVER_KEY = "ai-brain-cells"

CONFIG_PATHS = {
    "macOS": "~/Library/Application Support/Claude/claude_desktop_config.json",
    "Windows": "%APPDATA%\\Claude\\claude_desktop_config.json",
}


@dataclass
class DesktopConnection:
    python: str
    project_dir: str
    brain_path: str
    brain_exists: bool

    @property
    def entry(self) -> dict:
        return {
            "command": self.python,
            "args": ["-m", "brain_mcp", "--brain", self.brain_path],
            "env": {"PYTHONPATH": self.project_dir},
        }

    @property
    def config_json(self) -> str:
        return json.dumps({"mcpServers": {SERVER_KEY: self.entry}}, indent=2)

    @property
    def command_line(self) -> str:
        """The same launch, runnable in a terminal — the fastest way to see
        an import error that Claude Desktop would only show in its logs."""
        return (
            f"PYTHONPATH={self.project_dir} {self.python} "
            f"-m brain_mcp --brain {self.brain_path}"
        )


def describe(brain_path: Path) -> DesktopConnection:
    return DesktopConnection(
        python=sys.executable,
        project_dir=str(Path(settings.BASE_DIR).resolve()),
        brain_path=str(Path(brain_path).resolve()),
        brain_exists=Path(brain_path).is_dir(),
    )
