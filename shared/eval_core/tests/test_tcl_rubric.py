import pytest
from shared.eval_core.tcl_rubric import (
    tcl_rubric_markdown,
    tcl_content_score,
    TCL_L2_CHECKPOINTS,
)


def test_rubric_markdown_contains_all_checkpoints():
    md = tcl_rubric_markdown()
    for key, name, _ in TCL_L2_CHECKPOINTS:
        assert name in md, f"checkpoint {name} missing from rubric markdown"


def test_tcl_content_score_all_pass():
    checkpoints = {key: {"result": "Pass"} for key, _, _ in TCL_L2_CHECKPOINTS}
    content, expression, dim_scores = tcl_content_score(checkpoints)
    assert content == 100
    assert expression == 100
    assert "tech_depth" in dim_scores
    assert "architecture" in dim_scores
    assert "competency" in dim_scores
    assert "culture" in dim_scores


def test_tcl_content_score_all_fail():
    checkpoints = {key: {"result": "No-Pass"} for key, _, _ in TCL_L2_CHECKPOINTS}
    content, expression, dim_scores = tcl_content_score(checkpoints)
    assert content == 0
    assert expression == 0


def test_tcl_content_score_partial():
    checkpoints = {
        "tech_depth_knowledge": {"result": "Pass"},
        "tech_depth_impl":      {"result": "Pass"},
        "arch_e2e_design":      {"result": "No-Pass"},
        "arch_integration":     {"result": "No-Pass"},
        "tcl_competency_star":  {"result": "Pass"},
        "tcl_culture_fit":      {"result": "No-Pass"},
    }
    content, expression, dim_scores = tcl_content_score(checkpoints)
    assert 0 < content < 100
    assert dim_scores["tech_depth"] == 100
    assert dim_scores["architecture"] == 0


def test_dim_scores_keys():
    checkpoints = {key: {"result": "Pass"} for key, _, _ in TCL_L2_CHECKPOINTS}
    _, _, dim_scores = tcl_content_score(checkpoints)
    assert set(dim_scores.keys()) == {"tech_depth", "architecture", "competency", "culture"}
