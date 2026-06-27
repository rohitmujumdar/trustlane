from __future__ import annotations

import asyncio
import os

try:
    # Official 1Password Python SDK (async). Optional — the demo runs without it.
    #   pip install onepassword-sdk
    from onepassword.client import Client as _OPClient  # type: ignore

    _SDK_AVAILABLE = True
except Exception:  # pragma: no cover - import guard
    _SDK_AVAILABLE = False

from trustgate import config


class OnePasswordClient:
    """Resolves a secret reference to its value at runtime.

    The whole point: the secret is fetched only when an action clears policy,
    used by the broker to perform the protected call, and never returned to the
    agent's context or written to disk.

    Set OP_SERVICE_ACCOUNT_TOKEN (and install onepassword-sdk) to use the real
    vault. Otherwise a mock vault is used so the demo runs with zero credentials.
    """

    def __init__(self) -> None:
        self.token = os.environ.get("OP_SERVICE_ACCOUNT_TOKEN")
        self.live = bool(self.token and _SDK_AVAILABLE)

    def resolve(self, secret_ref: str) -> str:
        if self.live:
            return asyncio.run(self._resolve_live(secret_ref))
        # Mock path: deterministic fake value, never a real secret.
        return f"mock-secret::{secret_ref}"

    async def _resolve_live(self, secret_ref: str) -> str:
        client = await _OPClient.authenticate(
            auth=self.token,
            integration_name=config.PROJECT_NAME,
            integration_version="0.1.0",
        )
        # secret_ref is a 1Password secret reference, e.g.
        #   op://<vault>/<item>/<field>
        return await client.secrets.resolve(secret_ref)
