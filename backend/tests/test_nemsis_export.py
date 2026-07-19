"""NEMSIS v3.5 export: well-formedness and element mapping (docs/nemsis-export.md)."""

import xml.etree.ElementTree as ET

from app.nemsis_export import NEMSIS_NAMESPACE, NV_NOT_RECORDED, to_nemsis_xml

from conftest import _base_chart


def _parse(chart: dict) -> ET.Element:
    xml_bytes = to_nemsis_xml(chart)
    assert xml_bytes.startswith(b"<?xml version=\"1.0\" encoding=\"UTF-8\"?>")
    return ET.fromstring(xml_bytes)  # raises if not well-formed


def _find(root: ET.Element, path: str) -> ET.Element:
    ns = {"n": NEMSIS_NAMESPACE}
    el = root.find(path, ns)
    assert el is not None, f"missing element {path}"
    return el


def test_well_formed_and_namespaced():
    root = _parse(_base_chart())
    assert root.tag == f"{{{NEMSIS_NAMESPACE}}}PatientCareReport"
    assert root.get("nemsisVersion") == "3.5.0"


def test_maps_representative_chart_fields():
    chart = _base_chart()
    root = _parse(chart)

    assert _find(root, "n:eRecord/n:eRecord.01").text == chart["incidentId"]
    assert _find(root, "n:ePatient/n:ePatient.15").text == str(chart["patient"]["age"])
    assert _find(root, "n:ePatient/n:ePatient.25").text == chart["patient"]["sex"]
    assert _find(root, "n:ePayment/n:ePayment.01").text == chart["payer"]
    assert _find(root, "n:eResponse/n:eResponse.05").text == chart["levelOfService"]
    assert _find(root, "n:eResponse/n:eResponse.23").text == chart["transportPriority"]

    sbp, dbp = chart["vitals"]["bp"].split("/")
    assert _find(root, "n:eVitals/n:eVitals.06").text == sbp
    assert _find(root, "n:eVitals/n:eVitals.07").text == dbp
    assert _find(root, "n:eVitals/n:eVitals.10").text == str(chart["vitals"]["hr"])
    assert _find(root, "n:eVitals/n:eVitals.12").text == str(chart["vitals"]["spo2"])
    assert _find(root, "n:eVitals/n:eVitals.14").text == str(chart["vitals"]["rr"])
    assert _find(root, "n:eVitals/n:eVitals.23").text == str(chart["vitals"]["gcs"])

    narrative = _find(root, "n:eNarrative/n:eNarrative.01").text
    assert chart["chiefComplaint"] in narrative
    assert chart["mechanismOfInjury"] in narrative
    assert chart["interventions"][0] in narrative
    assert chart["comorbidities"][0] in narrative
    assert chart["narrative"] in narrative


def test_null_vitals_use_not_recorded_nv_attribute():
    chart = _base_chart(vitals={"gcs": None, "bp": None, "hr": None, "spo2": None, "rr": None})
    root = _parse(chart)

    for tag in ("eVitals.06", "eVitals.07", "eVitals.10", "eVitals.12", "eVitals.14", "eVitals.23"):
        el = _find(root, f"n:eVitals/n:{tag}")
        assert el.get("NV") == NV_NOT_RECORDED
        assert el.text is None


def test_malformed_bp_string_is_not_recorded_not_a_crash():
    chart = _base_chart(vitals={"gcs": 15, "bp": "unreadable", "hr": 80, "spo2": 99, "rr": 14})
    root = _parse(chart)
    assert _find(root, "n:eVitals/n:eVitals.06").get("NV") == NV_NOT_RECORDED
    assert _find(root, "n:eVitals/n:eVitals.07").get("NV") == NV_NOT_RECORDED


def test_empty_interventions_and_comorbidities_omitted_from_narrative():
    chart = _base_chart(interventions=[], comorbidities=[])
    root = _parse(chart)
    narrative = _find(root, "n:eNarrative/n:eNarrative.01").text
    assert "Interventions:" not in narrative
    assert "Comorbidities:" not in narrative
