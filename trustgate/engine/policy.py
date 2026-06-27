from __future__ import annotations

from trustgate import config
from trustgate.models import Policy

# Credential TTL per policy band, resolved from config into the Policy enum.
TTL = {Policy(name): seconds for name, seconds in config.TTL.items()}


def policy_for(score: int) -> Policy:
    """Map a 0..100 trust score to a policy band (highest threshold wins)."""
    for threshold, name in config.BANDS:
        if score >= threshold:
            return Policy(name)
    return Policy.DENY


def band_for(score: int) -> str:
    return policy_for(score).value
