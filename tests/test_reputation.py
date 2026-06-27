"""Reputation layer: build slow, decay fast, and only nudge (never override)."""
from reputation import ReputationStore


def test_new_agent_starts_neutral():
    store = ReputationStore()
    assert store.get("new") == 50.0
    assert store.adjust("new", 70) == 70  # neutral reputation = no nudge


def test_clean_history_builds_trust():
    store = ReputationStore()
    for _ in range(6):
        store.record_clean("alice")
    assert store.get("alice") > 50.0
    assert store.adjust("alice", 70) > 70  # trusted agent gets benefit of the doubt


def test_anomaly_decays_faster_than_it_builds():
    store = ReputationStore()
    for _ in range(4):
        store.record_clean("bob")        # +20 total
    before = store.get("bob")
    store.record_anomaly("bob")          # -30 in one shot
    assert store.get("bob") < before - 20  # one anomaly wipes out the slow build


def test_nudge_is_bounded_and_never_overrides_a_block():
    store = ReputationStore()
    for _ in range(50):
        store.record_clean("trusted")     # maxed reputation
    # a hard-capped BLOCK score (e.g. 10) stays a BLOCK; the nudge is small.
    assert store.adjust("trusted", 10) <= 20
