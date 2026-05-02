"""Amazon Transcribe async client for speech-to-text + word-level timing.

Workflow:
1. Raw PCM16 16kHz mono (the format we store in S3 for user audio) needs a
   WAV header — Transcribe doesn't accept raw PCM. We wrap it in a 44-byte
   WAV header on the fly into a side key `transcribe-input/{job}.wav`.
2. Submit StartTranscriptionJob pointing to the .wav key.
3. Poll GetTranscriptionJob until COMPLETED / FAILED.
4. Parse the output JSON (stored in our bucket) into a list of Word tuples.

Design notes:
- All boto3 calls wrapped in asyncio.to_thread (same pattern as s3_audio.py)
- job_name is deterministic: `{interview_id}-{question_id}-{role}` - allows
  idempotent resubmit (we describe first; if exists we just read result).
"""
from __future__ import annotations

import asyncio
import json
import logging
import struct
from dataclasses import dataclass

import boto3
from botocore.exceptions import ClientError

from app.clients import s3_audio
from app.config import settings

logger = logging.getLogger("interviewer.transcribe")

_client = None
# Polling parameters
_POLL_INTERVAL_SEC = 5
_POLL_TIMEOUT_SEC = 90


@dataclass(frozen=True)
class Word:
    """One transcribed word with timing + confidence."""

    text: str
    start_ms: int
    end_ms: int
    confidence: float  # 0..1


def _get_client():
    global _client
    if _client is None:
        _client = boto3.client("transcribe", region_name=settings.aws_region)
    return _client


def _pcm_to_wav_bytes(pcm: bytes, sample_rate: int = 16000) -> bytes:
    """Wrap raw PCM16 LE mono bytes in a WAV container.

    Minimal RIFF/WAVE header (44 bytes) followed by PCM payload.
    Transcribe requires a valid container; raw PCM is rejected.
    """
    channels = 1
    bits_per_sample = 16
    byte_rate = sample_rate * channels * bits_per_sample // 8
    block_align = channels * bits_per_sample // 8
    data_size = len(pcm)
    # Clamp any odd length to avoid WAV parser complaints
    if data_size % 2:
        pcm = pcm[:-1]
        data_size -= 1
    file_size = 36 + data_size

    header = b"RIFF"
    header += struct.pack("<I", file_size)
    header += b"WAVE"
    header += b"fmt "
    header += struct.pack("<I", 16)  # fmt chunk size
    header += struct.pack("<H", 1)   # format code: PCM
    header += struct.pack("<H", channels)
    header += struct.pack("<I", sample_rate)
    header += struct.pack("<I", byte_rate)
    header += struct.pack("<H", block_align)
    header += struct.pack("<H", bits_per_sample)
    header += b"data"
    header += struct.pack("<I", data_size)
    return header + pcm


def _describe_sync(job_name: str) -> dict | None:
    """Return the raw Transcribe API response, or None if job not found."""
    try:
        return _get_client().get_transcription_job(TranscriptionJobName=job_name)
    except ClientError as e:
        if e.response.get("Error", {}).get("Code") == "BadRequestException":
            return None
        raise


def _start_sync(job_name: str, media_s3_uri: str, language: str) -> None:
    _get_client().start_transcription_job(
        TranscriptionJobName=job_name,
        LanguageCode=language,
        MediaFormat="wav",
        Media={"MediaFileUri": media_s3_uri},
        OutputBucketName=settings.s3_bucket,
        OutputKey=f"transcribe-output/{job_name}.json",
    )


