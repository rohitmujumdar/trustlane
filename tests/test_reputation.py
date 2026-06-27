"""Reputation layer: auto-learning per-agent reputation with outcome-based updates."""
from reputation import ReputationTracker


def test_new_agent_starts_at_neutral():
    rt = ReputationTracker()
    assert rt.get("new") == 0.5  # default is 0.5 (neutral)


def test_allow_success_increases_reputation():
    rt = ReputationTracker()
    rep = rt.update("alice", "allow_success")
    assert abs(rep - 0.55) < 1e-9


def test_allow_error_decreases_reputation():
    rt = ReputationTracker()
    rep = rt.update("bob", "allow_error")
    assert abs(rep - 0.40) < 1e-9


def test_block_leaves_reputation_unchanged():
    rt = ReputationTracker()
    rep = rt.update("carol", "block")
    assert abs(rep - 0.5) < 1e-9


def test_review_approved_small_increase():
    rt = ReputationTracker()
    rep = rt.update("dave", "review_approved")
    assert abs(rep - 0.52) < 1e-9


def test_review_rejected_decreases_reputation():
    rt = ReputationTracker()
    rep = rt.update("eve", "review_rejected")
    assert abs(rep - 0.42) < 1e-9


def test_reputation_clamped_at_zero_and_one():
    rt = ReputationTracker()
    for _ in range(30):
        rt.update("maxed", "allow_success")
    assert rt.get("maxed") == 1.0

    for _ in range(30):
        rt.update("zeroed", "allow_error")
    assert rt.get("zeroed") == 0.0


def test_anomaly_decays_faster_than_build():
    """One allow_error (-0.10) wipes out two allow_success (+0.05 each)."""
    rt = ReputationTracker()
    rt.update("frank", "allow_success")
    rt.update("frank", "allow_success")
    before = rt.get("frank")  # 0.60
    rt.update("frank", "allow_error")  # -0.10
    assert rt.get("frank") < before - 0.05  # net negative


def test_reputation_nudge_never_overrides_hard_cap():
    """Even a fully trusted agent cannot push a hard-cap BLOCK score above REVIEW."""
    rt = ReputationTracker()
    for _ in range(20):
        rt.update("trusted", "allow_success")
    assert rt.get("trusted") == 1.0

    # The trust engine applies rep via: effective = raw * (0.7 + 0.3 * rep)
    # Hard cap of 10 (no-delegation) means cap applies AFTER rep adjustment
    # So rep cannot override hard caps
    from trust_engine import score, Action, Context
    from scenarios import all_scenarios
    v = score(all_scenarios()["3"].steps[0].action, all_scenarios()["3"].steps[0].context, 1.0)
    assert v.score <= 10  # hard cap still applies


def test_snapshot_and_reset():
    rt = ReputationTracker()
    rt.update("x", "allow_success")
    snap = rt.snapshot()
    assert "x" in snap
    rt.reset()
    assert rt.snapshot() == {}
    assert rt.get("x") == 0.5
