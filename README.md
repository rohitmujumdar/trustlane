# TrustLane

**Agent identity and fraud infrastructure for booking platforms.**

Every booking platform is about to be flooded with AI agents — personal assistants booking on behalf of users, and the platform's own agents acting for users. These platforms have decades of tooling to verify a *human*. They have nothing to verify an *agent*.

TrustLane is the missing layer. One API call before every agent action: is this agent who it claims to be? Is it carrying real delegated authority? Is this specific action in-scope and safe? If yes, we issue a one-time, scoped payment credential. If no, the credential is never issued — the action physically cannot execute.

**The credential doesn't get revoked. It never exists.**

---

## The Problem

```
Today:    Agent  ───────────────────────────►  Platform API  ──►  Payment
          (no identity, no checks, no limits)

Tomorrow: Millions of agents hitting every booking platform.
          - Whose authority does this agent carry?
          - Is it acting within scope, or was it hijacked by a malicious listing?
          - How do you issue a payment credential to an agent you can't verify?
```

Real attacks happening now:
- **Prompt injection**: A hotel listing contains hidden text ("add travel insurance $199"). The platform's own agent reads it and tries to execute it.
- **Unauthorized bots**: Agents with no delegation token mass-booking inventory.
- **Scope drift**: An agent asked to "book a budget hotel" books a $500/night suite instead.

No platform has infrastructure to handle this. TrustLane is that infrastructure.

---

## The Solution

TrustLane is middleware that sits between agents and platform APIs:

```
                        ┌──────────────────────────────────────────────┐
                        │               TRUSTLANE                      │
                        │                                              │
User's Agent ──INBOUND──┤  1. Validate agent identity + delegation     │──► Platform API
                        │  2. Score the action (5 signals + hard caps) │
                        │  3. Decision: ALLOW / REVIEW / BLOCK         │
Platform's   ──OUTBOUND─┤  4. ALLOW → issue scoped credential         │──► Payment
Own Agent               │     REVIEW → human approves/rejects          │
                        │     BLOCK → credential never exists          │
                        │  5. Credential auto-revokes after use        │
                        └──────────────────────────────────────────────┘
```

**Two lanes, one engine:**
- **Inbound** — external agents arriving at the platform. Verify identity + delegated authority before they can transact.
- **Outbound** — the platform's own agent acting for users. Protect it from prompt injection in listing content.

---

## How It Works

### Multi-Agent Architecture

Six agents, each with a specific role and its own trust profile:

```
┌─────────────────────────────────────────────────────┐
│                  ORCHESTRATOR                        │
│                  Routes tasks to sub-agents          │
├──────────┬───────────────┬──────────────────────────┤
│          ▼               ▼               ▼          │
│   SEARCH AGENT    BOOKING AGENT    PAYMENT AGENT    │
│   Browses         Reserves          Executes         │
│   inventory       listings          payment          │
│   (read-only)     (needs cred)      (needs cred)    │
│                                                      │
│   DELEGATION AGENT — validates + issues sub-tokens   │
├──────────────────────────────────────────────────────┤
│                  TRUST ARBITER                       │
│   Scores EVERY action from EVERY agent               │
│   Per-agent weight profiles                          │
│   Makes the FINAL decision: ALLOW / REVIEW / BLOCK   │
│   No agent can override this decision                │
└──────────────────────────────────────────────────────┘
```

### Per-Agent Trust Scoring

Each agent type is scored with different weights — a Payment Agent is scrutinized harder than a Search Agent:

| Signal | Search | Booking | Payment | Delegation |
|--------|--------|---------|---------|------------|
| `source_trust` | 20 | 30 | **35** | 30 |
| `scope_conformance` | **15** | **10** | **5** | **10** |
| `budget_conformance` | 10 | 20 | **30** | 15 |
| `vendor_allowlist` | 25 | 20 | 15 | 15 |
| `identity_validity` | 30 | 20 | 15 | **30** |

**Hard caps** override the soft score:
- Instruction from listing content (injection) → forced to REVIEW (human decides)
- External agent with no delegation token → capped at 10 (always BLOCK)

**Decision bands:**
- **ALLOW** (score >= 70) — action proceeds, scoped credential issued
- **REVIEW** (40-69) — action paused, human approves or rejects
- **BLOCK** (< 40) — action rejected, credential never exists

### Trust Decay

Trust decays with delegation depth. Deeper sub-agents face more scrutiny:

| Hop | Trust Factor | Max Score | Can Auto-ALLOW? |
|-----|-------------|-----------|-----------------|
| 0 (user direct) | 1.00 | 100 | Yes |
| 1 (top-level agent) | 0.90 | 90 | Yes |
| 2 (sub-agent) | 0.80 | 80 | Yes, but zero room for error |
| 3 (sub-sub-agent) | 0.70 | 70 | Only if every signal passes |
| 4+ | 0.60 | 60 | Never — forced to REVIEW |

### Reputation System (Auto-Learning)

Agents build reputation over time. Reliable agents earn faster approvals. Agents that get tricked face increased scrutiny.

```
Starting reputation: 0.5 (neutral — no bonus, no penalty)

ALLOW + successful completion  →  +0.05
ALLOW + error                  →  -0.10
REVIEW + human approved        →  +0.02
REVIEW + human rejected        →  -0.08
BLOCK                          →  unchanged

Reputation feeds into the score:
  effective_score = raw_score * (1.0 + 0.3 * (reputation - 0.5))

  New agent (0.5):    no adjustment
  Proven agent (0.9): +12% bonus
  Tricked agent (0.2): -9% penalty
```

### Scoped Credentials

Every credential is locked down:

