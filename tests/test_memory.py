"""Tests for immune memory (secondary-response bookkeeping)."""

from bluefish.core.events import make_process_event
from bluefish.core.memory import Memory


def _proc():
    return make_process_event(
        name="x", exe="/tmp/x", username="root", cmdline="/tmp/x", pid=1
    )


def test_recall_miss_returns_none(store):
    mem = Memory(store)
    assert mem.recall(_proc()) is None


def test_remember_then_recall(store):
    mem = Memory(store)
    ev = _proc()
    mem.remember(ev.signature, verdict="malicious", severity="critical", reason="test")
    hit = mem.recall(ev)
    assert hit is not None
    assert hit["verdict"] == "malicious"
    assert hit["severity"] == "critical"


def test_recall_increments_hits(store):
    mem = Memory(store)
    ev = _proc()
    mem.remember(ev.signature, verdict="malicious", severity="high", reason="r")
    mem.recall(ev)
    mem.recall(ev)
    entry = next(e for e in mem.entries() if e["signature"] == ev.signature)
    assert entry["hits"] == 2
