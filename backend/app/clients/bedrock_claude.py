"""Async Bedrock Claude Sonnet wrapper (sync boto3 via asyncio.to_thread)."""
import asyncio
import json
import time

import boto3
from shared.eval_core.utils import parse_json_strict

from app.config import settings

PRICE_IN_PER_1M = 3.0
PRICE_OUT_PER_1M = 15.0

_client = None


def _get_client():
    global _client
    if _client is None:
        _client = boto3.client("bedrock-runtime", region_name=settings.aws_region)
    return _client


def _invoke_sync(prompt: str, max_tokens: int, temperature: float) -> dict:
    body = {
        "anthropic_version": "bedrock-2023-05-31",
        "max_tokens": max_tokens,
        "temperature": temperature,
        "messages": [{"role": "user", "content": prompt}],
    }
    resp = _get_client().invoke_model(
        modelId=settings.claude_model_id,
        body=json.dumps(body),
        contentType="application/json",
    )
    return json.loads(resp["body"].read())


async def invoke_json(prompt: str, max_tokens: int = 1500, temperature: float = 0.3) -> tuple[dict, dict]:
    """Return (parsed_json, meta). Retries 3x on failure."""
    last_err = None
    for attempt in range(3):
        try:
            start = time.time()
            payload = await asyncio.to_thread(_invoke_sync, prompt, max_tokens, temperature)
            text = payload["content"][0]["text"]
            usage = payload.get("usage", {})
            in_tok = usage.get("input_tokens", 0)
            out_tok = usage.get("output_tokens", 0)
            cost = in_tok / 1e6 * PRICE_IN_PER_1M + out_tok / 1e6 * PRICE_OUT_PER_1M
            return parse_json_strict(text), {
                "input_tokens": in_tok,
                "output_tokens": out_tok,
                "cost_usd": cost,
                "elapsed_sec": time.time() - start,
                "raw_response": text,
            }
        except Exception as e:
            last_err = e
            if attempt < 2:
                await asyncio.sleep(2 ** attempt)
    raise RuntimeError(f"Claude invoke failed after 3 retries: {last_err}")


async def invoke_text(prompt: str, max_tokens: int = 1000, temperature: float = 0.7) -> tuple[str, dict]:
    """Plain text response (no JSON parse). Used for open-ended generation."""
    start = time.time()
    payload = await asyncio.to_thread(_invoke_sync, prompt, max_tokens, temperature)
    text = payload["content"][0]["text"].strip()
    usage = payload.get("usage", {})
    cost = (
        usage.get("input_tokens", 0) / 1e6 * PRICE_IN_PER_1M
        + usage.get("output_tokens", 0) / 1e6 * PRICE_OUT_PER_1M
    )
    return text, {"cost_usd": cost, "elapsed_sec": time.time() - start}
