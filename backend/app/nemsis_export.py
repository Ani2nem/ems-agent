"""EPCRChart -> NEMSIS v3.5 XML export.

Additive path alongside the frozen JSON ``ePCRChart`` shape in
``docs/api-contract.md`` - it does not change that contract. See
``docs/nemsis-export.md`` for the element-mapping table, sourcing, and
explicit scope/limitations (this is a well-formed, focused-subset export,
not a certified/registry-submittable NEMSIS file).

Element IDs below are drawn from the public NEMSIS v3.5 National EMS Data
Dictionary (nemsis.org) for the fields this chart actually captures. Fields
with no clean unlicensed-vocabulary NEMSIS home (NEMSIS favors SNOMED/ICD
coded pick-lists we have no code table for) are folded into the genuine
free-text narrative element (``eNarrative.01``) instead of being forced into
a coded element they don't validly belong in.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from typing import Optional

# Real NEMSIS v3.5 targetNamespace (eRecord_v3.xsd et al.).
NEMSIS_NAMESPACE = "http://www.nemsis.org"

# Standard NEMSIS "NOT Value" codes used to mark a coded/numeric element as
# present-but-empty rather than just omitting it (NEMSIS v3.5 Data Dictionary).
NV_NOT_RECORDED = "7701003"  # element is applicable but was left blank


def _numeric(parent: ET.Element, tag: str, value: Optional[int]) -> None:
    el = ET.SubElement(parent, tag)
    if value is None:
        el.set("NV", NV_NOT_RECORDED)
    else:
        el.text = str(value)


def _text(parent: ET.Element, tag: str, value: Optional[str]) -> None:
    el = ET.SubElement(parent, tag)
    if value is None or value == "":
        el.set("NV", NV_NOT_RECORDED)
    else:
        el.text = value


def _split_bp(bp: Optional[str]) -> tuple[Optional[int], Optional[int]]:
    if not bp:
        return None, None
    parts = bp.split("/")
    if len(parts) != 2:
        return None, None
    try:
        return int(parts[0].strip()), int(parts[1].strip())
    except ValueError:
        return None, None


def _compose_narrative(chart: dict) -> str:
    """Fold the fields NEMSIS would otherwise require coded/SNOMED values for
    into the genuine free-text narrative element, in the CC/MOI/Hx/Rx prose
    style real EMS charting already uses for exactly this situation."""
    lines = [
        f"Chief Complaint: {chart['chiefComplaint']}",
        f"Mechanism of Injury: {chart['mechanismOfInjury']}",
    ]
    if chart.get("interventions"):
        lines.append("Interventions: " + "; ".join(chart["interventions"]))
    if chart.get("comorbidities"):
        lines.append("Comorbidities: " + "; ".join(chart["comorbidities"]))
    lines.append("")
    lines.append(chart["narrative"])
    return "\n".join(lines)


def to_nemsis_xml(chart: dict) -> bytes:
    """Serialize an ``ePCRChart`` dict (post ``EPCRChart.model_dump()``) to
    well-formed NEMSIS v3.5-shaped XML. Returns UTF-8 encoded bytes with an
    XML declaration."""
    root = ET.Element("PatientCareReport", {"xmlns": NEMSIS_NAMESPACE, "nemsisVersion": "3.5.0"})

    e_record = ET.SubElement(root, "eRecord")
    _text(e_record, "eRecord.01", chart["incidentId"])  # PCR unique record number

    e_patient = ET.SubElement(root, "ePatient")
    _numeric(e_patient, "ePatient.15", chart["patient"]["age"])  # Age
    _text(e_patient, "ePatient.25", chart["patient"]["sex"])  # Sex

    e_payment = ET.SubElement(root, "ePayment")
    _text(e_payment, "ePayment.01", chart["payer"])  # Primary Method of Payment

    e_response = ET.SubElement(root, "eResponse")
    _text(e_response, "eResponse.05", chart["levelOfService"])  # Type of Service Requested (BLS/ALS)
    _text(e_response, "eResponse.23", chart["transportPriority"])  # Response Mode to Scene

    vitals = chart["vitals"]
    sbp, dbp = _split_bp(vitals.get("bp"))
    e_vitals = ET.SubElement(root, "eVitals")
    _numeric(e_vitals, "eVitals.06", sbp)  # Systolic Blood Pressure
    _numeric(e_vitals, "eVitals.07", dbp)  # Diastolic Blood Pressure
    _numeric(e_vitals, "eVitals.10", vitals.get("hr"))  # Heart Rate
    _numeric(e_vitals, "eVitals.12", vitals.get("spo2"))  # Pulse Oximetry
    _numeric(e_vitals, "eVitals.14", vitals.get("rr"))  # Respiratory Rate
    _numeric(e_vitals, "eVitals.23", vitals.get("gcs"))  # Total Glasgow Coma Score

    e_narrative = ET.SubElement(root, "eNarrative")
    _text(e_narrative, "eNarrative.01", _compose_narrative(chart))

    ET.indent(root, space="  ")
    return b'<?xml version="1.0" encoding="UTF-8"?>\n' + ET.tostring(root, encoding="UTF-8")
