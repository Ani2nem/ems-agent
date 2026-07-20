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


def test_rate_for_known_levels():
    assert agents.rate_for("BLS") == 500
    assert agents.rate_for("ALS") == 900


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


# --------------------------- age extraction --------------------------- #


@pytest.mark.parametrize(
    "transcript,expected_age",
    [
        ("58-year-old male involved in a fall.", 58),
        ("58 year old male involved in a fall.", 58),
        ("Patient is 58yo male.", 58),
        ("Patient is 58 y/o male.", 58),
        ("Patient is 58 y.o. male.", 58),
        ("Patient found down, no age given in the dictation.", None),
    ],
)
def test_mock_chart_age_extraction(transcript, expected_age):
    chart = agents.parse_chart(transcript)
    assert chart["patient"]["age"] == expected_age
    from app.models import EPCRChart

    EPCRChart.model_validate(chart)


# ------------------------- vitals extraction ------------------------- #


@pytest.mark.parametrize(
    "transcript,field,expected",
    [
        ("BP 120/80 on scene.", "bp", "120/80"),
        ("blood pressure 120 over 80 on scene.", "bp", "120/80"),
        ("Patient stable, no vitals called out.", "bp", None),
        ("heart rate 98 on the monitor.", "hr", 98),
        ("hr 98 on the monitor.", "hr", 98),
        ("pulse 98 palpated.", "hr", 98),
        ("Patient stable, no vitals called out.", "hr", None),
        ("spo2 96 on room air.", "spo2", 96),
        ("sats 96 on room air.", "spo2", 96),
        ("96% on room air.", "spo2", 96),
        ("Patient stable, no vitals called out.", "spo2", None),
        ("respiratory rate 18, non-labored.", "rr", 18),
        ("rr 18, non-labored.", "rr", 18),
        ("Patient stable, no vitals called out.", "rr", None),
        ("gcs 15, alert and oriented.", "gcs", 15),
        ("glasgow coma 15, alert and oriented.", "gcs", 15),
        ("Patient stable, no vitals called out.", "gcs", None),
    ],
)
def test_mock_chart_vitals_extraction(transcript, field, expected):
    chart = agents.parse_chart(transcript)
    assert chart["vitals"][field] == expected


# ---------------------------- billed amount ---------------------------- #


@pytest.mark.parametrize(
    "transcript,expected_level,expected_billed",
    [
        ("Patient assessed, ambulatory, no interventions performed.", "BLS", 500),
        ("Cardiac monitoring and IV access performed en route.", "ALS", 900),
    ],
)
def test_mock_chart_billed_amount_by_level_of_service(transcript, expected_level, expected_billed):
    chart = agents.parse_chart(transcript)
    assert chart["levelOfService"] == expected_level
    assert chart["billedAmount"] == expected_billed
    from app.models import EPCRChart

    EPCRChart.model_validate(chart)


# ---------------------- mechanism of injury ---------------------- #


def test_mock_chart_mechanism_of_injury_reflects_transcript():
    chart = agents.parse_chart(
        "58-year-old male, high-speed MVC with significant vehicular intrusion, "
        "transported to the trauma center."
    )
    assert "MVC" in chart["mechanismOfInjury"]
    assert chart["mechanismOfInjury"] != "Reported per dictation; see narrative."


def test_mock_chart_mechanism_of_injury_falls_back_when_absent():
    chart = agents.parse_chart("Patient reports chest pain, no trauma history.")
    assert chart["mechanismOfInjury"] == "Mechanism of injury not stated in dictation."


# ------------------------- comorbidities ------------------------- #


@pytest.mark.parametrize(
    "transcript,expected",
    [
        ("Patient has a history of diabetes.", ["diabetes"]),
        ("Patient has COPD and is on home oxygen.", ["COPD"]),
        ("History of CHF, currently compensated.", ["CHF"]),
        ("Patient has hypertension, well controlled.", ["hypertension"]),
        ("Patient is on dialysis for renal failure.", ["renal failure"]),
        ("Denies any past medical history.", []),
    ],
)
def test_mock_chart_comorbidity_extraction(transcript, expected):
    chart = agents.parse_chart(transcript)
    assert chart["comorbidities"] == expected


def test_mock_chart_comorbidity_extraction_multiple_no_duplicates():
    chart = agents.parse_chart(
        "History of diabetes, COPD, and hypertension; also diabetic per prior chart."
    )
    assert chart["comorbidities"] == ["diabetes", "COPD", "hypertension"]


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


# ------------------------- policy citation (mock) ------------------------- #


@pytest.mark.parametrize("payer", ["AETNA", "MEDICARE"])
def test_mock_deny_cites_genuine_policy_excerpt(payer):
    chart = _base_chart(payer=payer, levelOfService="BLS")  # necessity score is low -> CO-50
    policy = agents.load_policy(payer)
    content, reason = agents.deny(chart, payer, policy)
    assert reason == "CO-50"
    # The denial must quote the policy's own line for this code, not just say the code.
    excerpt = agents._policy_excerpt_for_reason(policy, "CO-50")
    assert excerpt is not None
    assert excerpt in content


