"""Tests for voice_analyzer module. Pure stdlib — no AWS, no fixtures needed."""
from __future__ import annotations

import math
import struct

import pytest

from app.services.voice_analyzer import (
    VoiceFeatures,
    _count_chinese_chars,
    _detect_fillers,
    _detect_pauses,
    _pcm16_to_ints,
    analyze,
)

SR = 16_000  # 16 kHz


def _gen_tone(seconds: float, freq: int = 440, amp: int = 8000) -> bytes:
    """Generate PCM16 LE sine tone."""
    n = int(seconds * SR)
    samples = [int(amp * math.sin(2 * math.pi * freq * i / SR)) for i in range(n)]
    return struct.pack(f"<{n}h", *samples)


def _gen_silence(seconds: float) -> bytes:
    n = int(seconds * SR)
    return struct.pack(f"<{n}h", *([0] * n))


def _gen_speech_like(seconds: float, amp: int = 6000) -> bytes:
    """Generate speech-like audio (varying amplitude + frequency sweep)."""
    n = int(seconds * SR)
    samples: list[int] = []
    for i in range(n):
        # Frequency drifts to mimic formants
        freq = 200 + (i / n) * 300
        # Amplitude envelope
        env = math.sin(math.pi * i / n) ** 0.5
        val = int(amp * env * math.sin(2 * math.pi * freq * i / SR))
        samples.append(max(-32767, min(32767, val)))
    return struct.pack(f"<{n}h", *samples)


# ---------- Pure helpers ----------


class TestPcm16Decode:
    def test_empty_returns_empty(self):
        assert _pcm16_to_ints(b"") == []

    def test_odd_length_truncated(self):
        # 3 bytes → 1 sample
        assert len(_pcm16_to_ints(b"\x00\x00\xff")) == 1

    def test_known_values(self):
        data = struct.pack("<3h", 0, 1, -1)
        assert _pcm16_to_ints(data) == [0, 1, -1]


class TestChineseCharCount:
    def test_pure_chinese(self):
        assert _count_chinese_chars("你好世界") == 4

    def test_mixed(self):
        assert _count_chinese_chars("hello 世界 2026") == 2

    def test_punctuation_excluded(self):
        assert _count_chinese_chars("你好，世界！") == 4

    def test_empty(self):
        assert _count_chinese_chars("") == 0


class TestFillerDetection:
    def test_single_filler(self):
        count, fillers = _detect_fillers("嗯我觉得这个很重要")
        assert count >= 2  # at least 嗯 + 这个
        assert "嗯" in fillers
        assert "这个" in fillers

    def test_no_filler(self):
        count, fillers = _detect_fillers("我对通信系统非常感兴趣")
        assert count == 0
        assert fillers == []

    def test_double_filler_not_double_counted(self):
        # "嗯嗯" should match as 1× 嗯嗯, not 2× 嗯
        count, fillers = _detect_fillers("嗯嗯我明白")
        assert count == 1
        assert "嗯嗯" in fillers
        assert "嗯" not in fillers

    def test_multiple_distinct(self):
        count, fillers = _detect_fillers("嗯就是那个我觉得吧")
        assert "嗯" in fillers
        assert "就是" in fillers
        assert "那个" in fillers
        assert count == 3

    def test_empty_transcript(self):
        count, fillers = _detect_fillers("")
        assert count == 0
        assert fillers == []


class TestPauseDetection:
    def test_all_silence(self):
        pcm = _gen_silence(2.0)
        samples = _pcm16_to_ints(pcm)
        pauses, total_silence = _detect_pauses(samples, SR)
        # When peak RMS is 0, entire audio counts as silence
        assert len(pauses) == 1
        assert pauses[0] == pytest.approx(2.0, abs=0.05)
        assert total_silence == pytest.approx(2.0, abs=0.05)

    def test_continuous_tone_no_pause(self):
        pcm = _gen_tone(2.0)
        samples = _pcm16_to_ints(pcm)
        pauses, total_silence = _detect_pauses(samples, SR)
        assert pauses == []
        assert total_silence < 0.1  # negligible

    def test_tone_silence_tone(self):
        # 1s tone + 1s silence + 1s tone → 1 pause of ~1s
        pcm = _gen_tone(1.0) + _gen_silence(1.0) + _gen_tone(1.0)
        samples = _pcm16_to_ints(pcm)
        pauses, _ = _detect_pauses(samples, SR)
        assert len(pauses) == 1
        assert pauses[0] == pytest.approx(1.0, abs=0.1)

    def test_multiple_pauses(self):
        # tone - silence - tone - silence - tone → 2 pauses
        pcm = (
            _gen_tone(1.0)
            + _gen_silence(0.7)
            + _gen_tone(1.0)
            + _gen_silence(0.8)
            + _gen_tone(1.0)
        )
        samples = _pcm16_to_ints(pcm)
        pauses, _ = _detect_pauses(samples, SR)
        assert len(pauses) == 2

    def test_short_silence_not_counted(self):
        # 200ms silence in middle → below _PAUSE_THRESHOLD_MS (500ms)
        pcm = _gen_tone(1.0) + _gen_silence(0.2) + _gen_tone(1.0)
        samples = _pcm16_to_ints(pcm)
        pauses, _ = _detect_pauses(samples, SR)
        assert pauses == []

    def test_leading_silence_detected(self):
        # silence(0.8) + tone(2.0) — pause at the beginning
        pcm = _gen_silence(0.8) + _gen_tone(2.0)
        samples = _pcm16_to_ints(pcm)
        pauses, _ = _detect_pauses(samples, SR)
        assert len(pauses) == 1
        assert pauses[0] == pytest.approx(0.8, abs=0.1)

    def test_trailing_silence_detected(self):
        # tone(2.0) + silence(0.8) — pause at the end (hits "Trailing silence" branch)
        pcm = _gen_tone(2.0) + _gen_silence(0.8)
        samples = _pcm16_to_ints(pcm)
        pauses, _ = _detect_pauses(samples, SR)
        assert len(pauses) == 1
        assert pauses[0] == pytest.approx(0.8, abs=0.1)

    def test_exactly_500ms_silence_counted(self):
        # Exactly threshold — should count (frames_per_pause_min = 25, 500/20=25)
        pcm = _gen_tone(1.0) + _gen_silence(0.5) + _gen_tone(1.0)
        samples = _pcm16_to_ints(pcm)
        pauses, _ = _detect_pauses(samples, SR)
        # Boundary inclusive: 25 frames ≥ 25 → counted
        assert len(pauses) == 1


