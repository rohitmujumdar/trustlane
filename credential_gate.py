"""
TrustLane — 1Password Credential Gate.

Async class that issues (or withholds) payment credentials based on the
trust Verdict produced by trust_engine.score().

Rules:
    ALLOW  (score >= 70) → resolve credential from 1Password, return it
    REVIEW (score 40-69) → raise PermissionError, credential never touched
    BLOCK  (score <  40) → raise PermissionError, credential never touched

Environment variables:
    OP_SERVICE_ACCOUNT_TOKEN   — 1Password service account token (required in prod)
    MOCK_OP=1                  — skip 1Password entirely; return a fake token
                                 so the end-to-end demo works without 1Password

Usage:
    gate = CredentialGate()
    event = await gate.issue(verdict)   # returns CredentialEvent dict
"""

from __future__ import annotations

import os
from datetime import datetime, timezone

from models import Verdict, Decision, CredentialEvent

# 1Password vault reference for the Expedia payment credential
_OP_REFERENCE = "op://TrustLane/ExpediaPayment/credential"

# Fake credential returned when MOCK_OP=1
_MOCK_CREDENTIAL = "mock-expedia-tok-****9999"
_MOCK_CREDENTIAL_MASKED = "****9999"


class CredentialGate:
    """
    Async credential gate backed by 1Password.

    Instantiate once and call `await gate.issue(verdict)` for each action.
    """

    def __init__(self) -> None:
        self._mock_mode = os.environ.get("MOCK_OP", "").strip() == "1"
        self._service_account_token = os.environ.get("OP_SERVICE_ACCOUNT_TOKEN", "")

        if not self._mock_mode and not self._service_account_token:
            raise EnvironmentError(
                "Set OP_SERVICE_ACCOUNT_TOKEN or MOCK_OP=1 before using CredentialGate."
            )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def issue(self, verdict: Verdict) -> dict:
        """
        Issue or withhold the Expedia payment credential.

        Parameters
        ----------
        verdict : Verdict — output of trust_engine.score()

        Returns
        -------
        dict representation of CredentialEvent

        Raises
        ------
        PermissionError  if verdict.decision is BLOCK or REVIEW
        """
        now = datetime.now(timezone.utc).isoformat()

        if verdict.decision != Decision.ALLOW:
            # Never resolve the secret — raise immediately
            event = CredentialEvent(
                status="withheld",
                credential="WITHHELD",
                timestamp=now,
                decision=verdict.decision,
                score=verdict.score,
                reason=(
                    f"Credential withheld: decision={verdict.decision.value}, "
                    f"score={verdict.score}"
                ),
            )
            raise PermissionError(
                f"TrustLane: credential withheld. "
                f"decision={verdict.decision.value} score={verdict.score}. "
                f"event={vars(event)}"
            )

        # ALLOW path — resolve credential
        raw_credential = await self._resolve_credential()
        masked = self._mask(raw_credential)

        event = CredentialEvent(
            status="issued",
            credential=masked,
            timestamp=now,
            decision=verdict.decision,
            score=verdict.score,
            reason="Credential issued after trust verification (ALLOW)",
        )
        return vars(event)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _resolve_credential(self) -> str:
        """Resolve the secret from 1Password (or return mock value)."""

        if self._mock_mode:
            # Return fake token — no 1Password call made
            return _MOCK_CREDENTIAL

        # TODO (on-site): confirm exact SDK method names against installed
        #   onepassword SDK version.  The pattern below targets the official
        #   1Password Python SDK (pip install onepassword-sdk).
        #   If using the Connect SDK (onepasswordconnectsdk), use:
        #       from onepasswordconnectsdk.client import new_client
        #       client = new_client(url=OP_CONNECT_URL, token=OP_ACCESS_TOKEN)
        #       item = client.get_item(item_id, vault_id)
        try:
            import onepassword  # type: ignore
            # TODO (on-site): verify Client constructor signature
            client = await onepassword.Client.authenticate(
                auth=self._service_account_token,
                integration_name="TrustLane",
                integration_version="1.0.0",
            )
            # TODO (on-site): confirm secrets.resolve() is the right method;
            #   may be client.secrets.resolve() or client.resolve_secret()
            credential: str = await client.secrets.resolve(_OP_REFERENCE)
            return credential
        except ImportError as exc:
            raise RuntimeError(
                "1Password SDK not installed. "
                "Run `pip install onepassword-sdk` or set MOCK_OP=1 for demo mode."
            ) from exc

    @staticmethod
    def _mask(credential: str) -> str:
        """Return a masked version of the credential for logs/events."""
        if len(credential) <= 4:
            return "****"
        return "****" + credential[-4:]
