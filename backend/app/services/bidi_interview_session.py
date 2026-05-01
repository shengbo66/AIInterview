"""Bidi interview session — persistence + system prompt composition.

Extracted from routers/demo_bidi.py to enable unit testing without a real
WebSocket. The session consumes a stream of Strands events (from agent.run's
output callback) and persists Interview/Question/Answer + usage as they arrive.

Design:
  - "turn" = one transcript stream with role=assistant|user and is_final=True.
  - assistant turn final → create Question (order_index = current assistant
    question count). AI-speaking audio accumulated from prior audio_stream
    events is uploaded to S3 and linked.
  - user turn final → create Answer linked to the latest Question. User audio
    accumulated since last assistant final is uploaded and linked.
  - bidi_usage → update cumulative token/cost on Interview.
  - session end (external close) → mark status=completed, bidi_ended_at=now.

Audio pricing (Nova Sonic, us-east-1, as of 2026-04):
  - audio input:  $0.0034 / 1k tokens
  - audio output: $0.0136 / 1k tokens
These are inputs from probe: inputTokens/outputTokens are totals across all
modalities; for walking-skeleton we use a blended rate to avoid complicating
the engine with modality_details. Can refine in later sprint.
"""
from __future__ import annotations

import asyncio
import base64
import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.clients import s3_audio
from app.models import Answer, CompanyStyle, Interview, Question

logger = logging.getLogger("interviewer.bidi_session")

# Blended price estimate; refine when we split per-modality in a later sprint.
PRICE_IN_PER_1K = 0.0034
PRICE_OUT_PER_1K = 0.0136


@dataclass
class _TurnBuffer:
    audio_chunks: list[bytes] = field(default_factory=list)
    started_at: datetime | None = None

    def append(self, pcm_bytes: bytes) -> None:
        if self.started_at is None:
            self.started_at = datetime.utcnow()
        self.audio_chunks.append(pcm_bytes)

    def flush(self) -> tuple[bytes, float]:
        """Return (concatenated PCM, duration_sec) and reset."""
        data = b"".join(self.audio_chunks)
        # PCM16 mono 16kHz: 2 bytes/sample, 16000 samples/sec = 32000 bytes/sec
        duration_sec = len(data) / 32000.0
        self.audio_chunks.clear()
        self.started_at = None
        return data, duration_sec


def compose_system_prompt(company_style: CompanyStyle, role_title: str) -> str:
    """Prefer CompanyStyle.prompt_context_text; fall back to inline defaults."""
    base = (company_style.prompt_context_text or "").strip()
    sample = "\n".join(f"- {q}" for q in (company_style.sample_questions or [])[:6])
    return (
        f"你是 {company_style.name} 面试官，正在面试一位应聘 \"{role_title}\" 的候选人。\n\n"
        f"{base}\n\n"
        "候选样题（可参考，也可基于候选人背景自然追问）：\n"
        f"{sample}\n\n"
        "面试规则：\n"
        "- 开场用一句话自我介绍，然后直接问第一题。\n"
        "- 每次只问一个问题，等候选人完整回答再继续。\n"
        "- 语气简洁专业，每次发言不超过两句话。\n"
        "- 面试控制在 45 分钟以内，约 6-8 题后礼貌收尾（说 \"今天的面试就到这里，感谢你的参与\"）。\n"
        "- 收尾后不再提问，等候选人告别即可。\n"
    )


