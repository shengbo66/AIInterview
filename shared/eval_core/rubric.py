"""Rubric definitions for evaluation."""

FAANG_CHECKPOINTS = [
    ("star_structure", "STAR Method Structure", "Situation / Task / Action / Result 四要素是否完整"),
    ("specificity_details", "Specificity & Details", "是否有具体事例、数据、指标"),
    ("impact_results", "Impact & Results", "是否清晰展示可量化的影响/结果"),
    ("leadership_ownership", "Leadership & Ownership", "是否体现个人主导/主动担当"),
    ("problem_solving", "Problem-Solving", "解决问题的思路是否清晰"),
    ("communication_clarity", "Communication Clarity", "表达是否结构化、易于跟随"),
]

EXPRESSION_LEVELS = [
    (1, (0, 20), "表达混乱、缺逻辑"),
    (2, (21, 40), "基本可理解但缺结构"),
    (3, (41, 60), "逻辑基本清晰"),
    (4, (61, 80), "结构化表达、重点突出"),
    (5, (81, 100), "开门见山 + 分点清晰 + 呼应问题"),
]

VOICE_WEIGHTS = {
    "talk_speed": 0.25,
    "pause_frequency": 0.20,
    "filler_ratio": 0.20,
    "speaking_ratio": 0.15,
    "sentiment": 0.20,
}

OVERALL_WEIGHTS = {"content": 0.5, "expression": 0.3, "voice": 0.2}

PASS_THRESHOLD = 75
NO_PASS_THRESHOLD = 50

FILLER_WORDS = {
    "zh": ["嗯", "啊", "呃", "就是", "然后", "那个", "这个", "其实", "就", "对"],
    "en": ["um", "uh", "like", "you know", "i mean", "actually", "basically", "sort of"],
}


def content_score_from_checkpoints(checkpoints: dict) -> int:
    """pass_count / 6 * 100."""
    pass_count = sum(1 for v in checkpoints.values() if v.get("result") == "Pass")
    return round(pass_count / len(FAANG_CHECKPOINTS) * 100)


def overall_result_label(overall_score: int) -> str:
    if overall_score >= PASS_THRESHOLD:
        return "Pass"
    if overall_score >= NO_PASS_THRESHOLD:
        return "Borderline"
    return "No-Pass"


def rubric_markdown() -> str:
    """Render rubric as markdown for prompt injection."""
    cp = "\n".join(f"- **{name}**: {desc}" for _, name, desc in FAANG_CHECKPOINTS)
    return f"""### Content Dimension — 6 FAANG Checkpoints (each Pass/No-Pass):
{cp}

### Expression Dimension — 5 levels (score 0-100):
1 (0-20): 混乱  2 (21-40): 缺结构  3 (41-60): 清晰  4 (61-80): 结构化  5 (81-100): 突出

### Voice Dimension — weighted objective metrics (score 0-100, provided below).

### Overall Result: Pass (>=75) / Borderline (50-74) / No-Pass (<50)
"""
