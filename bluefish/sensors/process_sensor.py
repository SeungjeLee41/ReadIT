"""Process sensor — emits an event for each newly-appeared process.

Each poll snapshots the process table and diffs it against the previous poll,
reporting only PIDs that are new. This keeps the event stream proportional to
activity (process *starts*) rather than to the number of running processes.
"""

from __future__ import annotations

import os

from bluefish.core.events import Event, make_process_event
from bluefish.sensors.base import Sensor

try:
    import psutil
except ImportError:  # pragma: no cover - psutil is a declared dependency
    psutil = None  # type: ignore[assignment]

# Self-tolerance: the immune system must not attack itself. Bluefish's own
# daemon and CLI invocations are recognized as self and never reported.
_SELF_MARKER = "bluefish"


class ProcessSensor(Sensor):
    name = "process"

    def __init__(self, poll_interval: float = 3.0):
        self.poll_interval = poll_interval
        self._seen: set[int] = set()
        self._primed = False
        self._own_pid = os.getpid()

    @staticmethod
    def _is_self(pid: int, own_pid: int, cmdline: str) -> bool:
        """Recognize Bluefish's own processes (self-tolerance)."""
        if pid == own_pid:
            return True
        # A separate `bluefish ...` CLI invocation is still self.
        return _SELF_MARKER in cmdline.lower()

    def poll(self) -> list[Event]:
        if psutil is None:
            return []

        events: list[Event] = []
        current: set[int] = set()

        for proc in psutil.process_iter(
            ["pid", "ppid", "name", "exe", "username", "cmdline"]
        ):
            try:
                info = proc.info
                pid = info["pid"]
                current.add(pid)
                if pid in self._seen:
                    continue
                if not self._primed:
                    # First poll only establishes the baseline set.
                    continue
                cmdline = " ".join(info.get("cmdline") or []) or (info.get("name") or "")
                if self._is_self(pid, self._own_pid, cmdline):
                    continue
                events.append(
                    make_process_event(
                        name=info.get("name") or "",
                        exe=info.get("exe") or "",
                        username=info.get("username") or "",
                        cmdline=cmdline,
                        pid=pid,
                        ppid=info.get("ppid") or 0,
                    )
                )
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                # Process vanished or is unreadable mid-scan; ignore it.
                continue
            except Exception:
                continue

        self._seen = current
        self._primed = True
        return events
