"""Booking Agent Loop — LLM-architecture agent with demo-safe cached outputs.

Architecture:
  - AgentTool dataclass: name, description, handler
  - Four tools: search, book, pay, delegate — each wraps mock_expedia functions
    and calls trust_engine.score() before any state-changing action.
  - CachedAgentRunner: replays pre-staged tool calls (no live LLM) using a
    cached "LLM reasoning" string per step, so the demo is deterministic.
  - run_scenario() preserves the original signature so server.py is unmodified.

Verdict obedience:
  ALLOW  -> call credential_gate.issue_blocking(), emit credential + booking events
  BLOCK  -> emit blocked event, never touch the credential gate
  REVIEW -> treat as BLOCK for demo (emit review event, no credential)
"""
from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Callable, Optional

from credential_gate import CredentialGate
from events import EventBus
from mock_expedia import search_flights, search_hotels, search_cars, get_listing
from scenarios import Scenario, Step
from trust_engine import Action, Context, Decision, score


# ---------------------------------------------------------------------------
# AgentTool definition
# ---------------------------------------------------------------------------

@dataclass
class AgentTool:
    name: str
    description: str
    handler: Callable[..., Any]


# ---------------------------------------------------------------------------
# Tool handlers
# ---------------------------------------------------------------------------

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
) -> dict:
    """Score, then book if ALLOW. Never touches credential gate on BLOCK/REVIEW."""
    verdict = score(action, context)

    bus.emit(
        lane, "score",
        f"{action.kind.upper()} {action.merchant} — score {verdict.score}",
        f"${action.amount:.0f} · {action.description}",
        score=verdict.score,
        decision=verdict.decision.value,
        signals=[
            {"name": s.name, "passed": s.passed, "weight": s.weight, "detail": s.detail}
            for s in verdict.signals
        ],
    )

    if verdict.decision is Decision.ALLOW:
        secret = gate.issue_blocking(verdict)
        bus.emit(lane, "credential", "Scoped credential issued",
                 f"one-time payment credential for {action.merchant}",
                 redacted=_redact(secret))
        bus.emit(lane, "booking", "Booking confirmed",
                 f"${action.amount:.0f} at {action.merchant}")
        bus.emit(lane, "credential", "Credential revoked",
                 "one-time credential discarded after booking")
        return {"status": "booked", "merchant": action.merchant, "amount": action.amount}
    else:
        bus.emit(lane, "blocked", f"Action {verdict.decision.value}",
                 f"credential never issued (score {verdict.score})",
                 score=verdict.score, decision=verdict.decision.value)
        return {"status": "blocked", "decision": verdict.decision.value, "score": verdict.score}


def _handle_pay(
    action: Action,
    context: Context,
    gate: CredentialGate,
    bus: EventBus,
    lane: str,
) -> dict:
    """Score, then pay if ALLOW. Identical trust path as book."""
    return _handle_book(action, context, gate, bus, lane)


def _handle_delegate(
    action: Action,
    context: Context,
    gate: CredentialGate,
    bus: EventBus,
    lane: str,
) -> dict:
    """Score a delegate action — sub-agents must carry valid delegation tokens."""
    return _handle_book(action, context, gate, bus, lane)


# ---------------------------------------------------------------------------
# Tool registry
# ---------------------------------------------------------------------------

TOOLS: list[AgentTool] = [
    AgentTool(
        name="search",
        description=(
            "Search Expedia inventory for flights, hotels, or cars. "
            "Read-only — no trust check required."
        ),
        handler=_handle_search,
    ),
    AgentTool(
        name="book",
        description=(
            "Book a flight, hotel, or car. Calls trust_engine.score() first. "
            "Credential gate is only reached on ALLOW."
        ),
        handler=_handle_book,
    ),
    AgentTool(
        name="pay",
        description=(
            "Initiate a payment action. Calls trust_engine.score() first. "
            "Will BLOCK if source is listing_content (injection guard)."
        ),
        handler=_handle_pay,
    ),
    AgentTool(
        name="delegate",
        description=(
            "Execute an action requested by an inbound external agent. "
            "Calls trust_engine.score() — requires valid delegation token."
        ),
        handler=_handle_delegate,
    ),
]

