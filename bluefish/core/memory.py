"""Immune memory — confirmed threats trigger an instant secondary response.

After the immune system defeats a pathogen it retains memory cells so a second
encounter is met faster and harder. Bluefish stores the signatures of events
that were confirmed malicious. On re-observation the pipeline can skip the slow
path (LLM analysis) and respond immediately, exactly like a secondary immune
response.
"""

from __future__ import annotations

from bluefish.core.events import Event
from bluefish.store.db import Store


class Memory:
    """Thin wrapper over the store's memory table."""

    def __init__(self, store: Store):
        self.store = store

    def remember(
        self,
        signature: str,
        *,
        verdict: str,
        severity: str,
        reason: str,
    ) -> None:
        self.store.remember(signature, verdict, severity, reason)

    def recall(self, event: Event) -> dict | None:
        """Return the stored threat record for this event, or None.

        A non-None result also records the hit (secondary-response bookkeeping).
        """
        return self.store.recall(event.signature)

    def entries(self) -> list[dict]:
        return self.store.memory_entries()
