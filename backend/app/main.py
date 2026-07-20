"""FastAPI app + Mangum handler - the BFF described in ``docs/api-contract.md``.

Served under ``/api`` (API Gateway HTTP API -> Lambda via Mangum in prod; uvicorn
locally with the Vite dev proxy). Errors are returned as ``{"error": "..."}`` per
the contract rather than FastAPI's default ``{"detail": ...}``.
"""

from __future__ import annotations

import json
import threading
import uuid

from fastapi import FastAPI, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from mangum import Mangum
from starlette.exceptions import HTTPException as StarletteHTTPException

from . import agents, negotiation, nemsis_export, store
from .config import settings
from .models import (
    ExportNemsisRequest,
    ParseAudioRequest,
    ParseAudioResponse,
    SubmitClaimRequest,
    SubmitClaimResponse,
)
from .bedrock import BedrockError

app = FastAPI(title="EMS Agent BFF")


# --------------------------------------------------------------------------- #
# Error shaping -> {"error": "..."}
# --------------------------------------------------------------------------- #


@app.exception_handler(StarletteHTTPException)
async def _http_exc(_: Request, exc: StarletteHTTPException):
    return JSONResponse(status_code=exc.status_code, content={"error": exc.detail})


@app.exception_handler(RequestValidationError)
async def _validation_exc(_: Request, exc: RequestValidationError):
    return JSONResponse(status_code=400, content={"error": _first_error(exc)})


def _first_error(exc: RequestValidationError) -> str:
    errors = exc.errors()
    if not errors:
        return "invalid request"
    err = errors[0]
    loc = ".".join(str(p) for p in err.get("loc", ()) if p != "body")
    return f"{loc}: {err.get('msg', 'invalid')}".lstrip(": ")


def _error(status: int, message: str) -> JSONResponse:
    return JSONResponse(status_code=status, content={"error": message})


# --------------------------------------------------------------------------- #
# Endpoints
# --------------------------------------------------------------------------- #


@app.post("/api/parse-audio", response_model=ParseAudioResponse)
def parse_audio(body: ParseAudioRequest):
    if not body.transcript.strip():
        return _error(400, "transcript is required")
    try:
        chart = agents.parse_chart(body.transcript)
    except BedrockError as exc:
        return _error(502, f"model failure: {exc}")
    return {"chartId": str(uuid.uuid4()), "chart": chart}


@app.post("/api/export-nemsis")
def export_nemsis(body: ExportNemsisRequest):
    """Additive path (docs/nemsis-export.md) - does not change the frozen
    ePCRChart JSON shape in docs/api-contract.md."""
    xml_bytes = nemsis_export.to_nemsis_xml(body.chart.model_dump())
    return Response(content=xml_bytes, media_type="application/xml")


@app.post("/api/submit-claim", status_code=202, response_model=SubmitClaimResponse)
def submit_claim(body: SubmitClaimRequest):
    new_job_id = str(uuid.uuid4())
    job_id = store.reserve_idempotency(body.idempotencyKey, new_job_id)
    if job_id != new_job_id:
        # Duplicate submit: return the existing job untouched.
        existing = store.get_job(job_id)
        status = existing["status"] if existing else "PENDING"
        return {"jobId": job_id, "status": status}

    chart = body.chart.model_dump()
    store.create_job(job_id, chart)
    store.append_audit(job_id, "Claim submitted to clearinghouse")
    _start_workflow(job_id, chart)
    return {"jobId": job_id, "status": "PENDING"}


@app.get("/api/submit-claim/{job_id}")
def get_claim(job_id: str):
    job = store.get_job(job_id)
    if job is None:
        return _error(404, "unknown jobId")
    return {
        "jobId": job_id,
        "status": job["status"],
        "rounds": job.get("rounds", []),
        "outcome": job.get("outcome"),
        "recoveredAmount": job.get("recoveredAmount"),
        "auditTrail": job.get("auditTrail", []),
    }


# --------------------------------------------------------------------------- #
# Workflow start: Step Functions (deployed) or in-process thread (local)
# --------------------------------------------------------------------------- #


def _start_workflow(job_id: str, chart: dict) -> None:
    cfg = settings()
    if cfg.use_bedrock and cfg.state_machine_arn:
        import boto3

        boto3.client("stepfunctions", region_name=cfg.aws_region).start_execution(
            stateMachineArn=cfg.state_machine_arn,
            name=job_id,
            input=json.dumps({"jobId": job_id, "chart": chart}),
        )
    else:
        threading.Thread(
            target=negotiation.run_local,
            args=(job_id, chart),
            kwargs={"delay": cfg.local_step_delay},
            daemon=True,
        ).start()


# Mangum adapter - the Lambda entrypoint referenced by SAM (app.main.handler).
# API Gateway HTTP API includes the stage name in rawPath (e.g. "/prod/api/...");
# strip it so FastAPI's routes ("/api/...") match.
_stage = settings().stage_name
handler = Mangum(app, api_gateway_base_path=f"/{_stage}" if _stage else "/")
