"""Thin wrapper over the Bedrock Converse API (Amazon Nova).

Only invoked when ``USE_BEDROCK=true``. In local/mock mode the agents never call
this module - they return deterministic output directly - so nothing here needs
AWS credentials to import or test.
"""

from __future__ import annotations

import boto3

from .config import settings


class BedrockError(RuntimeError):
    """Raised when the model call fails or returns nothing usable."""


_client = None


def _get_client():
    global _client
    if _client is None:
        _client = boto3.client("bedrock-runtime", region_name=settings().aws_region)
    return _client


def converse(system: str, user: str, *, max_tokens: int = 700, temperature: float = 0.4) -> str:
    """Send a single-turn prompt and return the model's text response.

    Raises ``BedrockError`` on any failure so callers can map it to a 502.
    """
    try:
        resp = _get_client().converse(
            modelId=settings().model_id,
            system=[{"text": system}],
            messages=[{"role": "user", "content": [{"text": user}]}],
            inferenceConfig={"maxTokens": max_tokens, "temperature": temperature},
        )
        return resp["output"]["message"]["content"][0]["text"].strip()
    except Exception as exc:  # noqa: BLE001 - surface any AWS/SDK failure uniformly
        raise BedrockError(str(exc)) from exc
