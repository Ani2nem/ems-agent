"""Agent-level tests: mock determinism, scoring, and the Bedrock parse path
(monkeypatched so no AWS is required)."""

import pytest

from app import agents, bedrock
from tests.conftest import _base_chart


# ------------------------------- scoring ------------------------------- #


def test_necessity_score_bounds():
    assert agents.necessity_score(_base_chart()) == 7  # maxed-out strong chart
    weak = _base_chart(
        levelOfService="BLS",
        interventions=[],
        vitals={"gcs": 15, "bp": None, "hr": None, "spo2": None, "rr": None},
        comorbidities=[],
        mechanismOfInjury="none",
        transportPriority="Priority 3 (non-urgent)",
    )
    assert agents.necessity_score(weak) == 0


def test_policy_loads_per_payer():
    assert "MEDICARE" in agents.load_policy("MEDICARE")
    assert "AETNA" in agents.load_policy("AETNA")


# --------------------------- mock determinism -------------------------- #


def test_mock_chart_keyword_extraction():
    chart = agents.parse_chart("72 y/o female medicare, cardiac arrest, 12-lead obtained")
    assert chart["payer"] == "MEDICARE"
    assert chart["levelOfService"] == "ALS"
    assert chart["patient"] == {"age": 72, "sex": "F"}
    # Chart validates against the frozen model.
    from app.models import EPCRChart

    EPCRChart.model_validate(chart)


def test_mock_ruling_reflects_score():
    strong = _base_chart()
    weak = _base_chart(
        levelOfService="BLS",
        interventions=[],
        vitals={"gcs": 15, "bp": None, "hr": None, "spo2": None, "rr": None},
        comorbidities=[],
        mechanismOfInjury="none",
        transportPriority="Priority 3",
    )
    assert agents.rule(strong, "appeal", "policy", biased=False)[0] == "overturn"
    assert agents.rule(weak, "appeal", "policy", biased=False)[0] == "uphold"
    # Biased final ruling flips a mid-score chart it would otherwise uphold.
    mid = _base_chart(
        levelOfService="BLS",
        interventions=["assessment"],
        vitals={"gcs": 14, "bp": "120/80", "hr": 88, "spo2": 96, "rr": 18},
        comorbidities=["COPD"],
        mechanismOfInjury="fall",
        transportPriority="Priority 1 (emergent)",
    )
    assert agents.rule(mid, "appeal", "policy", biased=False)[0] == "uphold"
    assert agents.rule(mid, "appeal", "policy", biased=True)[0] == "overturn"


# ------------------------- Bedrock parse paths ------------------------- #


@pytest.fixture
def _bedrock_on(monkeypatch):
    monkeypatch.setenv("USE_BEDROCK", "true")


def test_bedrock_denial_parses_reason_tag(_bedrock_on, monkeypatch):
    monkeypatch.setattr(
        bedrock, "converse", lambda *a, **k: "Denied per policy.\nREASON: CO-16"
    )
    content, reason = agents.deny(_base_chart(), "AETNA", "policy")
    assert reason == "CO-16"
    assert "REASON:" not in content


def test_bedrock_ruling_parses_decision_tag(_bedrock_on, monkeypatch):
    monkeypatch.setattr(
        bedrock, "converse", lambda *a, **k: "## Ruling\nApproved.\nDECISION: OVERTURN"
    )
    decision, content = agents.rule(_base_chart(), "appeal", "policy", biased=False)
    assert decision == "overturn"
    assert "DECISION:" not in content


def test_bedrock_ruling_falls_back_on_unparseable(_bedrock_on, monkeypatch):
    monkeypatch.setattr(bedrock, "converse", lambda *a, **k: "no tag here")
    # Unbiased re-review falls back to uphold; biased final falls back to overturn.
    assert agents.rule(_base_chart(), "a", "p", biased=False)[0] == "uphold"
    assert agents.rule(_base_chart(), "a", "p", biased=True)[0] == "overturn"


def test_bedrock_parse_chart_invalid_json_raises_502_error(_bedrock_on, monkeypatch):
    monkeypatch.setattr(bedrock, "converse", lambda *a, **k: "not json")
    with pytest.raises(bedrock.BedrockError):
        agents.parse_chart("some transcript")
