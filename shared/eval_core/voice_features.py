"""Extract objective voice metrics from Transcribe Call Analytics output + transcript."""
import re
from .rubric import FILLER_WORDS, VOICE_WEIGHTS


def count_units(text: str, language: str) -> int:
    """Chinese: count Han characters. English: count whitespace-separated words."""
    if language == "zh":
        return len(re.findall(r"[\u4e00-\u9fff]", text))
    return len([w for w in text.split() if w.strip()])


def count_fillers(text: str, language: str) -> tuple[int, list[str]]:
    """Return (count, unique detected fillers)."""
    text_lc = text.lower()
    detected = []
    total = 0
    for w in FILLER_WORDS.get(language, []):
        n = text_lc.count(w.lower())
        if n > 0:
            total += n
            detected.append(w)
    return total, detected


def extract_features(transcribe_result: dict, transcript_text: str, language: str, duration_sec: float) -> dict:
    """
    Build voice_features dict from Transcribe Call Analytics result.

    Expects transcribe_result with keys like:
      - Transcript: list of items with BeginOffsetMillis / EndOffsetMillis / Content
      - ConversationCharacteristics.Sentiment (optional)
    For simplified/mock input, accepts minimal shape.
    """
    word_count = count_units(transcript_text, language)
    filler_count, fillers_detected = count_fillers(transcript_text, language)
    filler_ratio = filler_count / word_count if word_count > 0 else 0.0

    # Pause analysis from Transcribe items
    items = transcribe_result.get("Transcript") or transcribe_result.get("transcript") or []
    pauses = []
    speaking_ms = 0
    prev_end = None
    for item in items:
        begin = float(item.get("BeginOffsetMillis", item.get("begin_offset_millis", 0))) / 1000.0
        end = float(item.get("EndOffsetMillis", item.get("end_offset_millis", 0))) / 1000.0
        speaking_ms += (end - begin) * 1000
        if prev_end is not None:
            gap = begin - prev_end
            if gap > 0.5:  # pause threshold: 0.5 sec
                pauses.append(gap)
        prev_end = end

    speaking_sec = speaking_ms / 1000.0
    speaking_ratio = speaking_sec / duration_sec if duration_sec > 0 else 0.0
    talk_speed = word_count / speaking_sec if speaking_sec > 0 else 0.0
    pause_count = len(pauses)
    avg_pause = sum(pauses) / len(pauses) if pauses else 0.0
    longest_pause = max(pauses) if pauses else 0.0
    pauses_per_min = (pause_count / duration_sec * 60) if duration_sec > 0 else 0.0

    sentiment = transcribe_result.get("ConversationCharacteristics", {}).get("Sentiment", {})
    overall_sentiment = sentiment.get("OverallSentiment", {}).get("CUSTOMER", "NEUTRAL") if sentiment else "NEUTRAL"

    return {
        "duration_total_sec": round(duration_sec, 2),
        "duration_speaking_sec": round(speaking_sec, 2),
        "speaking_ratio": round(speaking_ratio, 3),
        "word_count": word_count,
        "talk_speed_wps": round(talk_speed, 2),
        "pause_count": pause_count,
        "pause_count_per_minute": round(pauses_per_min, 2),
        "avg_pause_sec": round(avg_pause, 2),
        "longest_pause_sec": round(longest_pause, 2),
        "filler_word_count": filler_count,
        "filler_word_ratio": round(filler_ratio, 4),
        "filler_words_detected": fillers_detected,
        "transcribe_sentiment": {"overall": overall_sentiment},
    }


def voice_score(features: dict) -> int:
    """Map objective metrics to 0-100 voice score using weighted rubric."""
    def _norm(val, best_range, penalty_threshold):
        lo, hi = best_range
        if lo <= val <= hi:
            return 100
        if val < lo:
            return max(0, 100 * val / lo) if lo > 0 else 0
        if val > penalty_threshold:
            return 30
        return max(30, 100 - (val - hi) / (penalty_threshold - hi) * 70)

    speed_score = _norm(features["talk_speed_wps"], (2.5, 4.0), 6.0)
    pause_score = _norm(features["pause_count_per_minute"], (3, 8), 20)
    filler_val = features["filler_word_ratio"]
    filler_score = 100 if filler_val < 0.03 else max(0, 100 - (filler_val - 0.03) / 0.05 * 70)
    speaking_ratio = features["speaking_ratio"]
    sr_score = min(100, speaking_ratio / 0.7 * 100) if speaking_ratio < 0.7 else 100
    sr_score = max(0, sr_score)
    sentiment = features.get("transcribe_sentiment", {}).get("overall", "NEUTRAL")
    sent_score = {"POSITIVE": 100, "NEUTRAL": 80, "MIXED": 60, "NEGATIVE": 40}.get(sentiment, 80)

    total = (
        speed_score * VOICE_WEIGHTS["talk_speed"]
        + pause_score * VOICE_WEIGHTS["pause_frequency"]
        + filler_score * VOICE_WEIGHTS["filler_ratio"]
        + sr_score * VOICE_WEIGHTS["speaking_ratio"]
        + sent_score * VOICE_WEIGHTS["sentiment"]
    )
    return round(total)
