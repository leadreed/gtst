"""Validation helpers for filesystem-safe GSTS names."""

from __future__ import annotations

import re

from .errors import GstsPathError

NAME_PATTERN = re.compile(r"^[A-Za-z0-9_.-]+$")


def validate_name(value: str, *, label: str) -> None:
    if not isinstance(value, str):
        raise GstsPathError(f"{label} must be a string.")
    if not value:
        raise GstsPathError(f"{label} cannot be empty.")
    if value in {".", ".."}:
        raise GstsPathError(f"{label} cannot be '.' or '..'.")
    if "/" in value or "\\" in value:
        raise GstsPathError(f"{label} cannot contain path separators.")
    if not NAME_PATTERN.match(value):
        raise GstsPathError(
            f"{label} can only contain letters, numbers, underscore, dash, and dot."
        )
