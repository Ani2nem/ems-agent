"""In-process negotiation driver for mock/local mode (no Step Functions).

``run_local`` follows the identical order and Choice logic as
``infra/statemachine/negotiation.asl.json`` so the DynamoDB job record it
produces is indistinguishable from a real Step Functions execution. Keep the two
behaviorally in sync.
"""

from __future__ import annotations

import time

from . import handlers


def run_local(job_id: str, chart: dict, *, delay: float = 0.0) -> dict:
    """Drive the full negotiation for ``job_id`` to a terminal state.

    ``delay`` spaces the states out (mirrors the ASL Wait state) so the frontend
    poll loop can watch progression; tests use 0 for speed.
    """
    state = {
        "jobId": job_id,
        "chart": chart,
        "payer": chart["payer"],
        "round": 1,
        "decision": None,
    }

    def pause() -> None:
        if delay:
            time.sleep(delay)

    pause()  # SimulateClearinghouse
    state = handlers.deny(state)
    pause()
    state = handlers.appeal(state)
    pause()
    state = handlers.rereview(state)

    # DecisionChoice
    if state["decision"] == "overturn":
        return handlers.resolve(state)
    if state["decision"] == "uphold" and state["round"] < 2:
        pause()
        state = handlers.appeal(state)  # EscalateAppeal (sets round=2)
        pause()
        state = handlers.final_ruling(state)
        # FinalChoice
        if state["decision"] == "overturn":
            return handlers.resolve(state)
        return handlers.escalate(state)

    # DecisionChoice default (unreachable at round 1, kept for ASL parity)
    return handlers.escalate(state)
