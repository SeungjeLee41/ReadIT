"""The LLM analyst — a Claude-backed verdict for escalated alerts.

This is the deliberate, expensive branch of the immune response, analogous to
the adaptive processing in a lymph node. It is invoked only for alerts that the
cheap layers have already escalated, never per event.

Robustness principle: the analyst is *optional*. If the ``anthropic`` package
is not installed, or ``ANTHROPIC_API_KEY`` is unset, or the API call fails, the
system keeps running and returns an ``unconfirmed`` verdict so the body still
defends itself without a brain.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field

from bluefish.llm.prompts import SYSTEM_PROMPT, build_user_message

VERDICTS = ("benign", "suspicious", "malicious", "unconfirmed")


@dataclass
class Verdict:
    verdict: str = "unconfirmed"
    confidence: float = 0.0
    reasoning: str = ""
    recommended_actions: list[str] = field(default_factory=list)
    available: bool = True  # False when the analyst could not run

    def to_dict(self) -> dict:
        return {
            "verdict": self.verdict,
            "confidence": self.confidence,
            "reasoning": self.reasoning,
            "recommended_actions": self.recommended_actions,
            "available": self.available,
        }


class Analyst:
    """Wraps the Anthropic client. Degrades gracefully when unavailable."""

    def __init__(
        self,
        *,
        enabled: bool = True,
        model: str = "claude-sonnet-5",
        max_tokens: int = 1024,
        api_key: str | None = None,
    ):
        self.enabled = enabled
        self.model = model
        self.max_tokens = max_tokens
        self._api_key = api_key or os.environ.get("ANTHROPIC_API_KEY")
        self._client = None
        self._unavailable_reason: str | None = None

        if not self.enabled:
            self._unavailable_reason = "analyst disabled in config"
            return
        if not self._api_key:
            self._unavailable_reason = "ANTHROPIC_API_KEY not set"
            return
        try:
            import anthropic  # noqa: F401

            self._client = anthropic.Anthropic(api_key=self._api_key)
        except ImportError:
            self._unavailable_reason = "anthropic package not installed"
        except Exception as exc:  # pragma: no cover - defensive
            self._unavailable_reason = f"analyst init failed: {exc}"

    @property
    def available(self) -> bool:
        return self._client is not None

    @property
    def unavailable_reason(self) -> str | None:
        return self._unavailable_reason

    def analyze(self, alert: dict) -> Verdict:
        """Return a verdict for an escalated alert."""
        if not self.available:
            return Verdict(
                verdict="unconfirmed",
                reasoning=(
                    "LLM analyst unavailable "
                    f"({self._unavailable_reason}); verdict from local layers only."
                ),
                available=False,
            )

        try:
            message = self._client.messages.create(
                model=self.model,
                max_tokens=self.max_tokens,
                system=SYSTEM_PROMPT,
                messages=[{"role": "user", "content": build_user_message(alert)}],
            )
            text = _extract_text(message)
            return _parse_verdict(text)
        except Exception as exc:  # pragma: no cover - network/runtime dependent
            return Verdict(
                verdict="unconfirmed",
                reasoning=f"analyst call failed: {exc}",
                available=False,
            )


def _extract_text(message: object) -> str:
    """Pull the concatenated text out of an Anthropic message response."""
    parts: list[str] = []
    for block in getattr(message, "content", []) or []:
        text = getattr(block, "text", None)
        if text:
            parts.append(text)
    return "".join(parts).strip()


def _parse_verdict(text: str) -> Verdict:
    """Parse the model's JSON reply, tolerating stray formatting."""
    payload = _extract_json(text)
    if payload is None:
        return Verdict(
            verdict="unconfirmed",
            reasoning="analyst returned an unparseable response",
            available=True,
        )

    verdict = str(payload.get("verdict", "unconfirmed")).lower()
    if verdict not in VERDICTS:
        verdict = "suspicious"
    try:
        confidence = float(payload.get("confidence", 0.0))
    except (TypeError, ValueError):
        confidence = 0.0
    actions = payload.get("recommended_actions", [])
    if not isinstance(actions, list):
        actions = [str(actions)]
    return Verdict(
        verdict=verdict,
        confidence=max(0.0, min(1.0, confidence)),
        reasoning=str(payload.get("reasoning", "")),
        recommended_actions=[str(a) for a in actions],
        available=True,
    )


def _extract_json(text: str) -> dict | None:
    try:
        return json.loads(text)
    except (json.JSONDecodeError, TypeError):
        pass
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError:
            return None
    return None
