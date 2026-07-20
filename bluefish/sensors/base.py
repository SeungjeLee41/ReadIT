"""Sensor interface.

A sensor turns some slice of host activity into a list of :class:`Event`
objects each time it is polled. Sensors are stateful (they remember what they
have already reported) and must never raise out of :meth:`poll` — a flaky log
file or a race with a dying process should degrade to "no events", not crash
the daemon.
"""

from __future__ import annotations

from bluefish.core.events import Event


class Sensor:
    name = "sensor"

    #: default seconds between polls (overridden from config)
    poll_interval: float = 3.0

    def poll(self) -> list[Event]:  # pragma: no cover - interface
        raise NotImplementedError
