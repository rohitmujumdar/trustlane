"""Auto-learning reputation tracker per agent instance.

Agents build trust slowly over successful actions and decay fast on anomalies —
the way real fraud reputation works. Reputation is used as a multiplier in the
trust engine's score() function: effective_score = raw * (0.7 + 0.3 * reputation).
"""
from __future__ import annotations


class ReputationTracker:
    """Auto-learning reputation per agent instance."""

    def __init__(self):
        self._scores: dict[str, float] = {}  # agent_id -> reputation (0.0 to 1.0)

    def get(self, agent_id: str) -> float:
        return self._scores.get(agent_id, 0.5)  # default 0.5 for new agents

    def update(self, agent_id: str, outcome: str) -> float:
        """Update reputation based on outcome.

        Outcomes:
          "allow_success"   -> +0.05
          "allow_error"     -> -0.10
          "review_approved" -> +0.02
          "review_rejected" -> -0.08
          "block"           -> unchanged
        """
        current = self.get(agent_id)
        deltas = {
            "allow_success": 0.05,
            "allow_error": -0.10,
            "review_approved": 0.02,
            "review_rejected": -0.08,
            "block": 0.0,
        }
        new = max(0.0, min(1.0, current + deltas.get(outcome, 0.0)))
        self._scores[agent_id] = new
        return new

    def snapshot(self) -> dict[str, float]:
        return dict(self._scores)

    def reset(self):
        self._scores.clear()
