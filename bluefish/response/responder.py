"""The immune response — record alerts and (optionally) act.

By default Bluefish is observe-and-report: it persists alerts and logs them.
Active, potentially destructive measures (e.g. killing a process) are gated
behind BOTH a config flag (``response.allow_active_measures``) and an explicit
per-run ``--confirm``, so the tool never disrupts a host on its own judgment.
"""

from __future__ import annotations

import logging
import signal
from dataclasses import dataclass

from bluefish.store.db import Store

logger = logging.getLogger("bluefish.response")

# Severity ordering for comparisons / display.
SEVERITY_ORDER = {"info": 0, "low": 1, "medium": 2, "high": 3, "critical": 4}


@dataclass
class ResponderConfig:
    allow_active_measures: bool = False
    confirm_active: bool = False


class Responder:
    def __init__(self, store: Store, config: ResponderConfig | None = None):
        self.store = store
        self.config = config or ResponderConfig()

    def handle(self, alert: dict) -> int:
        """Persist an alert and emit a log line. Returns the new alert id."""
        alert_id = self.store.add_alert(alert)
        logger.warning(
            "ALERT #%s [%s] %s :: %s",
            alert_id,
            alert.get("severity", "?"),
            alert.get("signature", "?"),
            "; ".join(alert.get("reasons", [])) or "(no reasons)",
        )
        if alert.get("verdict") and alert.get("verdict") != "unconfirmed":
            logger.warning(
                "  verdict=%s confidence=%.2f",
                alert.get("verdict"),
                alert.get("confidence") or 0.0,
            )
        return alert_id

    def can_act(self) -> bool:
        return self.config.allow_active_measures and self.config.confirm_active

    def quarantine_process(self, pid: int, *, dry_run: bool = True) -> str:
        """Suggest or perform process containment.

        Returns a human-readable description of what was (or would be) done.
        Never terminates a process unless active measures are fully enabled.
        """
        if dry_run or not self.can_act():
            return (
                f"suggested: send SIGSTOP to pid {pid} for isolation "
                "(active measures disabled; not performed)"
            )
        try:
            import os

            os.kill(pid, signal.SIGSTOP)
            return f"performed: sent SIGSTOP to pid {pid} (process frozen for review)"
        except ProcessLookupError:
            return f"pid {pid} no longer exists"
        except PermissionError:
            return f"insufficient privileges to signal pid {pid}"
