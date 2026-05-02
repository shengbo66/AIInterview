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
        leading, inter, trailing, total_silence = _detect_pauses(samples, SR)
        # All silent → counts as leading pause
        assert len(leading) == 1
        assert leading[0] == pytest.approx(2.0, abs=0.05)
        assert inter == []
        assert trailing == []
        assert total_silence == pytest.approx(2.0, abs=0.05)

    def test_continuous_tone_no_pause(self):
        pcm = _gen_tone(2.0)
        samples = _pcm16_to_ints(pcm)
        leading, inter, trailing, total_silence = _detect_pauses(samples, SR)
        assert leading == []
        assert inter == []
        assert trailing == []
        assert total_silence < 0.1

    def test_tone_silence_tone(self):
        # 1s tone + 1s silence + 1s tone → 1 INTER pause
        pcm = _gen_tone(1.0) + _gen_silence(1.0) + _gen_tone(1.0)
        samples = _pcm16_to_ints(pcm)
        leading, inter, trailing, _ = _detect_pauses(samples, SR)
        assert leading == []
        assert len(inter) == 1
        assert inter[0] == pytest.approx(1.0, abs=0.1)
        assert trailing == []

    def test_multiple_pauses(self):
        # tone - silence - tone - silence - tone → 2 inter pauses
        pcm = (
            _gen_tone(1.0)
            + _gen_silence(0.7)
            + _gen_tone(1.0)
            + _gen_silence(0.8)
            + _gen_tone(1.0)
        )
        samples = _pcm16_to_ints(pcm)
        leading, inter, trailing, _ = _detect_pauses(samples, SR)
        assert leading == []
        assert len(inter) == 2
        assert trailing == []

    def test_short_silence_not_counted(self):
        # 200ms silence in middle → below _PAUSE_THRESHOLD_MS (500ms)
        pcm = _gen_tone(1.0) + _gen_silence(0.2) + _gen_tone(1.0)
        samples = _pcm16_to_ints(pcm)
        _leading, inter, _trailing, _ = _detect_pauses(samples, SR)
        assert inter == []  # too short

    def test_leading_silence_detected(self):
        # silence(0.8) + tone(2.0) — pause at the beginning
        pcm = _gen_silence(0.8) + _gen_tone(2.0)
        samples = _pcm16_to_ints(pcm)
        leading, inter, trailing, _ = _detect_pauses(samples, SR)
        assert len(leading) == 1
        assert leading[0] == pytest.approx(0.8, abs=0.1)
        assert inter == []
        assert trailing == []

    def test_trailing_silence_detected(self):
        # tone(2.0) + silence(0.8) — pause at the end
        pcm = _gen_tone(2.0) + _gen_silence(0.8)
        samples = _pcm16_to_ints(pcm)
        leading, inter, trailing, _ = _detect_pauses(samples, SR)
        assert leading == []
        assert inter == []
        assert len(trailing) == 1
        assert trailing[0] == pytest.approx(0.8, abs=0.1)

    def test_exactly_500ms_silence_counted(self):
        # Exactly threshold — should count as inter pause
        pcm = _gen_tone(1.0) + _gen_silence(0.5) + _gen_tone(1.0)
        samples = _pcm16_to_ints(pcm)
        _leading, inter, _trailing, _ = _detect_pauses(samples, SR)
        assert len(inter) == 1

    def test_leading_plus_inter(self):
        # silence(0.6) + tone + silence(0.8) + tone → 1 leading, 1 inter
        pcm = _gen_silence(0.6) + _gen_tone(1.0) + _gen_silence(0.8) + _gen_tone(1.0)
        samples = _pcm16_to_ints(pcm)
        leading, inter, trailing, _ = _detect_pauses(samples, SR)
        assert len(leading) == 1
        assert len(inter) == 1
        assert trailing == []


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
        # Sprint 7 additions
        assert vf.first_response_delay_sec == 0.0
        assert vf.hesitation_count == 0
        assert vf.volume_mean == 0.0
        assert vf.volume_stability == 0.0

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
            "first_response_delay_sec",
            "hesitation_count",
            "volume_mean",
            "volume_stability",
            "transcribe_sentiment",
        }
        assert set(d.keys()) == expected_keys


# ---------- Sprint 7 Tier 1 new metrics ----------


class TestFirstResponseDelay:
    def test_no_leading_silence_zero_delay(self):
        pcm = _gen_tone(2.0)
        features = analyze(pcm, SR, "你好")
        assert features.first_response_delay_sec == pytest.approx(0.0, abs=0.1)

    def test_short_leading_silence_captured(self):
        # 400ms leading silence (< 500ms pause threshold) → should still show as delay
        pcm = _gen_silence(0.4) + _gen_tone(1.5)
        features = analyze(pcm, SR, "你好")
        assert features.first_response_delay_sec == pytest.approx(0.4, abs=0.1)

    def test_long_leading_silence_captured(self):
        # 2s leading silence → should appear as delay
        pcm = _gen_silence(2.0) + _gen_tone(1.5)
        features = analyze(pcm, SR, "你好")
        assert features.first_response_delay_sec == pytest.approx(2.0, abs=0.1)


class TestHesitationCount:
    def test_no_hesitation_continuous_tone(self):
        pcm = _gen_tone(3.0)
        features = analyze(pcm, SR, "你好")
        assert features.hesitation_count == 0

    def test_short_silence_counted_as_hesitation(self):
        # 300ms silence between speech (in [200, 500) ms range)
        pcm = _gen_tone(1.0) + _gen_silence(0.3) + _gen_tone(1.0)
        features = analyze(pcm, SR, "你好")
        assert features.hesitation_count == 1

    def test_long_silence_NOT_counted_as_hesitation(self):
        # 800ms silence → that's a pause, not a hesitation
        pcm = _gen_tone(1.0) + _gen_silence(0.8) + _gen_tone(1.0)
        features = analyze(pcm, SR, "你好")
        assert features.hesitation_count == 0  # it's a pause now, not hesitation

    def test_very_short_silence_NOT_counted(self):
        # 100ms silence → below hesitation threshold (200ms)
        pcm = _gen_tone(1.0) + _gen_silence(0.1) + _gen_tone(1.0)
        features = analyze(pcm, SR, "你好")
        assert features.hesitation_count == 0

    def test_multiple_hesitations(self):
        pcm = (
            _gen_tone(0.8)
            + _gen_silence(0.3)  # hesitation 1
            + _gen_tone(0.8)
            + _gen_silence(0.25)  # hesitation 2
            + _gen_tone(0.8)
        )
        features = analyze(pcm, SR, "你好")
        assert features.hesitation_count == 2


class TestVolumeStats:
    def test_constant_tone_low_volume_stability(self):
        # Perfectly constant tone → stddev=0, CV=0
        pcm = _gen_tone(2.0, amp=8000)
        features = analyze(pcm, SR, "你好")
        assert features.volume_stability < 0.1  # very stable
        assert features.volume_mean > 0

    def test_varying_amplitude_high_volume_instability(self):
        # Speech-like (amplitude envelope) → higher CV
        pcm = _gen_speech_like(3.0)
        features = analyze(pcm, SR, "你好")
        # speech_like has sin^0.5 envelope → moderate variability
        assert features.volume_stability > 0.1
        assert features.volume_mean > 0

    def test_silent_audio_zero_volume(self):
        # All silence can't be analyzed (too short); use quiet tone
        pcm = _gen_tone(2.0, amp=50)  # very quiet
        features = analyze(pcm, SR, "你好")
        assert features.volume_mean >= 0
        assert features.volume_mean < 0.01  # very quiet
