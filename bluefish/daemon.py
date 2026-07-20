"""The Bluefish daemon — the running "body" that senses and defends.

The daemon wires configured sensors to the immune system and runs a poll loop.
It is deliberately single-threaded and cooperative: each sensor is polled on
its own interval, events are inspected in order, and the loop sleeps briefly
between passes. This keeps ordering deterministic (important for the danger
correlator's time window) and the resource footprint low.

Two entry points are provided:
  * :func:`build_system` — assemble an :class:`ImmuneSystem` from a Config
    (also used by ``learn`` and by tests).
  * :func:`run_daemon` — the monitoring loop, with signal handling and a pid
    file so ``bluefish stop`` can find it.
"""

from __future__ import annotations

import logging
import os
import signal
import time

from bluefish.config import Config
from bluefish.core.detectors.adaptive import AdaptiveDetector
from bluefish.core.detectors.danger import DangerCorrelator
from bluefish.core.detectors.innate import InnateDetector
from bluefish.core.immune_system import ImmuneSystem
from bluefish.core.memory import Memory
from bluefish.core.self_profile import SelfProfile
from bluefish.llm.analyst import Analyst
from bluefish.response.responder import Responder, ResponderConfig
from bluefish.sensors.log_sensor import LogSensor
from bluefish.sensors.process_sensor import ProcessSensor
from bluefish.store.db import Store

logger = logging.getLogger("bluefish.daemon")


def build_system(
    config: Config, store: Store, *, confirm_active: bool = False
) -> ImmuneSystem:
    """Assemble a fully-wired immune system from configuration."""
    self_profile = SelfProfile(
        store, numeric_k=config.get("self_profile", "numeric_k", default=3.0)
    )
    memory = Memory(store)
    responder = Responder(
        store,
        ResponderConfig(
            allow_active_measures=config.get(
                "response", "allow_active_measures", default=False
            ),
            confirm_active=confirm_active,
        ),
    )
    analyst = Analyst(
        enabled=config.get("llm", "enabled", default=True),
        model=config.get("llm", "model", default="claude-sonnet-5"),
        max_tokens=config.get("llm", "max_tokens", default=1024),
    )
    novelty_threshold = config.get(
        "detectors", "adaptive", "novelty_threshold", default=0.5
    )
    danger_window = config.get("detectors", "danger", "window_seconds", default=60)
    escalation = config.get(
        "detectors", "danger", "escalation_threshold", default=3.0
    )
    innate = InnateDetector(
        extra_rules=config.get("detectors", "innate", "extra_rules", default=[])
    )
    return ImmuneSystem(
        self_profile=self_profile,
        memory=memory,
        responder=responder,
        analyst=analyst,
        innate=innate,
        adaptive=AdaptiveDetector(self_profile, novelty_threshold=novelty_threshold),
        danger=DangerCorrelator(window_seconds=danger_window),
        novelty_threshold=novelty_threshold,
        escalation_threshold=escalation,
    )


def build_sensors(config: Config) -> list:
    """Construct enabled sensors from configuration."""
    sensors: list = []
    if config.get("sensors", "process", "enabled", default=True):
        sensors.append(
            ProcessSensor(
                poll_interval=config.get(
                    "sensors", "process", "poll_interval", default=3.0
                )
            )
        )
    if config.get("sensors", "log", "enabled", default=True):
        paths = config.get("sensors", "log", "paths", default=[])
        sensors.append(
            LogSensor(
                paths=paths,
                poll_interval=config.get(
                    "sensors", "log", "poll_interval", default=2.0
                ),
            )
        )
    return sensors


class _Stopper:
    """Small flag object flipped by SIGTERM/SIGINT to end the loop cleanly."""

    def __init__(self) -> None:
        self.stop = False

    def request(self, *_a: object) -> None:
        self.stop = True


def run_daemon(config: Config) -> None:
    """Run the monitoring loop until signaled to stop."""
    store = Store(config.db_path)
    confirm_active = bool(config.get("response", "_confirm_active", default=False))
    system = build_system(config, store, confirm_active=confirm_active)
    sensors = build_sensors(config)

    stopper = _Stopper()
    signal.signal(signal.SIGTERM, stopper.request)
    signal.signal(signal.SIGINT, stopper.request)

    _write_pid(config)
    store.set_meta("daemon_started", time.time())
    logger.info(
        "Bluefish daemon started (pid=%s, sensors=%s, analyst=%s)",
        os.getpid(),
        [s.name for s in sensors],
        "available" if system.analyst.available else "unavailable",
    )

    # Track each sensor's next-due time for independent polling intervals.
    next_due = {id(s): 0.0 for s in sensors}
    events_seen = 0
    try:
        while not stopper.stop:
            now = time.monotonic()
            for sensor in sensors:
                if now < next_due[id(sensor)]:
                    continue
                next_due[id(sensor)] = now + sensor.poll_interval
                try:
                    events = sensor.poll()
                except Exception:  # pragma: no cover - defensive
                    logger.exception("sensor %s failed", sensor.name)
                    events = []
                for event in events:
                    store.add_event(
                        event.ts,
                        event.source,
                        event.signature,
                        event.raw,
                        event.features,
                    )
                    events_seen += 1
                    try:
                        system.inspect(event)
                    except Exception:  # pragma: no cover - defensive
                        logger.exception("inspection failed for %s", event.signature)
            if events_seen and events_seen % 5000 == 0:
                store.prune_events()
            store.set_meta("last_heartbeat", time.time())
            store.set_meta("events_seen", events_seen)
            time.sleep(0.5)
    finally:
        store.set_meta("daemon_stopped", time.time())
        _remove_pid(config)
        store.close()
        logger.info("Bluefish daemon stopped (events_seen=%s)", events_seen)


def _write_pid(config: Config) -> None:
    config.ensure_data_dir()
    config.pid_path.write_text(str(os.getpid()), encoding="utf-8")


def _remove_pid(config: Config) -> None:
    try:
        config.pid_path.unlink()
    except FileNotFoundError:
        pass


def read_pid(config: Config) -> int | None:
    try:
        return int(config.pid_path.read_text(encoding="utf-8").strip())
    except (FileNotFoundError, ValueError):
        return None
