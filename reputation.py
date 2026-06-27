"""P2 reputation / anomaly layer (Rohit's stretch).

Agents build trust slowly over clean bookings and decay fast on anomalies — the
way real fraud reputation works. OPT-IN by design: this is NOT wired into the
demo's score() path, so the locked scenario numbers (70 / 15 / 10) are untouched.
Enable it by calling store.adjust(agent_id, verdict.score) after scoring if you
want a "the engine remembers" beat.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class ReputationStore:
    """Per-agent reputation in [0, 100]. Build slow, decay fast."""
    start: float = 50.0
    build_step: float = 5.0    # reward for a clean action
    decay_step: float = 30.0   # penalty for an anomaly (asymmetric on purpose)
    _rep: dict = field(default_factory=dict)

    def get(self, agent_id: str) -> float:
        return self._rep.get(agent_id, self.start)

    def record_clean(self, agent_id: str) -> float:
        self._rep[agent_id] = min(100.0, self.get(agent_id) + self.build_step)
        return self._rep[agent_id]

    def record_anomaly(self, agent_id: str) -> float:
        self._rep[agent_id] = max(0.0, self.get(agent_id) - self.decay_step)
        return self._rep[agent_id]

    def adjust(self, agent_id: str, base_score: int) -> int:
        """Blend reputation into a base trust score as a bounded nudge (-10..+10).

        A long-trusted agent gets a small benefit of the doubt; a recently
        anomalous one gets extra scrutiny. The nudge is deliberately small so
        reputation tunes the score, it never overrides the hard caps.
        """
        nudge = round((self.get(agent_id) - self.start) / 5)
        nudge = max(-10, min(10, nudge))
        return max(0, min(100, base_score + nudge))
