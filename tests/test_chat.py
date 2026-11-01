import json

import httpx

from app.config import Settings, get_settings
from app.services.rag import RetrievedChunk, RetrievedSource


def _configured_settings(**overrides):
    values = {
        "app_name": "AlaiLink",
        "environment": "test",
        "llm_api_key": "test-key",
        "llm_base_url": "https://generativelanguage.googleapis.com/v1beta/openai/",
        "llm_retry_delay_seconds": 0,
    }
    values.update(overrides)
    return Settings(_env_file=None, **values)


def _mock_retrieval(monkeypatch, chunks=None):
    evidence = chunks or [
        RetrievedChunk(
            "The official page describes the scheme.",
            RetrievedSource("Official Fisheries Scheme", "https://www.fisheries.tn.gov.in/"),
            0.1,
        )
    ]

    async def retrieve(_question, _settings):
        del _question, _settings
        return evidence

    monkeypatch.setattr("app.main.retrieve_context", retrieve)


def test_chat_returns_structured_answer_from_configured_provider(client, monkeypatch):
    async_client = httpx.AsyncClient
    _mock_retrieval(monkeypatch)

    async def handler(request):
        assert request.url.path == "/v1beta/openai/chat/completions"
        assert request.headers["Authorization"] == "Bearer test-key"
        request_payload = json.loads(request.read())
        assert "Official Fisheries Scheme" in request_payload["messages"][1]["content"]
        assert "https://www.fisheries.tn.gov.in/" in request_payload["messages"][1]["content"]
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "content": (
                                '{"answer":"இந்த தகவலை அதிகாரப்பூர்வ ஆவணங்களில் '
                                'உறுதிப்படுத்த முடியவில்லை.","summary":"தகவலை '
                                'உறுதிப்படுத்த முடியவில்லை."}'
                            )
                        }
                    }
                ]
            },
        )

    monkeypatch.setattr(
        "app.services.chat.httpx.AsyncClient",
        lambda **kwargs: async_client(transport=httpx.MockTransport(handler), **kwargs),
    )
    client.app.dependency_overrides[get_settings] = lambda: _configured_settings()

    response = client.post("/chat", json={"question": "நிவாரணம் எவ்வளவு?", "language": "ta"})

    assert response.status_code == 200
    assert response.json() == {
        "answer": "இந்த தகவலை அதிகாரப்பூர்வ ஆவணங்களில் உறுதிப்படுத்த முடியவில்லை.",
        "language": "ta",
        "sources": [
            {
                "title": "Official Fisheries Scheme",
                "url": "https://www.fisheries.tn.gov.in/",
            }
        ],
        "summary": "தகவலை உறுதிப்படுத்த முடியவில்லை.",
    }


def test_chat_requires_provider_configuration(client):
    response = client.post("/chat", json={"question": "How do I apply?", "language": "en"})

    assert response.status_code == 503
    assert response.json() == {
        "detail": "LLM_API_KEY or EMBEDDING_API_KEY is not configured."
    }


def test_chat_can_answer_unverified_without_llm_key_when_embedding_key_is_configured(
    client, monkeypatch
):
    async def no_results(_question, _settings):
        del _question, _settings
        return []

    monkeypatch.setattr("app.main.retrieve_context", no_results)
    client.app.dependency_overrides[get_settings] = lambda: _configured_settings(
        llm_api_key=None,
        embedding_api_key="embedding-key",
    )

    response = client.post(
        "/chat",
        json={"question": "How much is the relief?", "language": "en"},
    )

    assert response.status_code == 200
    assert response.json()["sources"] == []


