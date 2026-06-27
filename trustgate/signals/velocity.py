from __future__ import annotations

from typing import Sequence

from trustgate.models import ActionRequest, SignalResult


class VelocitySignal:
    """Repeated identical actions look like a runaway loop, so trust drops."""
    name = "velocity"

    def __init__(self, weight: float = 0.15, window: int = 10, threshold: int = 3):
        self.weight = weight
        self.window = window
        self.threshold = threshold

    def evaluate(
        self, request: ActionRequest, history: Sequence[ActionRequest]
    ) -> SignalResult:
        recent = list(history)[-self.window:]
        repeats = sum(
            1 for r in recent
            if r.action == request.action and r.agent_id == request.agent_id
        )
        if repeats >= self.threshold:
            risk = min(1.0, 0.4 + 0.15 * repeats)
            return SignalResult(
                self.name, risk, self.weight,
                f"'{request.action}' repeated {repeats}x in last {self.window} actions",
            )
        return SignalResult(self.name, 0.0, self.weight, "no loop detected")