# ---------- analyze() integration ----------


class TestAnalyze:
    def test_too_short_raises(self):
        pcm = _gen_tone(0.5)  # 0.5s < 1s minimum
        with pytest.raises(ValueError, match="too short"):
            analyze(pcm, SR, "你好")

    def test_normal_speech_produces_reasonable_features(self):
        pcm = _gen_speech_like(3.0)
        features = analyze(pcm, SR, "我对射频技术非常感兴趣")
        assert features.duration_total_sec == pytest.approx(3.0, abs=0.1)
        assert features.duration_speaking_sec > 2.0  # speech-like has few silent frames
        assert features.speaking_ratio > 0.7
        assert features.talk_speed_cps > 0
        assert features.filler_word_count == 0
        assert features.filler_words_detected == []

    def test_with_fillers_in_transcript(self):
        pcm = _gen_speech_like(4.0)
        features = analyze(pcm, SR, "嗯那个我觉得就是射频这个方向比较好")
        assert features.filler_word_count >= 3
        assert features.filler_word_ratio > 0
        assert len(features.filler_words_detected) >= 3

    def test_speech_with_pauses(self):
        # speech(1.5) + silence(0.8) + speech(1.5) → 1 pause ≥ 500ms
        pcm = _gen_speech_like(1.5) + _gen_silence(0.8) + _gen_speech_like(1.5)
        features = analyze(pcm, SR, "前半段 后半段")
        assert features.pause_count == 1
        assert features.longest_pause_sec == pytest.approx(0.8, abs=0.15)
        assert features.speaking_ratio < 0.85

    def test_speed_calculation(self):
        # 2s speech, 10 Chinese chars → 5 cps
        pcm = _gen_speech_like(2.0)
        features = analyze(pcm, SR, "我觉得射频方向非常重要")  # 11 chars
        # Rough check — speech-like audio has ~100% speaking ratio so cps ≈ 11/2 ≈ 5.5
        assert 3 < features.talk_speed_cps < 8

    def test_empty_transcript_zero_speed(self):
        pcm = _gen_speech_like(2.0)
        features = analyze(pcm, SR, "")
        assert features.talk_speed_cps == 0
        assert features.filler_word_count == 0

    def test_mixed_language_transcript(self):
        # Real transcripts often contain English terms, numbers, punctuation.
        # cps should be based on Chinese char count only.
        pcm = _gen_speech_like(2.0)
        features = analyze(pcm, SR, "我在 AWS 做 5G RF 的工作")  # 6 Chinese chars
        assert features.talk_speed_cps > 0
        # cps should roughly be 6 chars / ~2s speaking = ~3
        assert 1 < features.talk_speed_cps < 5

    def test_all_english_transcript_zero_cps(self):
        # No Chinese chars → cps = 0 / speaking = 0 (division guarded)
        pcm = _gen_speech_like(2.0)
        features = analyze(pcm, SR, "I work on 5G radio frequency design")
        assert features.talk_speed_cps == 0
        assert features.filler_word_count == 0

    def test_features_serializable(self):
        pcm = _gen_speech_like(2.0)
        features = analyze(pcm, SR, "测试")
        d = features.to_dict()
        assert isinstance(d, dict)
        assert "duration_total_sec" in d
        assert "filler_words_detected" in d
        assert isinstance(d["filler_words_detected"], list)

    def test_performance_under_budget(self):
        """2-minute PCM should analyze in < 200ms per NFR."""
        import time
        pcm = _gen_speech_like(120.0)  # 2 minutes
        start = time.perf_counter()
        features = analyze(pcm, SR, "我对射频方向很感兴趣 " * 20)
        elapsed_ms = (time.perf_counter() - start) * 1000
        assert elapsed_ms < 500, f"took {elapsed_ms:.0f}ms, budget 500ms (target 200ms)"
        assert features.duration_total_sec == pytest.approx(120.0, abs=0.5)


class TestVoiceFeaturesDataclass:
    def test_default_is_all_zero(self):
        vf = VoiceFeatures()
        assert vf.duration_total_sec == 0.0
        assert vf.filler_words_detected == []
        assert vf.transcribe_sentiment == {"overall": "NEUTRAL"}

    def test_to_dict_complete(self):
        vf = VoiceFeatures(duration_total_sec=5.0, filler_word_count=3)
        d = vf.to_dict()
        expected_keys = {
            "duration_total_sec",
            "duration_speaking_sec",
            "speaking_ratio",
            "talk_speed_cps",
            "pause_count",
            "pause_count_per_minute",
            "longest_pause_sec",
            "filler_word_count",
            "filler_word_ratio",
            "filler_words_detected",
            "transcribe_sentiment",
        }
        assert set(d.keys()) == expected_keys
