import asyncio
import hashlib
import logging

from sqlalchemy import delete, select

from app.config import get_settings
from app.database import DocumentChunk, get_session_factory, initialize_database
from app.services.documents import chunk_text, load_documents
from app.services.embeddings import EmbeddingProviderError, embed_texts

logger = logging.getLogger(__name__)


async def ingest() -> int:
    settings = get_settings()
    if not settings.database_url:
        raise RuntimeError("DATABASE_URL is not configured.")
    if settings.embedding_api_key is None and settings.llm_api_key is None:
        raise RuntimeError(
            "Neither EMBEDDING_API_KEY nor LLM_API_KEY is configured for embeddings."
        )

    await initialize_database(settings)
    session_factory = get_session_factory(settings)
    documents = list(load_documents(settings.pages_directory, settings.pdfs_directory))
    pending_chunks = []

    async with session_factory() as session:
        for document in documents:
            chunks = chunk_text(document.text)
            existing_result = await session.execute(
                select(DocumentChunk.chunk_index).where(
                    DocumentChunk.document_key == document.document_key,
                    DocumentChunk.embedding_provider == settings.embedding_provider,
                    DocumentChunk.embedding_model == settings.embedding_model,
                    DocumentChunk.embedding_dimensions == settings.embedding_dimensions,
                )
            )
            existing = set(existing_result.scalars().all())
            pending = [
                (document, index, chunk)
                for index, chunk in enumerate(chunks)
                if index not in existing
            ]
            pending_chunks.extend(pending)
        await session.commit()

    inserted = 0
    new_chunks = []
    for offset in range(0, len(pending_chunks), 50):
        batch = pending_chunks[offset : offset + 50]
        try:
            vectors = await embed_texts(
                [chunk for _, _, chunk in batch],
                settings,
                task_type="RETRIEVAL_DOCUMENT",
                titles=[document.title for document, _, _ in batch],
            )
        except EmbeddingProviderError:
            logger.error("Embedding batch failed at offset %s", offset)
            raise

        for (document, index, content), vector in zip(batch, vectors, strict=True):
            new_chunks.append(
                DocumentChunk(
                    document_key=document.document_key,
                    chunk_index=index,
                    chunk_hash=hashlib.sha256(content.encode()).hexdigest(),
                    title=document.title,
                    source_url=document.source_url,
                    content=content,
                    embedding=vector,
                    embedding_provider=settings.embedding_provider,
                    embedding_model=settings.embedding_model,
                    embedding_dimensions=settings.embedding_dimensions,
                )
            )
        inserted += len(batch)

    async with session_factory() as session:
        for document in documents:
            if document.source_url:
                await session.execute(
                    delete(DocumentChunk).where(
                        DocumentChunk.source_url == document.source_url,
                        DocumentChunk.document_key != document.document_key,
                    )
                )
        session.add_all(new_chunks)
        await session.commit()

    logger.info("Ingestion finished; inserted %s chunks across %s documents", inserted, len(documents))
    return inserted


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    inserted = asyncio.run(ingest())
    print(f"Inserted {inserted} new chunks.")


if __name__ == "__main__":
    main()
