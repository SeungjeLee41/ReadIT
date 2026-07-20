"""Bluefish command-line interface.

Commands
--------
learn    build/extend the "self" model by observing normal activity
start    run the monitoring daemon (foreground or background)
stop     stop a running daemon
status   show daemon state, inflammation, and recent counts
alerts   list recent alerts
explain  show the full analysis for one alert
memory   list immune-memory (confirmed-threat) signatures
"""

from __future__ import annotations

import logging
import os
import signal
import sys
import time
from datetime import datetime, timezone
from typing import Optional

import typer
from rich.console import Console
from rich.table import Table

from bluefish.config import Config, load_config
from bluefish.daemon import build_sensors, build_system, read_pid, run_daemon
from bluefish.store.db import Store

app = typer.Typer(
    add_completion=False,
    help="Bluefish — a host-security AI modeled on the human immune system.",
)
console = Console()

# Populated by the top-level callback so subcommands can reach the config.
_STATE: dict[str, object] = {}


def _config() -> Config:
    return _STATE["config"]  # type: ignore[return-value]


def _setup_logging(config: Config, to_file: bool = False) -> None:
    handlers: list[logging.Handler] = []
    if to_file:
        config.ensure_data_dir()
        handlers.append(logging.FileHandler(config.log_path))
    else:
        handlers.append(logging.StreamHandler(sys.stderr))
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        handlers=handlers,
        force=True,
    )


def _fmt_ts(ts: float | None) -> str:
    if not ts:
        return "-"
    return datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%SZ")


@app.callback()
def main(
    config_path: Optional[str] = typer.Option(
        None, "--config", "-c", help="Path to a YAML config file."
    ),
) -> None:
    """Load configuration for all subcommands."""
    _STATE["config"] = load_config(config_path)


@app.command()
def learn(
    minutes: Optional[float] = typer.Option(
        None, "--minutes", "-m", help="How long to observe (default from config)."
    ),
    update: bool = typer.Option(
        False, "--update", help="Extend an existing profile instead of noting reset."
    ),
) -> None:
    """Learn the 'self' profile by watching normal activity (immunization)."""
    config = _config()
    _setup_logging(config)
    duration = (
        minutes
        if minutes is not None
        else config.get("self_profile", "default_learn_minutes", default=5)
    )
    store = Store(config.db_path)
    system = build_system(config, store)
    sensors = build_sensors(config)

    existing = system.self_profile.signature_count()
    if existing and not update:
        console.print(
            f"[yellow]Note:[/yellow] extending existing profile "
            f"({existing} signatures). Use --update to silence this notice."
        )

    deadline = time.time() + duration * 60.0
    console.print(
        f"[bold cyan]Immunizing[/bold cyan] for {duration:g} min "
        f"(sensors: {', '.join(s.name for s in sensors)}). "
        "Exercise the host normally so Bluefish learns your baseline."
    )

    learned = 0
    next_due = {id(s): 0.0 for s in sensors}
    try:
        with console.status("Observing normal activity...") as status:
            while time.time() < deadline:
                now = time.monotonic()
                for sensor in sensors:
                    if now < next_due[id(sensor)]:
                        continue
                    next_due[id(sensor)] = now + sensor.poll_interval
                    for event in sensor.poll():
                        system.observe_for_learning(event)
                        learned += 1
                remaining = int(deadline - time.time())
                status.update(
                    f"Observing... {learned} events learned, {remaining}s left"
                )
                time.sleep(0.5)
    except KeyboardInterrupt:
        console.print("\n[yellow]Learning interrupted; keeping what was learned.[/yellow]")

    total = system.self_profile.signature_count()
    store.set_meta("last_learn", time.time())
    store.close()
    console.print(
        f"[bold green]Done.[/bold green] Learned {learned} events; "
        f"self-profile now holds {total} signatures."
    )


@app.command()
def start(
    foreground: bool = typer.Option(
        False, "--foreground", "-f", help="Run in the foreground (do not fork)."
    ),
    confirm: bool = typer.Option(
        False, "--confirm", help="Permit active (destructive) measures if enabled."
    ),
) -> None:
    """Start the monitoring daemon (the immune system's active defense)."""
    config = _config()
    if confirm:
        # Carry the flag into the daemon's responder via config overlay.
        config.data.setdefault("response", {})["_confirm_active"] = True

    existing = read_pid(config)
    if existing and _pid_alive(existing):
        console.print(f"[yellow]Already running (pid {existing}).[/yellow]")
        raise typer.Exit(1)

    if not _self_is_trained(config):
        console.print(
            "[yellow]Warning:[/yellow] no self-profile yet. Run "
            "[bold]bluefish learn[/bold] first, or the adaptive layer stays "
            "dormant and only innate rules fire."
        )

    if foreground:
        _setup_logging(config, to_file=False)
        console.print("[bold cyan]Bluefish[/bold cyan] running in foreground. Ctrl-C to stop.")
        run_daemon(config)
        return

    # Background: double-fork so the daemon detaches from the terminal.
    _daemonize(config)


@app.command()
def stop() -> None:
    """Stop a running Bluefish daemon."""
    config = _config()
    pid = read_pid(config)
    if not pid or not _pid_alive(pid):
        console.print("[yellow]No running daemon found.[/yellow]")
        raise typer.Exit(1)
    os.kill(pid, signal.SIGTERM)
    console.print(f"[green]Sent stop signal to pid {pid}.[/green]")


