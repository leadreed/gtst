"""Filesystem locking for GTST write operations."""

from __future__ import annotations

import os
from pathlib import Path
from types import TracebackType

from .errors import GtstLockError


class FileLock:
    """Advisory exclusive lock backed by a visible lock file."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self._handle = None
        self._backend = os.name

    def __enter__(self) -> "FileLock":
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._handle = self.path.open("a+", encoding="utf-8")
        try:
            self._lock()
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
            self._unlock()
        finally:
            self._handle.close()
            self._handle = None

    def _lock(self) -> None:
        if self._handle is None:
            return
        if self._backend == "nt":
            import msvcrt

            self._handle.seek(0, os.SEEK_END)
            if self._handle.tell() == 0:
                self._handle.write("\0")
                self._handle.flush()
            self._handle.seek(0)
            msvcrt.locking(self._handle.fileno(), msvcrt.LK_LOCK, 1)
            return

        import fcntl

        fcntl.flock(self._handle.fileno(), fcntl.LOCK_EX)

    def _unlock(self) -> None:
        if self._handle is None:
            return
        if self._backend == "nt":
            import msvcrt

            self._handle.seek(0)
            msvcrt.locking(self._handle.fileno(), msvcrt.LK_UNLCK, 1)
            return

        import fcntl

        fcntl.flock(self._handle.fileno(), fcntl.LOCK_UN)
