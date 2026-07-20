"""Shared test fixtures. Forces mock mode (zero AWS) and isolates the store."""

import os

os.environ.setdefault("USE_BEDROCK", "false")
os.environ.setdefault("LOCAL_STEP_DELAY_SECONDS", "0")

import pytest

from app import agents, store


@pytest.fixture(autouse=True)
def _clean_store():
    store.reset()
    yield
    store.reset()


def _base_chart(**overrides) -> dict:
    chart = {
        "incidentId": "INC-2026-04837",
        "patient": {"age": 45, "sex": "M"},
        "payer": "AETNA",
        "chiefComplaint": "Chest pain",
        "mechanismOfInjury": "high-speed MVC with significant vehicular intrusion",
        "vitals": {"gcs": 14, "bp": "118/76", "hr": 110, "spo2": 94, "rr": 22},
        "interventions": ["18-gauge IV access", "cardiac monitoring"],
        "comorbidities": ["hypertension"],
        "levelOfService": "ALS",
        "transportPriority": "Priority 1 (emergent)",
        "narrative": "Emergent ALS transport of a patient with chest pain.",
    }
    chart.update(overrides)
    chart.setdefault("billedAmount", agents.rate_for(chart["levelOfService"]))
    return chart


@pytest.fixture
def strong_chart():
    """Necessity score 7 -> overturned at re-review (round 1)."""
    return _base_chart()


@pytest.fixture
def moderate_chart():
    """Score 3: below the re-review bar (5) but above the biased final bar (2)
    -> upheld at re-review, overturned at the round-2 final ruling."""
    return _base_chart(
        levelOfService="BLS",  # +0
        interventions=["patient assessment"],  # +0 (len 1)
        vitals={"gcs": 14, "bp": "120/80", "hr": 88, "spo2": 96, "rr": 18},  # gcs<15 +1
        comorbidities=["COPD"],  # +1
        mechanismOfInjury="ground-level fall",  # +0
        transportPriority="Priority 1 (emergent)",  # +1
    )


@pytest.fixture
def weak_chart():
    """Necessity score 0 -> upheld both rounds -> escalated to human."""
    return _base_chart(
        levelOfService="BLS",
        interventions=["patient assessment"],
        vitals={"gcs": 15, "bp": "120/80", "hr": 80, "spo2": 99, "rr": 14},
        comorbidities=[],
        mechanismOfInjury="none reported",
        transportPriority="Priority 3 (non-urgent)",
    )