async def submit_job(
    pcm_s3_key: str,
    job_name: str,
    language: str = "zh-CN",
) -> str:
    """Idempotently start a Transcribe job. Returns job_name.

    If a job with the same name already exists (any status), don't re-submit.
    Caller should poll with get_result() for completion.
    """
    # Check idempotency: if job exists, return it
    existing = await asyncio.to_thread(_describe_sync, job_name)
    if existing is not None:
        status = existing.get("TranscriptionJob", {}).get("TranscriptionJobStatus")
        logger.info("transcribe job %s already exists (status=%s)", job_name, status)
        return job_name

    # Read PCM from S3, wrap in WAV, upload to transcribe-input/ prefix
    pcm = await s3_audio.download_bytes(pcm_s3_key)
    wav = _pcm_to_wav_bytes(pcm, sample_rate=16000)
    wav_key = f"transcribe-input/{job_name}.wav"
    await s3_audio.upload(wav_key, wav, content_type="audio/wav")
    media_uri = f"s3://{settings.s3_bucket}/{wav_key}"

    await asyncio.to_thread(_start_sync, job_name, media_uri, language)
    logger.info("transcribe job submitted: %s (media=%s)", job_name, media_uri)
    return job_name


async def get_result(job_name: str) -> dict | None:
    """Return raw job status dict or None if not found.

    Typical shape: {"status": "COMPLETED"|"IN_PROGRESS"|"FAILED",
                     "transcript_uri": str|None, "failure_reason": str|None}
    """
    resp = await asyncio.to_thread(_describe_sync, job_name)
    if resp is None:
        return None
    job = resp.get("TranscriptionJob", {})
    status = job.get("TranscriptionJobStatus")
    result = {"status": status}
    if status == "COMPLETED":
        result["transcript_uri"] = job.get("Transcript", {}).get("TranscriptFileUri")
    elif status == "FAILED":
        result["failure_reason"] = job.get("FailureReason")
    return result


async def wait_for_completion(
    job_name: str,
    timeout_sec: int = _POLL_TIMEOUT_SEC,
) -> dict | None:
    """Poll until COMPLETED / FAILED / timeout. Returns final status dict or None."""
    elapsed = 0
    while elapsed < timeout_sec:
        result = await get_result(job_name)
        if result is None:
            return None
        if result["status"] in ("COMPLETED", "FAILED"):
            return result
        await asyncio.sleep(_POLL_INTERVAL_SEC)
        elapsed += _POLL_INTERVAL_SEC
    logger.warning("transcribe job %s timed out after %ds", job_name, timeout_sec)
    return {"status": "TIMEOUT"}


async def parse_words(job_result: dict) -> list[Word]:
    """Download Transcribe output JSON and extract word-level data.

    Returns [] if job not COMPLETED, result JSON malformed, or no items.
    Each item in output.json.results.items has:
      {"type": "pronunciation"|"punctuation",
       "start_time": "1.23", "end_time": "1.45",
       "alternatives": [{"content": "...", "confidence": "0.98"}]}
    """
    if job_result.get("status") != "COMPLETED":
        return []

    # Transcribe result JSON lives in our S3 bucket at transcribe-output/{job}.json
    # We stored it with OutputKey so read directly
    transcript_uri = job_result.get("transcript_uri", "")
    # transcript_uri is like https://s3.<region>.amazonaws.com/{bucket}/transcribe-output/{job}.json
    # Extract key after the bucket name
    marker = f"/{settings.s3_bucket}/"
    idx = transcript_uri.find(marker)
    if idx < 0:
        logger.warning("unexpected transcript_uri format: %s", transcript_uri)
        return []
    key = transcript_uri[idx + len(marker):]

    try:
        body = await s3_audio.download_bytes(key)
    except Exception:
        logger.exception("failed to download transcribe output %s", key)
        return []

    try:
        data = json.loads(body)
    except json.JSONDecodeError:
        logger.exception("transcribe output JSON malformed")
        return []

    items = (data.get("results") or {}).get("items") or []
    words: list[Word] = []
    for item in items:
        if item.get("type") != "pronunciation":
            continue  # skip punctuation
        alts = item.get("alternatives") or []
        if not alts:
            continue
        alt = alts[0]
        text = alt.get("content", "").strip()
        if not text:
            continue
        try:
            start_ms = int(float(item.get("start_time", 0)) * 1000)
            end_ms = int(float(item.get("end_time", 0)) * 1000)
            confidence = float(alt.get("confidence", 0))
        except (TypeError, ValueError):
            continue
        words.append(Word(text=text, start_ms=start_ms, end_ms=end_ms, confidence=confidence))

    return words
