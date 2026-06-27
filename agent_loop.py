"""Multi-Agent Orchestrator — LLM-architecture agent with demo-safe cached outputs.

Architecture:
  - AgentInstance dataclass: agent_id, agent_type, hop, parent_id
  - Orchestrator: routes tasks to sub-agents, manages scoring, credentials, reputation
  - Per-agent weight profiles (from trust_engine.AGENT_WEIGHTS)
  - Trust decay by hop depth (from trust_engine.get_decay_factor)
  - Reputation tracking via ReputationTracker

Verdict obedience:
  ALLOW  -> call credential_gate.issue_blocking(), emit credential + booking events
  BLOCK  -> emit blocked event, never touch the credential gate
  REVIEW -> treat as BLOCK for demo (emit review event, no credential)

Demo safety: CachedAgentRunner pattern — pre-baked reasoning strings per step,
no live LLM, fully deterministic.
"""
from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Callable, Optional

from credential_gate import CredentialGate, ScopedCredential
from events import EventBus
from mock_expedia import search_flights, search_hotels, search_cars, get_listing
from reputation import ReputationTracker
from scenarios import Scenario, Step
from trust_engine import Action, AgentType, Context, Decision, score


# ---------------------------------------------------------------------------
# Module-level reputation tracker (shared across all scenarios in a session)
# ---------------------------------------------------------------------------

_REPUTATION = ReputationTracker()


# ---------------------------------------------------------------------------
# AgentInstance definition
# ---------------------------------------------------------------------------

@dataclass
class AgentInstance:
    agent_id: str           # e.g., "search-agent-001"
    agent_type: AgentType   # SEARCH, BOOKING, PAYMENT, DELEGATION
    hop: int                # delegation depth
    parent_id: Optional[str]  # parent agent ID


# ---------------------------------------------------------------------------
# Tool handlers (same as before, but now wrapped by Orchestrator)
# ---------------------------------------------------------------------------

@dataclass
class AgentTool:
    name: str
    description: str
    handler: Callable[..., Any]


def _handle_search(query: str, kind: str = "hotels") -> dict:
    """Search mock Expedia inventory. No trust check needed — read-only."""
    if kind == "flights":
        results = search_flights(query)
    elif kind == "cars":
        results = search_cars(query)
    else:
        results = search_hotels(query)
    return {"kind": kind, "query": query, "results": results, "count": len(results)}


def _handle_book(
    action: Action,
    context: Context,
    gate: CredentialGate,
    bus: EventBus,
    lane: str,
    reputation_score: float = 0.5,
    agent_id: str = "agent",
) -> dict:
    """Score, then book if ALLOW. Never touches credential gate on BLOCK/REVIEW."""
    verdict = score(action, context, reputation_score)

    bus.emit(
        lane, "score",
        f"{action.kind.upper()} {action.merchant} — score {verdict.score}",
        f"${action.amount:.0f} · {action.description}",
        score=verdict.score,
        decision=verdict.decision.value,
        agent_type=action.agent_type,
        hop=action.hop,
        signals=[
            {"name": s.name, "passed": s.passed, "weight": s.weight, "detail": s.detail}
            for s in verdict.signals
        ],
    )

    if verdict.decision is Decision.ALLOW:
        cred = gate.issue_blocking(
            verdict,
            holder=agent_id,
            scope="pay",
            merchant=action.merchant,
            max_amount=action.amount,
        )
        bus.emit(lane, "credential", "Scoped credential issued",
                 f"one-time payment credential for {action.merchant} (max ${action.amount:.0f})",
                 redacted=_redact(cred.secret),
                 credential_id=cred.credential_id,
                 merchant=cred.merchant,
                 max_amount=cred.max_amount,
                 can_delegate=cred.can_delegate)
        bus.emit(lane, "booking", "Booking confirmed",
                 f"${action.amount:.0f} at {action.merchant}")
        gate.revoke(cred)
        bus.emit(lane, "credential", "Credential revoked",
                 "one-time credential discarded after booking")
        return {"status": "booked", "merchant": action.merchant, "amount": action.amount, "outcome": "allow_success"}
    elif verdict.decision is Decision.REVIEW:
        bus.emit(lane, "blocked", f"Action {verdict.decision.value}",
                 f"credential withheld — requires human approval (score {verdict.score})",
                 score=verdict.score, decision=verdict.decision.value)
        return {"status": "review", "decision": verdict.decision.value, "score": verdict.score, "outcome": "block"}
    else:
        bus.emit(lane, "blocked", f"Action {verdict.decision.value}",
                 f"credential never issued (score {verdict.score})",
                 score=verdict.score, decision=verdict.decision.value)
        return {"status": "blocked", "decision": verdict.decision.value, "score": verdict.score, "outcome": "block"}


