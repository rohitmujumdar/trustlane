"""The numbers must land. These lock the three demo scenarios in place."""
from credential_gate import CredentialGate
from delegation import issue_delegation, validate_delegation
from scenarios import all_scenarios
from trust_engine import Decision, score


def _verdict(scenario):
    step = scenario.steps[0]
    return score(step.action, step.context)


def test_scenario_1_inbound_clean_allows():
    v = _verdict(all_scenarios()["1"])
    assert v.decision is Decision.ALLOW
    assert v.score >= 70


def test_scenario_2_outbound_injection_blocks():
    v = _verdict(all_scenarios()["2"])
    assert v.decision is Decision.BLOCK
    assert v.score <= 15  # injection hard cap


def test_scenario_3_inbound_fraud_blocks():
    v = _verdict(all_scenarios()["3"])
    assert v.decision is Decision.BLOCK
    assert v.score <= 10  # no-delegation hard cap


def test_gate_withholds_on_block():
    v = _verdict(all_scenarios()["2"])
    gate = CredentialGate()
    try:
        gate.issue_blocking(v)
        assert False, "gate must not issue on BLOCK"
    except PermissionError:
        pass


def test_gate_issues_on_allow():
    v = _verdict(all_scenarios()["1"])
    secret = CredentialGate().issue_blocking(v)
    assert secret  # mock or live, a value comes back only on ALLOW


def test_delegation_subset_enforced():
    # A child scope that exceeds the parent must fail the subset check.
    tok = issue_delegation(
        agent_id="a", principal="p",
        scope={"actions": ["book", "delegate"], "merchants": ["expedia"], "max_amount": 5000},
        parent_scope={"actions": ["book"], "merchants": ["expedia"], "max_amount": 800},
    )
    result = validate_delegation(tok)
    assert result["valid"] is True
    assert result["scope_is_subset"] is False


def test_delegation_tamper_detected():
    tok = issue_delegation(
        agent_id="a", principal="p",
        scope={"actions": ["book"], "merchants": ["expedia"], "max_amount": 800},
        parent_scope={"actions": ["book"], "merchants": ["expedia"], "max_amount": 800},
    )
    tok["scope"]["max_amount"] = 99999  # tamper after signing
    result = validate_delegation(tok)
    assert result["valid"] is False
