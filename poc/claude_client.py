"""Amazon Bedrock Claude Sonnet client."""
import json
import time
import boto3
from config import REGION, CLAUDE_MODEL_ID, CLAUDE_TEMPERATURE, CLAUDE_MAX_TOKENS, PRICING
from shared.eval_core.utils import parse_json_strict

_client = None


def _get_client():
    global _client
    if _client is None:
        _client = boto3.client("bedrock-runtime", region_name=REGION)
    return _client


def invoke(prompt: str, max_retries: int = 3) -> tuple[dict, dict]:
    """Invoke Claude Sonnet. Returns (parsed_json, meta {tokens, cost_usd, elapsed_sec})."""
    body = {
        "anthropic_version": "bedrock-2023-05-31",
        "max_tokens": CLAUDE_MAX_TOKENS,
        "temperature": CLAUDE_TEMPERATURE,
        "messages": [{"role": "user", "content": prompt}],
    }
    last_err = None
    for attempt in range(max_retries):
        try:
            start = time.time()
            resp = _get_client().invoke_model(
                modelId=CLAUDE_MODEL_ID,
                body=json.dumps(body),
                contentType="application/json",
            )
            elapsed = time.time() - start
            payload = json.loads(resp["body"].read())
            text = payload["content"][0]["text"]
            usage = payload.get("usage", {})
            in_tok = usage.get("input_tokens", 0)
            out_tok = usage.get("output_tokens", 0)
            cost = (
                in_tok / 1_000_000 * PRICING["claude_sonnet_input_per_1m"]
                + out_tok / 1_000_000 * PRICING["claude_sonnet_output_per_1m"]
            )
            parsed = parse_json_strict(text)
            return parsed, {
                "input_tokens": in_tok,
                "output_tokens": out_tok,
                "cost_usd": cost,
                "elapsed_sec": elapsed,
                "raw_response": text,
            }
        except Exception as e:
            last_err = e
            if attempt < max_retries - 1:
                time.sleep(2 ** attempt)
    raise RuntimeError(f"Claude invoke failed after {max_retries} retries: {last_err}")


def invoke_text(prompt: str) -> tuple[str, dict]:
    """Invoke Claude for plain text output (no JSON parsing). Used for sample generation."""
    body = {
        "anthropic_version": "bedrock-2023-05-31",
        "max_tokens": 1000,
        "temperature": 0.7,
        "messages": [{"role": "user", "content": prompt}],
    }
    start = time.time()
    resp = _get_client().invoke_model(
        modelId=CLAUDE_MODEL_ID, body=json.dumps(body), contentType="application/json"
    )
    elapsed = time.time() - start
    payload = json.loads(resp["body"].read())
    text = payload["content"][0]["text"].strip()
    usage = payload.get("usage", {})
    cost = (
        usage.get("input_tokens", 0) / 1_000_000 * PRICING["claude_sonnet_input_per_1m"]
        + usage.get("output_tokens", 0) / 1_000_000 * PRICING["claude_sonnet_output_per_1m"]
    )
    return text, {"cost_usd": cost, "elapsed_sec": elapsed}

