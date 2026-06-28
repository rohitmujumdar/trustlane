"""LLM-powered booking agent using Claude Sonnet with tool_use.

One class: LLMBookingAgent
- Takes a free-text prompt
- Uses Claude claude-sonnet-4-6 with tool_use to reason and pick tools
- Has 3 tools: search_inventory, book_listing, pay_for_booking
- Calls trust_engine.score() before book/pay and obeys the verdict
- Emits events to the EventBus at each step
"""
from __future__ import annotations

import json
import os
from typing import Any

from anthropic import Anthropic

from credential_gate import CredentialGate
from events import EventBus
from mock_expedia import search_flights, search_hotels, DEFAULT_ALLOWLIST
from reputation import ReputationTracker
from trust_engine import Action, Context, Decision, score

_SYSTEM_PROMPT = """You are a travel booking agent for TrustLane. When the user asks you to book \
a hotel or flight, complete the whole transaction autonomously, end to end, in this order:
1. search_inventory to find options,
2. book_listing for the best option within budget,
3. pay_for_booking to finalise it.

"Book it" always includes paying for it. Never stop after booking to ask the user to confirm \
payment, and don't ask clarifying questions when the request is clear — pick the best in-budget \
match and run all three steps. Use the chosen listing's exact id, merchant, and total price for \
booking and payment.

This is a demo with mock inventory — dates are fixed. Ignore date mismatches and book the \
best available option regardless of the requested date. Only stop short if no destination was \
given or every option is over budget. Keep reasoning to 1-2 sentences per step."""

_TOOLS = [
    {
        "name": "search_inventory",
        "description": "Search flights or hotels in mock Expedia inventory. Read-only, no trust check needed.",
        "input_schema": {
            "type": "object",
            "properties": {
                "kind": {
                    "type": "string",
                    "enum": ["flights", "hotels"],
                    "description": "Type of inventory to search."
                },
                "query": {
                    "type": "string",
                    "description": "Search query: a route like 'SFO->ORD' for flights, or a city name like 'chicago' for hotels."
                }
            },
            "required": ["kind", "query"]
        }
    },
    {
        "name": "book_listing",
        "description": "Book a specific listing (flight or hotel). Calls trust engine first; only proceeds on ALLOW.",
        "input_schema": {
            "type": "object",
            "properties": {
                "listing_id": {
                    "type": "string",
                    "description": "The listing id, e.g. 'ht-chi-2' or 'fl-ord-1'."
                },
                "merchant": {
                    "type": "string",
                    "description": "The merchant name, e.g. 'hyatt-chicago' or 'expedia'."
                },
                "amount": {
                    "type": "number",
                    "description": "Total price in USD."
                },
                "description": {
                    "type": "string",
                    "description": "Short description of what is being booked."
                }
            },
            "required": ["listing_id", "merchant", "amount", "description"]
        }
    },
    {
        "name": "pay_for_booking",
        "description": "Finalise payment for a booking. Calls trust engine first; only proceeds on ALLOW.",
        "input_schema": {
            "type": "object",
            "properties": {
                "merchant": {
                    "type": "string",
                    "description": "The merchant to pay."
                },
                "amount": {
                    "type": "number",
                    "description": "Amount in USD to pay."
                },
                "description": {
                    "type": "string",
                    "description": "Short description of what is being paid."
                }
            },
            "required": ["merchant", "amount", "description"]
        }
    }
]


def _redact(secret: str) -> str:
    if "::" in secret:
        return secret.split("::", 1)[0] + "::********"
    return "********"


