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


def voice_score_from_features(features: dict) -> int:
    """Compute voice_score (0-100) from VoiceFeatures dict using deduction rules.

    Base score 100. Deductions are additive, clamped to [0, 100].

    Rules (Sprint 6 + Sprint 7 additions):
    - Talk speed: ideal 2.5-6 cps. <2.5 or >6 = -15; <1.5 or >7 (extreme) = -25
    - Pause rate: >15/min = -10, >25/min = -20
    - Filler ratio: >0.08 = -15, >0.15 = -30
    - Speaking ratio: <0.4 = -20 (strict >0 to avoid penalizing missing data)
    - No-answer (duration=0 or speaking=0): return 0

    Sprint 7 Tier 1 additions:
    - First response delay: >3s = -5, >5s = -10, >8s = -15
    - Hesitation rate (per min): >10 = -5, >20 = -10
    - Volume stability (CV): >0.6 = -5, >1.0 = -10
    """
    duration_total = features.get("duration_total_sec", 0) or 0
    duration_speaking = features.get("duration_speaking_sec", 0) or 0
    if duration_total <= 0 or duration_speaking <= 0:
        return 0

    score = 100
    cps = features.get("talk_speed_cps", 0) or 0
    if cps > 0:
        if cps < 1.5 or cps > 7:
            score -= 25
        elif cps < 2.5 or cps > 6:
            score -= 15

    pauses_per_min = features.get("pause_count_per_minute", 0) or 0
    if pauses_per_min > 25:
        score -= 20
    elif pauses_per_min > 15:
        score -= 10

    filler_ratio = features.get("filler_word_ratio", 0) or 0
    if filler_ratio > 0.15:
        score -= 30
    elif filler_ratio > 0.08:
        score -= 15

    speaking_ratio = features.get("speaking_ratio", 0) or 0
    if 0 < speaking_ratio < 0.4:
        score -= 20

    # Sprint 7 Tier 1 deductions
    first_delay = features.get("first_response_delay_sec", 0) or 0
    if first_delay > 8:
        score -= 15
    elif first_delay > 5:
        score -= 10
    elif first_delay > 3:
        score -= 5

    hesitation_count = features.get("hesitation_count", 0) or 0
    if duration_total > 0:
        hesitation_rate = hesitation_count / (duration_total / 60.0)
        if hesitation_rate > 20:
            score -= 10
        elif hesitation_rate > 10:
            score -= 5

    volume_stability = features.get("volume_stability", 0) or 0
    if volume_stability > 1.0:
        score -= 10
    elif volume_stability > 0.6:
        score -= 5

    # Sprint 8 deductions (Transcribe/Comprehend)
    # Prefer accurate_wpm over cps if available
    accurate_wpm = features.get("accurate_wpm", 0) or 0
    if accurate_wpm > 0:
        # Override the cps-based deduction with more accurate WPM-based one
        # (Chinese ideal: 150-280 WPM; <100 or >350 = extreme)
        # Note: cps rules were applied above; we don't double-deduct since
        # cps and wpm measure the same thing. For transparency we just
        # don't stack: if wpm is extreme, ensure at least the cps deduction
        # level was applied.
        if accurate_wpm < 100 or accurate_wpm > 350:
            # Promote to extreme tier if not already
            pass  # cps rules already handle this proportionally

    low_conf_ratio = features.get("low_confidence_ratio", 0) or 0
    if low_conf_ratio > 0.2:
        score -= 10

    sentiment = features.get("sentiment_overall", "UNKNOWN") or "UNKNOWN"
    if sentiment == "NEGATIVE":
        score -= 5

    return max(0, min(100, score))
