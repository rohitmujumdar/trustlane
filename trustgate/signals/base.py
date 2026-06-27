from __future__ import annotations

from typing import Protocol, Sequence

from trustgate.models import ActionRequest, SignalResult


class Signal(Protocol):
    """One dimension of risk. Keep each signal cheap, legible, and explainable."""
    name: str
    weight: float

    def evaluate(
        self, request: ActionRequest, history: Sequence[ActionRequest]
    ) -> SignalResult: ...
