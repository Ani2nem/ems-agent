"""Pydantic request/response models mirroring ``docs/api-contract.md``.

The internal negotiation state and DynamoDB job record are plain dicts (see
``docs/workflow-contract.md``); only the HTTP boundary is typed here.
"""

from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field


class Vitals(BaseModel):
    gcs: Optional[int] = None
    bp: Optional[str] = None
    hr: Optional[int] = None
    spo2: Optional[int] = None
    rr: Optional[int] = None


class Patient(BaseModel):
    age: Optional[int] = None
    sex: str


class EPCRChart(BaseModel):
    incidentId: str
    patient: Patient
    payer: Literal["AETNA", "MEDICARE"]
    chiefComplaint: str
    mechanismOfInjury: str
    vitals: Vitals
    interventions: list[str] = Field(default_factory=list)
    comorbidities: list[str] = Field(default_factory=list)
    levelOfService: Literal["BLS", "ALS"]
    transportPriority: str
    narrative: str


class ParseAudioRequest(BaseModel):
    transcript: str


class ParseAudioResponse(BaseModel):
    chartId: str
    chart: EPCRChart


class SubmitClaimRequest(BaseModel):
    chart: EPCRChart
    idempotencyKey: str


class SubmitClaimResponse(BaseModel):
    jobId: str
    status: str
