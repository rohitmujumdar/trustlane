"""Delegation / identity for inbound external agents.

When someone's personal agent shows up to book, it must carry a signed delegation
token proving (a) the signature is valid and (b) its scope is a subset of what the
parent (the user) actually authorized. The trust engine's identity_validity signal
reads the normalized {valid, scope_is_subset} flags this module produces.

Tokens carry a `hop` count (delegation depth) and a `can_delegate` flag. If
`can_delegate` is False, a token cannot be used to issue child tokens.

Owner: Rohit (the trust path). P2: layer reputation/anomaly on top of this.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
from typing import Optional

# Shared secret the user's wallet/issuer signs delegation tokens with. In a real
# system this is asymmetric (issuer private key); HMAC is the demo stand-in.
DELEGATION_KEY = os.environ.get("TRUSTLANE_DELEGATION_KEY", "dev-delegation-key").encode()


def _sign(payload: dict) -> str:
    body = json.dumps(payload, sort_keys=True).encode()
    return hmac.new(DELEGATION_KEY, body, hashlib.sha256).hexdigest()


def issue_delegation(
    agent_id: str,
    principal: str,
    scope: dict,
    parent_scope: dict,
    key: bytes = DELEGATION_KEY,
    hop: int = 1,
    can_delegate: bool = True,
    parent_token: Optional[dict] = None,
) -> dict:
    """Mint a signed delegation token. `scope` is what this agent may do;
    `parent_scope` is what the principal authorized it to draw from.

    `hop` tracks delegation depth (1 = direct from user, 2 = sub-delegation, etc.).
    If `parent_token` is provided, hop is auto-incremented from the parent.
    `can_delegate` controls whether this token can issue child tokens.
    """
    # Auto-increment hop from parent token if provided
    if parent_token is not None:
        parent_hop = parent_token.get("hop", 1)
        # Respect can_delegate flag on parent
        if not parent_token.get("can_delegate", True):
            raise PermissionError("Parent token has can_delegate=False; cannot issue child token")
        hop = parent_hop + 1

    payload = {
        "agent_id": agent_id,
        "principal": principal,
        "scope": scope,
        "parent_scope": parent_scope,
        "hop": hop,
        "can_delegate": can_delegate,
    }
    body = json.dumps(payload, sort_keys=True).encode()
    payload["signature"] = hmac.new(key, body, hashlib.sha256).hexdigest()
    return payload


def _scope_is_subset(scope: dict, parent: dict) -> bool:
    """Every capability the child claims must be allowed by the parent."""
    actions_ok = set(scope.get("actions", [])) <= set(parent.get("actions", []))
    merchants_ok = set(scope.get("merchants", [])) <= set(parent.get("merchants", []))
    amount_ok = scope.get("max_amount", 0) <= parent.get("max_amount", 0)
    return actions_ok and merchants_ok and amount_ok


def validate_delegation(token: Optional[dict], key: bytes = DELEGATION_KEY) -> dict:
    """Verify signature + scope subset. Returns the {valid, scope_is_subset, hop}
    shape the trust engine's Context.agent_token expects.

    A missing token, a tampered signature, or a scope that exceeds the parent's
    all collapse to valid=False, so an undelegated bot can never pass.
    """
    if not token:
        return {"valid": False, "scope_is_subset": False, "reason": "no token", "hop": 0}

    claimed_sig = token.get("signature", "")
    payload = {k: token[k] for k in ("agent_id", "principal", "scope", "parent_scope", "hop", "can_delegate") if k in token}
    expected_sig = _sign(payload)
    sig_ok = hmac.compare_digest(claimed_sig, expected_sig)
    if not sig_ok:
        return {"valid": False, "scope_is_subset": False, "reason": "bad signature", "hop": 0}

    subset_ok = _scope_is_subset(token.get("scope", {}), token.get("parent_scope", {}))
    return {
        "valid": True,
        "scope_is_subset": subset_ok,
        "agent_id": token.get("agent_id"),
        "principal": token.get("principal"),
        "scope": token.get("scope"),
        "hop": token.get("hop", 1),
        "can_delegate": token.get("can_delegate", True),
        "reason": "ok" if subset_ok else "scope exceeds parent",
    }
