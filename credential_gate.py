"""1Password credential gate — the weave.

The payment secret lives in a 1Password vault. We only call resolve() — the one
line that pulls the secret into memory — when the verdict is ALLOW. On
BLOCK/REVIEW the secret is never touched, never enters the agent's context.
That is "the credential never gets issued," literally.

Owner: Swati (the execution path). Confirm exact SDK call + version on-site with
the 1Password Environments team.
"""
from __future__ import annotations

import asyncio
import os

try:
    # pip install onepassword-sdk  (async client)
    from onepassword.client import Client as _OPClient  # type: ignore

    _SDK_AVAILABLE = True
except Exception:  # pragma: no cover - optional dependency
    _SDK_AVAILABLE = False

from trust_engine import Decision, Verdict


class CredentialGate:
    """Resolves a one-time, task-scoped payment secret only on ALLOW.

    Set OP_SERVICE_ACCOUNT_TOKEN (and install onepassword-sdk) to use the real
    vault. Otherwise a mock secret is returned so the demo runs with no creds.
    The mock still honors the gate: BLOCK/REVIEW never produce a secret.
    """

    def __init__(
        self,
        op_service_account_token: str | None = None,
        secret_ref: str = "op://TrustLane/ExpediaPayment/credential",
    ) -> None:
        self._token = op_service_account_token or os.environ.get("OP_SERVICE_ACCOUNT_TOKEN")
        self._ref = secret_ref
        self._client = None
        self.live = bool(self._token and _SDK_AVAILABLE)

    async def _get_client(self):
        if self._client is None:
            self._client = await _OPClient.authenticate(
                auth=self._token,
                integration_name="TrustLane",
                integration_version="0.1.0",
            )
        return self._client

    async def issue(self, verdict: Verdict) -> str:
        """Resolve the scoped payment secret ONLY if approved.

        On block/review the secret is never pulled into context.
        """
        if verdict.decision is not Decision.ALLOW:
            raise PermissionError(
                f"Credential withheld — decision={verdict.decision.value}, "
                f"score={verdict.score}"
            )
        if self.live:
            client = await self._get_client()
            return await client.secrets.resolve(self._ref)  # <- the only resolve()
        # Mock path: a fake one-time token, never a real secret.
        return f"mock-scoped-credential::{self._ref}"

    def issue_blocking(self, verdict: Verdict) -> str:
        """Sync wrapper for the deterministic demo runner and the stdlib server."""
        if verdict.decision is not Decision.ALLOW:
            raise PermissionError(
                f"Credential withheld — decision={verdict.decision.value}, "
                f"score={verdict.score}"
            )
        if self.live:
            return asyncio.run(self.issue(verdict))
        return f"mock-scoped-credential::{self._ref}"
