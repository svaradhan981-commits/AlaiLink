import json

import httpx
import pytest

from app.config import Settings
from app.services.embeddings import EmbeddingProviderError, embed_texts


def _settings(**overrides):
    values = {
        "llm_api_key": "test-key",
        "embedding_dimensions": 3,
        "embedding_base_url": "https://generativelanguage.googleapis.com/v1beta",
    }
    values.update(overrides)
    return Settings(_env_file=None, **values)


@pytest.mark.anyio
async def test_gemini_embeddings_use_configured_dimension_and_task(monkeypatch, anyio_backend):
    _ = anyio_backend
    async_client = httpx.AsyncClient
    vectors = [[0.1, 0.2, 0.3], [0.4, 0.5, 0.6]]

    async def handler(request):
        assert request.url.path.endswith("/models/gemini-embedding-001:batchEmbedContents")
        assert request.headers["x-goog-api-key"] == "test-key"
        payload = json.loads(request.read())
        assert payload["requests"][0]["config"]["taskType"] == "RETRIEVAL_DOCUMENT"
        assert payload["requests"][0]["config"]["outputDimensionality"] == 3
        assert payload["requests"][0]["config"]["title"] == "Scheme"
        return httpx.Response(
            200,
            json={"embeddings": [{"values": vector} for vector in vectors]},
        )

    monkeypatch.setattr(
        "app.services.embeddings.httpx.AsyncClient",
        lambda **kwargs: async_client(transport=httpx.MockTransport(handler), **kwargs),
    )

    result = await embed_texts(
        ["first", "second"],
        _settings(),
        task_type="RETRIEVAL_DOCUMENT",
        titles=["Scheme", "Scheme"],
    )

    assert result == vectors


@pytest.mark.anyio
async def test_embedding_dimension_mismatch_is_rejected(monkeypatch, anyio_backend):
    _ = anyio_backend
    async_client = httpx.AsyncClient

    async def handler(_request):
        del _request
        return httpx.Response(200, json={"embeddings": [{"values": [0.1, 0.2]}]})

    monkeypatch.setattr(
        "app.services.embeddings.httpx.AsyncClient",
        lambda **kwargs: async_client(transport=httpx.MockTransport(handler), **kwargs),
    )

    with pytest.raises(EmbeddingProviderError, match="dimensions do not match"):
        await embed_texts(["query"], _settings(), task_type="RETRIEVAL_QUERY")


@pytest.mark.anyio
async def test_openai_compatible_embedding_provider_is_configurable(monkeypatch, anyio_backend):
    _ = anyio_backend
    async_client = httpx.AsyncClient

    async def handler(request):
        assert request.url.path == "/v1/embeddings"
        assert request.headers["Authorization"] == "Bearer test-key"
        body = json.loads(request.read())
        assert body["model"] == "compatible-embedding-model"
        assert body["dimensions"] == 3
        return httpx.Response(
            200,
            json={
                "data": [
                    {"index": 1, "embedding": [0.4, 0.5, 0.6]},
                    {"index": 0, "embedding": [0.1, 0.2, 0.3]},
                ]
            },
        )

    monkeypatch.setattr(
        "app.services.embeddings.httpx.AsyncClient",
        lambda **kwargs: async_client(transport=httpx.MockTransport(handler), **kwargs),
    )

    vectors = await embed_texts(
        ["first", "second"],
        _settings(
            embedding_provider="openai_compatible",
            embedding_model="compatible-embedding-model",
            embedding_base_url="https://embedding.example/v1",
        ),
        task_type="RETRIEVAL_QUERY",
    )

    assert vectors == [[0.1, 0.2, 0.3], [0.4, 0.5, 0.6]]
