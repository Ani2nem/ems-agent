"""Backend-selection regression test (see docs/workflow-contract.md).

USE_BEDROCK=true alone must NOT switch the job store to DynamoDB: that only
happens once real infra is deployed (DEPLOYED=true, a plain literal set via
SAM template Globals - see store.py's module docstring for why STATE_MACHINE_
ARN can't be this signal, despite looking like the obvious choice: it would
create a circular CloudFormation dependency between the handler Lambdas and
the state machine that invokes them). USE_BEDROCK=true with no deployed infra
- e.g. testing live Bedrock locally - must still use the in-process store,
per the workflow contract's "USE_BEDROCK=false or running locally" invariant.
"""

from app import store


def test_use_bedrock_alone_does_not_switch_to_dynamo(monkeypatch):
    monkeypatch.setenv("USE_BEDROCK", "true")
    monkeypatch.setenv("DEPLOYED", "false")

    assert store._backend() is store._memory


def test_use_bedrock_and_deployed_switches_to_dynamo(monkeypatch):
    monkeypatch.setenv("USE_BEDROCK", "true")
    monkeypatch.setenv("DEPLOYED", "true")
    monkeypatch.setattr(store, "_Dynamo", lambda: "fake-dynamo-backend")
    monkeypatch.setattr(store, "_dynamo", None)

    assert store._backend() == "fake-dynamo-backend"