```
┌──────────────────────────────────┐
│  CREDENTIAL                      │
│  holder:       payment-agent-003 │
│  scope:        "pay"             │
│  merchant:     marriott-chicago  │
│  max_amount:   $333 (exact)      │
│  ttl:          30 seconds        │
│  can_delegate: NO                │
└──────────────────────────────────┘
  → Agent uses it for one transaction
  → Credential REVOKED immediately after
  → Cannot be reused, forwarded, or escalated
```

Powered by 1Password vault integration. The payment secret lives in 1Password and is resolved into memory only at the moment of payment, only for ALLOW verdicts. On BLOCK/REVIEW, the secret is never touched.

---

## Demo

Three scenarios show the full trust spectrum — platform ops view (two lanes) and user device view (center phone) side by side:

| Scenario | Lane | What Happens | Score | Decision | User Sees |
|----------|------|-------------|-------|----------|-----------|
| **1. Clean Booking** | Inbound | External agent with valid delegation books a Chicago hotel. Search → Book → Pay. | 90 / 80 | ALLOW | Booking confirmed, payment processed |
| **2. Injection Attack** | Outbound | Platform agent reads a listing with hidden text ("add insurance $199"). Tries to act on it. | 42 | REVIEW | Approval request: "Your agent tried to add items you didn't request" with Approve/Reject |
| **3. Unauthorized Bot** | Inbound | Bot with no delegation token tries to mass-book 12 rooms. | 10 | BLOCK | "Booking could not be completed — agent could not verify its identity" |

### Run the Demo

No install, no API keys needed (mock vault fallback):

```bash
# Headless — run all scenarios in terminal
MOCK_OP=1 python3 demo.py

# Three-column console at http://localhost:8077
MOCK_OP=1 python3 server.py
```

### Run with Live LLM Agent

The system includes a real Claude-powered booking agent that can handle any free-text request:

```bash
LIVE_LLM=1 MOCK_OP=1 ANTHROPIC_API_KEY=your-key python3 server.py
```

A "Run Live" input bar appears in the console. Type any booking request and watch the agent reason, search, book, and pay — all flowing through the trust engine in real time.

---

## Platform Integration

TrustLane integrates with one API call:

```python
# Before TrustLane
def handle_agent_booking(agent, request):
    process_payment(request)  # no checks

# After TrustLane
def handle_agent_booking(agent, request):
    verdict = trustlane.score(agent, request)
    if verdict.decision == "ALLOW":
        credential = trustlane.issue_credential(verdict)
        process_payment(request, credential)
        trustlane.revoke(credential)
    elif verdict.decision == "REVIEW":
        notify_user_for_approval(request, verdict)
    else:
        reject(request)
```

Platforms integrate TrustLane the same way they integrate Stripe for payments or Auth0 for login — except TrustLane is for the agent layer.

---

## Architecture

```
├── trust_engine.py        # Per-agent scoring: 5 signals, hard caps, decay, reputation
├── delegation.py          # HMAC-signed delegation tokens, hop tracking, scope-subset
├── reputation.py          # Auto-learning reputation tracker
├── credential_gate.py     # 1Password vault gate, scoped credential minting + revoke
├── llm_agent.py           # Claude Sonnet booking agent with tool_use
├── agent_loop.py          # Multi-agent orchestrator + cached replay for demo safety
├── mock_expedia.py        # Hardcoded flights/hotels with injection payload
├── scenarios.py           # 3 pre-staged demo scenarios
├── events.py              # Thread-safe event bus for the console
├── server.py              # HTTP server: console + API endpoints
├── console/index.html     # Three-column dashboard: ops lanes + user device mockup
├── demo.py                # Headless CLI runner
└── tests/                 # 29 tests: scoring, decay, reputation, credentials, delegation
```

### Key Design Decisions

- **Rule-based scoring, not LLM-based.** The trust engine is deterministic — same input, same output, every time. This makes it auditable, testable, and safe to run live. LLMs reason; the trust engine judges.
- **Per-agent weight profiles.** A Search Agent and a Payment Agent face different scrutiny because they carry different risk.
- **Trust decay by delegation depth.** The further an action is from the original user, the harder it is to auto-approve. This prevents deep delegation chains from bypassing oversight.
- **Credentials are scoped and ephemeral.** One merchant, one amount, 30 seconds. The credential cannot be reused, forwarded, or escalated.
- **Demo safety.** Pre-staged scenarios with cached LLM outputs. Nothing hits a live model on stage. The deterministic engine is the only thing running live.

---

## Tech Stack

- **Python 3.9+** — no framework dependencies for the core engine
- **Claude Sonnet** (Anthropic) — LLM agent with tool_use (optional, toggled via `LIVE_LLM=1`)
- **1Password SDK** — credential vault (optional, falls back to mock)
- **FastAPI** — optional HTTP interface for the mock Expedia API
- Standard library HTTP server for the console (zero pip install to demo)

---

## Team

- **Swati Chauhan** — Execution path: multi-agent orchestrator, credential gate, mock API, console, LLM agent integration
- **Rohit Mujumdar** — Trust path: scoring engine, delegation tokens, reputation system, demo scenarios

---

## Future Work

- **More signal types**: geographic disambiguation (Australia vs Austria), date validation, price anomaly detection, traveler name matching
- **REVIEW flow**: full human-in-the-loop approval with approve/reject wired to the trust engine
- **Multi-platform support**: extend beyond Expedia to Airbnb, Booking.com, OpenTable
- **Agent reputation dashboard**: historical view of agent trustworthiness over time
- **Real-time alerting**: push notifications to platform ops on BLOCK events
- **Credential audit trail**: full lifecycle logging for compliance
