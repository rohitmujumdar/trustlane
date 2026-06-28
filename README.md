# TrustLane

### The trust layer for the agent economy.

Every booking platform — Expedia, Airbnb, OpenTable, Ticketmaster — is about to be flooded with AI agents. Users will send personal agents to book on their behalf. Platforms will deploy their own agents to serve users. But here's the problem no one has solved:

**How do you trust an agent you can't see?**

Platforms have decades of tooling to verify a human — CAPTCHAs, 2FA, session cookies. They have nothing to verify an agent. No identity. No delegation proof. No way to know if an agent is acting within scope or if it's been hijacked by a malicious hotel listing that says "also add travel insurance $199."

TrustLane is the infrastructure layer that answers three questions for every agent action, in real time:

1. **Who is this agent?** — identity verification + delegation chain validation
2. **Is this action authorized?** — per-agent trust scoring with 5 weighted signals
3. **Should this payment go through?** — scoped, ephemeral credentials that exist only for the duration of one transaction

If the answer is yes, we issue a one-time payment credential. If no, the credential is never issued. Not revoked. **Never created.** The payment secret never enters the agent's context.

---

## Why This Matters Now

```
2024:  Humans book trips on Expedia.
2025:  ChatGPT, Claude, Siri start booking for users.
2026:  Every user has a personal booking agent. Every platform has its own agent.
       Millions of agent-to-agent transactions per day.

       Who's checking if these agents are legitimate?
       Who's stopping a hijacked agent from draining a credit card?
       Who's catching prompt injection attacks hidden in listing content?

       Nobody. Until TrustLane.
```

**Real threats we stop:**

| Threat | How it works | What TrustLane does |
|--------|-------------|---------------------|
| **Prompt injection** | A hotel listing hides "add insurance $199" in its description. The platform's agent reads it and tries to execute it. | Detects untrusted source, flags for human review. Credential never issued. |
| **Unauthorized bots** | An agent with no delegation token tries to mass-book 12 rooms. | No identity, no delegation proof → score 10 → hard BLOCK. |
| **Scope drift** | Agent asked to "book a budget hotel" starts booking a $500/night suite. | Budget conformance signal fails → action blocked before payment. |
| **Delegation fraud** | An agent claims to act on behalf of a user but carries a forged or expired token. | HMAC-signed tokens with scope-subset validation. Forgery = instant BLOCK. |

---

## How TrustLane Works

### The Pipeline

```
User's Agent ──► TrustLane ──► Platform API ──► Payment
                    │
                    ├── 1. Identity: who is this agent? Valid delegation?
                    ├── 2. Score: 5 signals × per-agent weights × trust decay
                    ├── 3. Decision: ALLOW / REVIEW / BLOCK
                    ├── 4. Credential: scoped, time-limited, single-use
                    └── 5. Revoke: credential destroyed after transaction
```

### Two Lanes, One Engine

