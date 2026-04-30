"""Amazon Transcribe client — standard (non-Call-Analytics) for monologue audio."""
import time
import uuid
import json
import boto3
import urllib.request
from config import REGION, S3_BUCKET, TRANSCRIBE_POLL_INTERVAL_SEC, TRANSCRIBE_TIMEOUT_SEC, PRICING

_transcribe = None
_s3 = None


def _clients():
    global _transcribe, _s3
    if _transcribe is None:
        _transcribe = boto3.client("transcribe", region_name=REGION)
        _s3 = boto3.client("s3", region_name=REGION)
    return _transcribe, _s3


def upload_audio_to_s3(local_path: str) -> str:
    _, s3 = _clients()
    key = f"poc-audio/{uuid.uuid4()}/{local_path.split('/')[-1]}"
    s3.upload_file(local_path, S3_BUCKET, key)
    return f"s3://{S3_BUCKET}/{key}"


def run_call_analytics(s3_uri: str, language: str = "en") -> tuple[dict, dict]:
    """
    Standard Transcribe job (despite legacy function name kept for API compat).
    Returns (normalized_result, meta {cost_usd, elapsed_sec, duration_sec}).
    Normalized result shape matches what voice_features.py expects:
      { "Transcript": [ {BeginOffsetMillis, EndOffsetMillis, Content}, ... ] }
    """
    transcribe, _ = _clients()
    lang_code = "zh-CN" if language == "zh" else "en-US"
    job_name = f"poc-tx-{uuid.uuid4().hex[:12]}"

    start = time.time()
    transcribe.start_transcription_job(
        TranscriptionJobName=job_name,
        Media={"MediaFileUri": s3_uri},
        LanguageCode=lang_code,
        Settings={"ShowSpeakerLabels": False},
    )

    deadline = start + TRANSCRIBE_TIMEOUT_SEC
    while time.time() < deadline:
        job = transcribe.get_transcription_job(TranscriptionJobName=job_name)["TranscriptionJob"]
        status = job["TranscriptionJobStatus"]
        if status == "COMPLETED":
            elapsed = time.time() - start
            result_url = job["Transcript"]["TranscriptFileUri"]
            raw = _fetch_result(result_url)
            normalized = _normalize_transcript(raw)
            duration_sec = _extract_duration(normalized)
            cost = (duration_sec / 60.0) * PRICING["transcribe_call_analytics_per_min"]
            return normalized, {"cost_usd": cost, "elapsed_sec": elapsed, "duration_sec": duration_sec}
        if status == "FAILED":
            raise RuntimeError(f"Transcribe job failed: {job.get('FailureReason')}")
        time.sleep(TRANSCRIBE_POLL_INTERVAL_SEC)
    raise TimeoutError(f"Transcribe job {job_name} did not complete within {TRANSCRIBE_TIMEOUT_SEC}s")


def _fetch_result(url: str) -> dict:
    with urllib.request.urlopen(url) as r:
        return json.loads(r.read())


def _normalize_transcript(raw: dict) -> dict:
    """
    Convert standard Transcribe output to normalized shape.
    Standard output: { "results": { "items": [ {start_time, end_time, alternatives:[{content}]} ] } }
    """
    items = raw.get("results", {}).get("items", [])
    normalized_items = []
    for item in items:
        if item.get("type") != "pronunciation":
            continue  # skip punctuation
        content = item.get("alternatives", [{}])[0].get("content", "")
        normalized_items.append({
            "BeginOffsetMillis": int(float(item.get("start_time", 0)) * 1000),
            "EndOffsetMillis": int(float(item.get("end_time", 0)) * 1000),
            "Content": content,
        })
    return {
        "Transcript": normalized_items,
        # No sentiment in standard Transcribe — voice_features will default to NEUTRAL
        "ConversationCharacteristics": {},
    }


def _extract_duration(normalized: dict) -> float:
    items = normalized.get("Transcript", [])
    if not items:
        return 0.0
    return max(item["EndOffsetMillis"] / 1000.0 for item in items)
