# Deploy Validation Notes

Findings from validating a real `sam deploy` of `infra/template.yaml` against AWS (branch
`track/infra-deploy-validation`, PR #9).
Both bugs below were invisible in local dev and CI (`validate`/`test` workflows) because neither
exercises a live API Gateway stage - they only showed up once the stack was actually deployed and hit.

## Bug 1: every request 404'd behind API Gateway

`Mangum(app)` was constructed with no `api_gateway_base_path`.
API Gateway HTTP API includes the stage name in `rawPath` (e.g. `/prod/api/submit-claim`), but
FastAPI's routes are registered as `/api/submit-claim`.
Mangum passed the un-stripped path straight to FastAPI's router, so every route missed and returned 404.
This hit both the direct API Gateway invoke URL and CloudFront's `/api/*` proxy, since CloudFront's
origin path also forwards through `/prod`.

**Fix:** a new `STAGE_NAME` env var (set from the SAM `StageName` parameter, empty in local dev) is
read in `backend/app/config.py` and passed to Mangum as `api_gateway_base_path` in `backend/app/main.py`.
Empty stage name (local `uvicorn`) means no prefix is stripped, which is correct since there is no stage
prefix locally.

## Bug 2: `deploy.yml` param overrides broke when optional emails were unset

The old `--parameter-overrides` block interpolated GitHub Actions `vars.*` directly inline:

```
--parameter-overrides StageName=prod BudgetAlertEmail=${{ vars.BUDGET_ALERT_EMAIL }} ...
```

When `BUDGET_ALERT_EMAIL` / `ESCALATION_EMAIL` repo vars are unset (the common case for this
low-budget prototype), this rendered as `BudgetAlertEmail=` with no value. SAM CLI's shorthand
parser rejects a bare `Key=` with nothing after it and fails the *entire* `--parameter-overrides`
string, not just that key.

**Fix:** `deploy.yml` now builds the override string in a shell step, and only appends
`BudgetAlertEmail=...` / `EscalationEmail=...` when the corresponding var is non-empty. When
omitted, the template's own `Default:` for that parameter applies - same effective behavior, but
without failing the shorthand parser.

## Added: `scripts/smoke-deployed.sh`

A manual smoke test - `POST /api/submit-claim` against a live deployed API, then poll
`GET /api/submit-claim/{jobId}` until a terminal status (`RESOLVED`/`ESCALATED`) or timeout.
Deliberately kept out of `pytest`/CI since it needs a real deployed API URL and live AWS resources
(Bedrock, Step Functions, DynamoDB) - it would break CI runs that have no deployed stack.

Run manually after `sam deploy`:

```
./scripts/smoke-deployed.sh https://<api-id>.execute-api.<region>.amazonaws.com/prod
```

## Deployment status

Both fixes are live: the `deploy` workflow run against this branch (`workflow_dispatch`, run
`29704342091`) uploaded these exact built artifacts and CloudFormation reported
`No changes to deploy. Stack ems-agent-stack is up to date` - i.e. this commit's code already
matched what's deployed. `test` and `validate` also passed on PR #9.

No deviation from the frozen contracts (`api-contract.md`, `workflow-contract.md`) - both bugs were
plumbing/infra issues, not shape changes.
