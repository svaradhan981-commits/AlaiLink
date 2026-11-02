from datetime import datetime
from typing import Literal

from pydantic import AnyHttpUrl, BaseModel, Field


class ChatRequest(BaseModel):
    question: str = Field(min_length=1, max_length=2_000)
    language: Literal["ta", "en"]


class ChatSource(BaseModel):
    title: str
    url: AnyHttpUrl


class ChatResponse(BaseModel):
    answer: str
    language: Literal["ta", "en"]
    sources: list[ChatSource] = Field(default_factory=list)
    summary: str = Field(max_length=160)


class UsageRecordResponse(BaseModel):
    id: int
    timestamp: datetime
    model: str
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    total_tokens: int | None = None
    cost: float | None = None
    latency_seconds: float
    status: str
    error_message: str | None = None
    endpoint: str | None = None


class ModelUsageSummary(BaseModel):
    requests: int
    successful_requests: int
    failed_requests: int
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    cost: float


class UsageSummaryResponse(BaseModel):
    total_requests: int
    successful_requests: int
    failed_requests: int
    total_prompt_tokens: int
    total_completion_tokens: int
    total_tokens: int
    total_cost: float
    by_model: dict[str, ModelUsageSummary] = Field(default_factory=dict)
    recent_records: list[UsageRecordResponse] = Field(default_factory=list)