@app.command()
def status() -> None:
    """Show daemon state, inflammation, and recent activity."""
    config = _config()
    store = Store(config.db_path)
    pid = read_pid(config)
    running = bool(pid and _pid_alive(pid))

    table = Table(title="Bluefish status", show_header=False)
    table.add_row("Daemon", f"[green]running[/green] (pid {pid})" if running else "[red]stopped[/red]")
    table.add_row("Self signatures", str(store.self_signature_count()))
    table.add_row("Last learned", _fmt_ts(store.get_meta("last_learn")))
    table.add_row("Alerts recorded", str(store.alert_count()))
    table.add_row("Memory cells", str(len(store.memory_entries())))
    table.add_row("Events seen", str(store.get_meta("events_seen", 0)))
    table.add_row("Last heartbeat", _fmt_ts(store.get_meta("last_heartbeat")))
    console.print(table)
    store.close()


@app.command()
def alerts(
    limit: int = typer.Option(20, "--limit", "-n", help="Number of alerts to show."),
) -> None:
    """List the most recent alerts."""
    config = _config()
    store = Store(config.db_path)
    rows = store.recent_alerts(limit)
    store.close()
    if not rows:
        console.print("[green]No alerts recorded.[/green]")
        return

    table = Table(title=f"Recent alerts (last {len(rows)})")
    table.add_column("ID", justify="right")
    table.add_column("Time")
    table.add_column("Sev")
    table.add_column("Verdict")
    table.add_column("Signature", overflow="fold")
    for row in rows:
        table.add_row(
            str(row["id"]),
            _fmt_ts(row["ts"]),
            _severity_markup(row["severity"]),
            _verdict_markup(row.get("verdict")),
            row["signature"],
        )
    console.print(table)


@app.command()
def explain(alert_id: int = typer.Argument(..., help="Alert ID to explain.")) -> None:
    """Show the full evidence and analysis for one alert."""
    config = _config()
    store = Store(config.db_path)
    alert = store.get_alert(alert_id)
    store.close()
    if not alert:
        console.print(f"[red]No alert with id {alert_id}.[/red]")
        raise typer.Exit(1)

    console.print(f"[bold]Alert #{alert['id']}[/bold]  {_fmt_ts(alert['ts'])}")
    console.print(f"  Source     : {alert['source']}")
    console.print(f"  Signature  : {alert['signature']}")
    console.print(f"  Severity   : {_severity_markup(alert['severity'])}")
    console.print(f"  Verdict    : {_verdict_markup(alert.get('verdict'))} "
                  f"(confidence {alert.get('confidence') or 0:.2f})")
    console.print(f"  Novelty    : {alert['novelty']:.2f}   "
                  f"Inflammation: {alert['inflammation']:.2f}")
    if alert.get("from_memory"):
        console.print("  [magenta]Secondary immune response (matched memory).[/magenta]")
    console.print("\n  [bold]Observation[/bold]")
    console.print(f"    {alert['raw']}")
    console.print("\n  [bold]Why it fired[/bold]")
    for reason in alert.get("reasons", []):
        if reason:
            console.print(f"    - {reason}")
    if alert.get("analysis"):
        console.print("\n  [bold]Analyst reasoning[/bold]")
        console.print(f"    {alert['analysis']}")
    if alert.get("actions"):
        console.print("\n  [bold]Recommended actions[/bold]")
        for action in alert["actions"]:
            console.print(f"    - {action}")


@app.command()
def memory() -> None:
    """List immune-memory (confirmed-threat) signatures."""
    config = _config()
    store = Store(config.db_path)
    entries = store.memory_entries()
    store.close()
    if not entries:
        console.print("[green]No memory cells yet.[/green]")
        return
    table = Table(title="Immune memory")
    table.add_column("Signature", overflow="fold")
    table.add_column("Verdict")
    table.add_column("Sev")
    table.add_column("Hits", justify="right")
    table.add_column("Learned")
    for entry in entries:
        table.add_row(
            entry["signature"],
            _verdict_markup(entry["verdict"]),
            _severity_markup(entry["severity"]),
            str(entry["hits"]),
            _fmt_ts(entry["created_at"]),
        )
    console.print(table)


# --- small presentation / process helpers ------------------------------
def _severity_markup(severity: str | None) -> str:
    colors = {
        "critical": "bold red",
        "high": "red",
        "medium": "yellow",
        "low": "cyan",
        "info": "dim",
    }
    style = colors.get((severity or "").lower(), "white")
    return f"[{style}]{severity or '-'}[/{style}]"


def _verdict_markup(verdict: str | None) -> str:
    colors = {
        "malicious": "bold red",
        "suspicious": "yellow",
        "benign": "green",
        "unconfirmed": "dim",
    }
    style = colors.get((verdict or "").lower(), "dim")
    return f"[{style}]{verdict or 'unconfirmed'}[/{style}]"


def _pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _self_is_trained(config: Config) -> bool:
    store = Store(config.db_path)
    trained = store.self_signature_count() > 0
    store.close()
    return trained


def _daemonize(config: Config) -> None:
    """Detach into the background via a standard double fork."""
    config.ensure_data_dir()
    if os.fork() > 0:
        console.print("[green]Bluefish started in background.[/green]")
        os._exit(0)
    os.setsid()
    if os.fork() > 0:
        os._exit(0)

    # Grandchild: redirect standard streams and run.
    sys.stdout.flush()
    sys.stderr.flush()
    with open(os.devnull, "rb") as devnull_in:
        os.dup2(devnull_in.fileno(), sys.stdin.fileno())
    log_fd = open(config.log_path, "a")
    os.dup2(log_fd.fileno(), sys.stdout.fileno())
    os.dup2(log_fd.fileno(), sys.stderr.fileno())
    _setup_logging(config, to_file=True)
    run_daemon(config)
    os._exit(0)


if __name__ == "__main__":
    app()
