"""SQLAlchemy models for Interviewer MVP."""
from datetime import datetime
from uuid import uuid4

from sqlalchemy import JSON, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def _uuid() -> str:
    return str(uuid4())


def _now() -> datetime:
    return datetime.utcnow()


class Base(DeclarativeBase):
    pass


class CompanyStyle(Base):
    __tablename__ = "company_style"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(String(100))
    interviewer_style_tags: Mapped[list] = mapped_column(JSON, default=list)
    preferred_question_types: Mapped[list] = mapped_column(JSON, default=list)
    sample_questions: Mapped[list] = mapped_column(JSON, default=list)
    prompt_context_text: Mapped[str] = mapped_column(Text, default="")
    is_builtin: Mapped[bool] = mapped_column(default=False)
    rubric_type: Mapped[str] = mapped_column(String(20), default="faang")
    created_by: Mapped[str | None] = mapped_column(String(36), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)


class Interview(Base):
    __tablename__ = "interview"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    user_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    company_name: Mapped[str] = mapped_column(String(100))
    company_style_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("company_style.id"), nullable=True
    )
    role_title: Mapped[str] = mapped_column(String(200))
    language: Mapped[str] = mapped_column(String(10), default="zh")
    duration_min: Mapped[int] = mapped_column(Integer, default=45)
    question_count_target: Mapped[int] = mapped_column(Integer, default=8)
    mode: Mapped[str] = mapped_column(String(20), default="strict")
    status: Mapped[str] = mapped_column(String(30), default="in_progress")
    resume_context: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Nova Sonic bidi session accounting
    bidi_tokens_total: Mapped[int] = mapped_column(Integer, default=0)
    bidi_cost_usd: Mapped[float] = mapped_column(Float, default=0.0)
    bidi_started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    bidi_ended_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)

    questions: Mapped[list["Question"]] = relationship(
        back_populates="interview", cascade="all, delete-orphan"
    )
    evaluations: Mapped[list["Evaluation"]] = relationship(
        back_populates="interview", cascade="all, delete-orphan"
    )


class Question(Base):
    __tablename__ = "question"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    interview_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("interview.id", ondelete="CASCADE")
    )
    order_index: Mapped[int] = mapped_column(Integer)
    question_text: Mapped[str] = mapped_column(Text)
    question_audio_s3_key: Mapped[str | None] = mapped_column(String(500), nullable=True)
    generated_at: Mapped[datetime] = mapped_column(DateTime, default=_now)

    interview: Mapped["Interview"] = relationship(back_populates="questions")
    answer: Mapped["Answer | None"] = relationship(
        back_populates="question", cascade="all, delete-orphan", uselist=False
    )


class Answer(Base):
    __tablename__ = "answer"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    question_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("question.id", ondelete="CASCADE"), unique=True
    )
    user_audio_s3_key: Mapped[str | None] = mapped_column(String(500), nullable=True)
    transcript_text: Mapped[str] = mapped_column(Text, default="")
    duration_sec: Mapped[float] = mapped_column(Float, default=0.0)
    answered_at: Mapped[datetime] = mapped_column(DateTime, default=_now)

    question: Mapped["Question"] = relationship(back_populates="answer")


class Evaluation(Base):
    __tablename__ = "evaluation"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    interview_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("interview.id", ondelete="CASCADE")
    )
    question_id: Mapped[str | None] = mapped_column(String(36), nullable=True)  # NULL = overall
    content_score: Mapped[int] = mapped_column(Integer)
    expression_score: Mapped[int] = mapped_column(Integer)
    voice_score: Mapped[int] = mapped_column(Integer)
    overall_score: Mapped[int] = mapped_column(Integer)
    overall_result: Mapped[str] = mapped_column(String(20))  # Pass/Borderline/No-Pass
    improvement_suggestion: Mapped[str] = mapped_column(Text, default="")
    ideal_answer: Mapped[str | None] = mapped_column(Text, nullable=True)
    voice_features: Mapped[dict] = mapped_column(JSON, default=dict)
    rubric_version: Mapped[str] = mapped_column(String(20), default="v1.0")
    dimension_scores: Mapped[dict] = mapped_column(JSON, default=dict)
    raw_prompt: Mapped[str] = mapped_column(Text, default="")
    raw_response: Mapped[dict] = mapped_column(JSON, default=dict)
    evaluation_cost_usd: Mapped[float] = mapped_column(Float, default=0.0)
    generated_at: Mapped[datetime] = mapped_column(DateTime, default=_now)

    interview: Mapped["Interview"] = relationship(back_populates="evaluations")
