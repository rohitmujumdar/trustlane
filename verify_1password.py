"""Phase 0 check — prove 1Password resolves a real secret through the gate.

  python verify_1password.py

Reads OP_SERVICE_ACCOUNT_TOKEN and TRUSTLANE_SECRET_REF from your environment or
.env, then asks the credential gate to issue on a synthetic ALLOW verdict. On
success a real secret comes back — its value is never printed. This is the
handoff's Phase 0 goal made checkable: gate.issue() returning a value end to end.

Run this BEFORE wiring the demo to the live vault. Green here means the whole
weave is real; the secret stops being a mock string and starts being withheld
for real on BLOCK.
"""
from __future__ import annotations

import os

import credential_gate
from credential_gate import CredentialGate
from dotenv_lite import load_env
from trust_engine import Decision, Verdict

GREEN, RED, DIM, RESET = "\033[32m", "\033[31m", "\033[2m", "\033[0m"
DEFAULT_REF = "op://TrustLane/ExpediaPayment/credential"


def main() -> int:
    load_env()
    token = os.environ.get("OP_SERVICE_ACCOUNT_TOKEN")
    ref = os.environ.get("TRUSTLANE_SECRET_REF", DEFAULT_REF)
    sdk = credential_gate._SDK_AVAILABLE

    print("TrustLane · 1Password Phase 0 check")
    print("-" * 60)
    print(f"  SDK installed (onepassword-sdk): {'yes' if sdk else 'NO'}")
    print(f"  service account token present:   {'yes' if token else 'NO'}")
    print(f"  secret reference:                {ref}")
    print("-" * 60)

    if not sdk:
        print(f"{RED}FAIL{RESET} onepassword-sdk not installed.")
        print(f"{DIM}  -> pip install onepassword-sdk{RESET}")
        return 1
    if not token:
        print(f"{RED}FAIL{RESET} OP_SERVICE_ACCOUNT_TOKEN not set.")
        print(f"{DIM}  -> add it to .env, then re-run. See SETUP_1PASSWORD.md{RESET}")
        return 1

    gate = CredentialGate(secret_ref=ref)
    allow = Verdict(score=100, decision=Decision.ALLOW, signals=[])
    try:
        secret = gate.issue_blocking(allow)
    except Exception as e:
        print(f"{RED}FAIL{RESET} gate could not resolve the secret: {type(e).__name__}: {e}")
        print(f"{DIM}  check: the vault/item/field in the reference exist, and the service{RESET}")
        print(f"{DIM}  account has read access to that vault. Confirm the SDK call/version{RESET}")
        print(f"{DIM}  with the on-site 1Password engineers if it still fails.{RESET}")
        return 1

    if secret.startswith("mock-scoped-credential::"):
        print(f"{RED}FAIL{RESET} gate returned the MOCK secret — the live path is not active.")
        print(f"{DIM}  the token or SDK isn't being picked up; re-check .env and the install.{RESET}")
        return 1

    print(f"{GREEN}PASS{RESET} resolved a real secret through the gate "
          f"({len(secret)} chars, value hidden).")
    print(f"{GREEN}Phase 0 complete{RESET} — demo.py will now show 'LIVE vault' and the")
    print("gate resolves for real on ALLOW, withholds for real on BLOCK.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
