# API Contract (FROZEN)

This is the single source of truth for the interface between the frontend, the backend/BFF, and the negotiation workflow. **Do not change shapes without updating this file and notifying all workstreams.**

All request/response bodies are JSON. The API is served under `/api` (API Gateway HTTP API → Lambda FastAPI via Mangum). Base URL is the CloudFront/API-Gateway origin in prod, and `http://localhost:8000` in local dev (Vite proxies `/api` to it).

---

## Types

### `ePCRChart`
NEMSIS-inspired structured patient care report.

```jsonc
{
  "incidentId": "string",            // e.g. "INC-2026-04837"
  "patient": { "age": 45, "sex": "M" },
  "payer": "AETNA" | "MEDICARE",     // drives payer-based policy retrieval
  "chiefComplaint": "string",
  "mechanismOfInjury": "string",     // clinical phrasing, e.g. "high-speed MVC with significant vehicular intrusion"
  "vitals": {
    "gcs": 15,                        // number|null
    "bp": "120/80",                   // string|null
    "hr": 98,                         // number|null
    "spo2": 96,                       // number|null (percent)
    "rr": 18                          // number|null
  },
  "interventions": ["string"],        // e.g. ["18-gauge IV access", "cardiac monitoring"]
  "comorbidities": ["string"],
  "levelOfService": "BLS" | "ALS",
  "transportPriority": "string",      // e.g. "Priority 1 (emergent)"
  "narrative": "string"               // cleaned clinical narrative
}
```

### `NegotiationRound`
```jsonc
{
  "round": 1,                                         // 1-based
  "actor": "payer" | "defense",
  "type": "denial" | "appeal" | "ruling",
  "reasonCode": "CO-50" | "CO-16" | "CO-11" | "DOWNGRADE" | null,
  "content": "string",                                // Markdown for appeals/rulings, prose for denials
  "timestamp": "ISO-8601 string"
}
```

### `AuditEntry`
```jsonc
{ "ts": "ISO-8601 string", "event": "string" }        // e.g. "Denial intercepted"
```

### `JobStatus` (enum)
`"PENDING" | "DENIED" | "APPEALING" | "NEGOTIATING" | "RESOLVED" | "ESCALATED" | "ERROR"`

### `Outcome` (enum)
`"OVERTURNED" | "ESCALATED" | null`

---

## Endpoints

### `POST /api/parse-audio`
Turn a raw dictation transcript into a structured ePCR chart.

- **Request**
  ```jsonc
  { "transcript": "string" }
  ```
- **Response `200`**
  ```jsonc
  { "chartId": "uuid", "chart": ePCRChart }
  ```
- **Errors**: `400` (empty transcript), `502` (model/upstream failure) → `{ "error": "string" }`

---

### `POST /api/submit-claim`
Submit an approved chart. Starts the async negotiation workflow and returns immediately.

- **Request**
  ```jsonc
  { "chart": ePCRChart, "idempotencyKey": "uuid" }   // client-generated key; dedupes double-submits
  ```
- **Response `202`**
  ```jsonc
  { "jobId": "uuid", "status": "PENDING" }
  ```
  Re-submitting with the same `idempotencyKey` returns the **existing** `jobId` (no new workflow).
- **Errors**: `400` (missing/invalid chart) → `{ "error": "string" }`

---

### `GET /api/submit-claim/{jobId}`
Poll for negotiation progress and result. Frontend polls this (~1s interval) until `status` is terminal (`RESOLVED`, `ESCALATED`, or `ERROR`).

- **Response `200`**
  ```jsonc
  {
    "jobId": "uuid",
    "status": JobStatus,
    "rounds": [ NegotiationRound, ... ],   // grows as the workflow progresses
    "outcome": Outcome,                     // set when terminal
    "auditTrail": [ AuditEntry, ... ]
  }
  ```
- **Errors**: `404` (unknown jobId) → `{ "error": "string" }`

---

## Status progression (what the frontend renders)

```
PENDING     → workflow starting (Wait state simulating clearinghouse loop)
DENIED      → payer denial available (rounds[0]); frontend flashes red banner
APPEALING   → defense appeal available; banner flips green
NEGOTIATING → re-review / round 2 in progress
RESOLVED    → outcome=OVERTURNED; green "Revenue Recovered"
ESCALATED   → outcome=ESCALATED; "Escalated - Human Review"
ERROR       → surfaced to user; safe to retry with a new idempotencyKey
```

The frontend is driven entirely by `status` + the growing `rounds`/`auditTrail` arrays. New rounds appended in order; never mutated retroactively.
