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
