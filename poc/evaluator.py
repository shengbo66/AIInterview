"""Evaluator — Stage 1 (per-question) + Stage 2 (overall) orchestration."""
import time
from shared.eval_core.rubric import content_score_from_checkpoints, overall_result_label, OVERALL_WEIGHTS
from config import RUBRIC_VERSION
from shared.eval_core.prompt_template import stage1_prompt, stage2_prompt
from claude_client import invoke as claude_invoke
from shared.eval_core.voice_features import extract_features, voice_score
from transcribe_client import upload_audio_to_s3, run_call_analytics


def evaluate_one(
    audio_path: str,
    question: str,
    company: str,
    role: str,
    language: str,
    style_tags: list[str] | None = None,
) -> dict:
    """Evaluate a single Q&A. Returns {evaluation, voice_features, cost_usd, elapsed_sec}."""
    start = time.time()
    total_cost = 0.0

    s3_uri = upload_audio_to_s3(audio_path)
    tca_result, tca_meta = run_call_analytics(s3_uri, language=language)
    total_cost += tca_meta["cost_usd"]

    transcript_text = _extract_transcript_text(tca_result)
    features = extract_features(tca_result, transcript_text, language, tca_meta["duration_sec"])
    computed_voice_score = voice_score(features)

    prompt = stage1_prompt(question, transcript_text, features, company, role, language, style_tags)
    eval_json, claude_meta = claude_invoke(prompt)
    total_cost += claude_meta["cost_usd"]

    # Override computed scores to enforce rubric consistency
    computed_content_score = content_score_from_checkpoints(eval_json.get("content_checkpoints", {}))
    expression = eval_json.get("expression_score", 0)
    overall = round(
        computed_content_score * OVERALL_WEIGHTS["content"]
        + expression * OVERALL_WEIGHTS["expression"]
        + computed_voice_score * OVERALL_WEIGHTS["voice"]
    )
    eval_json["content_score"] = computed_content_score
    eval_json["voice_score"] = computed_voice_score
    eval_json["overall_score"] = overall
    eval_json["overall_result"] = overall_result_label(overall)

    return {
        "question": question,
        "transcript": transcript_text,
        "voice_features": features,
        "evaluation": eval_json,
        "cost_usd": round(total_cost, 4),
        "elapsed_sec": round(time.time() - start, 2),
        "rubric_version": RUBRIC_VERSION,
        "raw_prompt": prompt,
        "raw_response": claude_meta.get("raw_response", ""),
    }


def evaluate_interview(qas: list[dict]) -> dict:
    """
    Multi-question: qas = [{audio_path, question, company, role, language, style_tags?}, ...]
    Runs Stage 1 for each + Stage 2 overall aggregation.
    """
    start = time.time()
    per_q = []
    total_cost = 0.0
    for qa in qas:
        result = evaluate_one(**qa)
        per_q.append(result)
        total_cost += result["cost_usd"]

    # Stage 2 only if multiple questions
    if len(per_q) > 1:
        stage2 = stage2_prompt([r["evaluation"] for r in per_q])
        overall_json, meta2 = claude_invoke(stage2)
        total_cost += meta2["cost_usd"]
    else:
        # Single-question: use stage1 overall directly
        ev = per_q[0]["evaluation"]
        overall_json = {
            "overall_content_score": ev["content_score"],
            "overall_expression_score": ev["expression_score"],
            "overall_voice_score": ev["voice_score"],
            "overall_score": ev["overall_score"],
            "overall_result": ev["overall_result"],
            "overall_summary": ev.get("improvement_suggestions", ["-"])[0],
            "strengths": [],
            "top_3_improvement_priorities": ev.get("improvement_suggestions", [])[:3],
        }

    return {
        "per_question": per_q,
        "overall": overall_json,
        "total_cost_usd": round(total_cost, 4),
        "total_elapsed_sec": round(time.time() - start, 2),
        "rubric_version": RUBRIC_VERSION,
    }


def _extract_transcript_text(tca_result: dict) -> str:
    """Concatenate transcript items from Call Analytics output."""
    items = tca_result.get("Transcript") or tca_result.get("transcript") or []
    parts = []
    for item in items:
        content = item.get("Content") or item.get("content") or ""
        if content:
            parts.append(content)
    return " ".join(parts) if parts else tca_result.get("text", "")
