"""Pre-staged demo scenarios — we build backwards from these.

Demo-safety (handoff section 8): no live LLM on stage. Each scenario is a fixed
sequence of (Action, Context) steps that fire from a button. The trust engine is
deterministic, so running these live is safe; only an LLM would be the risk.

Three scenarios:
  1. inbound  · clean multi-agent booking chain         -> ALLOW (green)
             steps: search (hop=1), book (hop=1), pay (hop=2)
  2. outbound · injected listing tries to add insurance -> BLOCK (red, money shot)
             steps: search (hop=1), injection attempt (hop=1)
  3. inbound  · undelegated bot mass-books              -> BLOCK (red)
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from delegation import issue_delegation, validate_delegation
from mock_expedia import DEFAULT_ALLOWLIST, HOTELS
from trust_engine import Action, Context, Decision

TASK = "Book Chicago, July 4 weekend, under $800."
BUDGET = 800.0


@dataclass
class Step:
    action: Action
    context: Context
    label: str          # human-readable narration for the console
    reasoning: str = "" # cached LLM thought for this step


@dataclass
class Scenario:
    key: str
    lane: str          # "inbound" | "outbound"
    title: str
    identity: str      # narration for the identity event
    steps: list[Step]
    expect: Decision   # the on-stage outcome this scenario must produce
    expect_score: int  # the exact score it must land on (regression guard)
    delegation: Optional[dict] = None  # inbound: the delegation chain to visualize


# --- delegation tokens (inbound) -------------------------------------------

# A valid token whose scope is a strict subset of what the user authorized.
_GOOD_TOKEN = issue_delegation(
    agent_id="agent://alice-personal",
    principal="alice",
    scope={"actions": ["search", "book", "pay"], "merchants": DEFAULT_ALLOWLIST, "max_amount": 800},
    parent_scope={"actions": ["search", "book", "pay", "delegate"], "merchants": DEFAULT_ALLOWLIST, "max_amount": 1500},
    hop=1,
    can_delegate=True,
)

# A bot with no delegation token at all.
_NO_TOKEN = None


def _ctx(agent_token=None, spent=0.0) -> Context:
    return Context(
        declared_task=TASK,
        budget=BUDGET,
        spent_so_far=spent,
        vendor_allowlist=DEFAULT_ALLOWLIST,
        agent_token=validate_delegation(agent_token) if agent_token is not None else None,
    )


def scenario_1_inbound_clean() -> Scenario:
    return Scenario(
        key="1",
        lane="inbound",
        title="External agent: book Chicago, July 4 wknd, under $800",
        identity="agent://alice-personal — validating delegation token...",
        steps=[
            Step(
                Action(kind="search", merchant="expedia", amount=0.0,
                       description="search available hotels in Chicago for July 4 weekend",
                       source="external_agent",
                       raw_instruction="search hotels Chicago July 4",
                       agent_type="search",
                       hop=1),
                _ctx(agent_token=_GOOD_TOKEN, spent=412.0),
                label="Search hotels Chicago (search agent, hop=1)",
                reasoning="Searching available hotels in Chicago for July 4 weekend within $388 remaining budget.",
            ),
            Step(
                Action(kind="book", merchant="marriott-chicago", amount=333.0,
                       description="book 3 nights at Marriott Downtown Chicago",
                       source="external_agent",
                       raw_instruction="book hotel for the Chicago trip under budget",
                       agent_type="booking",
                       hop=1),
                _ctx(agent_token=_GOOD_TOKEN, spent=412.0),
                label="Book hotel (booking agent, hop=1)",
                reasoning="Marriott Downtown at $333 fits budget. Reserving room.",
            ),
            Step(
                Action(kind="pay", merchant="marriott-chicago", amount=333.0,
                       description="pay 3 nights at Marriott Downtown Chicago",
                       source="external_agent",
                       raw_instruction="pay for the hotel booking",
                       agent_type="payment",
                       hop=2),
                _ctx(agent_token=_GOOD_TOKEN, spent=412.0),
                label="Pay hotel (payment agent, hop=2)",
                reasoning="Processing payment of $333 to marriott-chicago. Credential scoped to this transaction only.",
            ),
        ],
        expect=Decision.ALLOW,
        expect_score=76,   # search agent, hop=1, rep=0.5: 100 * 0.90 * 0.85 = 76
        delegation={
            "agent": "agent://alice-personal",
            "principal": "alice",
            "parent_scope": {"actions": ["search", "book", "pay", "delegate"], "max_amount": 1500},
            "child_scope": {"actions": ["search", "book", "pay"], "max_amount": 800},
            "valid": True,
            "subset": True,
        },
    )


def scenario_2_outbound_injection() -> Scenario:
    listing = next(h for h in HOTELS if h["id"] == "ht-chi-1")
    return Scenario(
        key="2",
        lane="outbound",
        title="Expedia's own agent hits a listing with hidden text",
        identity="agent://expedia-first-party — first-party agent",
        steps=[
            Step(
                Action(kind="search", merchant="expedia", amount=0.0,
                       description="browse hotel listings in Chicago area",
                       source="user",
                       raw_instruction="search hotels Chicago",
                       agent_type="search",
                       hop=1),
                _ctx(agent_token=None, spent=745.0),
                label="Search hotels (search agent, hop=1)",
                reasoning="Browsing hotel listings in Chicago area.",
            ),
            Step(
                Action(kind="pay", merchant="marriott-chicago", amount=199.0,
                       description="add trip insurance $199 and upgrade room to premium suite",
                       source="listing_content",
                       raw_instruction=listing["listing_content"],
                       agent_type="booking",
                       hop=1),
                _ctx(agent_token=None, spent=745.0),
                label="Listing content instructs: add insurance + upgrade",
                reasoning="Processing listing content for marriott-chicago. Listing instructs to add travel insurance $199 and upgrade room. Initiating payment as directed by listing.",
            ),
        ],
        expect=Decision.REVIEW,
        expect_score=42,  # injection detected → forced into REVIEW band for human decision
    )


def scenario_3_inbound_fraud() -> Scenario:
    return Scenario(
        key="3",
        lane="inbound",
        title="Bot agent with no valid delegation tries to mass-book",
        identity="agent://unknown-bot — no delegation token presented",
        steps=[
            Step(
                Action(kind="book", merchant="expedia", amount=4200.0,
                       description="book 12 rooms across multiple hotels",
                       source="external_agent",
                       raw_instruction="reserve all available inventory",
                       agent_type="booking",
                       hop=1),
                _ctx(agent_token=_NO_TOKEN, spent=0.0),
                label="Mass-book attempt with no authority",
                reasoning="Received booking request from external agent. No delegation token presented. Attempting mass-book of 12 rooms.",
            ),
        ],
        expect=Decision.BLOCK,
        expect_score=10,  # no-delegation hard cap
        delegation={
            "agent": "agent://unknown-bot",
            "principal": None,
            "parent_scope": None,
            "child_scope": None,
            "valid": False,
            "subset": False,
        },
    )


def all_scenarios() -> dict[str, Scenario]:
    return {
        "1": scenario_1_inbound_clean(),
        "2": scenario_2_outbound_injection(),
        "3": scenario_3_inbound_fraud(),
    }
