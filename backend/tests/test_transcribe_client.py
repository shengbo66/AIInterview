"""Unit tests for transcribe_client.py — mock boto3 + s3_audio."""
from __future__ import annotations

import json
import struct
from unittest.mock import AsyncMock, patch

import pytest


class TestPcmToWavBytes:
    def test_header_length_44(self):
        from app.clients.transcribe_client import _pcm_to_wav_bytes

        pcm = b"\x00\x00" * 1000
        wav = _pcm_to_wav_bytes(pcm)
        # 44 header + 2000 pcm
        assert len(wav) == 44 + 2000

    def test_riff_wave_markers(self):
        from app.clients.transcribe_client import _pcm_to_wav_bytes

        pcm = b"\x00\x00" * 100
        wav = _pcm_to_wav_bytes(pcm)
        assert wav[:4] == b"RIFF"
        assert wav[8:12] == b"WAVE"
        assert wav[12:16] == b"fmt "
        assert wav[36:40] == b"data"

    def test_odd_length_pcm_truncated(self):
        from app.clients.transcribe_client import _pcm_to_wav_bytes

        pcm = b"\x00\x01\x02"  # 3 bytes → truncate to 2
        wav = _pcm_to_wav_bytes(pcm)
        assert len(wav) == 44 + 2

    def test_sample_rate_encoded(self):
        from app.clients.transcribe_client import _pcm_to_wav_bytes

        pcm = b"\x00\x00" * 100
        wav = _pcm_to_wav_bytes(pcm, sample_rate=16000)
        (rate,) = struct.unpack("<I", wav[24:28])
        assert rate == 16000


class TestParseWords:
    @pytest.mark.asyncio
    async def test_not_completed_returns_empty(self):
        from app.clients.transcribe_client import parse_words

        result = await parse_words({"status": "IN_PROGRESS"})
        assert result == []

        result = await parse_words({"status": "FAILED"})
        assert result == []

    @pytest.mark.asyncio
    async def test_valid_output_parsed(self):
        from app.clients.transcribe_client import parse_words

        # Build a realistic Transcribe output JSON
        payload = {
            "results": {
                "items": [
                    {
                        "type": "pronunciation",
                        "start_time": "0.0",
                        "end_time": "0.5",
                        "alternatives": [{"content": "我", "confidence": "0.98"}],
                    },
                    {
                        "type": "pronunciation",
                        "start_time": "0.5",
                        "end_time": "1.0",
                        "alternatives": [{"content": "对", "confidence": "0.45"}],  # low conf
                    },
                    {
                        "type": "punctuation",  # should be skipped
                        "alternatives": [{"content": "。", "confidence": "1.0"}],
                    },
                ]
            }
        }

        with patch("app.clients.transcribe_client.s3_audio") as mock_s3:
            mock_s3.download_bytes = AsyncMock(return_value=json.dumps(payload).encode())
            job_result = {
                "status": "COMPLETED",
                "transcript_uri": "https://s3.us-east-1.amazonaws.com/interviewer-poc-audio-484626021127/transcribe-output/foo.json",
            }
            words = await parse_words(job_result)

        assert len(words) == 2
        assert words[0].text == "我"
        assert words[0].start_ms == 0
        assert words[0].end_ms == 500
        assert words[0].confidence == pytest.approx(0.98)
        assert words[1].text == "对"
        assert words[1].confidence == pytest.approx(0.45)

    @pytest.mark.asyncio
    async def test_malformed_json_returns_empty(self):
        from app.clients.transcribe_client import parse_words

        with patch("app.clients.transcribe_client.s3_audio") as mock_s3:
            mock_s3.download_bytes = AsyncMock(return_value=b"not valid json")
            result = await parse_words(
                {
                    "status": "COMPLETED",
                    "transcript_uri": "https://s3.us-east-1.amazonaws.com/interviewer-poc-audio-484626021127/transcribe-output/foo.json",
                }
            )
        assert result == []

    @pytest.mark.asyncio
    async def test_unexpected_uri_format_returns_empty(self):
        from app.clients.transcribe_client import parse_words

        result = await parse_words(
            {"status": "COMPLETED", "transcript_uri": "https://other.com/foo.json"}
        )
        assert result == []


