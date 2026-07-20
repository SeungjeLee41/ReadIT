"""Common detector interfaces."""

from __future__ import annotations

from dataclasses import dataclass, field

from bluefish.core.events import Event


@dataclass
class DetectionResult:
    """The outcome of running a detector against one event.

    Attributes
    ----------
    score:
        A 0..1 measure of how concerning the event is to this detector.
    reasons:
        Human-readable strings explaining what fired (shown in alerts and
        handed to the LLM analyst as evidence).
    danger:
        Danger-signal weight contributed by this event (danger detector only;
        others leave it at 0).
    """

    score: float = 0.0
    reasons: list[str] = field(default_factory=list)
    danger: float = 0.0

    def merge(self, other: "DetectionResult") -> "DetectionResult":
        return DetectionResult(
            score=max(self.score, other.score),
            reasons=[*self.reasons, *other.reasons],
            danger=self.danger + other.danger,
        )


class Detector:
    """Base class for detectors. Subclasses implement :meth:`inspect`."""

    name = "detector"

    def inspect(self, event: Event) -> DetectionResult:  # pragma: no cover
        raise NotImplementedError
