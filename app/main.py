import asyncio
import json
import logging
from contextlib import asynccontextmanager
from typing import Annotated

from fastapi import Depends, FastAPI, Request
from fastapi.responses import JSONResponse, StreamingResponse

from app.config import Settings, get_settings
from app.database import DatabaseConfigurationError, initialize_database
from app.schemas import ChatRequest, ChatResponse, UsageSummaryResponse
from app.services.chat import (
    GeneratedAnswer,
    LLMConfigurationError,
    LLMProviderError,
    LLMTimeoutError,
    generate_answer,
    stream_answer,
)
from app.services.rag import RAGUnavailableError, format_evidence, retrieve_context
from app.services.usage import get_usage_service

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    if settings.database_url:
        try:
            await initialize_database(settings)
            logger.info("Database initialized successfully.")
        except Exception as error:
            logger.warning("Could not initialize database on startup: %s", error)
    yield


app = FastAPI(
    title="AlaiLink Fisheries Scheme Assistant",
    version="0.2.0",
    lifespan=lifespan,
)

SettingsDep = Annotated[Settings, Depends(get_settings)]


@app.exception_handler(DatabaseConfigurationError)
async def database_configuration_error_handler(
    _, error: DatabaseConfigurationError
) -> JSONResponse:
    return JSONResponse(status_code=503, content={"detail": str(error)})


@app.exception_handler(LLMConfigurationError)
async def llm_configuration_error_handler(_, error: LLMConfigurationError) -> JSONResponse:
    return JSONResponse(status_code=503, content={"detail": str(error)})


@app.exception_handler(LLMTimeoutError)
async def llm_timeout_error_handler(_, error: LLMTimeoutError) -> JSONResponse:
    return JSONResponse(status_code=504, content={"detail": str(error)})


@app.exception_handler(LLMProviderError)
async def llm_provider_error_handler(_, error: LLMProviderError) -> JSONResponse:
    return JSONResponse(status_code=502, content={"detail": str(error)})


@app.exception_handler(RAGUnavailableError)
async def rag_unavailable_error_handler(_, error: RAGUnavailableError) -> JSONResponse:
    return JSONResponse(status_code=503, content={"detail": str(error)})


@app.get("/hello")
def hello(settings: SettingsDep) -> dict:
    return {"message": f"Hello  {settings.app_name} in {settings.environment}!"}


@app.get("/health")
def health(settings: SettingsDep) -> dict:
    """Liveness: the process is up. Must be fast and must not call the LLM or the DB."""
    return {"status": "ok", "app": settings.app_name, "environment": settings.environment}


@app.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest, settings: SettingsDep) -> ChatResponse:
    if settings.llm_api_key is None and settings.embedding_api_key is None:
        raise LLMConfigurationError(
            "LLM_API_KEY or EMBEDDING_API_KEY is not configured."
        )
    chunks = await retrieve_context(request.question, settings)
    evidence, sources = format_evidence(chunks)
    answer, summary = await generate_answer(
        request.question, request.language, settings, evidence
    )
    return ChatResponse(
        answer=answer,
        language=request.language,
        sources=[{"title": source.title, "url": source.url} for source in sources],
        summary=summary,
    )


@app.post("/chat/stream")
async def chat_stream(
    request: ChatRequest,
    http_request: Request,
    settings: SettingsDep,
) -> StreamingResponse:
    if settings.llm_api_key is None and settings.embedding_api_key is None:
        raise LLMConfigurationError(
            "LLM_API_KEY or EMBEDDING_API_KEY is not configured."
        )
    chunks = await retrieve_context(request.question, settings)
    evidence, sources = format_evidence(chunks)

    async def events():
        answer_stream = stream_answer(
            request.question, request.language, settings, evidence
        )
        try:
            async for event_type, value in answer_stream:
                if await http_request.is_disconnected():
                    return

                if event_type == "delta":
                    data = {"content": value}
                elif event_type == "complete" and isinstance(value, GeneratedAnswer):
                    data = ChatResponse(
                        answer=value.answer,
                        language=request.language,
                        sources=[
                            {"title": source.title, "url": source.url}
                            for source in sources
                        ],
                        summary=value.summary,
                    ).model_dump(mode="json")
                else:
                    data = {}
                yield f"event: {event_type}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"
        except asyncio.CancelledError:
            raise
        except LLMConfigurationError as error:
            yield f"event: error\ndata: {json.dumps({'detail': str(error)})}\n\n"
        except LLMTimeoutError as error:
            yield f"event: error\ndata: {json.dumps({'detail': str(error)})}\n\n"
        except LLMProviderError as error:
            yield (
                f"event: error\ndata: "
                f"{json.dumps({'detail': str(error)}, ensure_ascii=False)}\n\n"
            )
        finally:
            await answer_stream.aclose()

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.get("/usage", response_model=UsageSummaryResponse)
async def get_usage(settings: SettingsDep) -> UsageSummaryResponse:
    if not settings.database_url:
        raise DatabaseConfigurationError("DATABASE_URL is not configured.")
    usage_service = get_usage_service(settings)
    return await usage_service.get_usage_summary()

