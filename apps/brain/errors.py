"""Errors raised while reading or validating brain files.

The split matters: `BrainFileError` means a file could not be read at all,
`BrainValidationError` means it was read but does not satisfy the contract.
The scanner catches both and reports them rather than crashing, because a
hand-edited file with a typo should show up as one item needing attention,
not take the whole dashboard down.
"""

from pathlib import Path


class BrainError(Exception):
    """Base class for everything this package raises."""


class BrainFileError(BrainError):
    def __init__(self, message: str, path: Path | None = None):
        super().__init__(message)
        self.message = message
        self.path = path


class BrainValidationError(BrainError):
    def __init__(self, message: str, field: str | None = None):
        super().__init__(message)
        self.message = message
        self.field = field
