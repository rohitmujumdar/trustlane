"""CLI demo — run all three scenarios through the real engine + gate (mock vault).

  python demo.py

The headless twin of the two-lane console: same scoring, same gate, printed
instead of rendered. Run this before going on stage to confirm the numbers land
and the core claim holds: the payment secret resolves ONLY on ALLOW and never
appears anywhere the console (or the agent) can read it.
"""
import json

from agent_loop import run_scenario
from credential_gate import CredentialGate
from events import EventBus
from scenarios import all_scenarios
from trust_engine import score

GREEN, RED, DIM, BOLD, RESET = "\033[32m", "\033[31m", "\033[2m", "\033[1m", "\033[0m"


def _print_events(events: list[dict]) -> None:
    for ev in events:
        line = f"[{ev['type']:10s}] {ev['title']}"
        if ev["detail"]:
            line += f"  — {ev['detail']}"
        print(line)
        if ev["type"] == "score":
            for s in ev["data"]["signals"]:
                mark = "ok " if s["passed"] else "FAIL"
                print(f"             [{mark}] {s['name']:18s} {s['detail']}")


def main() -> None:
    gate = CredentialGate()  # mock vault unless OP_SERVICE_ACCOUNT_TOKEN is set
    print(f"1Password gate: {'LIVE vault' if gate.live else 'mock vault (no token)'}\n")

    # The raw secret an ALLOW would resolve — we will prove it never leaks.
    sample_allow = next(s for s in all_scenarios().values() if s.expect.value == "ALLOW")
    raw_secret = gate.issue_blocking(score(sample_allow.steps[0].action, sample_allow.steps[0].context))

    all_events: list[dict] = []
    rows = []

    for key, scenario in all_scenarios().items():
        bus = EventBus()
        run_scenario(scenario, gate, bus)
        events = bus.snapshot()
        all_events += events

        verdict = score(scenario.steps[0].action, scenario.steps[0].context)
        landed = (verdict.decision is scenario.expect and verdict.score == scenario.expect_score)
        rows.append((key, scenario, verdict, landed))

        print("=" * 72)
        print(f"SCENARIO {key} · {scenario.lane.upper()} · {scenario.title}")
        print("-" * 72)
        _print_events(events)
        print()

    # ---- scoreboard: did each scenario land exactly as the demo needs? ----
    print("=" * 72)
    print(f"{BOLD}SCOREBOARD{RESET}")
    print("-" * 72)
    all_landed = True
    for key, scenario, verdict, landed in rows:
        color = GREEN if verdict.decision.value == "ALLOW" else RED
        status = f"{GREEN}PASS{RESET}" if landed else f"{RED}MISLANDED (expected {scenario.expect.value} {scenario.expect_score}){RESET}"
        all_landed &= landed
        print(f"  S{key} {scenario.lane:8s} {color}{verdict.score:>3} {verdict.decision.value:5s}{RESET}  {status}  {scenario.title}")

    # ---- core claim: secret resolves only on ALLOW, never enters the stream ----
    stream = json.dumps(all_events)
    leaked = raw_secret in stream
    issued = sum(1 for e in all_events if e["type"] == "credential" and "issued" in e["title"].lower())
    blocked = sum(1 for e in all_events if e["type"] == "blocked")
    print("-" * 72)
    print(f"{BOLD}CORE CLAIM{RESET}")
    print(f"  credential resolved (ALLOW): {issued}    withheld (BLOCK/REVIEW): {blocked}")
    print(f"  secret present in console event stream: "
          + (f"{RED}YES — LEAK{RESET}" if leaked else f"{GREEN}no{RESET}"))
    print("-" * 72)
    ok = all_landed and not leaked
    print(f"{(GREEN + 'DEMO READY' if ok else RED + 'NOT READY') + RESET}\n")


if __name__ == "__main__":
    main()
