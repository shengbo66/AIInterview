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
