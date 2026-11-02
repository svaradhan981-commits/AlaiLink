import asyncio
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.config import Settings, get_settings
from app.database import DatabaseConfigurationError, LLMUsageRecord
from app.schemas import UsageSummaryResponse
from app.services.usage import (
    UsageRepository,
    UsageService,
    calculate_cost,
)


def _configured_settings(**overrides):
    values = {
        "app_name": "AlaiLink",
        "environment": "test",
        "llm_api_key": "test-key",
        "llm_base_url": "https://generativelanguage.googleapis.com/v1beta/openai/",
        "database_url": "postgresql+psycopg://alailink:alailink@localhost:5432/alailink",
    }
    values.update(overrides)
    return Settings(_env_file=None, **values)


def test_calculate_cost_with_default_model_pricing():
    settings = Settings(_env_file=None)
    # gemini-3.5-flash-lite default: $0.075 / 1M prompt, $0.30 / 1M completion
    # 1,000 prompt tokens = 0.000075, 1,000 completion tokens = 0.0003 -> total = 0.000375
    cost = calculate_cost("gemini-3.5-flash-lite", 1000, 1000, settings)
    assert cost == 0.000375


def test_calculate_cost_with_custom_pricing_json():
    custom_json = '{"custom-model": {"input_per_million": 1.0, "output_per_million": 2.0}}'
    settings = Settings(_env_file=None, llm_pricing_json=custom_json)
    cost = calculate_cost("custom-model", 1_000_000, 500_000, settings)
    # 1M * 1.0 + 0.5M * 2.0 = 2.0
    assert cost == 2.0


def test_calculate_cost_returns_none_when_tokens_are_missing():
    settings = Settings(_env_file=None)
    # Requirement: Handle missing provider usage metadata without inventing token counts or costs
    assert calculate_cost("gemini-3.5-flash-lite", None, 100, settings) is None
    assert calculate_cost("gemini-3.5-flash-lite", 100, None, settings) is None
    assert calculate_cost("gemini-3.5-flash-lite", None, None, settings) is None


def test_usage_repository_raises_when_no_database_configured():
    repo = UsageRepository(session_factory=None)
    with pytest.raises(DatabaseConfigurationError, match="DATABASE_URL is not configured"):
        asyncio.run(repo.get_summary())


def test_usage_repository_returns_none_on_record_without_session():
    repo = UsageRepository(session_factory=None)
    result = asyncio.run(repo.record_usage(model="test", latency_seconds=1.0, status="success"))
    assert result is None


def test_usage_repository_summary_aggregates_correctly():
    # Mock database session returning sample usage records
    now = datetime.now(UTC)
    records = [
        LLMUsageRecord(
            id=1,
            timestamp=now,
            model="gemini-3.5-flash-lite",
            prompt_tokens=100,
            completion_tokens=50,
            total_tokens=150,
            cost=0.0000225,
            latency_seconds=0.45,
            status="success",
            error_message=None,
            endpoint="/chat",
        ),
        LLMUsageRecord(
            id=2,
            timestamp=now,
            model="gemini-3.5-flash-lite",
            prompt_tokens=None,
            completion_tokens=None,
            total_tokens=None,
            cost=None,
            latency_seconds=1.2,
            status="timeout",
            error_message="Request timed out",
            endpoint="/chat",
        ),
        LLMUsageRecord(
            id=3,
            timestamp=now,
            model="fallback-model",
            prompt_tokens=200,
            completion_tokens=80,
            total_tokens=280,
            cost=0.000039,
            latency_seconds=0.6,
            status="success",
            error_message=None,
            endpoint="/chat",
        ),
    ]

    mock_session = AsyncMock()
    mock_execute_result = MagicMock()
    mock_execute_result.scalars.return_value.all.return_value = records
    mock_session.execute.return_value = mock_execute_result

    class MockSessionFactory:
        def __call__(self):
            return self

        async def __aenter__(self):
            return mock_session

        async def __aexit__(self, *args):
            pass

    repo = UsageRepository(session_factory=MockSessionFactory())
    summary: UsageSummaryResponse = asyncio.run(repo.get_summary(limit=10))

    assert summary.total_requests == 3
    assert summary.successful_requests == 2
    assert summary.failed_requests == 1
    assert summary.total_prompt_tokens == 300
    assert summary.total_completion_tokens == 130
    assert summary.total_tokens == 430
    assert summary.total_cost == 0.0000615
    assert "gemini-3.5-flash-lite" in summary.by_model
    assert summary.by_model["gemini-3.5-flash-lite"].requests == 2
    assert summary.by_model["gemini-3.5-flash-lite"].successful_requests == 1
    assert summary.by_model["gemini-3.5-flash-lite"].failed_requests == 1
    assert "fallback-model" in summary.by_model
    assert summary.by_model["fallback-model"].requests == 1
    assert summary.by_model["fallback-model"].successful_requests == 1
    assert len(summary.recent_records) == 3


