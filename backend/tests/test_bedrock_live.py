"""Live integration tests against real AWS Bedrock (Amazon Nova Micro).

These hit the real Converse API and cost real (tiny) money, so they only run
when explicitly requested:

    RUN_BEDROCK_LIVE_TESTS=1 AWS_PROFILE=<profile> AWS_REGION=<region> \
        python -m pytest -q tests/test_bedrock_live.py

CI has no AWS credentials and does not set RUN_BEDROCK_LIVE_TESTS, so this
whole module is skipped there. The model's output is nondeterministic, so
assertions only check response *shape* (valid chart keys, allowed enum
values) - never exact wording.
"""

import os

import pytest

RUN_LIVE = os.getenv("RUN_BEDROCK_LIVE_TESTS", "").strip().lower() in {"1", "true", "yes"}

pytestmark = pytest.mark.skipif(
    not RUN_LIVE, reason="RUN_BEDROCK_LIVE_TESTS not set; skipping real Bedrock calls"
)

FIXED_TRANSCRIPT = (
    "72 year old male, found down, high-speed MVC with significant vehicular "
    "intrusion, unresponsive on scene, GCS 8, BP 88 over 60, heart rate 128, "
    "sp o2 89 percent on room air, respiratory rate 28. ALS crew established "
    "18-gauge IV access times two, placed on cardiac monitor, obtained a "
    "12-lead, administered oxygen via non-rebreather, transported priority 1 "
    "lights and sirens to the trauma center. Patient has a history of "
    "hypertension and COPD. Payer is Aetna."
)


@pytest.fixture(autouse=True)
def _use_bedrock(monkeypatch):
    monkeypatch.setenv("USE_BEDROCK", "true")


def test_parse_chart_live_returns_well_shaped_chart():
    from app import agents
    from app.models import EPCRChart

    chart = agents.parse_chart(FIXED_TRANSCRIPT)

    validated = EPCRChart.model_validate(chart)  # raises if shape is wrong
    assert validated.payer in {"AETNA", "MEDICARE"}
    assert validated.levelOfService in {"BLS", "ALS"}


def test_deny_appeal_ruling_live_round_trip():
    from app import agents

    chart = agents.parse_chart(FIXED_TRANSCRIPT)
    policy = agents.load_policy(chart["payer"])

    denial_content, reason = agents.deny(chart, chart["payer"], policy)
    assert reason in {"CO-50", "CO-16", "CO-11", "DOWNGRADE"}
    assert isinstance(denial_content, str) and denial_content.strip()
    assert "REASON:" not in denial_content  # tag line must be stripped

    appeal_content = agents.appeal(chart, denial_content, policy, escalated=False)
    assert isinstance(appeal_content, str) and appeal_content.strip()

    decision, ruling_content = agents.rule(chart, appeal_content, policy, biased=False)
    assert decision in {"overturn", "uphold"}
    assert "DECISION:" not in ruling_content

    # Round 2: escalated appeal + provider-biased final ruling.
    escalated_appeal = agents.appeal(chart, denial_content, policy, escalated=True)
    final_decision, final_content = agents.rule(chart, escalated_appeal, policy, biased=True)
    assert final_decision in {"overturn", "uphold"}
    assert "DECISION:" not in final_content


def test_submit_claim_live_full_negotiation_via_api():
    import time
    import uuid

    from fastapi.testclient import TestClient

    from app.main import app

    client = TestClient(app)

    chart_resp = client.post("/api/parse-audio", json={"transcript": FIXED_TRANSCRIPT})
    assert chart_resp.status_code == 200
    chart = chart_resp.json()["chart"]

    submit_resp = client.post(
        "/api/submit-claim",
        json={"chart": chart, "idempotencyKey": str(uuid.uuid4())},
    )
    assert submit_resp.status_code == 202
    job_id = submit_resp.json()["jobId"]

    deadline = time.time() + 60.0
    body = {}
    while time.time() < deadline:
        poll = client.get(f"/api/submit-claim/{job_id}")
        assert poll.status_code == 200
        body = poll.json()
        if body["status"] in {"RESOLVED", "ESCALATED", "ERROR"}:
            break
        time.sleep(0.5)
    else:
        raise AssertionError(f"job {job_id} did not reach a terminal state: {body}")

    assert body["status"] in {"RESOLVED", "ESCALATED"}, body
    assert body["rounds"], "expected at least one negotiation round"
    assert body["auditTrail"], "expected at least one audit entry"
