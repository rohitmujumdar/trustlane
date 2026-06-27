"""CLI demo — run all three scenarios through the real engine + gate (mock vault).

  python demo.py

This is the headless version of the two-lane console: same scoring, same gate,
printed instead of rendered. Use it to sanity-check that the numbers land before
wiring the web console.
"""
from agent_loop import run_scenario
from credential_gate import CredentialGate
from events import EventBus
from scenarios import all_scenarios


def main() -> None:
    gate = CredentialGate()  # mock vault unless OP_SERVICE_ACCOUNT_TOKEN is set
    print(f"1Password gate: {'LIVE vault' if gate.live else 'mock vault (no token)'}\n")

    for key, scenario in all_scenarios().items():
        bus = EventBus()
        run_scenario(scenario, gate, bus)
        lane = scenario.lane.upper()
        print("=" * 72)
        print(f"SCENARIO {key} · {lane} · {scenario.title}")
        print("-" * 72)
        for ev in bus.snapshot():
            line = f"[{ev['type']:10s}] {ev['title']}"
            if ev["detail"]:
                line += f"  — {ev['detail']}"
            print(line)
            if ev["type"] == "score":
                for s in ev["data"]["signals"]:
                    mark = "ok " if s["passed"] else "FAIL"
                    print(f"             [{mark}] {s['name']:18s} {s['detail']}")
        print()


if __name__ == "__main__":
    main()
