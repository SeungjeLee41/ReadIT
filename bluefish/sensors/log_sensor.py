"""Log sensor — tails one or more log files and emits an event per new line.

The sensor tracks each file by ``(inode, offset)`` so it survives rotation:
if a file is truncated or its inode changes, reading restarts from the top of
the new file. Files that do not exist (or are unreadable) are skipped quietly
so a locked-down host does not disable the whole daemon.
"""

from __future__ import annotations

import os

from bluefish.core.events import Event, make_log_event
from bluefish.sensors.base import Sensor

# Cap lines processed per file per poll so a log flood can't stall the loop.
_MAX_LINES_PER_POLL = 500


class _FileCursor:
    __slots__ = ("inode", "offset")

    def __init__(self) -> None:
        self.inode: int | None = None
        self.offset: int = 0


class LogSensor(Sensor):
    name = "log"

    def __init__(self, paths: list[str], poll_interval: float = 2.0):
        self.paths = list(paths)
        self.poll_interval = poll_interval
        self._cursors: dict[str, _FileCursor] = {p: _FileCursor() for p in self.paths}
        self._primed = False

    def poll(self) -> list[Event]:
        events: list[Event] = []
        for path in self.paths:
            events.extend(self._poll_file(path))
        # On the first poll, only establish cursors at end-of-file so we don't
        # replay history; subsequent polls report genuinely new lines.
        if not self._primed:
            self._primed = True
            return []
        return events

    def _poll_file(self, path: str) -> list[Event]:
        cursor = self._cursors[path]
        try:
            stat = os.stat(path)
        except (FileNotFoundError, PermissionError, OSError):
            return []

        # Detect rotation/truncation.
        if cursor.inode is None:
            cursor.inode = stat.st_ino
            # Start reading from the end on first sight of the file.
            cursor.offset = stat.st_size
            return []
        if stat.st_ino != cursor.inode:
            cursor.inode = stat.st_ino
            cursor.offset = 0
        elif stat.st_size < cursor.offset:
            cursor.offset = 0  # truncated

        events: list[Event] = []
        try:
            # Binary mode so byte offsets from os.stat/tell stay exact across
            # multibyte content and rotation.
            with open(path, "rb") as handle:
                handle.seek(cursor.offset)
                count = 0
                while count < _MAX_LINES_PER_POLL:
                    raw = handle.readline()
                    if not raw.endswith(b"\n"):
                        # Partial final line; leave the offset before it so the
                        # rest is read on the next poll.
                        break
                    cursor.offset = handle.tell()
                    count += 1
                    text = raw.decode("utf-8", "replace").rstrip("\n")
                    if text:
                        events.append(make_log_event(line=text, path=path))
        except (PermissionError, OSError):
            return []

        return events