def test_usage_service_safe_logging_does_not_raise():
    mock_repo = AsyncMock()
    mock_repo.record_usage.side_effect = RuntimeError("Database down")
    settings = Settings(_env_file=None)
    service = UsageService(mock_repo, settings)

    # Logging failure must not crash or bubble up
    asyncio.run(
        service.log_request(
            model="gemini-3.5-flash-lite",
            latency_seconds=0.5,
            status="success",
        )
    )
    assert mock_repo.record_usage.called


def test_get_usage_endpoint_requires_database(client):
    response = client.get("/usage")
    assert response.status_code == 503
    assert "DATABASE_URL is not configured" in response.json()["detail"]


def test_get_usage_endpoint_returns_summary(client, monkeypatch):
    expected = UsageSummaryResponse(
        total_requests=2,
        successful_requests=2,
        failed_requests=0,
        total_prompt_tokens=500,
        total_completion_tokens=150,
        total_tokens=650,
        total_cost=0.00008,
        by_model={},
        recent_records=[],
    )

    async def mock_summary(limit=50):
        del limit
        return expected

    mock_service = MagicMock()
    mock_service.get_usage_summary = mock_summary

    monkeypatch.setattr("app.main.get_usage_service", lambda _: mock_service)
    client.app.dependency_overrides[get_settings] = lambda: _configured_settings()

    response = client.get("/usage")
    assert response.status_code == 200
    data = response.json()
    assert data["total_requests"] == 2
    assert data["total_tokens"] == 650
    assert data["total_cost"] == 0.00008


def test_chat_logs_usage_on_success(client, monkeypatch):
    logged_records = []

    class MockUsageService:
        async def log_request(self, **kwargs):
            logged_records.append(kwargs)

    monkeypatch.setattr("app.services.chat.get_usage_service", lambda _: MockUsageService())

    async def mock_retrieval(_question, _settings):
        from app.services.rag import RetrievedChunk, RetrievedSource

        return [
            RetrievedChunk(
                "Excerpt",
                RetrievedSource("Scheme", "https://example.gov"),
                0.1,
            )
        ]

    monkeypatch.setattr("app.main.retrieve_context", mock_retrieval)

    import httpx

    async def handler(_request):
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "content": '{"answer":"Verified scheme","summary":"Summary"}'
                        }
                    }
                ],
                "usage": {
                    "prompt_tokens": 120,
                    "completion_tokens": 40,
                    "total_tokens": 160,
                },
            },
        )

    original_client = httpx.AsyncClient
    monkeypatch.setattr(
        "app.services.chat.httpx.AsyncClient",
        lambda **kwargs: original_client(transport=httpx.MockTransport(handler), **kwargs),
    )
    client.app.dependency_overrides[get_settings] = lambda: _configured_settings()

    response = client.post("/chat", json={"question": "Test?", "language": "en"})
    assert response.status_code == 200
    assert len(logged_records) == 1
    assert logged_records[0]["status"] == "success"
    assert logged_records[0]["prompt_tokens"] == 120
    assert logged_records[0]["completion_tokens"] == 40
    assert logged_records[0]["total_tokens"] == 160
    assert logged_records[0]["endpoint"] == "/chat"


def test_chat_logs_usage_with_missing_provider_metadata(client, monkeypatch):
    logged_records = []

    class MockUsageService:
        async def log_request(self, **kwargs):
            logged_records.append(kwargs)

    monkeypatch.setattr("app.services.chat.get_usage_service", lambda _: MockUsageService())

    async def mock_retrieval(_question, _settings):
        from app.services.rag import RetrievedChunk, RetrievedSource

        return [RetrievedChunk("Excerpt", RetrievedSource("Scheme", "https://example.gov"), 0.1)]

    monkeypatch.setattr("app.main.retrieve_context", mock_retrieval)

    import httpx

    async def handler(_request):
        # Provider response without usage dictionary
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "content": '{"answer":"Verified scheme","summary":"Summary"}'
                        }
                    }
                ]
            },
        )

    original_client = httpx.AsyncClient
    monkeypatch.setattr(
        "app.services.chat.httpx.AsyncClient",
        lambda **kwargs: original_client(transport=httpx.MockTransport(handler), **kwargs),
    )
    client.app.dependency_overrides[get_settings] = lambda: _configured_settings()

    response = client.post("/chat", json={"question": "Test?", "language": "en"})
    assert response.status_code == 200
    assert len(logged_records) == 1
    assert logged_records[0]["status"] == "success"
    assert logged_records[0]["prompt_tokens"] is None
    assert logged_records[0]["completion_tokens"] is None
    assert logged_records[0]["total_tokens"] is None


