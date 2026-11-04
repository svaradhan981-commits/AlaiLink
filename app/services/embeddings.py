import logging
import math

import httpx

from app.config import Settings

logger = logging.getLogger(__name__)


class EmbeddingProviderError(Exception):
    pass


async def embed_texts(
    texts: list[str],
    settings: Settings,
    *,
    task_type: str,
    titles: list[str] | None = None,
) -> list[list[float]]:
    if not texts:
        return []
    api_key = settings.embedding_api_key or settings.llm_api_key
    if api_key is None:
        raise EmbeddingProviderError(
            "Neither EMBEDDING_API_KEY nor LLM_API_KEY is configured for embeddings."
        )
    if titles is not None and len(titles) != len(texts):
        raise ValueError("The number of titles must match the number of texts.")

    try:
        async with httpx.AsyncClient(timeout=settings.embedding_timeout_seconds) as client:
            if settings.embedding_provider == "gemini":
                model_path = f"models/{settings.embedding_model}"
                payload = {
                    "requests": [
                        {
                            "model": model_path,
                            "content": {"parts": [{"text": text}]},
                            "config": {
                                "taskType": task_type,
                                "outputDimensionality": settings.embedding_dimensions,
                                **({"title": titles[index]} if titles is not None else {}),
                            },
                        }
                        for index, text in enumerate(texts)
                    ]
                }
                response = await client.post(
                    f"{settings.embedding_base_url.rstrip('/')}/{model_path}:batchEmbedContents",
                    headers={"x-goog-api-key": api_key.get_secret_value()},
                    json=payload,
                )
                response.raise_for_status()
                vectors = [item["values"] for item in response.json()["embeddings"]]
            else:
                response = await client.post(
                    f"{settings.embedding_base_url.rstrip('/')}/embeddings",
                    headers={"Authorization": f"Bearer {api_key.get_secret_value()}"},
                    json={
                        "model": settings.embedding_model,
                        "input": texts,
                        "dimensions": settings.embedding_dimensions,
                    },
                )
                response.raise_for_status()
                data = sorted(response.json()["data"], key=lambda item: item["index"])
                vectors = [item["embedding"] for item in data]
    except httpx.TimeoutException as error:
        logger.warning("Embedding provider request timed out")
        raise EmbeddingProviderError("The embedding provider request timed out.") from error
    except httpx.HTTPStatusError as error:
        logger.warning("Embedding provider returned HTTP %s", error.response.status_code)
        raise EmbeddingProviderError("The embedding provider could not complete the request.") from error
    except httpx.RequestError as error:
        logger.warning("Embedding provider network request failed: %s", type(error).__name__)
        raise EmbeddingProviderError("The embedding provider is temporarily unavailable.") from error
    except (KeyError, IndexError, TypeError, ValueError) as error:
        raise EmbeddingProviderError("The embedding provider returned an invalid response.") from error

    if len(vectors) != len(texts):
        raise EmbeddingProviderError("The embedding provider returned an unexpected number of vectors.")
    for vector in vectors:
        if len(vector) != settings.embedding_dimensions or not all(
            isinstance(value, (int, float)) and math.isfinite(value) for value in vector
        ):
            raise EmbeddingProviderError("The embedding dimensions do not match configuration.")
    return vectors
