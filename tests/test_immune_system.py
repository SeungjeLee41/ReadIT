"""End-to-end tests for the ImmuneSystem pipeline."""

from bluefish.core.detectors.adaptive import AdaptiveDetector
from bluefish.core.detectors.danger import DangerCorrelator
from bluefish.core.detectors.innate import InnateDetector
from bluefish.core.events import make_process_event
from bluefish.core.immune_system import ImmuneSystem
from bluefish.core.memory import Memory
from bluefish.core.self_profile import SelfProfile
from bluefish.llm.analyst import Analyst, Verdict
from bluefish.response.responder import Responder


def _build(store, analyst):
    profile = SelfProfile(store)
    return ImmuneSystem(
        self_profile=profile,
        memory=Memory(store),
        responder=Responder(store),
        analyst=analyst,
        innate=InnateDetector(),
        adaptive=AdaptiveDetector(profile, novelty_threshold=0.5),
        danger=DangerCorrelator(window_seconds=60),
        novelty_threshold=0.5,
        escalation_threshold=3.0,
    )


class _StubAnalyst(Analyst):
    """An analyst that returns a fixed verdict without any network call."""

    def __init__(self, verdict: Verdict):
        self._verdict = verdict

    @property
    def available(self) -> bool:  # type: ignore[override]
        return True

    def analyze(self, alert):  # type: ignore[override]
        return self._verdict


def test_benign_learned_process_no_alert(store):
    analyst = _StubAnalyst(Verdict(verdict="benign", confidence=0.9))
    system = _build(store, analyst)
    ev = make_process_event(
        name="nginx", exe="/usr/sbin/nginx", username="www-data",
        cmdline="nginx: worker", pid=1,
    )
    system.observe_for_learning(ev)
    # Re-observing a learned, non-dangerous process should not alert.
    assert system.inspect(ev) is None


def test_tmp_execution_raises_alert(store):
    analyst = _StubAnalyst(Verdict(verdict="malicious", confidence=0.95,
                                   reasoning="temp exec"))
    system = _build(store, analyst)
    ev = make_process_event(
        name="x", exe="/tmp/x", username="root", cmdline="/tmp/x", pid=2,
    )
    alert = system.inspect(ev)
    assert alert is not None
    assert alert["severity"] in ("high", "critical")
    # It was dangerous enough to consult the analyst and be memorized.
    assert alert["verdict"] == "malicious"
    assert store.recall(ev.signature) is not None


def test_memory_gives_instant_secondary_response(store):
    # First, no memory: a stub analyst that would return benign.
    analyst = _StubAnalyst(Verdict(verdict="benign", confidence=0.1))
    system = _build(store, analyst)
    ev = make_process_event(
        name="y", exe="/tmp/y", username="root", cmdline="/tmp/y", pid=3,
    )
    # Pre-seed memory as if previously confirmed malicious.
    system.memory.remember(
        ev.signature, verdict="malicious", severity="critical", reason="known bad"
    )
    alert = system.inspect(ev)
    assert alert is not None
    assert alert["from_memory"] is True
    assert alert["verdict"] == "malicious"
    assert alert["confidence"] == 1.0


def test_analyst_unavailable_still_alerts(store):
    # A real Analyst with no API key is unavailable but must not crash.
    analyst = Analyst(enabled=True, api_key=None)
    assert analyst.available is False
    system = _build(store, analyst)
    ev = make_process_event(
        name="z", exe="/tmp/z", username="root", cmdline="/tmp/z", pid=4,
    )
    alert = system.inspect(ev)
    assert alert is not None
    # Verdict is unconfirmed because no brain was available.
    assert alert.get("verdict") == "unconfirmed"


def test_verdict_unavailable_reason_for_missing_key():
    analyst = Analyst(enabled=True, api_key=None)
    v = analyst.analyze({"signature": "x", "reasons": []})
    assert v.verdict == "unconfirmed"
    assert v.available is False
