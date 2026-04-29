"""Pytest helper for running Windows temp-dir tests inside Codex sandbox."""

from __future__ import annotations

import os
from pathlib import Path
import tempfile


_original_os_mkdir = os.mkdir
_original_mkdir = Path.mkdir
_original_temporary_directory = tempfile.TemporaryDirectory


class _SandboxTemporaryDirectory(_original_temporary_directory):
    def __init__(
        self,
        suffix: str | None = None,
        prefix: str | None = None,
        dir: str | None = None,
        ignore_cleanup_errors: bool = True,
        *,
        delete: bool = True,
    ) -> None:
        super().__init__(
            suffix=suffix,
            prefix=prefix,
            dir=dir,
            ignore_cleanup_errors=ignore_cleanup_errors,
            delete=delete,
        )


def _sandbox_friendly_os_mkdir(
    path: str | bytes,
    mode: int = 0o777,
    *,
    dir_fd: int | None = None,
) -> None:
    if os.name == "nt" and mode == 0o700:
        mode = 0o777
    if dir_fd is None:
        return _original_os_mkdir(path, mode)
    return _original_os_mkdir(path, mode, dir_fd=dir_fd)


def _sandbox_friendly_mkdir(
    self: Path,
    mode: int = 0o777,
    parents: bool = False,
    exist_ok: bool = False,
) -> None:
    if os.name == "nt" and mode == 0o700:
        mode = 0o777
    return _original_mkdir(self, mode=mode, parents=parents, exist_ok=exist_ok)


def pytest_configure() -> None:
    sandbox_temp = os.environ.get("TMP") or os.environ.get("TEMP")
    if os.name == "nt" and sandbox_temp:
        tempfile.tempdir = sandbox_temp
        tempfile.TemporaryDirectory = _SandboxTemporaryDirectory
    os.mkdir = _sandbox_friendly_os_mkdir  # type: ignore[assignment]
    Path.mkdir = _sandbox_friendly_mkdir  # type: ignore[method-assign]