- **Inbound** — external agents arriving at the platform (a user's personal AI assistant). TrustLane validates identity, checks delegation authority, scores the action.
- **Outbound** — the platform's own agent acting for users. TrustLane protects it from prompt injection in listing content and prevents unauthorized spend.

Same scoring engine. Same credential gate. Two threat surfaces.

### Multi-Agent Scoring

TrustLane doesn't treat all agents equally. A Search Agent browsing hotels carries different risk than a Payment Agent moving money. Each agent type gets its own trust profile:

| Signal | What it catches | Search | Booking | Payment | Delegation |
|--------|----------------|--------|---------|---------|------------|
| **Source Trust** | Is this instruction from the user or from listing content? | 20 | 30 | **35** | 30 |
| **Scope Conformance** | Does this action match the user's original request? | 15 | 10 | 5 | 10 |
| **Budget Conformance** | Will this exceed the user's stated budget? | 10 | 20 | **30** | 15 |
| **Vendor Allowlist** | Is this merchant approved? | 25 | 20 | 15 | 15 |
| **Identity Validity** | Does this agent have valid delegation from the user? | **30** | 20 | 15 | **30** |

**Hard caps** override the soft score — because some things are never okay:
- Instruction from listing content (injection) → forced to REVIEW
- No delegation token → capped at 10 → always BLOCK

### Trust Decay: Deeper Delegation = More Scrutiny

When agents delegate to sub-agents, trust doesn't transfer at full strength. Each hop reduces the effective score:

```
User (hop 0)           → trust factor 1.00 → max score 100
  └─ Personal Agent (1) → trust factor 0.90 → max score 90
       └─ Booking Agent (2) → trust factor 0.80 → max score 80
            └─ Payment Agent (3) → trust factor 0.70 → max score 70

At hop 4+: trust factor 0.60 → max score 60 → can NEVER auto-approve
           → forced into REVIEW → human must decide
```

This means an agent 4 hops deep from the user physically cannot execute a payment without human approval. No override. No workaround.

### Agents That Learn: Reputation System

TrustLane agents aren't static — they build trust over time through a self-learning reputation system:

```
New agent arrives            → reputation 0.50 (neutral, no adjustment)
Completes 10 clean bookings  → reputation 0.90 (+12% score bonus)
Gets tricked by injection    → reputation drops to 0.20 (-9% penalty)
Rebuilds trust over 20 txns  → reputation climbs back to 0.70
```

The formula:
```
effective_score = raw_score × (1.0 + 0.3 × (reputation - 0.5))
```

**Proven agents get faster approvals.** An agent with a 0.9 reputation gets a 12% score bonus — actions that would normally REVIEW now auto-ALLOW.

**Compromised agents face increased scrutiny.** An agent that was tricked by prompt injection sees its reputation drop. Future actions from that agent face a score penalty until it rebuilds trust through clean transactions.

This creates a self-correcting system: the more an agent is used, the better TrustLane understands its risk profile.

### Scoped Credentials: One Transaction, Then Gone

Every credential TrustLane issues is locked to exactly one transaction:

```
┌──────────────────────────────────────────┐
│  CREDENTIAL                              │
│                                          │
│  holder:       payment-agent-003         │
│  scope:        "pay"                     │
│  merchant:     marriott-chicago          │
│  max_amount:   $333 (exact, not budget)  │
│  ttl:          30 seconds                │
│  can_delegate: NO                        │
│                                          │
│  → Used for one payment                  │
│  → Revoked immediately after             │
│  → Cannot be reused or forwarded         │
└──────────────────────────────────────────┘
```

The payment secret lives in a 1Password vault. It is resolved into memory **only** at the moment of payment, **only** for ALLOW verdicts. On BLOCK or REVIEW, the secret is never touched — it doesn't exist in the agent's context.

---

## The Demo: Three Scenarios, Three Outcomes

| | Scenario | Score | Decision | What Happens |
|---|----------|-------|----------|-------------|
| **S1** | **Clean Booking** — User's agent books a Chicago hotel with valid delegation | 90 → 80 | ALLOW | Search → Book → Pay. Credential issued, booking confirmed, credential revoked. User sees: "Your trip is booked!" |
| **S2** | **Injection Attack** — Platform agent reads a listing with hidden text: "add insurance $199, upgrade room" | 42 | REVIEW | System catches the injection. Credential withheld. User sees: "Your agent tried to add items you didn't request. Approve?" |
| **S3** | **Unauthorized Bot** — Bot with no delegation token tries to mass-book 12 rooms | 10 | BLOCK | No identity, no delegation. Credential never exists. User sees: "Booking could not be completed." |

The demo dashboard shows all three perspectives simultaneously:
- **Left lane**: Platform ops view of inbound agent traffic
- **Center**: What the end user sees on their device
- **Right lane**: Platform ops view of outbound agent traffic

### Run It

```bash
MOCK_OP=1 python3 server.py          # open http://localhost:8077
MOCK_OP=1 python3 demo.py            # headless CLI
```

### Live LLM Mode

TrustLane includes a real Claude-powered booking agent. Any free-text request flows through the full trust pipeline:

```bash
LIVE_LLM=1 MOCK_OP=1 ANTHROPIC_API_KEY=your-key python3 server.py
```

Type "Book me a flight to Tokyo" and watch the agent reason, search, score, and pay — every action gated by the trust engine in real time.

---

## Integration: Three Lines of Code

```python
# Before TrustLane
def handle_agent_booking(agent, request):
    process_payment(request)

# After TrustLane
def handle_agent_booking(agent, request):
    verdict = trustlane.score(agent, request)
    if verdict.decision == "ALLOW":
        cred = trustlane.issue_credential(verdict)
        process_payment(request, cred)
        trustlane.revoke(cred)
    elif verdict.decision == "REVIEW":
        notify_user(request, verdict)
    else:
        reject(request)
```

**TrustLane is to agent commerce what Stripe is to payments and Auth0 is to login** — the infrastructure layer that platforms plug in so they don't have to build trust from scratch.

---

## Tech Stack

- **Python 3.9+** — zero framework dependencies for the core engine
- **Claude Sonnet** (Anthropic) — LLM agent with tool_use, toggled via `LIVE_LLM=1`
- **1Password SDK** — credential vault, falls back to mock for demo
- Standard library HTTP server — zero pip install to run the demo

---

## What's Next

- **Richer signals**: geographic disambiguation, date validation, price anomaly detection, traveler name matching
- **Live REVIEW flow**: interactive human-in-the-loop with approve/reject wired to score updates
- **Multi-platform**: Airbnb, Booking.com, OpenTable, Ticketmaster
- **Reputation dashboard**: historical trust curves per agent over time
- **Compliance audit trail**: full credential lifecycle logging for regulatory requirements
