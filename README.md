# EMS Agent - Autonomous Revenue Cycle Management (Prototype)

A B2B vertical-AI SaaS prototype for EMS (ambulance) **Revenue Cycle Management + Ambient Documentation**.

- A paramedic **dictates** a shift report; AI turns messy speech into a clean, billing-grade **ePCR chart**.
- On claim submission, a **Payer/Adjudicator** agent issues a dynamic denial and a **Revenue Defense** agent autonomously fights back with a cited appeal - a capped 2-round negotiation, escalating to a human on hard cases.

Built **production-shaped but cheap**: fully serverless on AWS, designed to run many times for well under **$10**.

## Architecture

React SPA (S3 + CloudFront) → API Gateway HTTP API → Lambda (FastAPI + Mangum) →
Step Functions negotiation → Bedrock (Amazon Nova Micro) → DynamoDB (job state + audit trail).
Frontend polls for progress. See `docs/api-contract.md` (frozen interface) and the plan for full detail.

## Layout

```
frontend/   React + Vite SPA
backend/    FastAPI app, Bedrock wrapper, agents, Step Functions task handlers, policies
infra/      AWS SAM template + Step Functions ASL
docs/       Frozen API contract
.github/    CI/CD (GitHub Actions, OIDC)
```

## Local dev (free - no AWS)

```bash
# backend (mock mode: no Bedrock calls)
cd backend && pip install -r requirements.txt
USE_BEDROCK=false uvicorn app.main:app --reload --port 8000

# frontend (proxies /api -> localhost:8000)
cd frontend && npm install && npm run dev
```

## Notes

- **Models** are configured per-agent (Nova Micro everywhere in v1) and swappable via SSM/env.
- **Dictation** uses the browser Web Speech API (Chrome/Edge) with a textarea fallback. Amazon Transcribe Medical is the production path (not built here).
- **Data is synthetic.** Real public payer policies (CMS, Aetna) are used only as the medical-necessity knowledge base. This is a demo, not billing/legal advice.