def test_mock_deny_downgrade_cites_downgrade_excerpt():
    chart = _base_chart(levelOfService="ALS", vitals={"gcs": 15, "bp": None, "hr": None, "spo2": None, "rr": None}, interventions=[], comorbidities=[], mechanismOfInjury="none")
    policy = agents.load_policy("AETNA")
    content, reason = agents.deny(chart, "AETNA", policy)
    assert reason == "DOWNGRADE"
    excerpt = agents._policy_excerpt_for_reason(policy, "DOWNGRADE")
    assert excerpt is not None
    assert excerpt in content


@pytest.mark.parametrize("payer", ["AETNA", "MEDICARE"])
def test_mock_appeal_cites_genuine_policy_sentence(payer):
    chart = _base_chart(payer=payer)
    policy = agents.load_policy(payer)
    content = agents.appeal(chart, "denial text", policy, escalated=False)
    basis = agents._policy_basis_sentence(policy, chart)
    assert basis
    assert basis in content
    # It's a real sentence from the policy file, not the old boilerplate line.
    assert "The cited policy covers transport at the assessed level" not in content


def test_policy_excerpt_for_unknown_reason_is_none():
    policy = agents.load_policy("AETNA")
    assert agents._policy_excerpt_for_reason(policy, "CO-99") is None


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


def test_bedrock_denial_parses_reason_tag_title_case_and_lowercase_value(_bedrock_on, monkeypatch):
    """Real Nova Micro output doesn't always match the prompt's exact casing -
    found live on a ruling that said "Decision: OVERTURN" (title case) and
    was silently treated as the wrong default instead. Same class of bug is
    possible on the reason tag/value, covered here."""
    monkeypatch.setattr(
        bedrock, "converse", lambda *a, **k: "Denied per policy.\nReason: downgrade"
    )
    content, reason = agents.deny(_base_chart(), "AETNA", "policy")
    assert reason == "DOWNGRADE"
    assert "Reason:" not in content


def test_bedrock_ruling_parses_decision_tag(_bedrock_on, monkeypatch):
    monkeypatch.setattr(
        bedrock, "converse", lambda *a, **k: "## Ruling\nApproved.\nDECISION: OVERTURN"
    )
    decision, content = agents.rule(_base_chart(), "appeal", "policy", biased=False)
    assert decision == "overturn"
    assert "DECISION:" not in content


def test_bedrock_ruling_parses_decision_tag_title_case(_bedrock_on, monkeypatch):
    """Regression test for the exact bug found live: a round-1 (unbiased)
    ruling whose content plainly said "**Decision: OVERTURN**" was still
    treated as an uphold, because the old case-sensitive match only
    recognized the all-caps "DECISION:" the prompt asks for, silently
    falling back to the unbiased default (uphold) instead of the model's
    real decision - forcing an unnecessary round-2 escalation."""
    monkeypatch.setattr(
        bedrock, "converse", lambda *a, **k: "## Ruling\n\n**Decision: OVERTURN**"
    )
    decision, content = agents.rule(_base_chart(), "appeal", "policy", biased=False)
    assert decision == "overturn"
    assert "Decision" not in content


def test_bedrock_ruling_falls_back_on_unparseable(_bedrock_on, monkeypatch):
    monkeypatch.setattr(bedrock, "converse", lambda *a, **k: "no tag here")
    # Unbiased re-review falls back to uphold; biased final falls back to overturn.
    assert agents.rule(_base_chart(), "a", "p", biased=False)[0] == "uphold"
    assert agents.rule(_base_chart(), "a", "p", biased=True)[0] == "overturn"


@pytest.mark.parametrize(
    "raw",
    [
        "## Ruling\n\nSome reasoning.\n\n**DECISION: OVERTURN**",
        "## Ruling\n\nSome reasoning.\n\n**Final Decision:**\nDECISION: OVERTURN\n```",
        "## Ruling\n\nSome reasoning.\n\n**DECISION: OVERTURN**\n```",
    ],
)
def test_bedrock_ruling_strips_tag_despite_bold_and_trailing_fence(_bedrock_on, monkeypatch, raw):
    """Real Nova Micro output sometimes bolds the tag and/or appends a stray
    trailing code fence after it; the tag line must still be fully stripped."""
    monkeypatch.setattr(bedrock, "converse", lambda *a, **k: raw)
    decision, content = agents.rule(_base_chart(), "appeal", "policy", biased=False)
    assert decision == "overturn"
    assert "DECISION" not in content
    assert "```" not in content


def test_bedrock_parse_chart_invalid_json_raises_502_error(_bedrock_on, monkeypatch):
    monkeypatch.setattr(bedrock, "converse", lambda *a, **k: "not json")
    with pytest.raises(bedrock.BedrockError):
        agents.parse_chart("some transcript")
