"""Runtime configuration, read live from the environment.

A single flag, ``USE_BEDROCK``, distinguishes the two worlds this app runs in:

* ``false`` (local dev / tests): zero AWS calls. Agents return deterministic
  mock output, the job record lives in an in-process store, and the negotiation
  runs inline via ``negotiation.run_local`` instead of Step Functions.
* ``true`` (deployed): real Bedrock Converse, DynamoDB, and Step Functions.

Settings are read on each call rather than cached at import so tests can flip
env vars without reloading modules.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

_TRUTHY = {"1", "true", "yes", "on"}


def _flag(name: str, default: str = "false") -> bool:
    return os.getenv(name, default).strip().lower() in _TRUTHY


@dataclass(frozen=True)
class Settings:
    use_bedrock: bool
    model_id: str
    aws_region: str
    jobs_table: str
    state_machine_arn: str
    # A plain literal set in every Lambda's environment in infra/template.yaml
    # (Globals, not per-function) - true only for genuinely deployed Lambdas,
    # regardless of which function. See store.py's _backend() docstring:
    # STATE_MACHINE_ARN alone can't be that signal, because giving every
    # handler Lambda a !Ref to the state machine (instead of just ApiFunction)
    # would create a circular CloudFormation dependency - the state machine's
    # own definition already references those same Lambdas' ARNs.
    deployed: bool
    enable_ses_email: bool
    escalation_email: str
    # API Gateway HTTP API stage prefix (e.g. "prod"), stripped from Mangum's
    # ASGI scope path since API Gateway includes it in rawPath. Empty locally,
    # where uvicorn serves with no stage prefix.
    stage_name: str
    # Seconds to pause between negotiation states in local mode, so the frontend
    # poll loop can observe status/round progression. 0 in tests for speed.
    local_step_delay: float


def settings() -> Settings:
    return Settings(
        use_bedrock=_flag("USE_BEDROCK"),
        model_id=os.getenv("MODEL_ID", "amazon.nova-micro-v1:0"),
        aws_region=os.getenv("AWS_REGION", "us-east-1"),
        jobs_table=os.getenv("JOBS_TABLE", "ems-agent-jobs"),
        state_machine_arn=os.getenv("STATE_MACHINE_ARN", ""),
        deployed=_flag("DEPLOYED"),
        enable_ses_email=_flag("ENABLE_SES_EMAIL"),
        escalation_email=os.getenv("ESCALATION_EMAIL", ""),
        stage_name=os.getenv("STAGE_NAME", ""),
        local_step_delay=float(os.getenv("LOCAL_STEP_DELAY_SECONDS", "2")),
    )
