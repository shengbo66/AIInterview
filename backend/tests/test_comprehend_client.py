"""Unit tests for comprehend_client.py — mock boto3."""
from __future__ import annotations

from unittest.mock import patch

import pytest
from botocore.exceptions import ClientError


class TestDetectSentiment:
    @pytest.mark.asyncio
    async def test_empty_text_returns_unknown(self):
        from app.clients.comprehend_client import detect_sentiment

        result = await detect_sentiment("")
        assert result["overall"] == "UNKNOWN"

        result = await detect_sentiment("   ")
        assert result["overall"] == "UNKNOWN"

    @pytest.mark.asyncio
    async def test_positive_sentiment_parsed(self):
        from app.clients import comprehend_client

        def fake_detect(text, language):
            return {
                "Sentiment": "POSITIVE",
                "SentimentScore": {
                    "Positive": 0.92,
                    "Negative": 0.02,
                    "Neutral": 0.05,
                    "Mixed": 0.01,
                },
            }

        with patch.object(comprehend_client, "_detect_sync", fake_detect):
            result = await comprehend_client.detect_sentiment("我非常喜欢这个技术", language="zh")

        assert result["overall"] == "POSITIVE"
        assert result["scores"]["positive"] == pytest.approx(0.92)
        assert result["scores"]["negative"] == pytest.approx(0.02)

    @pytest.mark.asyncio
    async def test_client_error_returns_unknown(self):
        from app.clients import comprehend_client

        def fake_detect(text, language):
            raise ClientError(
                error_response={"Error": {"Code": "ThrottlingException", "Message": "slow down"}},
                operation_name="DetectSentiment",
            )

        with patch.object(comprehend_client, "_detect_sync", fake_detect):
            result = await comprehend_client.detect_sentiment("文本", language="zh")

        assert result["overall"] == "UNKNOWN"
        assert result["scores"]["positive"] == 0

    @pytest.mark.asyncio
    async def test_long_text_truncated(self):
        from app.clients import comprehend_client

        captured = {}

        def fake_detect(text, language):
            captured["text"] = text
            return {
                "Sentiment": "NEUTRAL",
                "SentimentScore": {"Positive": 0, "Negative": 0, "Neutral": 1, "Mixed": 0},
            }

        long_text = "好" * 3000  # ~9000 bytes UTF-8
        with patch.object(comprehend_client, "_detect_sync", fake_detect):
            await comprehend_client.detect_sentiment(long_text, language="zh")

        # Text should be truncated to fit limit
        assert len(captured["text"].encode("utf-8")) <= 4500
