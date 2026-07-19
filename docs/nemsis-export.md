# NEMSIS v3.5 export (scope and limitations)

`POST /api/export-nemsis` (`{ "chart": ePCRChart }` -> `application/xml`) is an
additive path.
It does not change the frozen `ePCRChart` JSON shape in `docs/api-contract.md`.

## Why this exists

The `ePCRChart` JSON (`docs/api-contract.md`, `backend/app/models.py`) is
"NEMSIS-inspired" - it borrows NEMSIS's field vocabulary (GCS, level of
service, transport priority) but is a flat demo shape, not a real NEMSIS
submission.
Real NEMSIS v3.5 is an XSD-governed XML format with coded elements and a
state/national EMS registry pipeline.
This export produces genuine NEMSIS v3.5 element structure for the fields
this chart actually captures, so the "NEMSIS" claim is backed by something
real rather than just vocabulary borrowing.

## What this is not

- **Not certified or registry-submittable.** A real submission needs the
  full NEMSIS XSD, Schematron validation, and a state's certified NEMSIS
  Reference Implementation toolchain.
- **Not validated against the national XSD.** This module guarantees
  well-formed XML (`xml.etree.ElementTree` round-trips it) with correct
  NEMSIS element IDs and nesting, not full schema conformance.
- **No SNOMED/ICD coding.** NEMSIS's coded pick-list elements (procedures,
  medical history, symptom taxonomy) require licensed clinical vocabularies
  this prototype has no access to. Rather than force free text into a coded
  element it doesn't validly belong in, `chiefComplaint`, `mechanismOfInjury`,
  `interventions`, and `comorbidities` are folded into the genuine free-text
  narrative element (`eNarrative.01`), in the CC/MOI/Hx/Rx prose style real
  EMS charting already uses for exactly this situation.

## Element mapping

Element IDs are drawn from the public NEMSIS v3.5 National EMS Data
Dictionary (nemsis.org).

| `ePCRChart` field | NEMSIS v3.5 element | Element name |
|---|---|---|
| `incidentId` | `eRecord.01` | EMS Agency's Unique Patient Care Report Number |
| `patient.age` | `ePatient.15` | Age |
| `patient.sex` | `ePatient.25` | Sex |
| `payer` | `ePayment.01` | Primary Method of Payment |
| `levelOfService` | `eResponse.05` | Type of Service Requested |
| `transportPriority` | `eResponse.23` | Response Mode to Scene |
| `vitals.bp` (split) | `eVitals.06` / `eVitals.07` | Systolic / Diastolic Blood Pressure |
| `vitals.hr` | `eVitals.10` | Heart Rate |
| `vitals.spo2` | `eVitals.12` | Pulse Oximetry |
| `vitals.rr` | `eVitals.14` | Respiratory Rate |
| `vitals.gcs` | `eVitals.23` | Total Glasgow Coma Score |
| `chiefComplaint`, `mechanismOfInjury`, `interventions`, `comorbidities`, `narrative` | `eNarrative.01` | Narrative (composed) |

`ePayment.01`, `eResponse.05`, and `eResponse.23` are coded elements in the
real standard; this export writes our own closed-enum label text
(`AETNA`/`MEDICARE`, `BLS`/`ALS`, the transport priority string) into them
rather than a licensed NEMSIS numeric code, since we don't have access to
the certified code-value-domain tables. This is the main reason the output
is well-formed but not XSD-valid.

## Null handling

NEMSIS v3.5 represents an applicable-but-blank coded/numeric element with an
`NV` (Not Value) attribute rather than omitting it. This export uses
`NV="7701003"` ("Not Recorded") for any `null` vitals field or blank string
field, matching the real standard's convention.
