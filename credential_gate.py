"""1Password credential gate — the weave.

The payment secret lives in a 1Password vault. We only call resolve() — the one
line that pulls the secret into memory — when the verdict is ALLOW. On
BLOCK/REVIEW the secret is never touched, never enters the agent's context.
That is "the credential never gets issued," literally.

Credentials are now scoped: locked to one merchant, capped at an exact amount,
and expire after a short TTL. They cannot be delegated further (can_delegate=False).

Owner: Swati (the execution path). Confirm exact SDK call + version on-site with
the 1Password Environments team.
"""
from __future__ import annotations

import asyncio
import os
import time
import uuid
from dataclasses import dataclass, field

try:
    # pip install onepassword-sdk  (async client)
    from onepassword.client import Client as _OPClient  # type: ignore

    _SDK_AVAILABLE = True
except Exception:  # pragma: no cover - optional dependency
    _SDK_AVAILABLE = False

from trust_engine import Decision, Verdict

MOCK_OP = os.environ.get("MOCK_OP", "0") == "1"


@dataclass
class ScopedCredential:
    credential_id: str          # unique ID
    holder: str                 # agent instance ID
    scope: str                  # "reserve" | "pay"
    merchant: str               # locked to one merchant
    max_amount: float           # exact amount
    ttl_seconds: int            # 30-60 seconds
    can_delegate: bool          # always False
    issued_at: float            # timestamp
    secret: str                 # the actual credential (masked in events)
    revoked: bool = False


class CredentialGate:
    """Resolves a one-time, task-scoped payment secret only on ALLOW.

    Set OP_SERVICE_ACCOUNT_TOKEN (and install onepassword-sdk) to use the real
    vault. Otherwise a mock secret is returned so the demo runs with no creds.
    The mock still honors the gate: BLOCK/REVIEW never produce a secret.

    Issued credentials are scoped: merchant-locked, amount-capped, short-TTL,
    and cannot be delegated (can_delegate=False).
    """

    def __init__(
        self,
        op_service_account_token: str | None = None,
        secret_ref: str = "op://TrustLane/ExpediaPayment/credential",
    ) -> None:
        self._token = op_service_account_token or os.environ.get("OP_SERVICE_ACCOUNT_TOKEN")
        self._ref = secret_ref
        self._client = None
        self.live = bool(self._token and _SDK_AVAILABLE and not MOCK_OP)

    async def _get_client(self):
        if self._client is None:
            # TODO(Swati): confirm exact SDK version + auth call with 1Password Environments team
            self._client = await _OPClient.authenticate(
                auth=self._token,
                integration_name="TrustLane",
                integration_version="0.1.0",
            )
        return self._client

    async def _resolve_secret(self) -> str:
        if self.live:
            client = await self._get_client()
            return await client.secrets.resolve(self._ref)  # <- the only resolve()
        # Mock path: a fake one-time token, never a real secret.
        return f"mock-scoped-credential::{self._ref}"

    async def issue(
        self,
        verdict: Verdict,
        holder: str = "agent",
        scope: str = "pay",
        merchant: str = "unknown",
        max_amount: float = 0.0,
        ttl: int = 30,
    ) -> ScopedCredential:
        """Issue a scoped credential ONLY on ALLOW.

        On BLOCK/REVIEW the secret is never pulled into context.
        The credential is locked to one merchant, capped at max_amount,
        and expires after ttl seconds. can_delegate is always False.
        """
        if verdict.decision is not Decision.ALLOW:
            raise PermissionError(
                f"Credential withheld — decision={verdict.decision.value}, "
                f"score={verdict.score}"
            )
        secret = await self._resolve_secret()
        return ScopedCredential(
            credential_id=str(uuid.uuid4()),
            holder=holder,
            scope=scope,
            merchant=merchant,
            max_amount=max_amount,
            ttl_seconds=ttl,
            can_delegate=False,
            issued_at=time.time(),
            secret=secret,
            revoked=False,
        )

    def issue_blocking(
        self,
        verdict: Verdict,
        holder: str = "agent",
        scope: str = "pay",
        merchant: str = "unknown",
        max_amount: float = 0.0,
        ttl: int = 30,
    ) -> ScopedCredential:
        """Sync wrapper for the deterministic demo runner and the stdlib server."""
        if verdict.decision is not Decision.ALLOW:
            raise PermissionError(
                f"Credential withheld — decision={verdict.decision.value}, "
                f"score={verdict.score}"
            )
        secret = (
            asyncio.run(self._resolve_secret()) if self.live
            else f"mock-scoped-credential::{self._ref}"
        )
        return ScopedCredential(
            credential_id=str(uuid.uuid4()),
            holder=holder,
            scope=scope,
            merchant=merchant,
            max_amount=max_amount,
            ttl_seconds=ttl,
            can_delegate=False,
            issued_at=time.time(),
            secret=secret,
            revoked=False,
        )

    def revoke(self, credential: ScopedCredential) -> None:
        """Mark credential as revoked."""
        credential.revoked = True
