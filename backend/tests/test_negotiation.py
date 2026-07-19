"""Local negotiation driver: the three outcome paths + record shape/invariants."""

import uuid

from app import agents, negotiation, store


def _run(chart) -> dict:
    job_id = str(uuid.uuid4())
    store.create_job(job_id, chart)
    negotiation.run_local(job_id, chart)
    return store.get_job(job_id)


def _rounds_of(job, rtype):
    return [r for r in job["rounds"] if r["type"] == rtype]


def test_overturn_at_rereview(strong_chart):
    assert agents.necessity_score(strong_chart) >= 5
    job = _run(strong_chart)

    assert job["status"] == "RESOLVED"
    assert job["outcome"] == "OVERTURNED"
    # Round 1 only: denial, appeal, single ruling. No round-2 escalation.
    assert [r["type"] for r in job["rounds"]] == ["denial", "appeal", "ruling"]
    assert all(r["round"] == 1 for r in job["rounds"])


def test_overturn_at_final_ruling(moderate_chart):
    score = agents.necessity_score(moderate_chart)
    assert 2 <= score < 5
    job = _run(moderate_chart)

    assert job["status"] == "RESOLVED"
    assert job["outcome"] == "OVERTURNED"
    # Full two-round negotiation: denial, appeal, ruling, appeal, ruling.
    assert [r["type"] for r in job["rounds"]] == [
        "denial",
        "appeal",
        "ruling",
        "appeal",
        "ruling",
    ]
    # Round invariant: the escalated appeal and final ruling are round 2.
    assert job["rounds"][3]["round"] == 2
    assert job["rounds"][4]["round"] == 2


def test_escalate_to_human(weak_chart):
    assert agents.necessity_score(weak_chart) < 2
    job = _run(weak_chart)

    assert job["status"] == "ESCALATED"
    assert job["outcome"] == "ESCALATED"
    assert len(_rounds_of(job, "ruling")) == 2  # both rulings upheld


def test_audit_trail_is_ordered_and_populated(moderate_chart):
    job = _run(moderate_chart)
    events = [a["event"] for a in job["auditTrail"]]
    assert events[0] == "Denial intercepted"
    assert "Appeal filed" in events
    assert "Escalated appeal filed" in events
    assert events[-1] == "Denial overturned - revenue recovered"


def test_denial_reason_code_downgrade_for_thin_als():
    # ALS billed, necessity score < 4 -> DOWNGRADE rather than a hard CO-50.
    from tests.conftest import _base_chart

    chart = _base_chart(
        levelOfService="ALS",
        interventions=["patient assessment"],
        vitals={"gcs": 15, "bp": "120/80", "hr": 80, "spo2": 99, "rr": 14},
        comorbidities=[],
        mechanismOfInjury="none reported",
        transportPriority="Priority 2 (urgent)",
    )
    assert agents.necessity_score(chart) < 4
    job = _run(chart)
    denial = next(r for r in job["rounds"] if r["type"] == "denial")
    assert denial["reasonCode"] == "DOWNGRADE"


def test_rounds_are_append_only_and_never_mutated(strong_chart):
    job_id = str(uuid.uuid4())
    store.create_job(job_id, strong_chart)
    negotiation.run_local(job_id, strong_chart)
    first = store.get_job(job_id)["rounds"][0]
    # Re-reading returns identical historical entries.
    again = store.get_job(job_id)["rounds"][0]
    assert first == again
    assert first["type"] == "denial"
