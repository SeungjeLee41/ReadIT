"""The :class:`Event` — Bluefish's notion of an antigen.

An event is a single, normalized observation from a sensor (a process that
appeared, or a log line that was written). Every event carries a stable
``signature`` used for both self-matching and immune memory, plus a bag of
``features`` used by detectors.

Signatures are intentionally *coarse* so that benign variation (PIDs, request
IDs, timestamps, ephemeral ports) does not make every observation look novel.
For log lines this is achieved by templating: numbers, hex blobs, IPs, and
similar volatile tokens are masked before hashing.
"""

from __future__ import annotations

import hashlib
import re
import time
from dataclasses import dataclass, field
from typing import Any

SOURCE_PROCESS = "process"
SOURCE_LOG = "log"

# Numeric features that are identifiers rather than behavioral measures. They
# are kept on the event (useful context) but never learned as distributions.
_NON_LEARNABLE_NUMERIC = {"pid", "ppid"}

# Volatile tokens are replaced before templating a log line so that lines
# differing only in these values collapse to one signature.
_MASKS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b"), "<IP>"),
    (re.compile(r"\b[0-9a-fA-F]{2}(?::[0-9a-fA-F]{2}){5}\b"), "<MAC>"),
    (re.compile(r"\b[0-9a-fA-F]{8}-(?:[0-9a-fA-F]{4}-){3}[0-9a-fA-F]{12}\b"), "<UUID>"),
    (re.compile(r"\b0x[0-9a-fA-F]+\b"), "<HEX>"),
    (re.compile(r"\b\d+\b"), "<N>"),
]

# Timestamps / syslog priority prefixes commonly lead a log line; drop them.
_SYSLOG_PREFIX = re.compile(
    r"^(?:<\d+>)?"                                  # optional priority
    r"(?:\w{3}\s+\d+\s+\d{2}:\d{2}:\d{2}\s+)?"      # 'Jan  4 12:34:56 '
    r"(?:\d{4}-\d{2}-\d{2}T[\d:.+\-Z]+\s+)?"        # ISO 8601
)


@dataclass
class Event:
    """A single normalized observation."""

    source: str
    raw: str
    features: dict[str, Any] = field(default_factory=dict)
    signature: str = ""
    ts: float = field(default_factory=time.time)

    def numeric_features(self) -> dict[str, float]:
        """Return numeric behavioral features used to learn distributions.

        Volatile identifiers (PIDs) are excluded: they are effectively random
        and would otherwise make every observation look like an outlier.
        """
        out: dict[str, float] = {}
        for key, value in self.features.items():
            if key in _NON_LEARNABLE_NUMERIC:
                continue
            if isinstance(value, bool):
                continue
            if isinstance(value, (int, float)):
                out[key] = float(value)
        return out


def _hash(text: str) -> str:
    return hashlib.sha1(text.encode("utf-8", "replace")).hexdigest()[:16]


def make_process_event(
    *,
    name: str,
    exe: str,
    username: str,
    cmdline: str,
    pid: int,
    ppid: int = 0,
    ts: float | None = None,
) -> Event:
    """Build an Event for an observed process.

    The signature is ``name|exe|username`` — stable across restarts of the
    same program by the same user, but distinct for a different binary path
    or user (a common indicator of masquerading).
    """
    exe = exe or ""
    features: dict[str, Any] = {
        "name": name,
        "exe": exe,
        "username": username,
        "cmdline": cmdline,
        "pid": pid,
        "ppid": ppid,
        "cmdline_len": len(cmdline),
        "runs_as_root": username in ("root", "0"),
        "from_tmp": exe.startswith(("/tmp/", "/dev/shm/", "/var/tmp/")),
        "no_exe_path": exe == "",
    }
    signature = f"proc:{name}|{exe}|{username}"
    return Event(
        source=SOURCE_PROCESS,
        raw=cmdline or name,
        features=features,
        signature=signature,
        ts=ts if ts is not None else time.time(),
    )


def templatize_log(line: str) -> str:
    """Reduce a log line to a stable template (volatile tokens masked)."""
    stripped = _SYSLOG_PREFIX.sub("", line.strip())
    for pattern, replacement in _MASKS:
        stripped = pattern.sub(replacement, stripped)
    return stripped.strip()


def make_log_event(*, line: str, path: str, ts: float | None = None) -> Event:
    """Build an Event for a single log line."""
    template = templatize_log(line)
    lowered = line.lower()
    features: dict[str, Any] = {
        "path": path,
        "template": template,
        "line_len": len(line),
        "auth_failure": any(
            token in lowered
            for token in ("authentication failure", "failed password", "invalid user")
        ),
        "privilege": any(
            token in lowered for token in ("sudo", "su:", "root", "setuid")
        ),
    }
    signature = f"log:{path}:{_hash(template)}"
    return Event(
        source=SOURCE_LOG,
        raw=line.strip(),
        features=features,
        signature=signature,
        ts=ts if ts is not None else time.time(),
    )
