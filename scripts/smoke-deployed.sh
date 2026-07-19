#!/usr/bin/env bash
# Smoke test for a *deployed* EMS Agent stack: submits a claim to the live
# API and polls until the negotiation reaches a terminal state.
#
# Not part of pytest/CI - it needs a live API URL and would break CI runs
# that have no deployed stack. Run it manually after `sam deploy`:
#
#   ./scripts/smoke-deployed.sh https://<api-id>.execute-api.<region>.amazonaws.com/prod
#
# Exits 0 on RESOLVED/ESCALATED, 1 on ERROR/timeout/HTTP failure.

set -euo pipefail

API_BASE="${1:?usage: smoke-deployed.sh <api-base-url> (e.g. .../prod)}"
POLL_ATTEMPTS="${POLL_ATTEMPTS:-30}"
POLL_INTERVAL_SECONDS="${POLL_INTERVAL_SECONDS:-3}"

IDEMPOTENCY_KEY="smoke-$(date -u +%Y%m%dT%H%M%S)-$$"

CHART=$(cat <<JSON
{
  "incidentId": "INC-SMOKE-$$",
  "patient": {"age": 61, "sex": "F"},
  "payer": "AETNA",
  "chiefComplaint": "chest pain",
  "mechanismOfInjury": "N/A - medical",
  "vitals": {"gcs": 15, "bp": "142/90", "hr": 102, "spo2": 94, "rr": 20},
  "interventions": ["12-lead ECG", "18-gauge IV access", "cardiac monitoring", "oxygen 4L NC"],
  "comorbidities": ["hypertension", "type 2 diabetes"],
  "levelOfService": "ALS",
  "transportPriority": "Priority 1 (emergent)",
  "narrative": "61yo F with acute onset chest pain radiating to left arm, diaphoretic, ALS transport with continuous cardiac monitoring."
}
JSON
)

echo "==> POST ${API_BASE}/api/submit-claim"
SUBMIT_RESP=$(curl -sS -w '\n%{http_code}' "${API_BASE}/api/submit-claim" \
  -H "Content-Type: application/json" \
  -d "{\"chart\": ${CHART}, \"idempotencyKey\": \"${IDEMPOTENCY_KEY}\"}")
SUBMIT_STATUS="${SUBMIT_RESP##*$'\n'}"
SUBMIT_BODY="${SUBMIT_RESP%$'\n'*}"

if [ "$SUBMIT_STATUS" != "202" ]; then
  echo "FAIL: submit-claim returned HTTP $SUBMIT_STATUS: $SUBMIT_BODY" >&2
  exit 1
fi

JOB_ID=$(printf '%s' "$SUBMIT_BODY" | python3 -c "import sys,json; print(json.load(sys.stdin)['jobId'])")
echo "==> jobId=$JOB_ID"

for i in $(seq 1 "$POLL_ATTEMPTS"); do
  POLL_RESP=$(curl -sS "${API_BASE}/api/submit-claim/${JOB_ID}")
  STATUS=$(printf '%s' "$POLL_RESP" | python3 -c "import sys,json; print(json.load(sys.stdin).get('status',''))")
  echo "[$i/${POLL_ATTEMPTS}] status=$STATUS"
  case "$STATUS" in
    RESOLVED|ESCALATED)
      printf '%s' "$POLL_RESP" | python3 -m json.tool
      echo "==> smoke test PASSED (terminal status: $STATUS)"
      exit 0
      ;;
    ERROR)
      printf '%s' "$POLL_RESP" | python3 -m json.tool >&2
      echo "FAIL: job reached ERROR status" >&2
      exit 1
      ;;
  esac
  sleep "$POLL_INTERVAL_SECONDS"
done

echo "FAIL: job $JOB_ID did not reach a terminal status after $POLL_ATTEMPTS attempts" >&2
exit 1
