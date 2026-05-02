"""Unit tests for rubric.py — pure logic, no external deps."""

from shared.eval_core.rubric import content_score_from_checkpoints, overall_result_label, FAANG_CHECKPOINTS


def _make_checkpoints(pass_count: int) -> dict:
    keys = [k for k, _, _ in FAANG_CHECKPOINTS]
    return {k: {"result": "Pass" if i < pass_count else "No-Pass", "reason": "x"} for i, k in enumerate(keys)}


class TestContentScore:
    def test_all_pass(self):
        assert content_score_from_checkpoints(_make_checkpoints(6)) == 100

    def test_all_fail(self):
        assert content_score_from_checkpoints(_make_checkpoints(0)) == 0

    def test_half(self):
        assert content_score_from_checkpoints(_make_checkpoints(3)) == 50

    def test_five_of_six(self):
        assert content_score_from_checkpoints(_make_checkpoints(5)) == 83

    def test_ignores_unknown_result_values(self):
        cp = {"star_structure": {"result": "Maybe", "reason": "x"}}
        assert content_score_from_checkpoints(cp) == 0


class TestOverallResult:
    def test_pass_boundary(self):
        assert overall_result_label(75) == "Pass"
        assert overall_result_label(100) == "Pass"

    def test_borderline(self):
        assert overall_result_label(50) == "Borderline"
        assert overall_result_label(74) == "Borderline"

    def test_no_pass(self):
        assert overall_result_label(49) == "No-Pass"
        assert overall_result_label(0) == "No-Pass"


# ---------------- voice_score_from_features ----------------
from shared.eval_core.rubric import voice_score_from_features


def _features(**overrides) -> dict:
    """Build a valid-by-default features dict, overriding specific fields."""
    base = {
        "duration_total_sec": 30.0,
        "duration_speaking_sec": 28.0,
        "speaking_ratio": 0.93,
        "talk_speed_cps": 4.0,
        "pause_count": 2,
        "pause_count_per_minute": 4.0,
        "longest_pause_sec": 0.6,
        "filler_word_count": 1,
        "filler_word_ratio": 0.02,
        "filler_words_detected": ["嗯"],
    }
    base.update(overrides)
    return base


class TestVoiceScoreFromFeatures:
    def test_ideal_answer_scores_100(self):
        assert voice_score_from_features(_features()) == 100

    def test_zero_duration_returns_zero(self):
        assert voice_score_from_features(_features(duration_total_sec=0)) == 0

    def test_zero_speaking_returns_zero(self):
        assert voice_score_from_features(_features(duration_speaking_sec=0)) == 0

    def test_slow_speed_deduction(self):
        assert voice_score_from_features(_features(talk_speed_cps=2.0)) == 85

    def test_fast_speed_deduction(self):
        assert voice_score_from_features(_features(talk_speed_cps=6.5)) == 85

    def test_extreme_slow_deduction(self):
        assert voice_score_from_features(_features(talk_speed_cps=1.0)) == 75

    def test_extreme_fast_deduction(self):
        assert voice_score_from_features(_features(talk_speed_cps=8.0)) == 75

    def test_too_many_pauses(self):
        assert voice_score_from_features(_features(pause_count_per_minute=20)) == 90

    def test_extreme_pauses(self):
        assert voice_score_from_features(_features(pause_count_per_minute=30)) == 80

    def test_filler_heavy(self):
        assert voice_score_from_features(_features(filler_word_ratio=0.10)) == 85

    def test_filler_extreme(self):
        assert voice_score_from_features(_features(filler_word_ratio=0.20)) == 70

    def test_low_speaking_ratio_penalty(self):
        # Half the time silent → -20
        assert voice_score_from_features(_features(speaking_ratio=0.3)) == 80

    def test_multiple_deductions_stack(self):
        # Slow (-15) + heavy fillers (-15) + low speaking (-20) = 50
        f = _features(talk_speed_cps=2.0, filler_word_ratio=0.10, speaking_ratio=0.3)
        assert voice_score_from_features(f) == 50

    def test_lower_bound_clamped(self):
        # All deductions maxed → should be >= 0
        f = _features(
            talk_speed_cps=0.5,
            pause_count_per_minute=30,
            filler_word_ratio=0.30,
            speaking_ratio=0.2,
        )
        assert voice_score_from_features(f) == 5  # 100-25-20-30-20 = 5

    def test_missing_keys_treated_as_zero(self):
        # Minimum valid → duration fields only
        f = {"duration_total_sec": 10, "duration_speaking_sec": 8}
        # cps=0 → no deduction, fillers=0, pauses=0, speaking=0 (missing) → no penalty
        assert voice_score_from_features(f) == 100

    def test_none_values_treated_as_zero(self):
        f = _features(talk_speed_cps=None, filler_word_ratio=None)
        assert voice_score_from_features(f) == 100

    def test_boundary_cps_lower(self):
        # Exactly 2.5 cps = on boundary, no deduction
        assert voice_score_from_features(_features(talk_speed_cps=2.5)) == 100
        # Just below
        assert voice_score_from_features(_features(talk_speed_cps=2.49)) == 85

    def test_boundary_cps_upper(self):
        assert voice_score_from_features(_features(talk_speed_cps=6.0)) == 100
        assert voice_score_from_features(_features(talk_speed_cps=6.01)) == 85

    def test_boundary_pause_rate(self):
        assert voice_score_from_features(_features(pause_count_per_minute=15)) == 100
        assert voice_score_from_features(_features(pause_count_per_minute=15.01)) == 90

    def test_speaking_ratio_none_not_penalized(self):
        # If speaking_ratio is missing/None, should NOT trigger <0.4 deduction
        # (guard: `0 < ratio < 0.4` — 0 < 0 is False)
        f = _features()
        f.pop("speaking_ratio")
        assert voice_score_from_features(f) == 100
        f2 = _features(speaking_ratio=None)
        assert voice_score_from_features(f2) == 100

    def test_speaking_ratio_exactly_zero_not_penalized(self):
        # Explicit 0 also should not deduct (strict < comparison)
        assert voice_score_from_features(_features(speaking_ratio=0)) == 100
