"""Tests for event construction, feature extraction, and templating."""

from bluefish.core.events import (
    SOURCE_LOG,
    SOURCE_PROCESS,
    make_log_event,
    make_process_event,
    templatize_log,
)


def test_process_event_signature_and_features():
    ev = make_process_event(
        name="nginx",
        exe="/usr/sbin/nginx",
        username="www-data",
        cmdline="nginx: worker process",
        pid=1234,
        ppid=1,
    )
    assert ev.source == SOURCE_PROCESS
    assert ev.signature == "proc:nginx|/usr/sbin/nginx|www-data"
    assert ev.features["runs_as_root"] is False
    assert ev.features["from_tmp"] is False
    # cmdline_len is numeric; pid/ppid too.
    assert "cmdline_len" in ev.numeric_features()


def test_process_from_tmp_and_root_flags():
    ev = make_process_event(
        name="x",
        exe="/tmp/x",
        username="root",
        cmdline="/tmp/x --evil",
        pid=99,
    )
    assert ev.features["from_tmp"] is True
    assert ev.features["runs_as_root"] is True


def test_templatize_masks_volatile_tokens():
    a = templatize_log("Jan  4 12:00:01 host sshd[2931]: Failed password from 10.0.0.5")
    b = templatize_log("Jan  4 12:00:59 host sshd[4102]: Failed password from 192.168.1.9")
    # Different PIDs, timestamps, and IPs collapse to the same template.
    assert a == b
    assert "<IP>" in a and "<N>" in a


def test_log_event_signature_stable_across_volatile_fields():
    e1 = make_log_event(
        line="Jan  4 12:00:01 host sshd[1]: Failed password for root from 10.0.0.1",
        path="/var/log/auth.log",
    )
    e2 = make_log_event(
        line="Jan  4 13:30:22 host sshd[2]: Failed password for root from 10.9.9.9",
        path="/var/log/auth.log",
    )
    assert e1.source == SOURCE_LOG
    assert e1.signature == e2.signature
    assert e1.features["auth_failure"] is True
