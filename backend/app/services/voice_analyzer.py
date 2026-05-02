"""Voice features analyzer for interview answer audio.

Given raw PCM16 LE mono audio + transcript, compute objective voice metrics:
- Duration (total / speaking / ratio)
- Talk speed (Chinese characters per second)
- Pause detection (count / longest / per-minute)
- Filler word usage (count / ratio / list)

Pure Python stdlib, no numpy. Performance target < 200ms for 2-min PCM.
Benchmark: 2min PCM = 1.92M int16 samples, ~6000 frames of 20ms, each RMS
loop over 320 samples → measured <50ms on modern CPU.

Used by evaluation_service to enrich per-question Evaluation records.
"""
from __future__ import annotations

import logging
import struct
from dataclasses import asdict, dataclass, field

logger = logging.getLogger("interviewer.voice_analyzer")

# Frame size for RMS calculation: 20ms @ 16kHz = 320 samples
_FRAME_MS = 20
_PAUSE_THRESHOLD_MS = 500  # contiguous low-RMS ≥ 500ms counts as a pause
_HESITATION_MIN_MS = 200  # short hesitation: 200ms ≤ silence < 500ms
_HESITATION_MAX_MS = 500
_MIN_SAMPLES_FOR_ANALYSIS = 16_000  # 1 second @ 16kHz (FR-4: fallback if shorter)

# Chinese filler words / disfluency markers
# Reference: 话语标记语 (discourse markers) common in Mandarin interviews
# Order matters (longer patterns first to avoid sub-matching "嗯" within "嗯嗯")
_FILLER_WORDS = [
    "嗯嗯",
    "嗯哼",
    "所以说",
    "对对",
    "然后就",
    "那个",
    "就是",
    "这个",
    "然后",
    "呃",
    "嗯",
    "啊",
    "呀",
]

# Relative RMS threshold: frames below this fraction of peak RMS count as silence
# Tuned to be robust against background noise
_SILENCE_REL_THRESHOLD = 0.05


@dataclass
class VoiceFeatures:
    """Objective voice metrics for one answer."""

    duration_total_sec: float = 0.0
    duration_speaking_sec: float = 0.0
    speaking_ratio: float = 0.0
    talk_speed_cps: float = 0.0
    pause_count: int = 0
    pause_count_per_minute: float = 0.0
    longest_pause_sec: float = 0.0
    filler_word_count: int = 0
    filler_word_ratio: float = 0.0
    filler_words_detected: list[str] = field(default_factory=list)
    # Sprint 7 additions (Tier 1, no external deps)
    first_response_delay_sec: float = 0.0
    hesitation_count: int = 0
    volume_mean: float = 0.0
    volume_stability: float = 0.0
    # Kept for backward compat with stage1 prompt template
    transcribe_sentiment: dict = field(default_factory=lambda: {"overall": "NEUTRAL"})

    def to_dict(self) -> dict:
        return asdict(self)


def _pcm16_to_ints(pcm: bytes) -> list[int]:
    """Decode raw PCM16 LE bytes to signed int samples.

    Truncates to even length (PCM16 = 2 bytes/sample).
    """
    n = len(pcm) // 2
    if n == 0:
        return []
    return list(struct.unpack(f"<{n}h", pcm[: n * 2]))


def _frame_rms(samples: list[int], start: int, size: int) -> float:
    """Root-mean-square of a sample window. Avoids overflow via float."""
    end = min(start + size, len(samples))
    if end <= start:
        return 0.0
    total = 0.0
    for i in range(start, end):
        v = samples[i]
        total += v * v
    return (total / (end - start)) ** 0.5