def test_chat_maps_provider_timeout(client, monkeypatch):
    async_client = httpx.AsyncClient
    calls = 0
    _mock_retrieval(monkeypatch)

    async def handler(_request):
        del _request
        nonlocal calls
        calls += 1
        raise httpx.ReadTimeout("timeout")

    monkeypatch.setattr(
        "app.services.chat.httpx.AsyncClient",
        lambda **kwargs: async_client(transport=httpx.MockTransport(handler), **kwargs),
    )
    client.app.dependency_overrides[get_settings] = lambda: _configured_settings(llm_max_retries=1)

    response = client.post("/chat", json={"question": "How do I apply?", "language": "en"})

    assert response.status_code == 504
    assert response.json() == {"detail": "The LLM request timed out."}
    assert calls == 2


def test_chat_rejects_invalid_request(client):
    response = client.post("/chat", json={"question": "", "language": "fr"})

    assert response.status_code == 422


def test_chat_returns_unverified_message_when_retrieval_has_no_results(client, monkeypatch):
    async def no_results(_question, _settings):
        del _question, _settings
        return []

    monkeypatch.setattr("app.main.retrieve_context", no_results)
    client.app.dependency_overrides[get_settings] = lambda: _configured_settings()

    response = client.post(
        "/chat",
        json={"question": "How much is the relief?", "language": "en"},
    )

    assert response.status_code == 200
    assert response.json()["answer"] == (
        "I could not verify this information in the available official documents."
    )
    assert response.json()["sources"] == []


def test_chat_retries_rate_limit(client, monkeypatch):
    calls = 0
    async_client = httpx.AsyncClient
    _mock_retrieval(monkeypatch)

    async def handler(_request):
        del _request
        nonlocal calls
        calls += 1
        if calls == 1:
            return httpx.Response(429)
        return httpx.Response(
            200,
            json={
                "choices": [
                    {"message": {"content": '{"answer":"Verified answer","summary":"Summary"}'}}
                ]
            },
        )

    monkeypatch.setattr(
        "app.services.chat.httpx.AsyncClient",
        lambda **kwargs: async_client(transport=httpx.MockTransport(handler), **kwargs),
    )
    client.app.dependency_overrides[get_settings] = lambda: _configured_settings(llm_max_retries=1)

    response = client.post("/chat", json={"question": "Question?", "language": "en"})

    assert response.status_code == 200
    assert response.json()["answer"] == "Verified answer"
    assert calls == 2


def test_chat_does_not_retry_permanent_provider_failure(client, monkeypatch):
    calls = 0
    async_client = httpx.AsyncClient
    _mock_retrieval(monkeypatch)

    async def handler(_request):
        del _request
        nonlocal calls
        calls += 1
        return httpx.Response(401)

    monkeypatch.setattr(
        "app.services.chat.httpx.AsyncClient",
        lambda **kwargs: async_client(transport=httpx.MockTransport(handler), **kwargs),
    )
    client.app.dependency_overrides[get_settings] = lambda: _configured_settings(llm_max_retries=3)

    response = client.post("/chat", json={"question": "Question?", "language": "en"})

    assert response.status_code == 502
    assert calls == 1


def test_chat_uses_fallback_after_primary_retries(client, monkeypatch):
    models = []
    async_client = httpx.AsyncClient
    _mock_retrieval(monkeypatch)

    async def handler(request):
        model = json.loads(request.read())["model"]
        models.append(model)
        if model != "fallback-model":
            return httpx.Response(503)
        return httpx.Response(
            200,
            json={
                "choices": [
                    {"message": {"content": '{"answer":"Fallback answer","summary":"Summary"}'}}
                ]
            },
        )

    monkeypatch.setattr(
        "app.services.chat.httpx.AsyncClient",
        lambda **kwargs: async_client(transport=httpx.MockTransport(handler), **kwargs),
    )
    client.app.dependency_overrides[get_settings] = lambda: _configured_settings(
        llm_max_retries=1,
        llm_fallback_model="fallback-model",
    )

    response = client.post("/chat", json={"question": "Question?", "language": "en"})

    assert response.status_code == 200
    assert response.json()["answer"] == "Fallback answer"
    assert len(models) == 3
    assert models == ["gemini-3.5-flash-lite", "gemini-3.5-flash-lite", "fallback-model"]


