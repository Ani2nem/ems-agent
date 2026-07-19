"""Job-record persistence (see ``docs/workflow-contract.md``).

Two backends behind one API, selected by ``USE_BEDROCK``:

* mock mode -> a thread-safe in-process dict (background negotiation thread and
  the request handlers share it).
* deployed  -> the single DynamoDB ``JobsTable`` (job items keyed by ``jobId``,
  idempotency items keyed by ``IDEMPOTENCY#<key>``).

Both share the append-only ``rounds`` / ``auditTrail`` semantics the API contract
promises: entries are appended in order and never mutated retroactively.
"""

from __future__ import annotations

import threading
import time
from datetime import datetime, timezone
from typing import Optional

from .config import settings

_TTL_SECONDS = 7 * 24 * 60 * 60


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _ttl() -> int:
    return int(time.time()) + _TTL_SECONDS


def _idem_pk(key: str) -> str:
    return f"IDEMPOTENCY#{key}"


# --------------------------------------------------------------------------- #
# In-memory backend (mock / local / tests)
# --------------------------------------------------------------------------- #

_lock = threading.Lock()
_jobs: dict[str, dict] = {}
_idem: dict[str, str] = {}


def reset() -> None:
    """Clear the in-memory store. Used between tests; no-op semantics in prod."""
    with _lock:
        _jobs.clear()
        _idem.clear()


class _Memory:
    def create_job(self, job_id: str, chart: dict) -> None:
        now = _now_iso()
        with _lock:
            _jobs[job_id] = {
                "pk": job_id,
                "status": "PENDING",
                "chart": chart,
                "rounds": [],
                "outcome": None,
                "auditTrail": [],
                "createdAt": now,
                "updatedAt": now,
                "ttl": _ttl(),
            }

    def get_job(self, job_id: str) -> Optional[dict]:
        with _lock:
            job = _jobs.get(job_id)
            return dict(job) if job else None

    def append_round(self, job_id: str, rnd: dict) -> None:
        with _lock:
            job = _jobs[job_id]
            job["rounds"].append(rnd)
            job["updatedAt"] = _now_iso()

    def append_audit(self, job_id: str, event: str) -> None:
        with _lock:
            job = _jobs[job_id]
            job["auditTrail"].append({"ts": _now_iso(), "event": event})
            job["updatedAt"] = _now_iso()

    def update_status(self, job_id: str, status: str, outcome: Optional[str] = None) -> None:
        with _lock:
            job = _jobs[job_id]
            job["status"] = status
            if outcome is not None:
                job["outcome"] = outcome
            job["updatedAt"] = _now_iso()

    def reserve_idempotency(self, key: str, new_job_id: str) -> str:
        """Return the authoritative jobId for ``key`` (existing wins over new)."""
        with _lock:
            return _idem.setdefault(key, new_job_id)


# --------------------------------------------------------------------------- #
# DynamoDB backend (deployed)
# --------------------------------------------------------------------------- #


class _Dynamo:
    def __init__(self) -> None:
        import boto3  # local import: never needed in mock mode

        self._table = boto3.resource(
            "dynamodb", region_name=settings().aws_region
        ).Table(settings().jobs_table)

    def create_job(self, job_id: str, chart: dict) -> None:
        now = _now_iso()
        self._table.put_item(
            Item={
                "pk": job_id,
                "status": "PENDING",
                "chart": chart,
                "rounds": [],
                "outcome": None,
                "auditTrail": [],
                "createdAt": now,
                "updatedAt": now,
                "ttl": _ttl(),
            }
        )

    def get_job(self, job_id: str) -> Optional[dict]:
        return self._table.get_item(Key={"pk": job_id}).get("Item")

    def append_round(self, job_id: str, rnd: dict) -> None:
        self._table.update_item(
            Key={"pk": job_id},
            UpdateExpression="SET rounds = list_append(rounds, :r), updatedAt = :u",
            ExpressionAttributeValues={":r": [rnd], ":u": _now_iso()},
        )

    def append_audit(self, job_id: str, event: str) -> None:
        self._table.update_item(
            Key={"pk": job_id},
            UpdateExpression="SET auditTrail = list_append(auditTrail, :a), updatedAt = :u",
            ExpressionAttributeValues={
                ":a": [{"ts": _now_iso(), "event": event}],
                ":u": _now_iso(),
            },
        )

    def update_status(self, job_id: str, status: str, outcome: Optional[str] = None) -> None:
        expr = "SET #s = :s, updatedAt = :u"
        values = {":s": status, ":u": _now_iso()}
        if outcome is not None:
            expr += ", outcome = :o"
            values[":o"] = outcome
        self._table.update_item(
            Key={"pk": job_id},
            UpdateExpression=expr,
            ExpressionAttributeNames={"#s": "status"},
            ExpressionAttributeValues=values,
        )

    def reserve_idempotency(self, key: str, new_job_id: str) -> str:
        from botocore.exceptions import ClientError

        try:
            self._table.put_item(
                Item={"pk": _idem_pk(key), "jobId": new_job_id, "ttl": _ttl()},
                ConditionExpression="attribute_not_exists(pk)",
            )
            return new_job_id
        except ClientError as exc:
            if exc.response["Error"]["Code"] != "ConditionalCheckFailedException":
                raise
            item = self._table.get_item(Key={"pk": _idem_pk(key)}).get("Item", {})
            return item.get("jobId", new_job_id)


# --------------------------------------------------------------------------- #
# Backend selection
# --------------------------------------------------------------------------- #

_memory = _Memory()
_dynamo: Optional[_Dynamo] = None


def _backend():
    global _dynamo
    if not settings().use_bedrock:
        return _memory
    if _dynamo is None:
        _dynamo = _Dynamo()
    return _dynamo


def create_job(job_id: str, chart: dict) -> None:
    _backend().create_job(job_id, chart)


def get_job(job_id: str) -> Optional[dict]:
    return _backend().get_job(job_id)


def append_round(job_id: str, rnd: dict) -> None:
    _backend().append_round(job_id, rnd)


def append_audit(job_id: str, event: str) -> None:
    _backend().append_audit(job_id, event)


def update_status(job_id: str, status: str, outcome: Optional[str] = None) -> None:
    _backend().update_status(job_id, status, outcome)


def reserve_idempotency(key: str, new_job_id: str) -> str:
    return _backend().reserve_idempotency(key, new_job_id)
