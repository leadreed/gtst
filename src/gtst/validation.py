"""Validation helpers for filesystem-safe GTST names."""

from __future__ import annotations

import re

from .errors import GtstPathError

NAME_PATTERN = re.compile(r"^[A-Za-z0-9_.-]+$")


def validate_name(value: str, *, label: str) -> None:
    if not isinstance(value, str):
        raise GtstPathError(f"{label} must be a string.")
    if not value:
        raise GtstPathError(f"{label} cannot be empty.")
    if value in {".", ".."}:
        raise GtstPathError(f"{label} cannot be '.' or '..'.")
    if "/" in value or "\\" in value:
        raise GtstPathError(f"{label} cannot contain path separators.")
    if not NAME_PATTERN.match(value):
        raise GtstPathError(
            f"{label} can only contain letters, numbers, underscore, dash, and dot."
        )