def _handle_pay(
    action: Action,
    context: Context,
    gate: CredentialGate,
    bus: EventBus,
    lane: str,
    reputation_score: float = 0.5,
    agent_id: str = "agent",
) -> dict:
    """Score, then pay if ALLOW. Identical trust path as book."""
    return _handle_book(action, context, gate, bus, lane, reputation_score, agent_id)


TOOLS: dict[str, AgentTool] = {
    "search": AgentTool(
        name="search",
        description="Search Expedia inventory for flights, hotels, or cars. Read-only.",
        handler=_handle_search,
    ),
    "book": AgentTool(
        name="book",
        description="Book a flight, hotel, or car. Calls trust_engine.score() first.",
        handler=_handle_book,
    ),
    "pay": AgentTool(
        name="pay",
        description="Initiate a payment. Calls trust_engine.score() first.",
        handler=_handle_pay,
    ),
}


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------

class Orchestrator:
    """Top-level agent that routes tasks to sub-agents."""

    def __init__(self, gate: CredentialGate, bus: EventBus, reputation: ReputationTracker) -> None:
        self.gate = gate
        self.bus = bus
        self.reputation = reputation

    def run_scenario(self, scenario: Scenario) -> None:
        """Execute a full scenario through the multi-agent system."""
        lane = scenario.lane

        # Emit identity event
        self.bus.emit(lane, "identity", scenario.title, scenario.identity)

        for i, step in enumerate(scenario.steps):
            action = step.action

            # Determine agent type and create agent instance
            try:
                agent_type_enum = AgentType(action.agent_type)
            except ValueError:
                agent_type_enum = AgentType.BOOKING

            agent_id = f"{action.agent_type}-agent-{i + 1:03d}"

            # 1. Emit "agent_start" event
            self.bus.emit(
                lane, "agent_start",
                f"{action.agent_type.capitalize()} Agent starting",
                f"Agent {agent_id} (hop={action.hop}) — {step.label}",
                agent_id=agent_id,
                agent_type=action.agent_type,
                hop=action.hop,
                step=i,
            )

            # 2. Emit "reasoning" event (cached LLM thought)
            reasoning_text = step.reasoning or f"Executing step {i + 1}: {step.label}"
            self.bus.emit(
                lane, "reasoning",
                "Agent reasoning",
                reasoning_text,
                step=i,
                agent_id=agent_id,
                tool=action.kind,
            )

            # Small deterministic pause so the console can render reasoning first
            time.sleep(0.05)

            # 3. Get reputation for this agent
            rep_score = self.reputation.get(agent_id)

            # 4. Search steps are read-only, no trust scoring needed
            if action.agent_type == "search" or action.kind == "search":
                _handle_search(action.merchant, action.kind)
                # Search always succeeds, small reputation boost
                new_rep = self.reputation.update(agent_id, "allow_success")
                self.bus.emit(
                    lane, "reputation",
                    f"Reputation updated: {agent_id}",
                    f"search completed → rep={new_rep:.2f}",
                    agent_id=agent_id,
                    reputation=new_rep,
                    outcome="allow_success",
                )
                continue

            # 5. Score and execute (book/pay/delegate)
            tool_name = action.kind if action.kind in TOOLS else "book"
            result = _handle_book(
                action,
                step.context,
                self.gate,
                self.bus,
                lane,
                reputation_score=rep_score,
                agent_id=agent_id,
            )

            # 6. Update reputation based on outcome
            outcome = result.get("outcome", "block")
            new_rep = self.reputation.update(agent_id, outcome)
            self.bus.emit(
                lane, "reputation",
                f"Reputation updated: {agent_id}",
                f"{outcome} → rep={new_rep:.2f}",
                agent_id=agent_id,
                reputation=new_rep,
                outcome=outcome,
            )


# ---------------------------------------------------------------------------
# Public entry point — same signature as the original simple loop
# ---------------------------------------------------------------------------

def run_scenario(scenario: Scenario, gate: CredentialGate, bus: EventBus) -> None:
    """Run a scenario through the multi-agent orchestrator.

    Uses the module-level _REPUTATION tracker so reputation persists across
    scenario runs in a session. The signature is kept identical to the original
    so server.py and demo.py continue to work unchanged.
    """
    orch = Orchestrator(gate, bus, _REPUTATION)
    orch.run_scenario(scenario)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _redact(secret: str) -> str:
    """Never surface the raw secret; show only a redacted shape for the console."""
    if "::" in secret:
        return secret.split("::", 1)[0] + "::********"
    return "********"
