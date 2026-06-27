from __future__ import annotations

import re
from typing import Sequence

from trustgate.models import ActionRequest, SignalResult


def _tokens(text: str) -> set[str]:
    return set(re.findall(r"[a-z]+", text.lower()))


class IntentDriftSignal:
    """Does the action match the task the agent was actually given?

    Placeholder heuristic: token overlap between the action name and the task.
    TODO(hackathon): swap in embedding similarity (you're the ML person) for a
    version that catches paraphrased drift instead of exact word matches.
    """
    name = "intent_drift"

    def __init__(self, weight: float = 0.25):
        self.weight = weight

    def evaluate(
        self, request: ActionRequest, history: Sequence[ActionRequest]
    ) -> SignalResult:
        action_tokens = _tokens(request.action.replace("_", " "))
        task_tokens = _tokens(request.task)
        if not action_tokens:
            return SignalResult(self.name, 0.5, self.weight, "no action tokens to compare")

        overlap = action_tokens & task_tokens
        if overlap:
            return SignalResult(
                self.name, 0.0, self.weight,
                f"action aligns with task ({', '.join(sorted(overlap))})",
            )
        return SignalResult(
            self.name, 0.7, self.weight,
            "action verb not found anywhere in the task description",
        )
