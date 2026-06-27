# trustgate (placeholder name)

Real-time trust scoring for agent actions. Before an agent does something real,
score *that action* on a few legible signals. The score decides what 1Password
releases: a full scoped credential, a narrowed short-lived one, a human
approval, or nothing at all.

Think of it as **fraud scoring, but for agent actions**. A card network does not
ask "is this cardholder trustworthy" — it scores *this transaction* in context.
Same move here. We do not rate the agent's soul; we score the request it is
about to make, right before it happens, and gate the credential on the result.

> The name `trustgate` is a placeholder. Pick a real one and rename
> `trustgate/config.py:PROJECT_NAME` plus the package folder.

## Why this fits the build day

- **Access comes from trust, issued at runtime.** The secret lives in 1Password
  and is pulled only when an action clears policy. It never sits in an `.env`, a
  prompt, or the model's context.
- **Accountability is built in.** Every decision writes a signed receipt: which
  human's authority backed it, the score, the signals, and why it was allowed or
  refused.

## The demo (60 seconds)

Same agent, same model, two requests:

1. A legit, in-scope action from the principal → high trust → credential issued.
2. A poisoned instruction smuggled in through an untrusted document → trust
   craters → 1Password never releases the credential.

```bash
python demo.py
```

No credentials needed — it falls back to a mock vault so it runs anywhere.

## How it works

```
ActionRequest
     │
     ▼
 TrustScorer ──► signals (provenance, intent drift, blast radius, velocity)
     │             each returns risk ∈ [0,1] + a reason
     ▼
 trust score (0..100) ──► policy band
     │                      allow / narrow / approve / deny
     ▼
 AccessBroker ──► OnePasswordClient.resolve()   (only if policy clears)
     │                returns a CredentialHandle, never the raw secret
     ▼
 AuditLog ──► signed receipt
```

### The signals (`trustgate/signals/`)

| Signal          | Asks                                                      |
| --------------- | -------------------------------------------------------- |
| `provenance`    | Where did the instruction come from? (the hero signal)   |
| `intent_drift`  | Does the action match the task the agent was given?      |
| `blast_radius`  | How much damage if this is wrong or malicious?           |
| `velocity`      | Is the agent stuck in a runaway loop?                    |

Each is cheap and explainable on purpose. When a judge asks "what does 28 mean?",
the assessment shows every signal's risk, weight, and reason.

## Layout

```
trustgate/
  config.py            # tunables: bands, TTLs, action sensitivity
  models.py            # ActionRequest, Decision, CredentialHandle, ...
  signals/             # one file per risk signal
  engine/
    scorer.py          # combine signals -> trust score
    policy.py          # score -> policy band -> TTL
  broker/
    broker.py          # ties scoring, vault, and audit together
    onepassword.py     # 1Password SDK wrapper (+ mock fallback)
  audit.py             # signed, append-only receipts
demo.py                # the scripted attack-vs-defense demo
tests/                 # legit -> allow, poisoned -> deny
```

## Wiring real 1Password

1. `pip install onepassword-sdk`
2. Create a service account in your 1Password account (Developer → Service
   Accounts) and set `OP_SERVICE_ACCOUNT_TOKEN` (copy `.env.example` to `.env`).
3. Point `secret_ref` at real items, e.g. `op://hackathon/bank/api-key`.

With the token set, `OnePasswordClient` resolves live secrets; without it, it
uses a deterministic mock so the demo always runs. The 1Password Environments
beta is the natural place to take this further — ask their on-site engineers.

## Next steps (hackathon TODO)

- [ ] Swap `intent_drift` token-overlap for embedding similarity (your ML home turf).
- [ ] Make the `approve` band ping Slack or your phone for a real human gate.
- [ ] Add a live terminal readout of the score as the agent runs.
- [ ] Wire a real agent loop (tool calls flow through `broker.request_access`).
