"""
TrustLane — Shared dataclasses and enums.

Owned by: shared (used by both execution path and trust-scoring engine).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional


# ---------------------------------------------------------------------------
# Trust-scoring primitives
# ---------------------------------------------------------------------------

class Decision(str, Enum):
    ALLOW = "ALLOW"    # score >= 70
    REVIEW = "REVIEW"  # score 40-69
    BLOCK = "BLOCK"    # score < 40


@dataclass
class Signal:
    """A single named signal that contributed to the trust score."""
    name: str
    value: Any
    weight: float = 0.0
    note: str = ""


@dataclass
class Action:
    """
    Represents a single agent action to be scored.

    kind:
        "search"          — reading listings / flights
        "book"            — submitting a reservation
        "pay"             — initiating a payment
        "delegate"        — handing control to a sub-agent

    source:
        "user"            — action originated from the human user
        "listing_content" — action was inferred from third-party listing text (injection risk)
        "external_agent"  — action came from a delegated / third-party agent
    """
    kind: str                    # "search" | "book" | "pay" | "delegate"
    merchant: str
    amount: float
    description: str
    source: str                  # "user" | "listing_content" | "external_agent"
    raw_instruction: str         # the original instruction string, verbatim


@dataclass
class Context:
    """Runtime context at the moment the action is evaluated."""
    declared_task: str           # e.g. "Book cheapest flight CHI Jul 4-6"
    budget: float
    spent_so_far: float
    vendor_allowlist: list[str]
    agent_token: Optional[str] = None  # delegation token for external agents


@dataclass
class Verdict:
    """Output of trust_engine.score()."""
    score: int                   # 0–100
    decision: Decision
    signals: list[Signal] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Credential gate event
# ---------------------------------------------------------------------------

@dataclass
class CredentialEvent:
    """
    Emitted by CredentialGate.issue() for audit logging and the event bus.

    status:
        "issued"    — credential was resolved and returned (ALLOW path)
        "withheld"  — credential was never resolved (BLOCK / REVIEW path)
    """
    status: str                  # "issued" | "withheld"
    credential: str              # masked value, e.g. "****1234" or "WITHHELD"
    timestamp: str               # ISO-8601
    decision: Decision
    score: int
    reason: str = ""