class BidiInterviewSession:
    """Handles one interview's persistence + usage accounting.

    Usage:
        session = BidiInterviewSession(session_factory, role_title="...")
        await session.setup()                   # loads CompanyStyle, creates Interview
        prompt = session.system_prompt           # pass to BidiAgent
        async for event in events:
            await session.on_event(event)       # updates DB/S3 in background
        await session.finalize()                 # mark completed
    """

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        role_title: str,
        s3_prefix: str = "interviews",
    ) -> None:
        self._sf = session_factory
        self._role_title = role_title
        self._s3_prefix = s3_prefix
        self._ai_buf = _TurnBuffer()
        self._user_buf = _TurnBuffer()
        self._interview_id: str | None = None
        self._company_style_id: str | None = None
        self._system_prompt: str | None = None
        self._q_count = 0  # assistant turns persisted so far
        self._last_question_id: str | None = None
        # Per-question user audio accumulator. Key = question_id, value = PCM chunks.
        # Uploaded to S3 when the next assistant turn starts (= user finished answering)
        # or during finalize (for the last answer).
        self._user_audio_chunks: dict[str, list[bytes]] = {}
        # Serialize all DB writes. SQLite can't handle concurrent write
        # transactions well; other backends benefit from this too since
        # our writes are naturally ordered (Q → A → Q → A).
        self._db_lock: asyncio.Lock = asyncio.Lock()
        # Background tasks (S3 uploads) started by on_event processing.
        # Drained in finalize() so WS close doesn't lose in-flight uploads.
        self._background_tasks: set[asyncio.Task] = set()
        # usage snapshot (latest bidi_usage event values)
        self._input_tokens = 0
        self._output_tokens = 0
        self._total_tokens = 0
        # avoid double-finalize
        self._finalized = False

    # ------------------------------------------------------------------ props
    @property
    def interview_id(self) -> str | None:
        return self._interview_id

    @property
    def system_prompt(self) -> str:
        if self._system_prompt is None:
            raise RuntimeError("call setup() first")
        return self._system_prompt

    # ------------------------------------------------------------------ setup
    async def setup(self) -> None:
        """Load Huawei CompanyStyle, compose prompt, create Interview row."""
        async with self._sf() as db:
            cs = await self._load_huawei_style(db)
            self._company_style_id = cs.id
            self._system_prompt = compose_system_prompt(cs, self._role_title)

            iv = Interview(
                company_name=cs.name,
                company_style_id=cs.id,
                role_title=self._role_title,
                language="zh",
                mode="strict",
                status="in_progress",
                bidi_started_at=datetime.utcnow(),
                started_at=datetime.utcnow(),
            )
            db.add(iv)
            await db.commit()
            await db.refresh(iv)
            self._interview_id = iv.id
            logger.info("session setup: interview_id=%s company=%s", iv.id, cs.name)

    async def _load_huawei_style(self, db: AsyncSession) -> CompanyStyle:
        res = await db.execute(
            select(CompanyStyle).where(CompanyStyle.is_builtin.is_(True)).limit(1)
        )
        cs = res.scalar_one_or_none()
        if cs is None:
            raise RuntimeError("No builtin CompanyStyle seeded; run seed first")
        return cs

    # -------------------------------------------------------- event handling
    async def on_event(self, event: dict[str, Any]) -> None:
        """Consume one Strands output event."""
        if self._interview_id is None:
            return  # pre-setup; silently drop
        t = event.get("type")
        if t == "bidi_audio_stream":
            # AI audio frame — buffer it for the current AI turn
            b64 = event.get("audio")
            if isinstance(b64, str):
                try:
                    self._ai_buf.append(base64.b64decode(b64))
                except Exception:
                    logger.debug("bad ai audio b64", exc_info=True)
        elif t == "bidi_transcript_stream":
            role = event.get("role")
            text = event.get("text") or ""
            is_final = bool(event.get("is_final"))
            if not is_final:
                return
            if role == "assistant":
                await self._finalize_assistant_turn(text)
            elif role == "user":
                await self._finalize_user_turn(text)
        elif t == "bidi_usage":
            self._input_tokens = int(event.get("inputTokens", self._input_tokens))
            self._output_tokens = int(event.get("outputTokens", self._output_tokens))
            self._total_tokens = int(event.get("totalTokens", self._total_tokens))
        elif t == "bidi_interruption":
            # User interrupted AI mid-speech. Discard any buffered AI audio
            # so the next Question's S3 upload doesn't include half of an
            # aborted turn.
            self._ai_buf.flush()
            logger.info("interruption received; ai_buf flushed")
        # audio_stream from user side is sent from browser — we don't currently
        # receive it as an event here; user audio comes as part of the input
        # side. For the walking skeleton we skip user audio upload; it will be
        # wired in a later sprint when we buffer user PCM in the router layer.

    async def _finalize_assistant_turn(self, text: str) -> None:
        """Persist Question synchronously (fast), upload AI audio in background.

        Also triggers upload of the *previous* question's user audio (if any),
        since a new assistant turn means the user finished answering.

        DB commit is fast (<10ms in-memory / <50ms SQLite WAL). S3 upload is
        slow (100ms-1s). We commit the Question row first so downstream user
        turn events have a valid FK target immediately, then fire-and-forget
        the S3 upload + `question_audio_s3_key` update.
        """
        from uuid import uuid4

        pcm, _dur = self._ai_buf.flush()
        order = self._q_count
        self._q_count += 1

        question_id = str(uuid4())
        self._last_question_id = question_id

        # Commit Question row first — synchronous, fast, makes FK valid.
        async with self._db_lock, self._sf() as db:
            q = Question(
                id=question_id,
                interview_id=self._interview_id,
                order_index=order,
                question_text=text,
                question_audio_s3_key=None,  # filled by background upload
            )
            db.add(q)
            await db.commit()
        logger.info(
            "persisted Q id=%s interview=%s order=%s len=%s",
            question_id, self._interview_id, order, len(text),
        )

        # Fire-and-forget: upload AI audio + patch s3_key (doesn't block).
        if pcm:
            task = asyncio.create_task(self._upload_and_patch_q(question_id, order, pcm))
            self._background_tasks.add(task)
            task.add_done_callback(self._background_tasks.discard)

        # Upload previous question's user audio (new assistant turn = user finished answering).
        self._flush_user_audio_for_previous_question()

    async def _upload_and_patch_q(self, question_id: str, order: int, pcm: bytes) -> None:
        s3_key = f"{self._s3_prefix}/{self._interview_id}/q{order}.pcm"
        try:
            await s3_audio.upload(s3_key, pcm, content_type="audio/pcm")
        except Exception:
            logger.exception("ai audio upload failed key=%s", s3_key)
            return
        async with self._db_lock, self._sf() as db:
            q = await db.get(Question, question_id)
            if q is not None:
                q.question_audio_s3_key = s3_key
                await db.commit()

    def _flush_user_audio_for_previous_question(self) -> None:
        """Upload accumulated user audio for all questions that have chunks."""
        for qid, chunks in list(self._user_audio_chunks.items()):
            pcm = b"".join(chunks)
            if not pcm:
                continue
            del self._user_audio_chunks[qid]
            task = asyncio.create_task(self._upload_user_audio(qid, pcm))
            self._background_tasks.add(task)
            task.add_done_callback(self._background_tasks.discard)

    async def _upload_user_audio(self, question_id: str, pcm: bytes) -> None:
        s3_key = f"{self._s3_prefix}/{self._interview_id}/a_{question_id}.pcm"
        try:
            await s3_audio.upload(s3_key, pcm, content_type="audio/pcm")
        except Exception:
            logger.exception("user audio upload failed key=%s", s3_key)
            return
        async with self._db_lock, self._sf() as db:
            a = (
                await db.execute(
                    select(Answer).where(Answer.question_id == question_id)
                )
            ).scalar_one_or_none()
            if a is not None:
                a.user_audio_s3_key = s3_key
                await db.commit()
        logger.info("uploaded user audio key=%s", s3_key)
        logger.debug("patched Q audio key=%s", s3_key)

    async def _finalize_user_turn(self, text: str) -> None:
        """Persist Answer for the current question.

        Nova Sonic can emit MULTIPLE `is_final=True` user transcripts within
        a single user turn (one per utterance / endpointed chunk). We must
        coalesce these into a single Answer row per question_id, because
        the Answer.question_id column has a UNIQUE constraint.

        Strategy: UPSERT.
          - First fragment: insert new Answer(transcript_text=text).
          - Subsequent fragments for the same question: append to the
            existing transcript_text and grow duration_sec.

        The audio buffer (user_buf) is flushed on every fragment, so the
        duration value is cumulative per fragment; we add it up.
        """
        if self._last_question_id is None:
            logger.debug("user transcript before any question; dropping")
            self._user_buf.flush()
            return
        question_id = self._last_question_id
        pcm_chunk, duration = self._user_buf.flush()
        # Accumulate user audio for later S3 upload
        if pcm_chunk:
            self._user_audio_chunks.setdefault(question_id, []).append(pcm_chunk)
        async with self._db_lock, self._sf() as db:
            existing = (
                await db.execute(
                    select(Answer).where(Answer.question_id == question_id)
                )
            ).scalar_one_or_none()
            if existing is None:
                a = Answer(
                    question_id=question_id,
                    transcript_text=text,
                    duration_sec=duration,
                    user_audio_s3_key=None,
                )
                db.add(a)
                action = "inserted"
            else:
                existing.transcript_text = (
                    f"{existing.transcript_text or ''}{text}"
                    if existing.transcript_text
                    else text
                )
                existing.duration_sec = (existing.duration_sec or 0.0) + duration
                action = "appended"
            await db.commit()
        logger.info(
            "persisted A for Q=%s len=%s action=%s", question_id, len(text), action
        )

    # ---------------------------------------------------- input-side helpers
    def append_user_audio(self, pcm_bytes: bytes) -> None:
        """Called from the WS router whenever the browser sends a PCM chunk."""
        self._user_buf.append(pcm_bytes)

    # --------------------------------------------------------------- finalize
    async def finalize(self, status: str = "completed") -> None:
        if self._finalized or self._interview_id is None:
            return
        self._finalized = True
        # Upload any remaining user audio (last answer before session ends).
        self._flush_user_audio_for_previous_question()
        # Drain background S3 uploads so the Interview row reflects final state.
        if self._background_tasks:
            logger.info("draining %d background tasks before finalize", len(self._background_tasks))
            try:
                await asyncio.wait(list(self._background_tasks), timeout=10.0)
            except Exception:
                logger.exception("error draining background tasks")
        cost_usd = (
            self._input_tokens / 1000.0 * PRICE_IN_PER_1K
            + self._output_tokens / 1000.0 * PRICE_OUT_PER_1K
        )
        async with self._db_lock, self._sf() as db:
            iv = await db.get(Interview, self._interview_id)
            if iv is None:
                return
            iv.status = status
            iv.bidi_ended_at = datetime.utcnow()
            iv.ended_at = datetime.utcnow()
            iv.bidi_tokens_total = self._total_tokens
            iv.bidi_cost_usd = round(cost_usd, 6)
            await db.commit()
        logger.info(
            "finalized interview=%s status=%s tokens=%s cost=$%.4f",
            self._interview_id, status, self._total_tokens, cost_usd,
        )

    async def finalize_safe(self, status: str = "completed") -> None:
        """Finalize without raising; safe for `finally` blocks."""
        try:
            await asyncio.wait_for(self.finalize(status=status), timeout=5.0)
        except Exception:
            logger.exception("finalize failed")