def test_chat_stream_emits_progressive_deltas_and_structured_completion(client, monkeypatch):
    async_client = httpx.AsyncClient
    _mock_retrieval(monkeypatch)
    fragments = ['{"answer":"Progress', 'ive answer","summary":"A summary"}']

    async def handler(request):
        assert json.loads(request.read())["stream"] is True
        chunks = [
            "data: "
            + json.dumps({"choices": [{"delta": {"content": fragment}}]})
            + "\n\n"
            for fragment in fragments
        ]
        chunks.append("data: [DONE]\n\n")
        return httpx.Response(200, text="".join(chunks))

    monkeypatch.setattr(
        "app.services.chat.httpx.AsyncClient",
        lambda **kwargs: async_client(transport=httpx.MockTransport(handler), **kwargs),
    )
    client.app.dependency_overrides[get_settings] = lambda: _configured_settings()

    response = client.post(
        "/chat/stream",
        json={"question": "Question?", "language": "en"},
    )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert response.text.count("event: delta") == 2
    completion = response.text.split("event: complete\ndata: ", maxsplit=1)[1].split("\n\n", maxsplit=1)[0]
    assert json.loads(completion) == {
        "answer": "Progressive answer",
        "language": "en",
        "sources": [
            {
                "title": "Official Fisheries Scheme",
                "url": "https://www.fisheries.tn.gov.in/",
            }
        ],
        "summary": "A summary",
    }


def test_chat_stream_reports_provider_failure_as_sse_error(client, monkeypatch):
    async_client = httpx.AsyncClient
    calls = 0
    _mock_retrieval(monkeypatch)

    async def handler(_request):
        del _request
        nonlocal calls
        calls += 1
        return httpx.Response(400)

    monkeypatch.setattr(
        "app.services.chat.httpx.AsyncClient",
        lambda **kwargs: async_client(transport=httpx.MockTransport(handler), **kwargs),
    )
    client.app.dependency_overrides[get_settings] = lambda: _configured_settings(
        llm_max_retries=2,
    )

    response = client.post(
        "/chat/stream",
        json={"question": "Question?", "language": "en"},
    )

    assert response.status_code == 200
    assert "event: error" in response.text
    assert "could not complete the request" in response.text
    assert calls == 1


def test_chat_stream_retries_primary_then_uses_fallback(client, monkeypatch):
    async_client = httpx.AsyncClient
    models = []
    _mock_retrieval(monkeypatch)

    async def handler(request):
        payload = json.loads(request.read())
        models.append(payload["model"])
        if payload["model"] == "gemini-3.5-flash-lite":
            return httpx.Response(503)
        chunks = [
            "data: "
            + json.dumps(
                {"choices": [{"delta": {"content": '{"answer":"Fallback stream",'}}]}
            )
            + "\n\n",
            "data: "
            + json.dumps({"choices": [{"delta": {"content": '"summary":"Done"}'}}]})
            + "\n\n",
            "data: [DONE]\n\n",
        ]
        return httpx.Response(200, text="".join(chunks))

    monkeypatch.setattr(
        "app.services.chat.httpx.AsyncClient",
        lambda **kwargs: async_client(transport=httpx.MockTransport(handler), **kwargs),
    )
    client.app.dependency_overrides[get_settings] = lambda: _configured_settings(
        llm_max_retries=1,
        llm_fallback_model="stream-fallback",
    )

    response = client.post(
        "/chat/stream",
        json={"question": "Question?", "language": "en"},
    )

    assert response.status_code == 200
    assert "event: complete" in response.text
    assert '"answer": "Fallback stream"' in response.text
    assert models == [
        "gemini-3.5-flash-lite",
        "gemini-3.5-flash-lite",
        "stream-fallback",
    ]
