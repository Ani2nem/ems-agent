"""HTTP endpoint contract from docs/api-contract.md, via the FastAPI TestClient."""

import time
import uuid
import xml.etree.ElementTree as ET

import pytest
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)

TERMINAL = {"RESOLVED", "ESCALATED", "ERROR"}


def _poll_until_terminal(job_id: str, timeout: float = 5.0) -> dict:
    deadline = time.time() + timeout
    body = {}
    while time.time() < deadline:
        resp = client.get(f"/api/submit-claim/{job_id}")
        assert resp.status_code == 200
        body = resp.json()
        if body["status"] in TERMINAL:
            return body
        time.sleep(0.02)
    raise AssertionError(f"job {job_id} did not reach a terminal state: {body}")


# --------------------------- parse-audio --------------------------- #


def test_parse_audio_returns_valid_chart():
    resp = client.post(
        "/api/parse-audio",
        json={"transcript": "62 yo male, medicare, chest pain, started IV access and cardiac monitoring, priority 1."},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert uuid.UUID(body["chartId"])  # parseable uuid
    chart = body["chart"]
    assert chart["payer"] == "MEDICARE"
    assert chart["levelOfService"] == "ALS"
    assert chart["patient"]["age"] == 62
    assert chart["patient"]["sex"] == "M"


def test_parse_audio_is_deterministic():
    payload = {"transcript": "45 yo female, aetna, difficulty breathing"}
    a = client.post("/api/parse-audio", json=payload).json()
    b = client.post("/api/parse-audio", json=payload).json()
    assert a["chart"] == b["chart"]  # same transcript -> same chart


def test_parse_audio_empty_transcript_is_400():
    resp = client.post("/api/parse-audio", json={"transcript": "   "})
    assert resp.status_code == 400
    assert "error" in resp.json()


def test_parse_audio_missing_field_is_400():
    resp = client.post("/api/parse-audio", json={})
    assert resp.status_code == 400
    assert "error" in resp.json()


# --------------------------- export-nemsis --------------------------- #


def test_export_nemsis_returns_well_formed_xml(strong_chart):
    resp = client.post("/api/export-nemsis", json={"chart": strong_chart})
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("application/xml")
    root = ET.fromstring(resp.content)  # raises if not well-formed
    assert root.tag.endswith("PatientCareReport")


def test_export_nemsis_invalid_chart_is_400():
    resp = client.post("/api/export-nemsis", json={"chart": {"payer": "AETNA"}})
    assert resp.status_code == 400
    assert "error" in resp.json()


# --------------------------- submit-claim --------------------------- #


def test_submit_claim_full_flow(strong_chart):
    resp = client.post(
        "/api/submit-claim",
        json={"chart": strong_chart, "idempotencyKey": str(uuid.uuid4())},
    )
    assert resp.status_code == 202
    body = resp.json()
    assert body["status"] == "PENDING"
    job_id = body["jobId"]

    final = _poll_until_terminal(job_id)
    assert final["status"] == "RESOLVED"
    assert final["outcome"] == "OVERTURNED"
    assert final["rounds"][0]["type"] == "denial"
    assert final["auditTrail"]


def test_submit_claim_idempotency_returns_same_job(strong_chart):
    key = str(uuid.uuid4())
    first = client.post("/api/submit-claim", json={"chart": strong_chart, "idempotencyKey": key}).json()
    second = client.post("/api/submit-claim", json={"chart": strong_chart, "idempotencyKey": key}).json()
    assert first["jobId"] == second["jobId"]


def test_submit_claim_invalid_chart_is_400():
    resp = client.post(
        "/api/submit-claim",
        json={"chart": {"payer": "AETNA"}, "idempotencyKey": str(uuid.uuid4())},
    )
    assert resp.status_code == 400
    assert "error" in resp.json()


def test_submit_claim_rejects_bad_payer_enum(strong_chart):
    bad = dict(strong_chart, payer="CIGNA")
    resp = client.post(
        "/api/submit-claim",
        json={"chart": bad, "idempotencyKey": str(uuid.uuid4())},
    )
    assert resp.status_code == 400


def test_get_unknown_job_is_404():
    resp = client.get(f"/api/submit-claim/{uuid.uuid4()}")
    assert resp.status_code == 404
    assert resp.json() == {"error": "unknown jobId"}


def test_escalation_flow_via_api(weak_chart):
    resp = client.post(
        "/api/submit-claim",
        json={"chart": weak_chart, "idempotencyKey": str(uuid.uuid4())},
    )
    job_id = resp.json()["jobId"]
    final = _poll_until_terminal(job_id)
    assert final["status"] == "ESCALATED"
    assert final["outcome"] == "ESCALATED"
