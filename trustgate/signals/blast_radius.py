from __future__ import annotations

from typing import Optional, Sequence

from trustgate.config import SENSITIVITY
from trustgate.models import ActionRequest, SignalResult


class BlastRadiusSignal:
    """How much damage could this action do if it is wrong or malicious?

    High-stakes actions need higher trust to clear. A money amount above a
    threshold pushes the blast radius up regardless of the action name.
    """
    name = "blast_radius"

    def __init__(self, weight: float = 0.2, table: Optional[dict] = None):
        self.weight = weight
        self.table = table or SENSITIVITY

    def evaluate(
        self, request: ActionRequest, history: Sequence[ActionRequest]
    ) -> SignalResult:
        base = self.table.get(request.action, 0.5)
        reason = f"action '{request.action}' base sensitivity {base:.2f}"

        amount = request.params.get("amount")
        if isinstance(amount, (int, float)) and amount >= 1000:
            base = max(base, 0.9)
            reason += f"; high amount ${amount}"

        return SignalResult(self.name, base, self.weight, reason)
