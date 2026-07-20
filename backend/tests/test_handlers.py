"""Individual handler contracts from docs/workflow-contract.md."""

import uuid

from app import agents, handlers, store


def _state(chart):
    job_id = str(uuid.uuid4())
    store.create_job(job_id, chart)
    return {"jobId": job_id, "chart": chart, "payer": chart["payer"], "round": 1, "decision": None}


def test_deny_sets_round_and_status(strong_chart):
    state = handlers.deny(_state(strong_chart))
    assert state["round"] == 1
    assert state["payer"] == "AETNA"
    job = store.get_job(state["jobId"])
    assert job["status"] == "DENIED"
    assert job["rounds"][-1]["actor"] == "payer"
    assert job["rounds"][-1]["type"] == "denial"


def test_appeal_first_pass_is_round_1(strong_chart):
    state = _state(strong_chart)
    state = handlers.deny(state)
    state = handlers.appeal(state)
    assert state["round"] == 1
    job = store.get_job(state["jobId"])
    assert job["status"] == "APPEALING"
    assert job["rounds"][-1]["type"] == "appeal"
    assert job["rounds"][-1]["round"] == 1


def test_escalate_appeal_becomes_round_2(strong_chart):
    """A prior ruling on record flips the reused appeal handler to round 2."""
    state = _state(strong_chart)
    state = handlers.deny(state)
    state = handlers.appeal(state)
    state = handlers.rereview(state)  # appends a ruling
    state = handlers.appeal(state)  # EscalateAppeal
    assert state["round"] == 2
    job = store.get_job(state["jobId"])
    assert job["rounds"][-1]["round"] == 2
    assert "Escalated appeal filed" in [a["event"] for a in job["auditTrail"]]


def test_rereview_sets_decision(strong_chart, weak_chart):
    s = _state(strong_chart)
    s = handlers.deny(s)
    s = handlers.appeal(s)
    s = handlers.rereview(s)
    assert s["decision"] == "overturn"

    w = _state(weak_chart)
    w = handlers.deny(w)
    w = handlers.appeal(w)
    w = handlers.rereview(w)
    assert w["decision"] == "uphold"


def test_final_ruling_is_biased_to_overturn(moderate_chart):
    state = _state(moderate_chart)
    state = handlers.deny(state)
    state = handlers.appeal(state)
    state = handlers.rereview(state)
    assert state["decision"] == "uphold"  # strict re-review
    state = handlers.appeal(state)
    state = handlers.final_ruling(state)
    assert state["decision"] == "overturn"  # biased final ruling


def test_resolve_and_escalate_terminal_side_effects(strong_chart):
    r = _state(strong_chart)
    handlers.resolve(r)
    job = store.get_job(r["jobId"])
    assert job["status"] == "RESOLVED" and job["outcome"] == "OVERTURNED"
    assert job["recoveredAmount"] == strong_chart["billedAmount"]

    e = _state(strong_chart)
    handlers.escalate(e)
    job = store.get_job(e["jobId"])
    assert job["status"] == "ESCALATED" and job["outcome"] == "ESCALATED"
    # No denial round on record in this synthetic state -> nothing recovered.
    assert job["recoveredAmount"] == 0


def test_escalate_after_downgrade_denial_recovers_bls_rate(strong_chart):
    """A DOWNGRADE denial only contests the ALS differential - the BLS base
    rate is still recovered even if the ALS appeal itself escalates.

    The mock necessity-score math can never produce this combination
    naturally (every ALS chart scores >= 2, which always clears the biased
    final-ruling threshold and overturns) - it's a real, reachable outcome
    in live Bedrock mode though, where the reason code and ruling decision
    come from two independent model calls with no such coupling. Tested
    directly at the handler level for that reason.
    """
    state = _state(strong_chart)
    store.append_round(
        state["jobId"],
        {
            "round": 1,
            "actor": "payer",
            "type": "denial",
            "reasonCode": "DOWNGRADE",
            "content": "Claim adjusted under DOWNGRADE.",
            "timestamp": "2026-01-01T00:00:00+00:00",
        },
    )
    handlers.escalate(state)
    job = store.get_job(state["jobId"])
    assert job["status"] == "ESCALATED" and job["outcome"] == "ESCALATED"
    assert job["recoveredAmount"] == agents.rate_for("BLS")
    assert job["recoveredAmount"] < strong_chart["billedAmount"]  # partial, not full
