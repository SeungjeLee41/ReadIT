"""Innate immunity — fast, rule-based recognition of known-bad patterns.

Innate detectors do not depend on the learned self-model. Like pattern-
recognition receptors that respond to conserved pathogen features, they fire
immediately on structurally suspicious activity regardless of whether the host
has "seen" it before. Rules are cheap and run on every event.

Built-in rules can be extended from config via ``detectors.innate.extra_rules``
(a list of ``{name, pattern, score, applies_to}`` entries matched against the
event's raw text).
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from bluefish.core.detectors.base import DetectionResult, Detector
from bluefish.core.events import SOURCE_LOG, SOURCE_PROCESS, Event

# Command-line patterns that are almost never benign.
_PIPE_TO_SHELL = re.compile(
    r"(?:curl|wget|fetch)\b.*\|\s*(?:ba)?sh\b", re.IGNORECASE
)
_REVERSE_SHELL = re.compile(
    r"(?:bash\s+-i|nc\s+.*-e|/dev/tcp/|python.*socket.*subprocess|"
    r"sh\s+-i\s+.*>&|mkfifo\b.*\|.*sh)",
    re.IGNORECASE,
)
_ENCODED_EXEC = re.compile(
    r"(?:base64\s+-d|--decode).*\|\s*(?:ba)?sh|"
    r"(?:python|perl|ruby)\b.*-e\b.*(?:exec|eval|decode)",
    re.IGNORECASE,
)
_CRED_ACCESS = re.compile(
    r"(?:/etc/shadow|/etc/gshadow|\.ssh/id_(?:rsa|ed25519)|\.aws/credentials)",
    re.IGNORECASE,
)


@dataclass
class _Rule:
    name: str
    pattern: re.Pattern[str]
    score: float
    applies_to: str  # "process", "log", or "any"

    def matches(self, event: Event) -> bool:
        if self.applies_to != "any" and self.applies_to != event.source:
            return False
        return self.pattern.search(event.raw) is not None


class InnateDetector(Detector):
    name = "innate"

    def __init__(self, extra_rules: list[dict] | None = None):
        self.extra_rules: list[_Rule] = []
        for spec in extra_rules or []:
            try:
                self.extra_rules.append(
                    _Rule(
                        name=str(spec["name"]),
                        pattern=re.compile(str(spec["pattern"]), re.IGNORECASE),
                        score=float(spec.get("score", 0.7)),
                        applies_to=str(spec.get("applies_to", "any")),
                    )
                )
            except (KeyError, re.error):
                # A malformed custom rule must never crash the pipeline.
                continue

    def inspect(self, event: Event) -> DetectionResult:
        result = DetectionResult()

        if event.source == SOURCE_PROCESS:
            self._inspect_process(event, result)
        elif event.source == SOURCE_LOG:
            self._inspect_log(event, result)

        # Text-pattern rules apply to both sources via event.raw.
        if _PIPE_TO_SHELL.search(event.raw):
            _bump(result, 0.9, "piped remote content directly into a shell")
        if _REVERSE_SHELL.search(event.raw):
            _bump(result, 0.95, "reverse-shell indicator in command")
        if _ENCODED_EXEC.search(event.raw):
            _bump(result, 0.85, "decode-and-execute pattern")
        if _CRED_ACCESS.search(event.raw):
            _bump(result, 0.8, "access to sensitive credential file")

        for rule in self.extra_rules:
            if rule.matches(event):
                _bump(result, rule.score, f"custom rule: {rule.name}")

        return result

    @staticmethod
    def _inspect_process(event: Event, result: DetectionResult) -> None:
        f = event.features
        if f.get("from_tmp"):
            _bump(result, 0.8, f"executable runs from a temp dir: {f.get('exe')}")
        if f.get("no_exe_path") and not f.get("name", "").startswith("["):
            _bump(result, 0.6, "process has no on-disk executable path")

    @staticmethod
    def _inspect_log(event: Event, result: DetectionResult) -> None:
        # Per-line innate signal is weak on its own; auth failures gain weight
        # through the danger correlator's burst detection.
        if event.features.get("auth_failure"):
            _bump(result, 0.3, "authentication failure log line")


def _bump(result: DetectionResult, score: float, reason: str) -> None:
    result.score = max(result.score, score)
    result.reasons.append(reason)
