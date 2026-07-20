"""Bluefish — a host-security AI modeled on the human immune system.

Bluefish learns a profile of the "self" (normal processes and log activity),
then uses layered defenses inspired by biological immunity to detect and
respond to "non-self" activity:

  * innate detectors   — fast, rule-based recognition of known-bad patterns
  * adaptive detector  — negative-selection self/non-self discrimination
  * danger correlator  — accumulates real-harm signals into an "inflammation"
  * LLM analyst         — a Claude-backed verdict for escalated alerts
  * memory              — confirmed threats trigger an instant secondary response
"""

__version__ = "0.1.0"
