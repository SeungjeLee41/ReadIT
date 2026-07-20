"""Danger theory — distinguish an event's own harm from systemic inflammation.

Matzinger's danger theory holds that the immune system reacts not merely to
non-self but to signals of actual tissue damage. Bluefish mirrors this, and
keeps two related-but-distinct quantities:

  * **own danger** — the harm signaled by *this* event, used to set the alert's
    severity. For a repeating attack (an auth-failure burst) it scales with the
    burst so the attack's own events intensify; it does *not* inherit danger
    from unrelated activity.
  * **inflammation** — a body-wide, time-decayed sum of danger, used as an
    escalation gate (whether to alert on a borderline event and whether to
    consult the analyst). A quiet host has low inflammation; a host under
    attack runs hot.

Separating the two means a benign ``grep`` that happens to run *during* an
auth-failure flood is scored on its own merits (mild), even though the system
as a whole is inflamed.
"""

from __future__ import annotations

import time
from collections import deque

from bluefish.core.detectors.base import DetectionResult, Detector
from bluefish.core.events import SOURCE_LOG, SOURCE_PROCESS, Event

# Per-signal danger weights. These reflect *harm*, not mere novelty: a
# first-seen process is the adaptive layer's concern, so "novel root" carries
# only a light weight. Hard indicators of actual damage carry real weight.
_W_ROOT_NOVEL = 0.5      # a not-yet-known process running as root
_W_FROM_TMP = 2.0        # execution from a world-writable temp location
_W_NO_EXE = 1.5          # process with no backing executable on disk
_W_AUTH_FAIL = 1.0       # a single authentication failure (scaled by burst)
_W_PRIVILEGE = 0.5       # privilege-related log activity

# Cap how much a single burst can amplify its own danger.
_AUTH_BURST_CAP = 6


class DangerCorrelator(Detector):
    """Stateful correlator; keeps a decaying window of danger contributions."""

    name = "danger"

    def __init__(self, window_seconds: float = 60.0):
        self.window_seconds = window_seconds
        self._window: deque[tuple[float, float]] = deque()  # (ts, base_weight)
        self._auth_events: deque[float] = deque()           # ts of auth failures

    def _now(self) -> float:
        return time.time()

    def _prune(self, now: float) -> None:
        cutoff = now - self.window_seconds
        while self._window and self._window[0][0] < cutoff:
            self._window.popleft()
        while self._auth_events and self._auth_events[0] < cutoff:
            self._auth_events.popleft()

    def inspect(self, event: Event, *, signature_known: bool = True) -> DetectionResult:
        """Score danger for one event and fold it into the window.

        ``signature_known`` lets the caller pass the adaptive layer's verdict so
        that "novel + root" is treated as more dangerous than a familiar daemon.

        Returns a :class:`DetectionResult` whose ``danger`` field is this
        event's *own* danger (burst-aware) — the value used for severity.
        """
        result = DetectionResult()
        now = event.ts or self._now()
        self._prune(now)

        base_weight = 0.0   # contributes to systemic inflammation
        own_weight = 0.0    # this event's own danger (drives severity)
        f = event.features

        if event.source == SOURCE_PROCESS:
            if f.get("from_tmp"):
                base_weight += _W_FROM_TMP
                own_weight += _W_FROM_TMP
                result.reasons.append("danger: execution from temp directory")
            if f.get("runs_as_root") and not signature_known:
                base_weight += _W_ROOT_NOVEL
                own_weight += _W_ROOT_NOVEL
                result.reasons.append("danger: novel process running as root")
            if f.get("no_exe_path") and not str(f.get("name", "")).startswith("["):
                base_weight += _W_NO_EXE
                own_weight += _W_NO_EXE
                result.reasons.append("danger: process without executable on disk")
        elif event.source == SOURCE_LOG:
            if f.get("auth_failure"):
                self._auth_events.append(now)
                burst = min(len(self._auth_events), _AUTH_BURST_CAP)
                base_weight += _W_AUTH_FAIL
                own_weight += _W_AUTH_FAIL * burst
                suffix = f" (x{burst} in window)" if burst > 1 else ""
                result.reasons.append(f"danger: authentication failure{suffix}")
            elif f.get("privilege"):
                base_weight += _W_PRIVILEGE
                own_weight += _W_PRIVILEGE

        if base_weight > 0:
            self._window.append((now, base_weight))

        result.danger = own_weight
        return result

    def inflammation(self, now: float | None = None) -> float:
        """Current systemic danger over the sliding window (the escalation gate)."""
        now = now if now is not None else self._now()
        self._prune(now)
        return sum(weight for _, weight in self._window)
