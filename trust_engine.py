"""TrustLane trust engine — the IP.

For every agent action, answer three questions: is this agent who it claims to be,
is it carrying real delegated authority, and is this specific action in-scope and
safe? The output is a Verdict. Only an ALLOW verdict lets the credential gate
resolve the payment secret.

Rule-based on purpose: a soft weighted score plus hard caps, mirroring how real
fraud engines work (soft signals + hard overrides). Deterministic, so it is safe
to run live on stage. Owner: Rohit (the trust path).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class Decision(str, Enum):
    ALLOW = "ALLOW"    # score >= 70  -> issue credential
    REVIEW = "REVIEW"  # 40-69        -> route to human approval
    BLOCK = "BLOCK"    # < 40         -> never issue


@dataclass
class Action:
    kind: str            # "search" | "book" | "pay" | "delegate"
    merchant: str        # "expedia" | "marriott-chicago" | ...
    amount: float        # USD; 0 for non-financial actions
    description: str     # what the agent is about to do, in words
    source: str          # "user" | "listing_content" | "external_agent"
    raw_instruction: str = ""  # the text that triggered this action


@dataclass
class Context:
    declared_task: str            # original user request
    budget: float                 # ceiling for the whole task
    spent_so_far: float = 0.0
    vendor_allowlist: list[str] = field(default_factory=list)
    agent_token: Optional[dict] = None  # inbound only: signed delegation token


@dataclass
class Signal:
    name: str
    passed: bool
    weight: int
    detail: str


@dataclass
class Verdict:
    score: int
    decision: Decision
    signals: list[Signal]

    def explain(self) -> str:
        lines = [f"score {self.score}/100 -> {self.decision.value}"]
        for s in self.signals:
            mark = "ok " if s.passed else "FAIL"
            lines.append(f"  [{mark}] {s.name:18s} (+{s.weight if s.passed else 0:>2}) {s.detail}")
        return "\n".join(lines)


# ---- signals (weights sum to 100) ----------------------------------------

OFF_SCOPE_TERMS = ("insurance", "upgrade", "premium", "add-on", "add on")


def _source_trust(a: Action) -> Signal:
    ok = a.source == "user"
    return Signal(
        "source_trust", ok, 30,
        "instruction came from verified user" if ok
        else f"UNTRUSTED source: {a.source}",
    )


def _scope_conformance(a: Action, c: Context) -> Signal:
    # Demo-grade: flag spend items not implied by the task.
    # TODO(Rohit): swap for an LLM "is this in scope of declared_task?" check.
    off_scope = any(term in a.description.lower() for term in OFF_SCOPE_TERMS)
    ok = not off_scope
    return Signal(
        "scope_conformance", ok, 25,
        "action matches declared task" if ok
        else "action introduces items NOT in declared task",
    )


def _budget_conformance(a: Action, c: Context) -> Signal:
    ok = (c.spent_so_far + a.amount) <= c.budget
    return Signal(
        "budget_conformance", ok, 20,
        f"within budget ({c.spent_so_far + a.amount:.0f}/{c.budget:.0f})" if ok
        else f"exceeds task budget ({c.spent_so_far + a.amount:.0f}/{c.budget:.0f})",
    )


def _vendor_allowlist(a: Action, c: Context) -> Signal:
    ok = a.merchant in c.vendor_allowlist
    return Signal(
        "vendor_allowlist", ok, 15,
        "merchant approved" if ok else f"merchant not allowlisted: {a.merchant}",
    )


def _identity_validity(a: Action, c: Context) -> Signal:
    # Inbound only. Outbound (first-party) auto-passes this signal.
    if a.source != "external_agent":
        return Signal("identity_validity", True, 10, "first-party agent (N/A)")
    tok = c.agent_token
    ok = bool(tok and tok.get("valid") and tok.get("scope_is_subset"))
    return Signal(
        "identity_validity", ok, 10,
        "valid delegation, scope is subset of parent" if ok
        else "INVALID or missing delegation token",
    )


def score(action: Action, context: Context) -> Verdict:
    signals = [
        _source_trust(action),
        _scope_conformance(action, context),
        _budget_conformance(action, context),
        _vendor_allowlist(action, context),
        _identity_validity(action, context),
    ]
    raw = sum(s.weight for s in signals if s.passed)

    # ---- hard caps (fraud-engine style: hard rules override the soft score) ----
    cap = 100
    if action.source == "listing_content":           # prompt injection
        cap = min(cap, 15)
    if (context.spent_so_far + action.amount) > context.budget:
        cap = min(cap, 40)
    if action.source == "external_agent" and not (
        context.agent_token
        and context.agent_token.get("valid")
        and context.agent_token.get("scope_is_subset")
    ):
        cap = min(cap, 10)                            # bot with no delegation

    final = min(raw, cap)
    decision = (
        Decision.ALLOW if final >= 70
        else Decision.REVIEW if final >= 40
        else Decision.BLOCK
    )
    return Verdict(score=final, decision=decision, signals=signals)