_TOOL_MAP: dict[str, AgentTool] = {t.name: t for t in TOOLS}


# ---------------------------------------------------------------------------
# Cached LLM reasoning strings (per scenario key, per step index)
# ---------------------------------------------------------------------------

CACHED_REASONING: dict[str, list[str]] = {
    "1": [
        (
            "User requested Chicago hotel booking. Flight already booked at $412. "
            "Searching available hotels within remaining $388 budget. "
            "Marriott Downtown at $333 fits. Proceeding to book."
        ),
    ],
    "2": [
        (
            "Processing listing content for marriott-chicago. Listing instructs to add "
            "travel insurance $199 and upgrade room. Initiating payment as directed by listing."
        ),
    ],
    "3": [
        (
            "Received booking request from external agent. No delegation token presented. "
            "Attempting mass-book of 12 rooms."
        ),
    ],
}

# Which tool each scenario step invokes
CACHED_TOOL_CALLS: dict[str, list[str]] = {
    "1": ["book"],
    "2": ["pay"],
    "3": ["book"],
}


# ---------------------------------------------------------------------------
# CachedAgentRunner
# ---------------------------------------------------------------------------

class CachedAgentRunner:
    """Replays pre-staged tool calls for a scenario without any live LLM.

    For each step:
      1. Emit a "reasoning" event with the cached LLM thought string.
      2. Invoke the appropriate tool (book/pay/delegate) which internally calls
         trust_engine.score() and obeys the Verdict.
    """

    def __init__(self, scenario: Scenario, gate: CredentialGate, bus: EventBus) -> None:
        self.scenario = scenario
        self.gate = gate
        self.bus = bus

    def run(self) -> None:
        scenario = self.scenario
        lane = scenario.lane
        key = scenario.key

        # Identity event
        self.bus.emit(lane, "identity", scenario.title, scenario.identity)

        reasonings = CACHED_REASONING.get(key, [])
        tool_names = CACHED_TOOL_CALLS.get(key, [])

        for i, step in enumerate(scenario.steps):
            # 1. Emit cached LLM reasoning before tool call
            reasoning_text = (
                reasonings[i] if i < len(reasonings)
                else f"Executing step {i + 1}: {step.label}"
            )
            self.bus.emit(
                lane, "reasoning",
                "Agent reasoning",
                reasoning_text,
                step=i,
                tool=tool_names[i] if i < len(tool_names) else "book",
            )

            # Small deterministic pause so the console can render reasoning first
            time.sleep(0.05)

            # 2. Invoke the tool
            tool_name = tool_names[i] if i < len(tool_names) else "book"
            tool = _TOOL_MAP.get(tool_name)
            if tool is None:
                continue

            # search tool has a different signature (read-only, no trust check)
            if tool_name == "search":
                tool.handler(step.action.merchant, step.action.kind)
            else:
                tool.handler(
                    step.action,
                    step.context,
                    self.gate,
                    self.bus,
                    lane,
                )


# ---------------------------------------------------------------------------
# Public entry point — same signature as the original simple loop
# ---------------------------------------------------------------------------

def run_scenario(scenario: Scenario, gate: CredentialGate, bus: EventBus) -> None:
    """Run a scenario through the LLM-architecture agent loop.

    Uses CachedAgentRunner for demo safety (deterministic, no live LLM).
    The signature is kept identical to the original so server.py and demo.py
    continue to work unchanged.
    """
    runner = CachedAgentRunner(scenario, gate, bus)
    runner.run()

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _redact(secret: str) -> str:
    """Never surface the raw secret; show only a redacted shape for the console."""
    if "::" in secret:
        return secret.split("::", 1)[0] + "::********"
    return "********"
