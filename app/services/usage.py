import json
import logging
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.config import DEFAULT_MODEL_PRICING, Settings
from app.database import (
    DatabaseConfigurationError,
    LLMUsageRecord,
    get_session_factory,
)
from app.schemas import (
    ModelUsageSummary,
    UsageRecordResponse,
    UsageSummaryResponse,
)

logger = logging.getLogger(__name__)


def calculate_cost(
    model: str,
    prompt_tokens: int | None,
    completion_tokens: int | None,
    settings: Settings,
) -> float | None:
    """Calculate estimated cost in USD based on configurable pricing.

    Returns None if token metadata is missing, avoiding invented numbers.
    """
    if prompt_tokens is None or completion_tokens is None:
        return None

    input_rate = settings.llm_default_input_cost_per_million
    output_rate = settings.llm_default_output_cost_per_million

    # Check custom JSON pricing config
    if settings.llm_pricing_json:
        try:
            custom_pricing = json.loads(settings.llm_pricing_json)
            if model in custom_pricing:
                model_cfg = custom_pricing[model]
                input_rate = model_cfg.get("input_per_million", input_rate)
                output_rate = model_cfg.get("output_per_million", output_rate)
        except (json.JSONDecodeError, TypeError) as error:
            logger.warning("Failed to parse LLM_PRICING_JSON: %s", error)
    elif model in DEFAULT_MODEL_PRICING:
        model_cfg = DEFAULT_MODEL_PRICING[model]
        input_rate = model_cfg.get("input_per_million", input_rate)
        output_rate = model_cfg.get("output_per_million", output_rate)

    input_cost = (prompt_tokens / 1_000_000.0) * input_rate
    output_cost = (completion_tokens / 1_000_000.0) * output_rate
    return round(input_cost + output_cost, 8)


class UsageRepository:
    """Repository handling persistence of LLM usage records to PostgreSQL."""

    def __init__(self, session_factory: async_sessionmaker | None) -> None:
        self.session_factory = session_factory

    async def record_usage(self, **data: Any) -> LLMUsageRecord | None:
        if not self.session_factory:
            return None
        async with self.session_factory() as session:
            record = LLMUsageRecord(**data)
            session.add(record)
            await session.commit()
            await session.refresh(record)
            return record

    async def get_summary(self, limit: int = 50) -> UsageSummaryResponse:
        if not self.session_factory:
            raise DatabaseConfigurationError("DATABASE_URL is not configured.")

        async with self.session_factory() as session:
            statement = select(LLMUsageRecord).order_by(LLMUsageRecord.timestamp.desc())
            result = await session.execute(statement)
            records = result.scalars().all()

        total_requests = len(records)
        successful_requests = sum(1 for r in records if r.status == "success")
        failed_requests = total_requests - successful_requests

        total_prompt_tokens = sum(r.prompt_tokens for r in records if r.prompt_tokens is not None)
        total_completion_tokens = sum(
            r.completion_tokens for r in records if r.completion_tokens is not None
        )
        total_tokens = sum(r.total_tokens for r in records if r.total_tokens is not None)
        total_cost = round(sum(r.cost for r in records if r.cost is not None), 8)

        by_model: dict[str, ModelUsageSummary] = {}
        for r in records:
            if r.model not in by_model:
                by_model[r.model] = ModelUsageSummary(
                    requests=0,
                    successful_requests=0,
                    failed_requests=0,
                    prompt_tokens=0,
                    completion_tokens=0,
                    total_tokens=0,
                    cost=0.0,
                )
            summary = by_model[r.model]
            summary.requests += 1
            if r.status == "success":
                summary.successful_requests += 1
            else:
                summary.failed_requests += 1

            if r.prompt_tokens is not None:
                summary.prompt_tokens += r.prompt_tokens
            if r.completion_tokens is not None:
                summary.completion_tokens += r.completion_tokens
            if r.total_tokens is not None:
                summary.total_tokens += r.total_tokens
            if r.cost is not None:
                summary.cost = round(summary.cost + r.cost, 8)

        recent_records = [
            UsageRecordResponse(
                id=r.id,
                timestamp=r.timestamp,
                model=r.model,
                prompt_tokens=r.prompt_tokens,
                completion_tokens=r.completion_tokens,
                total_tokens=r.total_tokens,
                cost=r.cost,
                latency_seconds=r.latency_seconds,
                status=r.status,
                error_message=r.error_message,
                endpoint=r.endpoint,
            )
            for r in records[:limit]
        ]

        return UsageSummaryResponse(
            total_requests=total_requests,
            successful_requests=successful_requests,
            failed_requests=failed_requests,
            total_prompt_tokens=total_prompt_tokens,
            total_completion_tokens=total_completion_tokens,
            total_tokens=total_tokens,
            total_cost=total_cost,
            by_model=by_model,
            recent_records=recent_records,
        )


class UsageService:
    """Service orchestrating LLM usage recording, pricing, and analytics."""

    def __init__(self, repository: UsageRepository, settings: Settings) -> None:
        self.repository = repository
        self.settings = settings

    async def log_request(
        self,
        *,
        model: str,
        prompt_tokens: int | None = None,
        completion_tokens: int | None = None,
        total_tokens: int | None = None,
        latency_seconds: float = 0.0,
        status: str = "success",
        error_message: str | None = None,
        endpoint: str | None = None,
    ) -> None:
        cost = calculate_cost(model, prompt_tokens, completion_tokens, self.settings)
        try:
            await self.repository.record_usage(
                model=model,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                total_tokens=total_tokens,
                cost=cost,
                latency_seconds=latency_seconds,
                status=status,
                error_message=error_message,
                endpoint=endpoint,
            )
        except Exception as error:
            logger.warning("Failed to persist LLM usage record: %s", error)

    async def get_usage_summary(self, limit: int = 50) -> UsageSummaryResponse:
        return await self.repository.get_summary(limit=limit)


def get_usage_service(settings: Settings) -> UsageService:
    session_factory = None
    if settings.database_url:
        try:
            session_factory = get_session_factory(settings)
        except DatabaseConfigurationError:
            session_factory = None
    repository = UsageRepository(session_factory)
    return UsageService(repository, settings)