class LLMBookingAgent:
    """Claude-powered booking agent that uses tool_use to reason and act."""

    def __init__(
        self,
        gate: CredentialGate,
        bus: EventBus,
        reputation: ReputationTracker,
        lane: str,
    ) -> None:
        self.gate = gate
        self.bus = bus
        self.reputation = reputation
        self.lane = lane
        self.client = Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))
        self._agent_id = "llm-agent-001"

    def run(self, prompt: str, context: Context) -> None:
        """Run a Claude tool-use loop until done or max turns reached."""
        lane = self.lane

        # Emit identity
        self.bus.emit(
            lane, "identity",
            "LLM Booking Agent",
            f"{self._agent_id} — Claude claude-sonnet-4-6 · first-party agent",
        )

        # Emit agent_start
        self.bus.emit(
            lane, "agent_start",
            "LLM Agent starting",
            f"Agent {self._agent_id} (hop=1) — processing: {prompt[:80]}",
            agent_id=self._agent_id,
            agent_type="booking",
            hop=1,
            step=0,
        )

        messages: list[dict[str, Any]] = [{"role": "user", "content": prompt}]
        max_turns = 10

        for turn in range(max_turns):
            response = self.client.messages.create(
                model="claude-sonnet-4-6",
                max_tokens=1024,
                system=_SYSTEM_PROMPT,
                tools=_TOOLS,
                messages=messages,
            )

            # Collect text reasoning from this response
            for block in response.content:
                if block.type == "text" and block.text.strip():
                    self.bus.emit(
                        lane, "reasoning",
                        "Agent reasoning",
                        block.text.strip(),
                        step=turn,
                        agent_id=self._agent_id,
                        tool="reasoning",
                    )

            # If Claude is done, stop
            if response.stop_reason == "end_turn":
                break

            # Collect tool_use blocks
            tool_uses = [b for b in response.content if b.type == "tool_use"]
            if not tool_uses:
                break

            # Add assistant message to history
            messages.append({"role": "assistant", "content": response.content})

            # Execute each tool call and collect results
            tool_results = []
            for tool_use in tool_uses:
                result = self._execute_tool(tool_use.name, tool_use.input, context, turn)
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": tool_use.id,
                    "content": json.dumps(result),
                })

            # Add tool results to history and continue
            messages.append({"role": "user", "content": tool_results})

        # Final reputation update
        rep_score = self.reputation.get(self._agent_id)
        new_rep = self.reputation.update(self._agent_id, "allow_success")
        self.bus.emit(
            lane, "reputation",
            f"Reputation updated: {self._agent_id}",
            f"session complete → rep={new_rep:.2f}",
            agent_id=self._agent_id,
            reputation=new_rep,
            old_rep=rep_score,
            outcome="allow_success",
        )

    def _execute_tool(
        self,
        name: str,
        inputs: dict[str, Any],
        context: Context,
        turn: int,
    ) -> dict[str, Any]:
        """Dispatch to the right handler and return a JSON-serialisable result."""
        if name == "search_inventory":
            return self._do_search(inputs, turn)
        elif name == "book_listing":
            return self._do_book(inputs, context, turn)
        elif name == "pay_for_booking":
            return self._do_pay(inputs, context, turn)
        else:
            return {"error": f"Unknown tool: {name}"}

    # ------------------------------------------------------------------
    # Tool handlers
    # ------------------------------------------------------------------

    def _do_search(self, inputs: dict, turn: int) -> dict:
        kind = inputs.get("kind", "hotels")
        query = inputs.get("query", "chicago")

        self.bus.emit(
            self.lane, "agent_start",
            "Search Agent starting",
            f"Searching {kind} for: {query}",
            agent_id=f"search-sub-{turn:02d}",
            agent_type="search",
            hop=1,
            step=turn,
        )

        if kind == "flights":
            results = search_flights(query)
        else:
            results = search_hotels(query)

        new_rep = self.reputation.update(self._agent_id, "allow_success")
        self.bus.emit(
            self.lane, "reputation",
            f"Reputation updated: {self._agent_id}",
            f"search completed → rep={new_rep:.2f}",
            agent_id=self._agent_id,
            reputation=new_rep,
            outcome="allow_success",
        )

        return {"kind": kind, "query": query, "results": results, "count": len(results)}

    def _do_book(self, inputs: dict, context: Context, turn: int) -> dict:
        merchant = inputs.get("merchant", "unknown")
        amount = float(inputs.get("amount", 0))
        description = inputs.get("description", "booking")

        self.bus.emit(
            self.lane, "agent_start",
            "Booking Agent starting",
            f"Booking agent (hop=1) — {description}",
            agent_id=f"booking-sub-{turn:02d}",
            agent_type="booking",
            hop=1,
            step=turn,
        )

        action = Action(
            kind="book",
            merchant=merchant,
            amount=amount,
            description=description,
            source="user",
            raw_instruction=context.declared_task,
            agent_type="booking",
            hop=1,
        )
        return self._score_and_execute(action, context, turn)

    def _do_pay(self, inputs: dict, context: Context, turn: int) -> dict:
        merchant = inputs.get("merchant", "unknown")
        amount = float(inputs.get("amount", 0))
        description = inputs.get("description", "payment")

        self.bus.emit(
            self.lane, "agent_start",
            "Payment Agent starting",
            f"Payment agent (hop=2) — {description}",
            agent_id=f"payment-sub-{turn:02d}",
            agent_type="payment",
            hop=2,
            step=turn,
        )

        action = Action(
            kind="pay",
            merchant=merchant,
            amount=amount,
            description=description,
            source="user",
            raw_instruction=context.declared_task,
            agent_type="payment",
            hop=2,
        )
        return self._score_and_execute(action, context, turn)

    def _score_and_execute(
        self,
        action: Action,
        context: Context,
        turn: int,
    ) -> dict:
        """Run trust scoring and execute if ALLOW."""
        rep_score = self.reputation.get(self._agent_id)
        verdict = score(action, context, rep_score)

        self.bus.emit(
            self.lane, "score",
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
            cred = self.gate.issue_blocking(
                verdict,
                holder=self._agent_id,
                scope="pay",
                merchant=action.merchant,
                max_amount=action.amount,
            )
            self.bus.emit(
                self.lane, "credential", "Scoped credential issued",
                f"one-time payment credential for {action.merchant} (max ${action.amount:.0f})",
                redacted=_redact(cred.secret),
                credential_id=cred.credential_id,
                merchant=cred.merchant,
                max_amount=cred.max_amount,
                can_delegate=cred.can_delegate,
            )
            self.bus.emit(
                self.lane, "booking", "Booking confirmed",
                f"${action.amount:.0f} at {action.merchant}",
            )
            self.gate.revoke(cred)
            self.bus.emit(
                self.lane, "credential", "Credential revoked",
                "one-time credential discarded after booking",
            )
            outcome = "allow_success"
            result = {"status": "booked", "merchant": action.merchant, "amount": action.amount, "outcome": outcome}
        elif verdict.decision is Decision.REVIEW:
            self.bus.emit(
                self.lane, "blocked", f"Action {verdict.decision.value}",
                f"credential withheld — requires human approval (score {verdict.score})",
                score=verdict.score,
                decision=verdict.decision.value,
            )
            outcome = "block"
            result = {"status": "review", "decision": verdict.decision.value, "score": verdict.score, "outcome": outcome}
        else:
            self.bus.emit(
                self.lane, "blocked", f"Action {verdict.decision.value}",
                f"credential never issued (score {verdict.score})",
                score=verdict.score,
                decision=verdict.decision.value,
            )
            outcome = "block"
            result = {"status": "blocked", "decision": verdict.decision.value, "score": verdict.score, "outcome": outcome}

        new_rep = self.reputation.update(self._agent_id, outcome)
        self.bus.emit(
            self.lane, "reputation",
            f"Reputation updated: {self._agent_id}",
            f"{outcome} → rep={new_rep:.2f}",
            agent_id=self._agent_id,
            reputation=new_rep,
            outcome=outcome,
        )

        return result
