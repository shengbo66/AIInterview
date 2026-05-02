"""Amazon Comprehend client for sentiment detection.

Lightweight wrapper — single sync call per answer. Used by evaluation_service
to enrich voice_features with sentiment analysis of the transcript.
"""
from __future__ import annotations

import asyncio
import logging

import boto3
from botocore.exceptions import ClientError

from app.config import settings

logger = logging.getLogger("interviewer.comprehend")

_client = None

# Max bytes per Comprehend DetectSentiment request (5000 bytes UTF-8)
_MAX_TEXT_BYTES = 4500


def _get_client():
    global _client
    if _client is None:
        _client = boto3.client("comprehend", region_name=settings.aws_region)
    return _client


def _detect_sync(text: str, language: str) -> dict:
    return _get_client().detect_sentiment(Text=text, LanguageCode=language)


async def detect_sentiment(text: str, language: str = "zh") -> dict:
    """Return {"overall": "POSITIVE"|"NEGATIVE"|"NEUTRAL"|"MIXED"|"UNKNOWN",
              "scores": {"positive": 0.1, "negative": 0.7, "neutral": 0.1, "mixed": 0.1}}.

    Returns UNKNOWN overall and zero scores if text empty or Comprehend errors.
    """
    if not text or not text.strip():
        return {"overall": "UNKNOWN", "scores": {"positive": 0, "negative": 0, "neutral": 0, "mixed": 0}}

    # Comprehend has a 5000 byte limit; truncate long transcripts
    text_bytes = text.encode("utf-8")
    if len(text_bytes) > _MAX_TEXT_BYTES:
        text = text_bytes[:_MAX_TEXT_BYTES].decode("utf-8", errors="ignore")

    try:
        resp = await asyncio.to_thread(_detect_sync, text, language)
    except ClientError as e:
        logger.warning("comprehend detect_sentiment failed: %s", e)
        return {"overall": "UNKNOWN", "scores": {"positive": 0, "negative": 0, "neutral": 0, "mixed": 0}}

    scores_raw = resp.get("SentimentScore", {}) or {}
    return {
        "overall": resp.get("Sentiment", "UNKNOWN"),
        "scores": {
            "positive": round(float(scores_raw.get("Positive", 0)), 3),
            "negative": round(float(scores_raw.get("Negative", 0)), 3),
            "neutral": round(float(scores_raw.get("Neutral", 0)), 3),
            "mixed": round(float(scores_raw.get("Mixed", 0)), 3),
        },
    }
