"""The "self" model — Bluefish's learned sense of what is normal.

Biological immunity spends early life learning to tolerate the body's own
molecules; anything not recognized as self later becomes a candidate for
attack. :class:`SelfProfile` is the computational analogue:

  * a set of known-good *signatures* (processes and log templates), and
  * running distributions (mean/stddev) of numeric features.

An event is "self" when its signature is known **and** its numeric features
sit within ``mean ± k*stddev`` of what was learned. Learning is incremental,
so ``bluefish learn --update`` can extend an existing profile.
"""

from __future__ import annotations

from bluefish.core.events import Event
from bluefish.store.db import Store

# A numeric feature needs at least this many learned samples before its
# distribution is trusted for deviation scoring. With fewer samples the
# variance estimate is meaningless, so we abstain rather than cry outlier.
_MIN_NUMERIC_SAMPLES = 5


class SelfProfile:
    """Read/update the learned self-model, backed by the :class:`Store`."""

    def __init__(self, store: Store, numeric_k: float = 3.0):
        self.store = store
        self.numeric_k = numeric_k

    # --- learning -------------------------------------------------------
    def learn(self, event: Event) -> None:
        """Fold one event into the self-model (signature + numeric stats)."""
        self.store.add_self_signatures([(event.signature, event.source)])
        for name, value in event.numeric_features().items():
            self.store.update_numeric(f"{event.source}:{name}", value)

    def learn_many(self, events: list[Event]) -> None:
        for event in events:
            self.learn(event)

    def signature_count(self) -> int:
        return self.store.self_signature_count()

    def is_trained(self) -> bool:
        return self.signature_count() > 0

    # --- matching -------------------------------------------------------
    def signature_is_self(self, event: Event) -> bool:
        return self.store.is_self_signature(event.signature)

    def numeric_deviation(self, event: Event) -> float:
        """Largest normalized deviation of any numeric feature from self.

        Returns a value in ``[0, 1]``: 0 when every feature is well within the
        learned band, approaching 1 as features stray far beyond ``k*stddev``.
        Unknown features (never learned) contribute a moderate deviation.
        """
        worst = 0.0
        for name, value in event.numeric_features().items():
            stats = self.store.get_numeric(f"{event.source}:{name}")
            if stats is None:
                # Never-learned feature: mildly unusual, not conclusive.
                worst = max(worst, 0.3)
                continue
            n, mean, stddev = stats
            if n < _MIN_NUMERIC_SAMPLES:
                # Too little data to trust the distribution; abstain.
                continue
            if stddev <= 1e-9:
                # A genuinely constant feature: a difference is meaningful but
                # not maximal on its own.
                deviation = 0.0 if abs(value - mean) < 1e-9 else 0.5
            else:
                z = abs(value - mean) / stddev
                # Within k*stddev -> 0; scales up to 1 by 2*k*stddev.
                deviation = max(0.0, (z - self.numeric_k) / self.numeric_k)
                deviation = min(1.0, deviation)
            worst = max(worst, deviation)
        return worst

    def is_self(self, event: Event) -> bool:
        """True when signature is known and numeric features are in-band."""
        if not self.signature_is_self(event):
            return False
        return self.numeric_deviation(event) < 1.0
