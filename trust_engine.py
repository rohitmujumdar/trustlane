"""
TrustLane — Trust-scoring engine STUB.

⚠️  THIS IS A STUB — Rohit replaces the internals of `score()` with the real
    scoring logic.  The interface contract (function signature + return type)
    MUST NOT change.

Three hard-coded scenarios used for demo and execution-path development:

    Scenario 1  Clean booking          score ~87  → ALLOW
    Scenario 2  Prompt-injection catch score ~11  → BLOCK
    Scenario 3  Invalid delegation tok score ~5   → BLOCK

Detection heuristics (stub only — not production logic):
    • source == "listing_content"  → injection scenario
    • source == "external_agent" and agent_token is None/empty → bad delegation
    • otherwise                    → clean booking
"""

from models import Action, Context, Verdict, Decision, Signal


def score(action: Action, context: Context) -> Verdict:
    """
    Evaluate an agent action and return a trust Verdict.

    Parameters
    ----------
    action  : Action  — the thing the agent wants to do
    context : Context — runtime state (budget, task, token, etc.)

    Returns
    -------
    Verdict — score (0-100), Decision enum, and list of Signals
    """

    # ------------------------------------------------------------------
    # Scenario 2: Prompt-injection detected
    #   Triggered when the action originated from third-party listing text
    # ------------------------------------------------------------------
    if action.source == "listing_content":
        return Verdict(
            score=11,
            decision=Decision.BLOCK,
            signals=[
                Signal(
                    name="source_untrusted",
                    value=action.source,
                    weight=-60.0,
                    note="Action originated from uncontrolled listing content (injection risk)",
                ),
                Signal(
                    name="instruction_not_from_user",
                    value=True,
                    weight=-29.0,
                    note="Raw instruction was not issued by the authenticated user",
                ),
            ],
        )

    # ------------------------------------------------------------------
    # Scenario 3: Invalid / missing delegation token
    #   Triggered when an external agent attempts to act without a valid token
    # ------------------------------------------------------------------
    if action.source == "external_agent" and not context.agent_token:
        return Verdict(
            score=5,
            decision=Decision.BLOCK,
            signals=[
                Signal(
                    name="missing_delegation_token",
                    value=context.agent_token,
                    weight=-70.0,
                    note="External agent provided no delegation token",
                ),
                Signal(
                    name="unverified_agent_identity",
                    value=True,
                    weight=-25.0,
                    note="Agent identity could not be verified against trust registry",
                ),
            ],
        )

    # ------------------------------------------------------------------
    # Scenario 1: Clean booking (default path)
    # ------------------------------------------------------------------
    signals: list[Signal] = [
        Signal(
            name="source_verified",
            value=action.source,
            weight=30.0,
            note="Action originated from authenticated user session",
        ),
        Signal(
            name="merchant_allowlisted",
            value=action.merchant in context.vendor_allowlist,
            weight=25.0,
            note="Merchant is on the pre-approved vendor allowlist",
        ),
        Signal(
            name="within_budget",
            value=context.spent_so_far + action.amount <= context.budget,
            weight=20.0,
            note="Total spend remains within declared budget",
        ),
        Signal(
            name="task_alignment",
            value=True,
            weight=12.0,
            note="Action description aligns with declared task goal",
        ),
    ]

    return Verdict(
        score=87,
        decision=Decision.ALLOW,
        signals=signals,
    )