class TestIdempotentSubmit:
    @pytest.mark.asyncio
    async def test_existing_job_not_resubmitted(self):
        """If _describe_sync returns a response, we return the job_name
        without calling _start_sync."""
        from app.clients import transcribe_client

        existing_response = {
            "TranscriptionJob": {"TranscriptionJobStatus": "COMPLETED"}
        }

        def fake_describe(job_name):
            return existing_response

        start_called = False

        def fake_start(*args, **kwargs):
            nonlocal start_called
            start_called = True

        with patch.object(transcribe_client, "_describe_sync", fake_describe), \
             patch.object(transcribe_client, "_start_sync", fake_start):
            result = await transcribe_client.submit_job("some/key.pcm", "my-job")

        assert result == "my-job"
        assert start_called is False


class TestGetResult:
    @pytest.mark.asyncio
    async def test_completed_returns_uri(self):
        from app.clients import transcribe_client

        def fake_describe(job_name):
            return {
                "TranscriptionJob": {
                    "TranscriptionJobStatus": "COMPLETED",
                    "Transcript": {"TranscriptFileUri": "https://example/out.json"},
                }
            }

        with patch.object(transcribe_client, "_describe_sync", fake_describe):
            result = await transcribe_client.get_result("my-job")

        assert result["status"] == "COMPLETED"
        assert result["transcript_uri"] == "https://example/out.json"

    @pytest.mark.asyncio
    async def test_failed_returns_reason(self):
        from app.clients import transcribe_client

        def fake_describe(job_name):
            return {
                "TranscriptionJob": {
                    "TranscriptionJobStatus": "FAILED",
                    "FailureReason": "unsupported format",
                }
            }

        with patch.object(transcribe_client, "_describe_sync", fake_describe):
            result = await transcribe_client.get_result("my-job")

        assert result["status"] == "FAILED"
        assert result["failure_reason"] == "unsupported format"

    @pytest.mark.asyncio
    async def test_not_found_returns_none(self):
        from app.clients import transcribe_client

        with patch.object(transcribe_client, "_describe_sync", lambda _: None):
            result = await transcribe_client.get_result("unknown-job")
        assert result is None


class TestWaitForCompletion:
    @pytest.mark.asyncio
    async def test_completed_returns_immediately(self):
        from app.clients import transcribe_client

        def fake_describe(job_name):
            return {
                "TranscriptionJob": {
                    "TranscriptionJobStatus": "COMPLETED",
                    "Transcript": {"TranscriptFileUri": "https://example/out.json"},
                }
            }

        with patch.object(transcribe_client, "_describe_sync", fake_describe):
            result = await transcribe_client.wait_for_completion("my-job", timeout_sec=30)
        assert result["status"] == "COMPLETED"

    @pytest.mark.asyncio
    async def test_timeout_returns_timeout_status(self):
        """If job stays IN_PROGRESS until timeout, return {'status': 'TIMEOUT'}."""
        from app.clients import transcribe_client

        def fake_describe(job_name):
            return {"TranscriptionJob": {"TranscriptionJobStatus": "IN_PROGRESS"}}

        # Mock asyncio.sleep to return instantly (skip polling delay)
        async def fake_sleep(sec):
            pass

        with patch.object(transcribe_client, "_describe_sync", fake_describe), \
             patch("app.clients.transcribe_client.asyncio.sleep", fake_sleep):
            result = await transcribe_client.wait_for_completion("my-job", timeout_sec=10)
        assert result is not None
        assert result["status"] == "TIMEOUT"

    @pytest.mark.asyncio
    async def test_job_not_found_returns_none(self):
        from app.clients import transcribe_client

        with patch.object(transcribe_client, "_describe_sync", lambda _: None):
            result = await transcribe_client.wait_for_completion("missing", timeout_sec=5)
        assert result is None
