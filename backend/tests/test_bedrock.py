"""Tests for the boto3 Bedrock wrapper, mocking the boto3 client itself (not
``bedrock.converse``) so the request/response shape and the retry-on-malformed-
JSON behavior in ``agents._parse_chart_bedrock`` are covered without any real
AWS calls or credentials."""

import json

import pytest

from app import agents, bedrock

VALID_CHART = {
    "incidentId": "INC-2026-00001",
    "patient": {"age": 40, "sex": "M"},
    "payer": "AETNA",
    "chiefComplaint": "Chest pain",
    "mechanismOfInjury": "unknown",
    "vitals": {"gcs": 15, "bp": None, "hr": None, "spo2": None, "rr": None},
    "interventions": [],
    "comorbidities": [],
    "levelOfService": "BLS",
    "transportPriority": "Priority 2 (urgent)",
    "narrative": "chest pain reported",
}


class _FakeBedrockClient:
    """Stands in for the boto3 bedrock-runtime client's ``.converse()``."""

    def __init__(self, texts):
        self._texts = iter(texts)
        self.calls: list[dict] = []

    def converse(self, **kwargs):
        self.calls.append(kwargs)
        text = next(self._texts)
        return {"output": {"message": {"content": [{"text": text}]}}}


@pytest.fixture
def _bedrock_on(monkeypatch):
    monkeypatch.setenv("USE_BEDROCK", "true")


def test_converse_sends_expected_request_shape(_bedrock_on, monkeypatch):
    fake_client = _FakeBedrockClient(["hello back"])
    monkeypatch.setattr(bedrock, "_get_client", lambda: fake_client)

    result = bedrock.converse("system prompt", "user prompt", max_tokens=123, temperature=0.5)

    assert result == "hello back"
    assert len(fake_client.calls) == 1
    call = fake_client.calls[0]
    assert call["modelId"] == "amazon.nova-micro-v1:0"
    assert call["system"] == [{"text": "system prompt"}]
    assert call["messages"] == [{"role": "user", "content": [{"text": "user prompt"}]}]
    assert call["inferenceConfig"] == {"maxTokens": 123, "temperature": 0.5}


def test_converse_wraps_any_failure_in_bedrock_error(_bedrock_on, monkeypatch):
    class _BoomClient:
        def converse(self, **kwargs):
            raise RuntimeError("throttled")

    monkeypatch.setattr(bedrock, "_get_client", lambda: _BoomClient())

    with pytest.raises(bedrock.BedrockError):
        bedrock.converse("system", "user")


def test_parse_chart_retries_once_on_malformed_json_via_mocked_boto3(_bedrock_on, monkeypatch):
    fake_client = _FakeBedrockClient(["not valid json {{{", json.dumps(VALID_CHART)])
    monkeypatch.setattr(bedrock, "_get_client", lambda: fake_client)

    transcript = "patient with chest pain"
    chart = agents.parse_chart(transcript)

    # incidentId and billedAmount are always backend-assigned (never
    # requested from the model), so they override/extend VALID_CHART.
    expected = dict(
        VALID_CHART,
        incidentId=agents._incident_id(transcript),
        billedAmount=agents.rate_for(VALID_CHART["levelOfService"]),
    )
    assert chart == expected
    assert len(fake_client.calls) == 2
    # The repair prompt on retry must reference the parse failure so the model
    # knows to correct its output.
    second_user_msg = fake_client.calls[1]["messages"][0]["content"][0]["text"]
    assert "could not be parsed" in second_user_msg


def test_parse_chart_raises_if_retry_is_also_malformed(_bedrock_on, monkeypatch):
    fake_client = _FakeBedrockClient(["still not json", "still not json either"])
    monkeypatch.setattr(bedrock, "_get_client", lambda: fake_client)

    with pytest.raises(bedrock.BedrockError):
        agents.parse_chart("patient with chest pain")

    assert len(fake_client.calls) == 2