def _detect_pauses(
    samples: list[int],
    sample_rate: int,
) -> tuple[list[float], list[float], list[float], float]:
    """Return (leading_pauses, inter_pauses, trailing_pauses, total_silence_sec).

    A "pause" is contiguous low-RMS frames ≥ _PAUSE_THRESHOLD_MS.
    - leading_pauses: silence at the beginning (before any speech)
    - inter_pauses: silence between speech segments
    - trailing_pauses: silence after the last speech segment
    - total_silence_sec: sum of ALL frames below threshold (includes all three)

    Uses relative threshold (fraction of peak RMS) to handle varying mic levels.

    Returning 3 buckets (vs Sprint 6's single list) prevents double-counting
    leading silence as both `first_response_delay` and `pause_count` (architect
    review MED).
    """
    frame_size = int(sample_rate * _FRAME_MS / 1000)
    if frame_size <= 0 or len(samples) < frame_size:
        return [], [], [], 0.0

    # Compute RMS for each frame
    rmss: list[float] = []
    for i in range(0, len(samples) - frame_size + 1, frame_size):
        rmss.append(_frame_rms(samples, i, frame_size))

    if not rmss:
        return [], [], [], 0.0

    peak = max(rmss)
    if peak <= 0:
        # Entire audio is silent → one big leading pause
        total_sec = len(samples) / sample_rate
        return [total_sec], [], [], total_sec

    threshold = peak * _SILENCE_REL_THRESHOLD
    frames_per_pause_min = _PAUSE_THRESHOLD_MS // _FRAME_MS

    # First pass: classify each frame as silent (True) / voiced (False)
    is_silent = [r < threshold for r in rmss]
    total_silence_frames = sum(is_silent)

    # Find first and last voiced frame
    first_voiced = next((i for i, s in enumerate(is_silent) if not s), None)
    last_voiced = next(
        (len(is_silent) - 1 - i for i, s in enumerate(reversed(is_silent)) if not s),
        None,
    )

    if first_voiced is None:
        # All silent — already handled above (peak <= 0), defensive
        total_sec = total_silence_frames * _FRAME_MS / 1000.0
        return [total_sec], [], [], total_sec

    # Leading silence: frames [0, first_voiced)
    leading_pauses: list[float] = []
    if first_voiced > 0:
        length_sec = first_voiced * _FRAME_MS / 1000.0
        if first_voiced >= frames_per_pause_min:
            leading_pauses.append(length_sec)
        # If < 500ms we don't count it as a formal pause (too short)
        # but first_response_delay_sec still uses it

    # Trailing silence: frames (last_voiced, end)
    trailing_pauses: list[float] = []
    trailing_frames = len(is_silent) - 1 - last_voiced
    if trailing_frames >= frames_per_pause_min:
        trailing_pauses.append(trailing_frames * _FRAME_MS / 1000.0)

    # Inter pauses: silence segments strictly within [first_voiced, last_voiced]
    inter_pauses: list[float] = []
    current_silence_frames = 0
    for idx in range(first_voiced, last_voiced + 1):
        if is_silent[idx]:
            current_silence_frames += 1
        else:
            if current_silence_frames >= frames_per_pause_min:
                inter_pauses.append(current_silence_frames * _FRAME_MS / 1000.0)
            current_silence_frames = 0
    # Don't add trailing segment here (it's handled above)

    total_silence_sec = total_silence_frames * _FRAME_MS / 1000.0
    return leading_pauses, inter_pauses, trailing_pauses, total_silence_sec


def _count_hesitations(samples: list[int], sample_rate: int) -> int:
    """Count short silence segments in [_HESITATION_MIN_MS, _HESITATION_MAX_MS).

    Only counts INTER-speech hesitations (strictly between voiced frames),
    not leading/trailing silence.
    """
    frame_size = int(sample_rate * _FRAME_MS / 1000)
    if frame_size <= 0 or len(samples) < frame_size:
        return 0

    rmss: list[float] = []
    for i in range(0, len(samples) - frame_size + 1, frame_size):
        rmss.append(_frame_rms(samples, i, frame_size))
    if not rmss:
        return 0
    peak = max(rmss)
    if peak <= 0:
        return 0

    threshold = peak * _SILENCE_REL_THRESHOLD
    is_silent = [r < threshold for r in rmss]
    first_voiced = next((i for i, s in enumerate(is_silent) if not s), None)
    last_voiced = next(
        (len(is_silent) - 1 - i for i, s in enumerate(reversed(is_silent)) if not s),
        None,
    )
    if first_voiced is None or last_voiced is None:
        return 0

    hesitations = 0
    current_silence_frames = 0
    min_frames = _HESITATION_MIN_MS // _FRAME_MS
    max_frames = _HESITATION_MAX_MS // _FRAME_MS

    for idx in range(first_voiced, last_voiced + 1):
        if is_silent[idx]:
            current_silence_frames += 1
        else:
            if min_frames <= current_silence_frames < max_frames:
                hesitations += 1
            current_silence_frames = 0

    return hesitations


def _compute_volume_stats(samples: list[int], sample_rate: int) -> tuple[float, float]:
    """Return (volume_mean_normalized, volume_stability_cv).

    - volume_mean: mean RMS of non-silent frames, normalized by int16 max (32768)
    - volume_stability: coefficient of variation (stddev/mean) of non-silent frame RMS.
      0 = perfectly stable, >1 = highly unstable (stddev > mean)

    If no non-silent frames found, returns (0, 0).
    """
    frame_size = int(sample_rate * _FRAME_MS / 1000)
    if frame_size <= 0 or len(samples) < frame_size:
        return 0.0, 0.0

    rmss: list[float] = []
    for i in range(0, len(samples) - frame_size + 1, frame_size):
        rmss.append(_frame_rms(samples, i, frame_size))
    if not rmss:
        return 0.0, 0.0

    peak = max(rmss)
    if peak <= 0:
        return 0.0, 0.0

    threshold = peak * _SILENCE_REL_THRESHOLD
    voiced_rms = [r for r in rmss if r >= threshold]
    if not voiced_rms:
        return 0.0, 0.0

    mean = sum(voiced_rms) / len(voiced_rms)
    if mean <= 0:
        return 0.0, 0.0

    variance = sum((r - mean) ** 2 for r in voiced_rms) / len(voiced_rms)
    stddev = variance ** 0.5
    cv = stddev / mean  # coefficient of variation

    return mean / 32768.0, cv


