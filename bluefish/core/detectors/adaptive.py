"""Adaptive immunity — negative-selection self/non-self discrimination.

Classic negative selection generates detectors and discards any that match
"self", so the surviving repertoire recognizes only non-self. Bluefish applies
the same principle at the signature level: an event whose signature was learned
as self is tolerated; an unlearned signature is non-self and scored by how far
its numeric features also depart from the learned norms.

This layer only matters once a self-profile exists. Before training, every
event looks novel, so the detector reports a low, clearly-labeled score and
lets the innate layer carry detection.
"""

from __future__ import annotations

from bluefish.core.detectors.base import DetectionResult, Detector
from bluefish.core.events import Event
from bluefish.core.self_profile import SelfProfile


class AdaptiveDetector(Detector):
    name = "adaptive"

    def __init__(self, self_profile: SelfProfile, novelty_threshold: float = 0.5):
        self.self_profile = self_profile
        self.novelty_threshold = novelty_threshold

    def inspect(self, event: Event) -> DetectionResult:
        result = DetectionResult()

        if not self.self_profile.is_trained():
            # No immunity has formed yet; do not cry wolf at everything.
            return result

        signature_known = self.self_profile.signature_is_self(event)
        deviation = self.self_profile.numeric_deviation(event)

        if signature_known:
            # Known signature but out-of-band numeric behavior is mild novelty.
            novelty = 0.4 * deviation
        else:
            # Unseen signature: this is the core non-self signal. Numeric
            # deviation nudges it up but is kept below the range that would,
            # by itself, imply an incident (severity comes from danger/innate).
            novelty = min(0.9, 0.6 + 0.3 * deviation)
            result.reasons.append(
                f"non-self: unlearned {event.source} signature"
            )

        if deviation > 0:
            result.reasons.append(
                f"numeric features deviate from self (dev={deviation:.2f})"
            )

        result.score = novelty
        return result

    def is_non_self(self, event: Event) -> bool:
        return self.inspect(event).score >= self.novelty_threshold
