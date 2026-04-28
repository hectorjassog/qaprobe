"""Unit tests for reconciliation logic."""

from qaprobe.agent import AgentResult
from qaprobe.report import reconcile_verdict
from qaprobe.verifier import VerifierResult


def _agent(verdict, reasoning=""):
    return AgentResult(verdict=verdict, reasoning=reasoning, steps=[], final_snapshot="")


def _verifier(goal_achieved, confidence="high", reasoning=""):
    return VerifierResult(goal_achieved=goal_achieved, confidence=confidence, reasoning=reasoning)


def test_both_pass():
    assert reconcile_verdict(_agent("pass"), _verifier(True)) == "pass"


def test_both_fail():
    assert reconcile_verdict(_agent("fail"), _verifier(False)) == "fail"


def test_agent_pass_verifier_fail():
    assert reconcile_verdict(_agent("pass"), _verifier(False)) == "inconclusive"


def test_agent_fail_verifier_pass():
    assert reconcile_verdict(_agent("fail"), _verifier(True)) == "inconclusive"


def test_timeout_verdict_is_fail():
    result = _agent("timeout")
    assert reconcile_verdict(result, _verifier(False)) == "fail"
    assert reconcile_verdict(result, _verifier(True)) == "inconclusive"


def test_low_confidence_pass_is_inconclusive():
    """Confidence calibration: both pass but low confidence → inconclusive."""
    assert reconcile_verdict(_agent("pass"), _verifier(True, confidence="low")) == "inconclusive"


def test_medium_confidence_pass_is_pass():
    assert reconcile_verdict(_agent("pass"), _verifier(True, confidence="medium")) == "pass"
