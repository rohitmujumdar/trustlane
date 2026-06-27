"""Booking agent loop — runs a scenario's actions through the trust gate.

The contract (handoff section 4): before every state-changing action the agent
calls score(); it obeys the Verdict, and only on ALLOW does it call
gate.issue(). The console renders the resulting stream of (action, verdict,
credential_event).

For demo safety this runner is deterministic: it replays the pre-staged scenario
steps rather than calling a live LLM. Swati can drop a real LLM tool loop in
behind the same score() -> gate.issue() contract later.
"""
from __future__ import annotations

from credential_gate import CredentialGate
from events import EventBus
from scenarios import Scenario
from trust_engine import Decision, score


def run_scenario(scenario: Scenario, gate: CredentialGate, bus: EventBus) -> None:
    lane = scenario.lane

    bus.emit(lane, "identity", scenario.title, scenario.identity)

    deleg = getattr(scenario, "delegation", None)
    if deleg:
        bus.emit(lane, "delegation", "Delegation chain", "", **deleg)

    for step in scenario.steps:
        verdict = score(step.action, step.context)

        bus.emit(
            lane, "score",
            f"{step.action.kind.upper()} {step.action.merchant} — score {verdict.score}",
            step.label,
            score=verdict.score,
            decision=verdict.decision.value,
            signals=[
                {"name": s.name, "passed": s.passed, "weight": s.weight, "detail": s.detail}
                for s in verdict.signals
            ],
        )

        if verdict.decision is Decision.ALLOW:
            secret = gate.issue_blocking(verdict)              # secret resolved ONLY here
            bus.emit(lane, "credential", "Scoped credential issued",
                     f"one-time payment credential for {step.action.merchant}",
                     redacted=_redact(secret))
            bus.emit(lane, "booking", "Booking confirmed",
                     f"${step.action.amount:.0f} at {step.action.merchant}")
            bus.emit(lane, "credential", "Credential revoked",
                     "one-time credential discarded after booking")
        else:
            # No gate.issue() call at all -> the secret is never pulled into context.
            bus.emit(lane, "blocked", f"Action {verdict.decision.value}",
                     f"credential never issued (score {verdict.score})",
                     score=verdict.score, decision=verdict.decision.value)


def _redact(secret: str) -> str:
    """Never surface the raw secret; show only a redacted shape for the console."""
    if "::" in secret:
        return secret.split("::", 1)[0] + "::********"
    return "********"