def test_chat_logs_primary_failure_and_fallback_success(client, monkeypatch):
    logged_records = []

    class MockUsageService:
        async def log_request(self, **kwargs):
            logged_records.append(kwargs)

    monkeypatch.setattr("app.services.chat.get_usage_service", lambda _: MockUsageService())

    async def mock_retrieval(_question, _settings):
        from app.services.rag import RetrievedChunk, RetrievedSource

        return [RetrievedChunk("Excerpt", RetrievedSource("Scheme", "https://example.gov"), 0.1)]

    monkeypatch.setattr("app.main.retrieve_context", mock_retrieval)

    import json

    import httpx

    async def handler(request):
        body = json.loads(request.read())
        model = body["model"]
        if model != "fallback-model":
            return httpx.Response(503)
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "content": '{"answer":"Fallback answer","summary":"Summary"}'
                        }
                    }
                ],
                "usage": {"prompt_tokens": 80, "completion_tokens": 20, "total_tokens": 100},
            },
        )

    original_client = httpx.AsyncClient
    monkeypatch.setattr(
        "app.services.chat.httpx.AsyncClient",
        lambda **kwargs: original_client(transport=httpx.MockTransport(handler), **kwargs),
    )
    client.app.dependency_overrides[get_settings] = lambda: _configured_settings(
        llm_max_retries=0,
        llm_fallback_model="fallback-model",
    )

    response = client.post("/chat", json={"question": "Test?", "language": "en"})
    assert response.status_code == 200
    assert len(logged_records) == 2
    # First attempt: primary failed
    assert logged_records[0]["model"] == "gemini-3.5-flash-lite"
    assert logged_records[0]["status"] == "error_503"
    # Second attempt: fallback succeeded
    assert logged_records[1]["model"] == "fallback-model"
    assert logged_records[1]["status"] == "success"
    assert logged_records[1]["total_tokens"] == 100


def test_chat_stream_logs_usage(client, monkeypatch):
    logged_records = []

    class MockUsageService:
        async def log_request(self, **kwargs):
            logged_records.append(kwargs)

    monkeypatch.setattr("app.services.chat.get_usage_service", lambda _: MockUsageService())

    async def mock_retrieval(_question, _settings):
        from app.services.rag import RetrievedChunk, RetrievedSource

        return [RetrievedChunk("Excerpt", RetrievedSource("Scheme", "https://example.gov"), 0.1)]

    monkeypatch.setattr("app.main.retrieve_context", mock_retrieval)

    import json

    import httpx

    async def handler(_request):
        chunks = [
            "data: "
            + json.dumps({"choices": [{"delta": {"content": '{"answer":"Stream ans",'}}]})
            + "\n\n",
            "data: "
            + json.dumps({"choices": [{"delta": {"content": '"summary":"Done"}'}}]})
            + "\n\n",
            "data: "
            + json.dumps(
                {
                    "choices": [],
                    "usage": {
                        "prompt_tokens": 50,
                        "completion_tokens": 15,
                        "total_tokens": 65,
                    },
                }
            )
            + "\n\n",
            "data: [DONE]\n\n",
        ]
        return httpx.Response(200, text="".join(chunks))

    original_client = httpx.AsyncClient
    monkeypatch.setattr(
        "app.services.chat.httpx.AsyncClient",
        lambda **kwargs: original_client(transport=httpx.MockTransport(handler), **kwargs),
    )
    client.app.dependency_overrides[get_settings] = lambda: _configured_settings()

    response = client.post("/chat/stream", json={"question": "Test?", "language": "en"})
    assert response.status_code == 200
    assert "event: complete" in response.text
    assert len(logged_records) == 1
    assert logged_records[0]["status"] == "success"
    assert logged_records[0]["total_tokens"] == 65
    assert logged_records[0]["endpoint"] == "/chat/stream"

