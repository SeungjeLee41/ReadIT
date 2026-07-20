"""The immune system — the orchestrator that ties every layer together.

For each event Bluefish runs a pipeline modeled on immune response:

  1. memory   — if the signature is a known threat, mount an instant secondary
                response (skip the slow analyst path).
  2. innate   — cheap rule-based recognition of known-bad structure.
  3. adaptive — negative-selection self/non-self novelty scoring.
  4. danger   — accumulate harm signals into the current inflammation.
  5. escalate — if novelty + inflammation cross the threshold, raise an alert;
                for sufficiently dangerous alerts, consult the LLM analyst.

The learning path (``observe_for_learning``) folds events into the self-model
instead of judging them.
"""

from __future__ import annotations

import logging

from bluefish.core.detectors.adaptive import AdaptiveDetector
from bluefish.core.detectors.base import DetectionResult
from bluefish.core.detectors.danger import DangerCorrelator
from bluefish.core.detectors.innate import InnateDetector
from bluefish.core.events import Event
from bluefish.core.memory import Memory
from bluefish.core.self_profile import SelfProfile
from bluefish.llm.analyst import Analyst
from bluefish.response.responder import Responder

logger = logging.getLogger("bluefish.immune")


def _severity_from_scores(novelty: float, own_danger: float, innate: float) -> str:
    """Map an event's own scores to a coarse severity label.

    Severity reflects *this event's* evidence — its innate red flags, its
    novelty, and its own danger contribution — never the systemic inflammation,
    so a benign event during an unrelated incident is not mislabeled. Novelty
    and criticality are kept distinct: a first-seen ("non-self") event is worth
    surfacing but is not, on its own, an incident, so pure novelty caps at
    "medium". High/critical is reserved for structural red flags and real harm.
    """
    if innate >= 0.85 or own_danger >= 4.0:
        return "critical"
    if innate >= 0.6 or own_danger >= 2.0:
        return "high"
    if novelty >= 0.5 or own_danger >= 1.0:
        return "medium"
    return "low"


class ImmuneSystem:
    """Owns the detector stack and the inspection pipeline."""

    def __init__(
        self,
        *,
        self_profile: SelfProfile,
        memory: Memory,
        responder: Responder,
        analyst: Analyst,
        innate: InnateDetector | None = None,
        adaptive: AdaptiveDetector | None = None,
        danger: DangerCorrelator | None = None,
        novelty_threshold: float = 0.5,
        escalation_threshold: float = 3.0,
    ):
        self.self_profile = self_profile
        self.memory = memory
        self.responder = responder
        self.analyst = analyst
        self.innate = innate or InnateDetector()
        self.adaptive = adaptive or AdaptiveDetector(
            self_profile, novelty_threshold=novelty_threshold
        )
        self.danger = danger or DangerCorrelator()
        self.novelty_threshold = novelty_threshold
        self.escalation_threshold = escalation_threshold

    # --- learning path --------------------------------------------------
    def observe_for_learning(self, event: Event) -> None:
        self.self_profile.learn(event)

    # --- detection path -------------------------------------------------
    def inspect(self, event: Event) -> dict | None:
        """Run the full pipeline for one event. Returns an alert dict if raised."""
        # 1. Immune memory: instant secondary response to a known threat.
        remembered = self.memory.recall(event)
        if remembered is not None:
            return self._raise_from_memory(event, remembered)

        # 2-3. Innate + adaptive.
        innate_result = self.innate.inspect(event)
        adaptive_result = self.adaptive.inspect(event)
        signature_known = self.self_profile.signature_is_self(event)

        # 4. Danger correlation (stateful; updates inflammation window).
        danger_result = self.danger.inspect(event, signature_known=signature_known)
        inflammation = self.danger.inflammation(now=event.ts)

        combined = DetectionResult().merge(innate_result).merge(adaptive_result)
        combined = combined.merge(danger_result)
        novelty = adaptive_result.score

        # 5. Escalation decision.
        if not self._should_alert(novelty, innate_result.score, inflammation):
            return None

        severity = _severity_from_scores(
            novelty, danger_result.danger, innate_result.score
        )
        alert = {
            "ts": event.ts,
            "signature": event.signature,
            "source": event.source,
            "severity": severity,
            "novelty": novelty,
            "inflammation": inflammation,
            "reasons": combined.reasons,
            "raw": event.raw,
            "features": event.features,
            "baseline": self._baseline_summary(),
        }

        # Consult the analyst only for genuinely dangerous alerts.
        if self._should_escalate_to_analyst(severity, inflammation):
            verdict = self.analyst.analyze(alert)
            alert["verdict"] = verdict.verdict
            alert["confidence"] = verdict.confidence
            alert["analysis"] = verdict.reasoning
            alert["actions"] = verdict.recommended_actions
            # Confirmed malicious -> form an immune memory.
            if verdict.verdict == "malicious":
                self.memory.remember(
                    event.signature,
                    verdict="malicious",
                    severity=severity,
                    reason=verdict.reasoning or "; ".join(combined.reasons),
                )

        self.responder.handle(alert)
        return alert

    # --- helpers --------------------------------------------------------
    def _should_alert(self, novelty: float, innate: float, inflammation: float) -> bool:
        if innate >= 0.6:
            return True
        if novelty >= self.novelty_threshold and inflammation > 0:
            return True
        if inflammation >= self.escalation_threshold:
            return True
        return False

    def _should_escalate_to_analyst(self, severity: str, inflammation: float) -> bool:
        return severity in ("high", "critical") or inflammation >= self.escalation_threshold

    def _raise_from_memory(self, event: Event, remembered: dict) -> dict:
        alert = {
            "ts": event.ts,
            "signature": event.signature,
            "source": event.source,
            "severity": remembered.get("severity", "high"),
            "novelty": 1.0,
            "inflammation": self.danger.inflammation(now=event.ts),
            "reasons": [
                "immune memory: signature matches a previously confirmed threat",
                remembered.get("reason", ""),
            ],
            "raw": event.raw,
            "features": event.features,
            "baseline": self._baseline_summary(),
            "verdict": remembered.get("verdict", "malicious"),
            "confidence": 1.0,
            "analysis": "Secondary immune response: matched a memorized threat "
            "signature; responded without re-analysis.",
            "actions": ["isolate and investigate the recurring threat"],
            "from_memory": True,
        }
        self.responder.handle(alert)
        return alert

    def _baseline_summary(self) -> dict:
        return {
            "self_signatures": self.self_profile.signature_count(),
            "trained": self.self_profile.is_trained(),
        }
