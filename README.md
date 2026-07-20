# Bluefish 🐟🛡️

**Bluefish** is a host-security AI modeled on the human immune system. It learns
what "normal" looks like on a machine, then uses layered, biologically-inspired
defenses to detect and explain suspicious process and log activity — combining
fast immune-style algorithms with an optional Claude-powered analyst.

> The immune system does not memorize every threat in advance. It learns the
> body ("self"), reacts fast to known danger, adapts to the unknown, and
> remembers what it has fought. Bluefish is built the same way.

---

## Why an immune system?

Signature-only antivirus fails on novel threats; pure anomaly detection drowns
you in false positives. Biological immunity solves exactly this tension with a
layered design, and Bluefish mirrors it:

| Immune concept | Bluefish component | Role |
|---|---|---|
| Self (the body) | **Self Profile** | Learned baseline of normal processes & log patterns |
| Antigen | **Event** | One normalized observation from a sensor |
| Innate immunity | **Innate Detectors** | Fast rules for known-bad structure (temp exec, reverse shells…) |
| Adaptive immunity + negative selection | **Adaptive Detector** | Flags "non-self" (never-learned) activity |
| Danger theory | **Danger Correlator** | Accumulates real-harm signals into an "inflammation" level |
| Lymph node / judgment | **LLM Analyst** (Claude) | Deliberate verdict + explanation for escalated alerts |
| Memory cells | **Memory** | Confirmed threats trigger an instant secondary response |
| Immune response | **Responder** | Records alerts; active measures are opt-in and guarded |

A key design choice follows biology: **novelty and danger are separate**. A
first-seen process is *interesting* (the adaptive layer notes it) but not an
incident. Only structural red flags and accumulated danger raise an alert to
high/critical — so ordinary new commands don't scream "critical".

---

## Architecture

```
sensors ─▶ events ─▶ ImmuneSystem ─▶ Responder ─▶ alerts / memory
                        │
        ┌───────────────┼────────────────────────────┐
        ▼               ▼               ▼              ▼
     memory          innate         adaptive        danger
   (2nd response)   (rules)     (self/non-self)  (inflammation)
                                                     │
                                          escalate ──▶ LLM Analyst (Claude)
```

For each event the pipeline runs: **memory** (instant secondary response to a
known threat) → **innate** (cheap rules) → **adaptive** (negative-selection
self/non-self) → **danger** (systemic inflammation). If novelty and inflammation
cross the threshold an alert is raised; only genuinely dangerous alerts consult
the LLM analyst, and a *confirmed-malicious* verdict forms an immune memory.

---

## Install

```bash
pip install -e .            # core (innate + adaptive + danger)
pip install -e '.[llm]'     # add the Claude analyst
```

The LLM analyst is **optional**. Without the `anthropic` package or an
`ANTHROPIC_API_KEY`, Bluefish still runs on its innate + adaptive layers and
marks verdicts as `unconfirmed`. *The body defends itself even without a brain.*

```bash
export ANTHROPIC_API_KEY=sk-...   # to enable the analyst
```

## Quick start

```bash
# 1. Immunize: learn "self" while the host does its normal work.
#    Train for as long as is representative — minutes for a demo, longer
#    for a real host. Under-training makes ordinary activity look novel.
bluefish learn --minutes 30

# 2. Defend: start the monitoring daemon.
bluefish start                # background;  add --foreground to watch live

# 3. Observe.
bluefish status               # daemon state, self size, counts
bluefish alerts               # recent alerts
bluefish explain 42           # full evidence + analyst reasoning for one alert
bluefish memory               # confirmed-threat signatures (memory cells)

# 4. Stop.
bluefish stop
```

Configuration is optional; copy `config.example.yaml` to `~/.bluefish/config.yaml`
or pass `--config path.yaml`. Every value has a sensible default.

## What it watches

- **Processes** (`psutil`): each newly-started process becomes an event.
  Bluefish is self-tolerant — it never flags its own daemon or CLI.
- **Logs** (file tail): new lines from `auth.log`, `syslog`, etc. Volatile
  tokens (PIDs, IPs, timestamps) are masked so lines that differ only in those
  collapse to one signature, and rotation/truncation is handled.

## Safety

Bluefish is **observe-and-report by default**. It never kills or freezes a
process on its own judgment. Active (potentially destructive) measures require
*both* `response.allow_active_measures: true` in config *and* an explicit
`bluefish start --confirm`. Alerts and suggestions are always non-destructive.

## Development

```bash
pip install -e '.[dev]'
pytest
```

Tests cover event templating, self-profile learning, each detector layer, the
memory secondary response, sensor tailing/self-tolerance, and the end-to-end
`ImmuneSystem` pipeline (including the analyst-unavailable path).

## Status

v0.1 — a working first version. Roadmap: journald/network sensors, self-profile
decay/aging, and richer active-response playbooks.
