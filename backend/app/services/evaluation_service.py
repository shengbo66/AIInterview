"""Evaluation pipeline: runs Claude on completed interviews.

Flow:
  1. Load interview + questions + answers
  2. For each Q/A pair: build stage1 prompt → Claude → per-question Evaluation row
  3. Aggregate per-question results → stage2 prompt → Claude → overall Evaluation row
  4. Update interview.status = "evaluated"

Retry: Claude invoke_json already retries 3x internally. If the whole pipeline
fails, we catch and set status = "evaluation_failed".

Sprint 3 scope: voice_score is always 0 (voice_features analysis deferred to Sprint 4).
"""
import logging

from shared.eval_core.prompt_template import stage1_prompt, stage2_prompt
from shared.eval_core.rubric import content_score_from_checkpoints, overall_result_label
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import selectinload

from app.clients import bedrock_claude
from app.models import Answer, Evaluation, Interview, Question

logger = logging.getLogger("interviewer.evaluation")

# Dummy voice features for Sprint 3 (no audio analysis yet)
_DUMMY_VOICE = {
    "duration_total_sec": 0,
    "talk_speed_wps": 0,
    "pause_count": 0,
    "pause_count_per_minute": 0,
    "longest_pause_sec": 0,
    "filler_word_ratio": 0,
    "filler_words_detected": [],
    "speaking_ratio": 0,
    "transcribe_sentiment": {"overall": "NEUTRAL"},
}


async def evaluate_interview(
    session_factory: async_sessionmaker[AsyncSession],
    interview_id: str,
) -> None:
    """Run full evaluation pipeline. Called as a background task after finalize."""
    try:
        await _run_pipeline(session_factory, interview_id)
    except Exception:
        logger.exception("evaluation pipeline failed for %s", interview_id)
        try:
            async with session_factory() as db:
                iv = await db.get(Interview, interview_id)
                if iv:
                    iv.status = "evaluation_failed"
                    await db.commit()
        except Exception:
            logger.exception("failed to mark evaluation_failed for %s", interview_id)


async def _run_pipeline(
    sf: async_sessionmaker[AsyncSession],
    interview_id: str,
) -> None:
    # 1. Load interview with Q/A
    async with sf() as db:
        res = await db.execute(
            select(Interview)
            .where(Interview.id == interview_id)
            .options(
                selectinload(Interview.questions).selectinload(Question.answer),
            )
        )
        iv = res.scalar_one_or_none()
        if iv is None:
            logger.error("interview %s not found", interview_id)
            return
        company = iv.company_name
        role = iv.role_title
        language = iv.language
        questions = sorted(iv.questions, key=lambda q: q.order_index)

    # 2. Filter Q/A pairs with actual answers
    qa_pairs: list[tuple[Question, Answer]] = []
    for q in questions:
        if q.answer and q.answer.transcript_text.strip():
            qa_pairs.append((q, q.answer))

    if not qa_pairs:
        logger.info("interview %s has no answered questions; skipping evaluation", interview_id)
        async with sf() as db:
            iv = await db.get(Interview, interview_id)
            if iv:
                iv.status = "evaluation_skipped"
                await db.commit()
        return

    # 3. Per-question evaluation (stage 1)
    per_q_results: list[dict] = []
    per_q_evals: list[Evaluation] = []

    for q, a in qa_pairs:
        voice_features = {**_DUMMY_VOICE, "duration_total_sec": a.duration_sec}
        prompt = stage1_prompt(
            question=q.question_text,
            transcript=a.transcript_text,
            voice_features=voice_features,
            company=company,
            role=role,
            language=language,
        )
        parsed, meta = await bedrock_claude.invoke_json(prompt, max_tokens=2000)

        # Extract scores
        checkpoints = parsed.get("content_checkpoints", {})
        c_score = content_score_from_checkpoints(checkpoints)
        e_score = int(parsed.get("expression_score", 0))
        v_score = 0  # Sprint 3: no voice analysis
        o_score = round(c_score * 0.5 + e_score * 0.3 + v_score * 0.2)

        suggestions = parsed.get("improvement_suggestions", [])
        suggestion_text = "\n".join(f"• {s}" for s in suggestions) if suggestions else ""

        ev = Evaluation(
            interview_id=interview_id,
            question_id=q.id,
            content_score=c_score,
            expression_score=e_score,
            voice_score=v_score,
            overall_score=o_score,
            overall_result=overall_result_label(o_score),
            improvement_suggestion=suggestion_text,
            ideal_answer=parsed.get("ideal_answer"),
            voice_features=voice_features,
            raw_prompt=prompt[:5000],  # truncate to save space
            raw_response=parsed,
            evaluation_cost_usd=meta.get("cost_usd", 0),
        )
        per_q_evals.append(ev)
        per_q_results.append({
            "question": q.question_text,
            "content_score": c_score,
            "expression_score": e_score,
            "voice_score": v_score,
            "overall_score": o_score,
            "improvement_suggestions": suggestions,
        })

    # 4. Overall evaluation (stage 2)
    overall_prompt = stage2_prompt(per_q_results)
    overall_parsed, overall_meta = await bedrock_claude.invoke_json(overall_prompt, max_tokens=1500)

    overall_ev = Evaluation(
        interview_id=interview_id,
        question_id=None,  # NULL = overall
        content_score=int(overall_parsed.get("overall_content_score", 0)),
        expression_score=int(overall_parsed.get("overall_expression_score", 0)),
        voice_score=int(overall_parsed.get("overall_voice_score", 0)),
        overall_score=int(overall_parsed.get("overall_score", 0)),
        overall_result=overall_parsed.get("overall_result", "Borderline"),
        improvement_suggestion="\n".join(
            f"• {p}" for p in overall_parsed.get("top_3_improvement_priorities", [])
        ),
        ideal_answer=None,
        voice_features={},
        raw_prompt=overall_prompt[:5000],
        raw_response=overall_parsed,
        evaluation_cost_usd=overall_meta.get("cost_usd", 0),
    )

    # 5. Persist all evaluations + update status
    async with sf() as db:
        for ev in per_q_evals:
            db.add(ev)
        db.add(overall_ev)
        iv = await db.get(Interview, interview_id)
        if iv:
            iv.status = "evaluated"
        await db.commit()

    total_cost = sum(e.evaluation_cost_usd for e in per_q_evals) + overall_ev.evaluation_cost_usd
    logger.info(
        "evaluation complete for %s: %d questions, overall=%d (%s), cost=$%.4f",
        interview_id,
        len(per_q_evals),
        overall_ev.overall_score,
        overall_ev.overall_result,
        total_cost,
    )
