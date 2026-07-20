"""Step Functions task handlers (Workstream A side of ``docs/workflow-contract.md``).

Each function is a Lambda entrypoint ``(event, context) -> state`` where ``event``
is the current negotiation state. It is a near-pure ``state -> state`` transform
plus one side effect: it appends a round and/or audit entry to the DynamoDB job
record and updates ``status``. The same functions are driven in-process by
``negotiation.run_local`` in mock mode, so the ASL and the local driver produce
byte-identical job records.

``EscalateAppeal`` reuses :func:`appeal`; the round number is derived from the
record (a prior ruling means we are in round 2), which keeps the round invariant
the ASL relies on without the state machine having to set it.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from . import agents, store
from .config import settings


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _round(rnd: int, actor: str, rtype: str, content: str, reason_code: Optional[str] = None) -> dict:
    return {
        "round": rnd,
        "actor": actor,
        "type": rtype,
        "reasonCode": reason_code,
        "content": content,
        "timestamp": _now_iso(),
    }


def _last_round(job: dict, rtype: str) -> Optional[dict]:
    for rnd in reversed(job.get("rounds", [])):
        if rnd["type"] == rtype:
            return rnd
    return None


# --------------------------------------------------------------------------- #
# Handlers
# --------------------------------------------------------------------------- #


def deny(event, context=None):
    state = event
    job_id, chart = state["jobId"], state["chart"]
    payer = chart["payer"]
    policy = agents.load_policy(payer)

    content, reason_code = agents.deny(chart, payer, policy)
    store.append_round(job_id, _round(1, "payer", "denial", content, reason_code))
    store.append_audit(job_id, "Denial intercepted")
    store.update_status(job_id, "DENIED")

    state["payer"] = payer
    state["round"] = 1
    return state


def appeal(event, context=None):
    state = event
    job_id, chart = state["jobId"], state["chart"]
    payer = state.get("payer") or chart["payer"]
    policy = agents.load_policy(payer)

    job = store.get_job(job_id)
    # A ruling already on record means this is the round-2 escalated appeal.
    escalated = _last_round(job, "ruling") is not None
    rnd = 2 if escalated else 1
    denial = _last_round(job, "denial")
    denial_content = denial["content"] if denial else ""

    content = agents.appeal(chart, denial_content, policy, escalated=escalated)
    store.append_round(job_id, _round(rnd, "defense", "appeal", content))
    store.append_audit(job_id, "Escalated appeal filed" if escalated else "Appeal filed")
    store.update_status(job_id, "APPEALING")

    state["payer"] = payer
    state["round"] = rnd
    return state


def rereview(event, context=None):
    state = event
    job_id, chart = state["jobId"], state["chart"]
    payer = state.get("payer") or chart["payer"]
    policy = agents.load_policy(payer)

    job = store.get_job(job_id)
    appeal_round = _last_round(job, "appeal")
    appeal_content = appeal_round["content"] if appeal_round else ""

    decision, content = agents.rule(chart, appeal_content, policy, biased=False)
    store.append_round(job_id, _round(state.get("round", 1), "payer", "ruling", content))
    store.append_audit(job_id, f"Re-review complete: denial {decision}")
    store.update_status(job_id, "NEGOTIATING")

    state["decision"] = decision
    return state


def final_ruling(event, context=None):
    state = event
    job_id, chart = state["jobId"], state["chart"]
    payer = state.get("payer") or chart["payer"]
    policy = agents.load_policy(payer)

    job = store.get_job(job_id)
    appeal_round = _last_round(job, "appeal")
    appeal_content = appeal_round["content"] if appeal_round else ""

    decision, content = agents.rule(chart, appeal_content, policy, biased=True)
    store.append_round(job_id, _round(state.get("round", 2), "payer", "ruling", content))
    store.append_audit(job_id, f"Final ruling: denial {decision}")

    state["decision"] = decision
    return state


def resolve(event, context=None):
    state = event
    job_id, chart = state["jobId"], state["chart"]
    # Overturned means the original billed amount stands - whether the
    # denial was a full CO-50 necessity denial or an ALS->BLS DOWNGRADE, an
    # "overturn" reverses it entirely.
    store.update_status(job_id, "RESOLVED", outcome="OVERTURNED", recovered_amount=chart["billedAmount"])
    store.append_audit(job_id, "Denial overturned - revenue recovered")
    return state


def escalate(event, context=None):
    state = event
    job_id = state["jobId"]
    # A DOWNGRADE denial only ever contests the ALS differential - the BLS
    # base rate was never in dispute, so it's still recovered even when the
    # ALS appeal itself fails and escalates. Any other denial reason means
    # nothing is recovered automatically.
    job = store.get_job(job_id)
    denial = _last_round(job, "denial")
    reason_code = denial["reasonCode"] if denial else None
    recovered = agents.rate_for("BLS") if reason_code == "DOWNGRADE" else 0

    store.update_status(job_id, "ESCALATED", outcome="ESCALATED", recovered_amount=recovered)
    store.append_audit(job_id, "Escalated for human review")

    cfg = settings()
    if cfg.enable_ses_email and cfg.escalation_email:
        _send_escalation_email(job_id, cfg.escalation_email)
    return state


def _send_escalation_email(job_id: str, to_address: str) -> None:
    """Best-effort SES notice; never fail the workflow on email trouble."""
    import boto3  # local import: only used behind the ENABLE_SES_EMAIL flag

    try:
        boto3.client("ses", region_name=settings().aws_region).send_email(
            Source=to_address,
            Destination={"ToAddresses": [to_address]},
            Message={
                "Subject": {"Data": f"EMS claim escalated for human review: {job_id}"},
                "Body": {
                    "Text": {
                        "Data": (
                            f"Job {job_id} exhausted the automated 2-round "
                            "negotiation without overturning the denial and needs "
                            "human review."
                        )
                    }
                },
            },
        )
    except Exception:  # noqa: BLE001 - notification is non-critical
        pass
