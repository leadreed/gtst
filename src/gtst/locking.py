"""Filesystem locking for GTST write operations."""

from __future__ import annotations

from pathlib import Path
import fcntl
from types import TracebackType

from .errors import GtstLockError


class FileLock:
    """Advisory exclusive lock backed by a visible lock file."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self._handle = None

    def __enter__(self) -> "FileLock":
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._handle = self.path.open("a+", encoding="utf-8")
        try:
            fcntl.flock(self._handle.fileno(), fcntl.LOCK_EX)
        except OSError as exc:
            self._handle.close()
            self._handle = None
            raise GtstLockError(f"Could not acquire GTST lock: {self.path}") from exc
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        if self._handle is None:
            return
        try:
            fcntl.flock(self._handle.fileno(), fcntl.LOCK_UN)
        finally:
            self._handle.close()
            self._handle = None
