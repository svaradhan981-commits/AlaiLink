import logging
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError

from app.config import Settings
from app.database import DatabaseConfigurationError, DocumentChunk, get_session_factory
from app.services.embeddings import EmbeddingProviderError, embed_texts

logger = logging.getLogger(__name__)


class RAGUnavailableError(Exception):
    pass


@dataclass(frozen=True)
class RetrievedSource:
    title: str
    url: str


@dataclass(frozen=True)
class RetrievedChunk:
    content: str
    source: RetrievedSource | None
    distance: float


async def retrieve_context(question: str, settings: Settings) -> list[RetrievedChunk]:
    try:
        session_factory = get_session_factory(settings)
        engine = session_factory.kw["bind"]
        async with engine.connect() as connection:
            await connection.exec_driver_sql("SELECT 1")
        query_vector = (
            await embed_texts(
                [question],
                settings,
                task_type="RETRIEVAL_QUERY",
            )
        )[0]
        distance = DocumentChunk.embedding.cosine_distance(query_vector).label("distance")
        statement = (
            select(DocumentChunk, distance)
            .where(
                DocumentChunk.embedding_provider == settings.embedding_provider,
                DocumentChunk.embedding_model == settings.embedding_model,
                DocumentChunk.embedding_dimensions == settings.embedding_dimensions,
                DocumentChunk.source_url.is_not(None),
            )
            .order_by(distance)
            .limit(settings.rag_top_k)
        )
        async with session_factory() as session:
            rows = (await session.execute(statement)).all()
    except DatabaseConfigurationError as error:
        raise RAGUnavailableError(str(error)) from error
    except EmbeddingProviderError as error:
        raise RAGUnavailableError(str(error)) from error
    except SQLAlchemyError as error:
        logger.error("Document retrieval failed (%s)", type(error).__name__)
        raise RAGUnavailableError("The document database is unavailable.") from error

    results = []
    for chunk, score in rows:
        if score is None or score > settings.rag_max_distance:
            continue
        source = RetrievedSource(chunk.title, chunk.source_url) if chunk.source_url else None
        results.append(RetrievedChunk(chunk.content, source, float(score)))
    return results


def format_evidence(chunks: list[RetrievedChunk]) -> tuple[str, list[RetrievedSource]]:
    context_lines = []
    sources = []
    seen = set()
    for chunk in chunks:
        if chunk.source and chunk.source.url not in seen:
            sources.append(chunk.source)
            seen.add(chunk.source.url)
        citation = next(
            (f"[{index}]" for index, source in enumerate(sources, start=1) if chunk.source == source),
            "[unverified source]",
        )
        context_lines.append(
            f"{citation} Title: {chunk.source.title if chunk.source else 'Unknown'}\n"
            f"URL: {chunk.source.url if chunk.source else 'Unavailable'}\n"
            f"Text: {chunk.content}"
        )
    return "\n\n".join(context_lines), sources
