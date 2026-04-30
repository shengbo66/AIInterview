"""Pydantic request/response schemas."""
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class CompanyStyleOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    interviewer_style_tags: list[str]
    preferred_question_types: list[str]
    sample_questions: list[str]
    prompt_context_text: str
    is_builtin: bool
    created_at: datetime


class InterviewCreate(BaseModel):
    company_name: str = Field(min_length=1, max_length=100)
    role_title: str = Field(min_length=1, max_length=200)
    company_style_id: str | None = None
    language: str = Field(default="zh", pattern=r"^(zh|en)$")
    duration_min: int = Field(default=45, ge=5, le=180)
    question_count_target: int = Field(default=8, ge=1, le=30)
    mode: str = Field(default="strict", pattern=r"^(strict|friendly)$")
    resume_context: str | None = None


class InterviewSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    company_name: str
    role_title: str
    language: str
    status: str
    created_at: datetime


class QuestionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    order_index: int
    question_text: str
    question_audio_s3_key: str | None


class AnswerOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    transcript_text: str
    duration_sec: float
    user_audio_s3_key: str | None


class EvaluationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    question_id: str | None
    content_score: int
    expression_score: int
    voice_score: int
    overall_score: int
    overall_result: str
    improvement_suggestion: str
    ideal_answer: str | None


class InterviewDetail(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    company_name: str
    role_title: str
    language: str
    duration_min: int
    question_count_target: int
    mode: str
    status: str
    resume_context: str | None
    bidi_tokens_total: int
    bidi_cost_usd: float
    created_at: datetime
    questions: list[QuestionOut]
    evaluations: list[EvaluationOut]


class AudioUrlResponse(BaseModel):
    url: str
    expires_in_sec: int


class HealthResponse(BaseModel):
    status: str
    version: str
