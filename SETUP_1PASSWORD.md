# Wiring the real 1Password vault (Phase 0)

Goal: make `gate.issue()` resolve a **real** secret on ALLOW, so the pitch stops
being a mock and the demo's "secret never enters context" claim is backed by an
actual vault. The handoff calls this Phase 0 — do it first, with the on-site
1Password engineers (Jody Heavener / the Environments team) if anything fights you.

You should be able to finish this in ~10 minutes. When `python verify_1password.py`
prints **PASS**, you're done.

## 1. Create the vault and the secret

In your 1Password account:

1. Create a vault named **`TrustLane`**.
2. In it, create an item named **`ExpediaPayment`** (type: API Credential or
   Password is fine).
3. Put the payment secret in a field named **`credential`** (a Stripe test key or
   any test token — this is what the gate resolves on ALLOW).

That maps to the secret reference the gate uses:

```
op://TrustLane/ExpediaPayment/credential
```

If you name things differently, set `TRUSTLANE_SECRET_REF` in `.env` to match.

## 2. Create a Service Account token

1. In 1Password: **Developer → Service Accounts → New Service Account**.
2. Give it **read-only** access to the **`TrustLane`** vault and nothing else.
   (Least privilege: the demo only ever needs to read one secret.)
3. Copy the token. You only see it once.

## 3. Install the SDK and fill in `.env`

```bash
pip install onepassword-sdk
cp .env.example .env
```

Then edit `.env`:

```
OP_SERVICE_ACCOUNT_TOKEN=<paste the service account token>
TRUSTLANE_SECRET_REF=op://TrustLane/ExpediaPayment/credential
```

`.env` is gitignored, so the token never gets committed.

## 4. Verify

```bash
python verify_1password.py
```

Expected:

```
PASS resolved a real secret through the gate (NN chars, value hidden).
Phase 0 complete — demo.py will now show 'LIVE vault' ...
```

If it fails, the script tells you which step is missing (SDK not installed, token
not set, vault/item/field names wrong, or the service account can't read the
vault).

## 5. Run the demo live

```bash
python demo.py
```

The header now reads `1Password gate: LIVE vault`, and on Scenario 1 the gate
resolves the real secret. On Scenarios 2 and 3 it is never resolved — that is the
whole point, now backed by a real vault instead of a mock string.

## Notes

- The SDK is async: `Client.authenticate(auth=token, integration_name=...,
  integration_version=...)` then `client.secrets.resolve("op://...")`. Pin the
  exact version and method names with the on-site team — APIs move.
- Alternative path: `op run --environment` (the Environments beta) injects secrets
  at runtime instead of an SDK resolve. Ask the Environments folks if you'd rather
  demo that surface.
- Never print the resolved secret. The gate returns it for the booking call and
  discards it; `verify_1password.py` only ever prints its length.
