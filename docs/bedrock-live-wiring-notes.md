# Bedrock Live Wiring Notes (`track/bedrock-live-wiring`)

Findings from actually running the real Bedrock path (Nova Micro, us-east-1) end-to-end for the first time, beyond what `TASK_BRIEF.md` for that track anticipated.
Status: on branch `track/bedrock-live-wiring`, PR [#8](https://github.com/Ani2nem/ems-agent/pull/8) into `main`, **not yet merged**.
Anything branched from `main` before this merges won't have these fixes.

## Deviations from the original plan

The brief expected regex/prompt tweaks might be needed for `REASON:`/`DECISION:` tag reliability - that part was correct, and got fixed (see below).
Two things were **not** anticipated by the brief and came from actually running against real AWS:

1. **`incidentId` schema failure.** The parse-chart prompt asked the model for `incidentId`. A model correctly following "do not invent facts" returns `null` for it, since it's never in the transcript, which fails the chart's required-string schema.
2. **`store.py` backend-selection bug.** `USE_BEDROCK=true` alone routed the job store to real DynamoDB even with no infra deployed. `main._start_workflow` already correctly gates Step Functions on `use_bedrock AND state_machine_arn`; `store.py` didn't mirror that, so live-Bedrock local testing hit a `ResourceNotFoundException` against a table that was never created.

## If you're touching related code (other tracks)

- **Infra/deploy track:** `store.py`'s DynamoDB backend activates when both `USE_BEDROCK=true` and (originally) `STATE_MACHINE_ARN` were set. **Correction, found the hard way against real deployed infra after this merged:** `STATE_MACHINE_ARN` can't actually be that signal on anything but `ApiFunction` - giving every handler Lambda a `!Ref` to the state machine creates a circular CloudFormation dependency, since the state machine's own definition already references those same Lambdas' ARNs. It shipped anyway (nothing in CI or `sam validate` catches a working-but-wrong runtime signal), and every real negotiation on the deployed stack failed with a `KeyError` in `store.append_round` - each handler Lambda silently fell back to the in-process store, empty on every fresh invocation. Fixed by introducing a dedicated `DEPLOYED=true` literal (no resource reference, zero dependency risk) set via SAM template Globals instead. See `store.py`'s module docstring for the full explanation.
- **Agents/prompts track:** `incidentId` must never be requested from the model - it's backend-generated (same deterministic hash the mock path already used). Don't reintroduce it into the parse-chart prompt's requested key list.
- **Anything parsing tagged model output:** real Nova Micro output sometimes wraps a tag in markdown bold (`**DECISION: OVERTURN**`) and/or appends a stray trailing code fence after it, even when the prompt never mentions fences. `agents._extract_tag`/`_strip_tag_line` now tolerate that; any new tagged-output prompt elsewhere should assume the same variance rather than anchoring parsing to end-of-string.

## Local dev environment

The machine's default `python3` is 3.14, which currently has no prebuilt `pydantic-core` wheel and fails to compile it from source (missing rust target). The backend venv needs Python 3.12: `brew install python@3.12`, then create the venv from the Cellar path (e.g. `/opt/homebrew/Cellar/python@3.12/*/bin/python3.12 -m venv .venv`).

## Running live Bedrock tests

Gated behind `RUN_BEDROCK_LIVE_TESTS=1` so CI (no AWS creds) always skips them. Needs `USE_BEDROCK=true`, `AWS_REGION`, and an AWS profile/credentials with `bedrock:InvokeModel` scoped to `amazon.nova-micro-v1:0`. See `backend/tests/test_bedrock_live.py` for the exact invocation.
