"""Backend-selection regression test (see docs/workflow-contract.md).

USE_BEDROCK=true alone must NOT switch the job store to DynamoDB: that only
happens once real infra is deployed (state_machine_arn set by SAM), mirroring
how main._start_workflow gates Step Functions. USE_BEDROCK=true with no
deployed infra - e.g. testing live Bedrock locally - must still use the
in-process store, per the workflow contract's "USE_BEDROCK=false or running
locally" invariant.
"""

from app import store


def test_use_bedrock_alone_does_not_switch_to_dynamo(monkeypatch):
    monkeypatch.setenv("USE_BEDROCK", "true")
    monkeypatch.setenv("STATE_MACHINE_ARN", "")

    assert store._backend() is store._memory


def test_use_bedrock_and_state_machine_arn_switches_to_dynamo(monkeypatch):
    monkeypatch.setenv("USE_BEDROCK", "true")
    monkeypatch.setenv("STATE_MACHINE_ARN", "arn:aws:states:us-east-1:123456789012:stateMachine:fake")
    monkeypatch.setattr(store, "_Dynamo", lambda: "fake-dynamo-backend")
    monkeypatch.setattr(store, "_dynamo", None)

    assert store._backend() == "fake-dynamo-backend"
