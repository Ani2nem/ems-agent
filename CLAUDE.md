# EMS Agent - Team Rulebook

Autonomous EMS (ambulance) **Revenue Cycle Management + Ambient Documentation** prototype.
Production-shaped serverless, built deliberately cheap (target: well under $10 total AWS spend). Read this first.

## Frozen sources of truth - do NOT change these shapes without updating the doc and flagging it in your PR
- `docs/api-contract.md` - HTTP interface between frontend and backend. FROZEN.
- `docs/workflow-contract.md` - negotiation state I/O and the DynamoDB job-record schema (backend <-> infra). FROZEN.
- `.claude/plans/i-m-trying-to-build-cozy-castle.md` - full architecture, rationale, and product flow.

## Living notes (not frozen, but read before touching related code)
- `docs/bedrock-live-wiring-notes.md` - findings from running the real Bedrock path against Nova Micro (PR #8, not yet merged): a job-store backend-selection fix relevant to the infra/deploy track, and prompt/parsing gotchas relevant to anyone touching agent prompts or tagged-output parsing.

## Tech stack
- **Backend:** Python 3.12, FastAPI + Mangum (on Lambda), boto3 Bedrock **Converse** API.
- **AI model:** Amazon **Nova Micro** (`amazon.nova-micro-v1:0`) for every agent in v1. Each agent's model id is config (SSM/env), swappable independently later.
- **Frontend:** React + Vite (TypeScript).
- **Infra:** AWS SAM - API Gateway HTTP API, Lambda, Step Functions, DynamoDB (on-demand + TTL), X-Ray. No VPC/NAT.
- **CI/CD:** GitHub Actions via OIDC assume-role (no stored AWS keys).

## Architecture (one line)
React SPA (S3+CloudFront) -> HTTP API -> Lambda (FastAPI) -> Step Functions negotiation -> Bedrock (Nova) -> DynamoDB; the frontend polls for progress. Two adversarial agents (Payer vs Defense) run a capped 2-round negotiation with an escalate-to-human fallback.

## Repo layout
- `frontend/` - React + Vite SPA
- `backend/` - FastAPI app, Bedrock wrapper, agents, Step Functions task handlers, policy files
- `infra/` - SAM `template.yaml` + Step Functions ASL
- `docs/` - frozen contracts and reference docs
- `.github/workflows/` - CI/CD

## Build / dev / test
**Backend**
- Install: `cd backend && pip install -r requirements.txt -r requirements-dev.txt`
- Local (free, no AWS): `cd backend && USE_BEDROCK=false uvicorn app.main:app --reload --port 8000`
- Test: `cd backend && pytest -q`

**Frontend**
- Install + dev: `cd frontend && npm install && npm run dev` (Vite proxies `/api` -> `http://localhost:8000`)
- Test: `cd frontend && npm test`
- Build: `cd frontend && npm run build`

**Infra**
- Validate: `cd infra && sam validate --lint`
- Build + deploy: `cd infra && sam build && sam deploy --guided`

## Architecture style: YAGNI
Build only what the current milestone needs. No speculative abstractions, config knobs, or "future-proofing."
Prefer the simplest thing that works and reads clearly; delete dead code; one obvious way to do a thing.
The backend is stateless (the chart round-trips through the client). No datastore beyond the DynamoDB job/audit table.

## Conventions
- **Synthetic data only.** Real payer policy text (CMS, Aetna) is public reference material, not billing/legal advice.
- **Cost guardrails:** no VPC/NAT, no provisioned concurrency, no Secrets Manager (use SSM Parameter Store), nothing always-on.
- **Local dev must run with `USE_BEDROCK=false`** (mock fallback). Never require AWS credentials to run or test.
- **Keep this file under 150 lines.** New context goes in a `docs/<topic>.md` with a one-line pointer here (progressive disclosure); do not bloat this file.
- **Commits:** Conventional Commits (`feat:`, `fix:`, `chore:`, `test:`, `docs:`). Do not add AI co-author trailers. Use plain dashes, never em dashes.
