"""
TrustLane — Demo console / UI backend.

PLACEHOLDER — Swati owns this file.

This module will serve the split-lane demo UI:
  Left lane  — execution path (agent_loop events)
  Right lane — trust signals (Verdict, score, signals list)

Three scenario buttons will trigger pre-staged flows:
  Scenario 1: Clean booking      → score ~87 ALLOW, credential issued then revoked
  Scenario 2: Injection caught   → score ~11 BLOCK, credential withheld
  Scenario 3: Bad delegation tok → score ~5  BLOCK, credential withheld

TODO: implement
"""
