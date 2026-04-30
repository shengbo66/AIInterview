"""Unit tests for voice_features.py — pure logic."""

from shared.eval_core.voice_features import count_units, count_fillers, extract_features, voice_score


class TestCountUnits:
    def test_english_words(self):
        assert count_units("Hello world foo", "en") == 3

    def test_english_extra_whitespace(self):
        assert count_units("  a   b  ", "en") == 2

    def test_chinese_characters(self):
        assert count_units("你好世界", "zh") == 4

    def test_chinese_with_punctuation(self):
        assert count_units("你好，世界！", "zh") == 4

    def test_empty(self):
        assert count_units("", "en") == 0
        assert count_units("", "zh") == 0


class TestCountFillers:
    def test_english_fillers(self):
        count, detected = count_fillers("um so uh yeah like you know", "en")
        assert count == 4
        assert "um" in detected
        assert "uh" in detected
        assert "like" in detected
        assert "you know" in detected

    def test_chinese_fillers(self):
        count, detected = count_fillers("嗯那个这个就是说的话", "zh")
        assert count >= 3  # 嗯 + 那个 + 这个 + 就是
        assert "嗯" in detected

    def test_no_fillers(self):
        count, detected = count_fillers("Clean answer with no fillers.", "en")
        assert count == 0
        assert detected == []


class TestExtractFeatures:
    def test_minimal_input(self):
        tca = {
            "Transcript": [
                {"BeginOffsetMillis": 1000, "EndOffsetMillis": 3000, "Content": "hello"},
                {"BeginOffsetMillis": 4000, "EndOffsetMillis": 6000, "Content": "world"},
            ]
        }
        features = extract_features(tca, "hello world", "en", duration_sec=10.0)
        assert features["word_count"] == 2
        assert features["duration_total_sec"] == 10.0
        assert features["pause_count"] == 1  # gap between 3s and 4s

    def test_with_fillers(self):
        tca = {"Transcript": [{"BeginOffsetMillis": 0, "EndOffsetMillis": 5000, "Content": "um so yeah"}]}
        features = extract_features(tca, "um so uh yeah", "en", duration_sec=5.0)
        assert features["filler_word_count"] >= 2


class TestVoiceScore:
    def _base(self):
        return {
            "talk_speed_wps": 3.0,
            "pause_count_per_minute": 5,
            "filler_word_ratio": 0.02,
            "speaking_ratio": 0.8,
            "transcribe_sentiment": {"overall": "NEUTRAL"},
        }

    def test_optimal_features(self):
        score = voice_score(self._base())
        assert score >= 80  # all in optimal ranges

    def test_too_fast_penalized(self):
        f = self._base()
        f["talk_speed_wps"] = 7.0  # way too fast
        assert voice_score(f) < voice_score(self._base())

    def test_too_many_fillers_penalized(self):
        f = self._base()
        f["filler_word_ratio"] = 0.15
        assert voice_score(f) < voice_score(self._base())

    def test_negative_sentiment_penalized(self):
        f = self._base()
        f["transcribe_sentiment"] = {"overall": "NEGATIVE"}
        assert voice_score(f) < voice_score(self._base())