def _count_chinese_chars(text: str) -> int:
    """Count CJK unified ideographs (excluding punctuation/spaces/numbers/english)."""
    return sum(1 for c in text if "\u4e00" <= c <= "\u9fff")


def _detect_fillers(transcript: str) -> tuple[int, list[str]]:
    """Return (total_filler_count, distinct_fillers_detected).

    Iterates in order (longest first). After matching, removes the matched
    substring from the working copy to avoid double-counting (e.g. 嗯嗯 should
    not also count as 2× 嗯).
    """
    if not transcript:
        return 0, []

    working = transcript
    detected: list[str] = []
    total = 0

    for filler in _FILLER_WORDS:
        # Count and remove
        count = working.count(filler)
        if count > 0:
            total += count
            detected.append(filler)
            working = working.replace(filler, "")

    return total, detected


def analyze(
    pcm_bytes: bytes,
    sample_rate: int,
    transcript: str,
) -> VoiceFeatures:
    """Analyze one answer's audio + transcript. Returns VoiceFeatures.

    Raises ValueError if pcm_bytes is shorter than 1 second (caller should
    fall back to dummy per FR-4).
    """
    samples = _pcm16_to_ints(pcm_bytes)
    if len(samples) < _MIN_SAMPLES_FOR_ANALYSIS:
        raise ValueError(
            f"PCM too short: {len(samples)} samples, need ≥ {_MIN_SAMPLES_FOR_ANALYSIS}"
        )

    duration_total = len(samples) / sample_rate

    leading_pauses, inter_pauses, _trailing_pauses, silence_total = _detect_pauses(
        samples, sample_rate
    )
    # Speaking time excludes all silence (leading + inter + trailing)
    duration_speaking = max(0.0, duration_total - silence_total)
    speaking_ratio = duration_speaking / duration_total if duration_total > 0 else 0.0

    # first_response_delay: total silence at the start (even if < 500ms threshold,
    # still useful signal for candidates who freeze)
    first_voiced_frame_offset_sec = 0.0
    if leading_pauses:
        first_voiced_frame_offset_sec = leading_pauses[0]
    else:
        # Check if there was short leading silence (< 500ms) not classified as pause
        frame_size = int(sample_rate * _FRAME_MS / 1000)
        rmss: list[float] = []
        for i in range(0, len(samples) - frame_size + 1, frame_size):
            rmss.append(_frame_rms(samples, i, frame_size))
        if rmss:
            peak = max(rmss)
            if peak > 0:
                threshold = peak * _SILENCE_REL_THRESHOLD
                for i, r in enumerate(rmss):
                    if r >= threshold:
                        first_voiced_frame_offset_sec = i * _FRAME_MS / 1000.0
                        break

    hesitation_count = _count_hesitations(samples, sample_rate)
    volume_mean, volume_stability = _compute_volume_stats(samples, sample_rate)

    # Chinese char count (excludes filler-word chars in filler_word_ratio denom?
    # We keep total char count as denom for an honest ratio.)
    char_count = _count_chinese_chars(transcript)
    filler_count, fillers = _detect_fillers(transcript)

    talk_speed = char_count / duration_speaking if duration_speaking >= 0.5 else 0.0
    filler_ratio = filler_count / char_count if char_count > 0 else 0.0

    # pause_count = inter-speech pauses only (not leading/trailing)
    # This avoids double-counting with first_response_delay_sec (architect review MED)
    pause_count = len(inter_pauses)
    longest_pause = max(inter_pauses) if inter_pauses else 0.0
    pauses_per_min = pause_count / (duration_total / 60.0) if duration_total > 0 else 0.0

    return VoiceFeatures(
        duration_total_sec=round(duration_total, 2),
        duration_speaking_sec=round(duration_speaking, 2),
        speaking_ratio=round(speaking_ratio, 3),
        talk_speed_cps=round(talk_speed, 2),
        pause_count=pause_count,
        pause_count_per_minute=round(pauses_per_min, 2),
        longest_pause_sec=round(longest_pause, 2),
        filler_word_count=filler_count,
        filler_word_ratio=round(filler_ratio, 3),
        filler_words_detected=fillers,
        first_response_delay_sec=round(first_voiced_frame_offset_sec, 2),
        hesitation_count=hesitation_count,
        volume_mean=round(volume_mean, 3),
        volume_stability=round(volume_stability, 3),
    )
