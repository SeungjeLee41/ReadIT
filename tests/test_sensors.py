"""Tests for sensors (log tailing and process self-tolerance)."""

from bluefish.sensors.log_sensor import LogSensor
from bluefish.sensors.process_sensor import ProcessSensor


def test_log_sensor_only_reports_new_lines(tmp_path):
    log = tmp_path / "app.log"
    log.write_text("existing line before Bluefish started\n", encoding="utf-8")
    sensor = LogSensor([str(log)])

    # First poll primes cursors at EOF: no historical replay.
    assert sensor.poll() == []

    # Append two new lines; only these should be reported.
    with open(log, "a", encoding="utf-8") as handle:
        handle.write("Failed password for root from 10.0.0.1\n")
        handle.write("Accepted publickey for alice\n")
    events = sensor.poll()
    assert len(events) == 2
    assert events[0].features["auth_failure"] is True
    assert events[1].features["auth_failure"] is False


def test_log_sensor_handles_missing_file(tmp_path):
    sensor = LogSensor([str(tmp_path / "does-not-exist.log")])
    # Missing files are skipped quietly, never raise.
    assert sensor.poll() == []
    assert sensor.poll() == []


def test_log_sensor_survives_truncation(tmp_path):
    log = tmp_path / "rotating.log"
    log.write_text("line one\n", encoding="utf-8")
    sensor = LogSensor([str(log)])
    sensor.poll()  # prime
    with open(log, "a", encoding="utf-8") as handle:
        handle.write("line two\n")
    assert len(sensor.poll()) == 1
    # Truncate (as logrotate copytruncate would).
    log.write_text("", encoding="utf-8")
    sensor.poll()
    with open(log, "a", encoding="utf-8") as handle:
        handle.write("post-rotation line\n")
    events = sensor.poll()
    assert len(events) == 1
    assert events[0].raw == "post-rotation line"


def test_process_sensor_recognizes_self():
    # Own PID is always self.
    assert ProcessSensor._is_self(1234, 1234, "anything") is True
    # A separate bluefish CLI invocation is self.
    assert ProcessSensor._is_self(5, 1234, "/usr/bin/bluefish status") is True
    # An unrelated process is not self.
    assert ProcessSensor._is_self(5, 1234, "/tmp/x --evil") is False
