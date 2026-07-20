# Workflow Contract (FROZEN)

The internal interface between the **backend Step Functions task handlers** (Workstream A) and the
**Step Functions state machine / infra** (Workstream C). This is to the A<->C seam what
`api-contract.md` is to the B<->A seam. Do not change shapes without updating this file and flagging it.

The frontend never sees any of this - it only reads the DynamoDB-backed job record via `GET /api/submit-claim/{jobId}` (see `api-contract.md`).

---

## Execution input

`ApiFunction` (POST /api/submit-claim) writes the initial job record, then starts the state machine with:

```jsonc
{ "jobId": "uuid", "chart": ePCRChart }
```

## State object (passed state -> state)

Every task handler receives the current state JSON and returns the **merged** state JSON (Step Functions
passes each state's output to the next). The Choice states branch **only** on `decision` and `round`.

```jsonc
{
  "jobId": "uuid",
  "chart": ePCRChart,          // unchanged throughout
  "payer": "AETNA" | "MEDICARE", // resolved from chart.payer; selects the policy file
  "round": 1,                    // 1 at ReReview, 2 at FinalRuling (see invariant below)
  "decision": "overturn" | "uphold" | null  // set by ReReview and FinalRuling; read by Choice states
}
```

**Round invariant (what the ASL relies on):** `Deny` initializes `round = 1`. When the negotiation
enters round 2 (the `EscalateAppeal` state), `round` becomes `2`, so `FinalRuling` always runs with
`round == 2`. Backend owns incrementing it; the ASL only reads it.

## Handler responsibilities (Workstream A)

Each handler is a pure-ish function `state -> state` plus a **side effect**: it appends to the DynamoDB
job record (rounds / auditTrail) and updates `status`. Handlers call Bedrock via the shared wrapper
(mock when `USE_BEDROCK=false`).

| Handler (`app.handlers.*`) | Reads | Writes to state | DynamoDB side effect |
|---|---|---|---|
| `deny` | chart, payer, policy | `round=1` | status=`DENIED`; append denial round + audit |
| `appeal` | chart, denial, policy | - | status=`APPEALING`; append appeal round + audit |
| `rereview` | chart, appeal, policy | `decision` | status=`NEGOTIATING`; append ruling round + audit |
| `final_ruling` | chart, appeal, policy | `decision` (prompt-biased to overturn) | append final ruling round + audit |
| `resolve` | chart | - | status=`RESOLVED`, outcome=`OVERTURNED`, recoveredAmount=`chart.billedAmount`; audit |
| `escalate` | chart, denial | - | status=`ESCALATED`, outcome=`ESCALATED`, recoveredAmount=BLS rate if the original denial was `DOWNGRADE` else `0`; audit; optional SES email if `ENABLE_SES_EMAIL=true` |

`EscalateAppeal` reuses the `appeal` handler; it must set `round=2`.

## DynamoDB job record (single table `JobsTable`, key `pk`)

Two item kinds share the table:

```jsonc
// Job item
{
  "pk": "<jobId>",
  "status": JobStatus,                 // see api-contract.md
  "chart": ePCRChart,
  "rounds": [ NegotiationRound ],       // append-only, ordered
  "outcome": Outcome,                   // null until terminal
  "recoveredAmount": number|null,       // null until terminal; see api-contract.md "Recovery amounts"
  "auditTrail": [ AuditEntry ],         // append-only, ordered
  "createdAt": "ISO-8601",
  "updatedAt": "ISO-8601",
  "ttl": 1712345678                     // epoch seconds, createdAt + 7 days
}

// Idempotency item (dedupes double-submit)
{ "pk": "IDEMPOTENCY#<idempotencyKey>", "jobId": "<jobId>", "ttl": 1712345678 }
```

`store.py` (Workstream A) owns all reads/writes. Idempotency: `submit-claim` does a conditional put on
the `IDEMPOTENCY#<key>` item; if it already exists, return the stored `jobId` without starting a new execution.

## Local / mock orchestration (no Step Functions)

When `USE_BEDROCK=false` or running locally, there is no Step Functions. `submit-claim` runs the **same
handler functions** through a simple in-process driver (`app.negotiation.run_local(state)`) that follows
the identical order and Choice logic as `negotiation.asl.json`, producing an identical DynamoDB job record.
This is what makes the full flow testable locally for free. Keep the ASL and `run_local` behaviorally in sync.
