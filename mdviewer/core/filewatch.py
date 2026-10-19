"""File watching state machine for MD Viewer (pure logic, injectable stat)."""

from enum import Enum


class WatchEvent(str, Enum):
    UNCHANGED = "unchanged"
    CHANGED = "changed"
    MISSING = "missing"


class Watcher:
    """Poll a file's (mtime_ns, size) and report transitions.

    stat_fn(path) must return an object exposing st_mtime_ns and st_size
    (e.g. os.stat) or raise FileNotFoundError when the path is gone.
    Other OSError is treated as a transient stat failure and ignored.
    """

    def __init__(self, path, stat_fn):
        self.path = path
        self.stat_fn = stat_fn
        self._last = None
        self._expected = None
        self._was_missing = False

    def poll(self) -> WatchEvent:
        state = self._stat()
        if state is None:
            if self._was_missing or self._last is None:
                return WatchEvent.UNCHANGED
            self._was_missing = True
            return WatchEvent.MISSING
        if self._was_missing:
            self._was_missing = False
            self._last = state
            return WatchEvent.CHANGED
        if self._expected is not None:
            self._expected = None
            if state == self._last:
                return WatchEvent.UNCHANGED
        if self._last is None:
            self._last = state
            return WatchEvent.UNCHANGED
        if state != self._last:
            self._last = state
            return WatchEvent.CHANGED
        return WatchEvent.UNCHANGED

    def note_write(self, mtime_ns: int, size: int) -> None:
        """Register the disk state produced by our own save (echo suppression)."""
        state = (mtime_ns, size)
        self._expected = state
        self._last = state

    def _stat(self):
        try:
            st = self.stat_fn(self.path)
        except FileNotFoundError:
            return None
        except OSError:
            return self._last
        return (st.st_mtime_ns, st.st_size)
