import asyncio

import pytest

from app.config import Settings
from app.services.rag import (
    RAGUnavailableError,
    RetrievedChunk,
    RetrievedSource,
    format_evidence,
    retrieve_context,
)


def test_format_evidence_deduplicates_source_citations():
    source = RetrievedSource("Official Scheme", "https://example.gov/scheme")

    evidence, sources = format_evidence(
        [
            RetrievedChunk("First excerpt.", source, 0.1),
            RetrievedChunk("Second excerpt.", source, 0.2),
        ]
    )

    assert len(sources) == 1
    assert evidence.count("[1]") == 2
    assert "First excerpt." in evidence
    assert "Second excerpt." in evidence


def test_retrieval_requires_database_before_embedding(monkeypatch):
    async def unexpected_embedding(*args, **kwargs):
        del args, kwargs
        raise AssertionError("Embedding should not be requested without a database URL.")

    monkeypatch.setattr("app.services.rag.embed_texts", unexpected_embedding)
    settings = Settings(_env_file=None, database_url=None)

    with pytest.raises(RAGUnavailableError, match="DATABASE_URL is not configured"):
        asyncio.run(retrieve_context("query", settings))
