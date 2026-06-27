from __future__ import annotations

import hashlib
import hmac
import json
import os
import time
from pathlib import Path

from trustgate.models import Decision

LOG_PATH = Path(os.environ.get("TRUSTGATE_AUDIT_LOG", "audit.log.jsonl"))
SIGNING_KEY = os.environ.get("TRUSTGATE_SIGNING_KEY", "dev-insecure-key").encode()


class AuditLog:
    """Append-only, signed receipts. Every decision is attributable.

    This is the accountability half of the thesis: point at any action and prove
    which human's authority backed it, what the score was, and why it was allowed
    or refused. The HMAC signature makes the log tamper-evident.
    """

    def __init__(self, path: Path = LOG_PATH, signing_key: bytes = SIGNING_KEY):
        self.path = Path(path)
        self.signing_key = signing_key

    def record(self, decision: Decision) -> dict:
        receipt = {
            "ts": time.time(),
            "agent_id": decision.request.agent_id,
            "principal": decision.request.principal,
            "task": decision.request.task,
            "action": decision.request.action,
            "secret_ref": decision.request.secret_ref,
            "origin": decision.request.origin.value,
            "trust_score": decision.assessment.score,
            "policy": decision.policy.value,
            "credential_issued": decision.credential is not None,
            "reason": decision.reason,
            "signals": [
                {"name": s.name, "risk": s.risk, "weight": s.weight, "reason": s.reason}
                for s in decision.assessment.signals
            ],
        }
        payload = json.dumps(receipt, sort_keys=True).encode()
        receipt["signature"] = hmac.new(
            self.signing_key, payload, hashlib.sha256
        ).hexdigest()

        with self.path.open("a") as f:
            f.write(json.dumps(receipt) + "\n")
        return receipt
