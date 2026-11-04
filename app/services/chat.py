import asyncio
import json
import logging
import time
from collections.abc import AsyncGenerator, AsyncIterator
from typing import Any

import httpx
from pydantic import BaseModel, Field, ValidationError

from app.config import Settings
from app.services.usage import get_usage_service

logger = logging.getLogger(__name__)


class LLMConfigurationError(Exception):
    pass


class LLMTimeoutError(Exception):
    pass


class LLMProviderError(Exception):
    pass


class GeneratedAnswer(BaseModel):
    answer: str = Field(min_length=1)
    summary: str = Field(max_length=160)


class _AttemptFailure(Exception):
    def __init__(self, message: str, *, status_code: int | None = None, timed_out: bool = False):
        super().__init__(message)
        self.status_code = status_code
        self.timed_out = timed_out

    @property
    def retryable(self) -> bool:
        return (
            self.timed_out
            or self.status_code == 429
            or (self.status_code is not None and self.status_code >= 500)
            or self.status_code is None
        )


def _payload(question: str, language: str, model: str, evidence: str) -> dict:
    prompt = (
        "Answer the user's question using only the verified official Fisheries Department evidence "
        "in the user message. Do not use outside knowledge or infer missing scheme amounts, eligibility, "
        "or deadlines. Cite relevant evidence inline using its [number]. If the evidence does not verify "
        "the answer, clearly say so in the requested language. Return only a JSON object with string "
        'fields "answer" and "summary"; keep summary within 160 characters.'
    )
    return {
        "model": model,
        "messages": [
            {"role": "system", "content": prompt},
            {
                "role": "user",
                "content": (
                    f"Requested language: {language}\nQuestion: {question}\n\n"
                    f"Verified evidence:\n{evidence or '(No relevant verified evidence was retrieved.)'}"
                ),
            },
        ],
        "response_format": {"type": "json_object"},
    }


def _read_answer(response: httpx.Response | dict) -> GeneratedAnswer:
    try:
        data = response if isinstance(response, dict) else response.json()
        content = data["choices"][0]["message"]["content"]
        return GeneratedAnswer.model_validate_json(content)
    except (KeyError, IndexError, TypeError, ValueError, ValidationError) as error:
        raise LLMProviderError("The LLM provider returned an invalid response.") from error


def _public_error(failure: _AttemptFailure) -> LLMProviderError | LLMTimeoutError:
    if failure.timed_out:
        return LLMTimeoutError("The LLM request timed out.")
    return LLMProviderError("The LLM provider could not complete the request.")


async def _request_answer(
    client: httpx.AsyncClient,
    question: str,
    language: str,
    model: str,
    settings: Settings,
    evidence: str,
) -> GeneratedAnswer:
    timeout = httpx.Timeout(settings.llm_timeout_seconds)
    payload = _payload(question, language, model, evidence)
    retry_count = settings.llm_max_retries
    usage_service = get_usage_service(settings)

    for attempt in range(retry_count + 1):
        start_time = time.perf_counter()
        try:
            async with asyncio.timeout(settings.llm_timeout_seconds):
                response = await client.post(
                    f"{settings.llm_base_url.rstrip('/')}/chat/completions",
                    headers={"Authorization": f"Bearer {settings.llm_api_key.get_secret_value()}"},
                    json=payload,
                    timeout=timeout,
                )
            latency = time.perf_counter() - start_time
            if response.status_code >= 400:
                await usage_service.log_request(
                    model=model,
                    latency_seconds=latency,
                    status=f"error_{response.status_code}",
                    error_message=f"HTTP {response.status_code}",
                    endpoint="/chat",
                )
                failure = _AttemptFailure("Provider returned an error", status_code=response.status_code)
                if not failure.retryable:
                    raise LLMProviderError("The LLM provider could not complete the request.")
                raise failure

            try:
                response_data = response.json()
            except Exception:
                response_data = {}

            usage_info = response_data.get("usage") if isinstance(response_data, dict) else None
            prompt_tokens = usage_info.get("prompt_tokens") if isinstance(usage_info, dict) else None
            completion_tokens = usage_info.get("completion_tokens") if isinstance(usage_info, dict) else None
            total_tokens = usage_info.get("total_tokens") if isinstance(usage_info, dict) else None

            answer = _read_answer(response_data)
            await usage_service.log_request(
                model=model,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                total_tokens=total_tokens,
                latency_seconds=latency,
                status="success",
                endpoint="/chat",
            )
            logger.info("LLM answer generated by model %s", model)
            return answer
        except asyncio.CancelledError:
            raise
        except (httpx.TimeoutException, TimeoutError):
            latency = time.perf_counter() - start_time
            await usage_service.log_request(
                model=model,
                latency_seconds=latency,
                status="timeout",
                error_message="Request timed out",
                endpoint="/chat",
            )
            failure = _AttemptFailure("Provider request timed out", timed_out=True)
        except httpx.RequestError as error:
            latency = time.perf_counter() - start_time
            await usage_service.log_request(
                model=model,
                latency_seconds=latency,
                status="error",
                error_message=type(error).__name__,
                endpoint="/chat",
            )
            failure = _AttemptFailure(type(error).__name__)
        except _AttemptFailure as error:
            failure = error

        if attempt >= retry_count:
            raise _public_error(failure)

        logger.warning(
            "Retrying LLM request for model %s after attempt %s (%s)",
            model,
            attempt + 1,
            (
                "timeout"
                if failure.timed_out
                else f"HTTP {failure.status_code}"
                if failure.status_code
                else "network error"
            ),
        )
        await asyncio.sleep(settings.llm_retry_delay_seconds * (2**attempt))

    raise AssertionError("unreachable")


def _unverified_answer(language: str) -> GeneratedAnswer:
    if language == "ta":
        return GeneratedAnswer(
            answer="கிடைத்த அதிகாரப்பூர்வ ஆவணங்களில் இந்தத் தகவலை உறுதிப்படுத்த முடியவில்லை.",
            summary="அதிகாரப்பூர்வ ஆவணங்களில் தகவலை உறுதிப்படுத்த முடியவில்லை.",
        )
    return GeneratedAnswer(
        answer="I could not verify this information in the available official documents.",
        summary="Could not verify this information in the available official documents.",
    )


async def generate_answer(
    question: str,
    language: str,
    settings: Settings,
    evidence: str = "",
) -> tuple[str, str]:
    if not evidence.strip():
        generated = _unverified_answer(language)
        return generated.answer, generated.summary
    if settings.llm_api_key is None:
        raise LLMConfigurationError("LLM_API_KEY is not configured.")

    fallback = (settings.llm_fallback_model or "").strip()
    models = [settings.llm_model]
    if fallback and fallback != settings.llm_model:
        models.append(fallback)

    async with httpx.AsyncClient() as client:
        for index, model in enumerate(models):
            try:
                generated = await _request_answer(client, question, language, model, settings, evidence)
                return generated.answer, generated.summary
            except (LLMTimeoutError, LLMProviderError):
                if index + 1 == len(models):
                    raise
                logger.warning(
                    "Primary LLM model %s failed after retries; attempting configured fallback model %s",
                    model,
                    models[index + 1],
                )

    raise AssertionError("unreachable")


async def _stream_attempt(
    client: httpx.AsyncClient,
    question: str,
    language: str,
    model: str,
    settings: Settings,
    evidence: str,
) -> AsyncIterator[tuple[str, Any]]:
    timeout = httpx.Timeout(settings.llm_timeout_seconds)
    payload = _payload(question, language, model, evidence)
    payload["stream"] = True
    payload["stream_options"] = {"include_usage": True}
    content_parts = []
    stream_usage = None

    async with asyncio.timeout(settings.llm_timeout_seconds):
        async with client.stream(
            "POST",
            f"{settings.llm_base_url.rstrip('/')}/chat/completions",
            headers={"Authorization": f"Bearer {settings.llm_api_key.get_secret_value()}"},
            json=payload,
            timeout=timeout,
        ) as response:
            if response.status_code >= 400:
                failure = _AttemptFailure("Provider returned an error", status_code=response.status_code)
                if failure.retryable:
                    raise failure
                raise LLMProviderError("The LLM provider could not complete the request.")

            async for line in response.aiter_lines():
                if not line.startswith("data:"):
                    continue
                data = line[5:].strip()
                if data == "[DONE]":
                    break
                try:
                    event = json.loads(data)
                    choices = event.get("choices") or []
                    if choices:
                        delta = choices[0].get("delta", {}).get("content")
                        if isinstance(delta, str) and delta:
                            content_parts.append(delta)
                            yield "delta", delta
                    if "usage" in event and event["usage"]:
                        stream_usage = event["usage"]
                except (KeyError, IndexError, TypeError, ValueError) as error:
                    raise LLMProviderError("The LLM provider returned an invalid stream.") from error

    try:
        generated = GeneratedAnswer.model_validate_json("".join(content_parts))
    except (ValueError, ValidationError) as error:
        raise LLMProviderError("The LLM provider returned an invalid response.") from error
    yield "validated", generated
    yield "usage", stream_usage


async def stream_answer(
    question: str,
    language: str,
    settings: Settings,
    evidence: str = "",
) -> AsyncGenerator[tuple[str, str | GeneratedAnswer], None]:
    if not evidence.strip():
        yield "complete", _unverified_answer(language)
        return
    if settings.llm_api_key is None:
        raise LLMConfigurationError("LLM_API_KEY is not configured.")

    fallback = (settings.llm_fallback_model or "").strip()
    models = [settings.llm_model]
    if fallback and fallback != settings.llm_model:
        models.append(fallback)

    usage_service = get_usage_service(settings)

    async with httpx.AsyncClient() as client:
        for model_index, model in enumerate(models):
            last_error: LLMProviderError | LLMTimeoutError | None = None
            for attempt in range(settings.llm_max_retries + 1):
                emitted_delta = False
                generated = None
                stream_usage = None
                start_time = time.perf_counter()
                try:
                    async for event_type, value in _stream_attempt(
                        client, question, language, model, settings, evidence
                    ):
                        if event_type == "delta":
                            emitted_delta = True
                            yield event_type, value
                        elif event_type == "usage":
                            stream_usage = value
                        else:
                            generated = value
                except asyncio.CancelledError:
                    raise
                except (httpx.TimeoutException, TimeoutError):
                    latency = time.perf_counter() - start_time
                    await usage_service.log_request(
                        model=model,
                        latency_seconds=latency,
                        status="timeout",
                        error_message="Request timed out",
                        endpoint="/chat/stream",
                    )
                    failure = _AttemptFailure("Provider request timed out", timed_out=True)
                    last_error = _public_error(failure)
                except httpx.RequestError as error:
                    latency = time.perf_counter() - start_time
                    await usage_service.log_request(
                        model=model,
                        latency_seconds=latency,
                        status="error",
                        error_message=type(error).__name__,
                        endpoint="/chat/stream",
                    )
                    failure = _AttemptFailure(type(error).__name__)
                    last_error = _public_error(failure)
                except _AttemptFailure as error:
                    latency = time.perf_counter() - start_time
                    await usage_service.log_request(
                        model=model,
                        latency_seconds=latency,
                        status=f"error_{error.status_code}" if error.status_code else "error",
                        error_message=str(error),
                        endpoint="/chat/stream",
                    )
                    failure = error
                    last_error = _public_error(failure)
                except LLMProviderError as error:
                    latency = time.perf_counter() - start_time
                    await usage_service.log_request(
                        model=model,
                        latency_seconds=latency,
                        status="error",
                        error_message=str(error),
                        endpoint="/chat/stream",
                    )
                    last_error = error
                    break
                else:
                    latency = time.perf_counter() - start_time
                    if not isinstance(generated, GeneratedAnswer):
                        await usage_service.log_request(
                            model=model,
                            latency_seconds=latency,
                            status="error",
                            error_message="Invalid response format",
                            endpoint="/chat/stream",
                        )
                        last_error = LLMProviderError("The LLM provider returned an invalid response.")
                        break

                    prompt_tokens = (
                        stream_usage.get("prompt_tokens") if isinstance(stream_usage, dict) else None
                    )
                    completion_tokens = (
                        stream_usage.get("completion_tokens") if isinstance(stream_usage, dict) else None
                    )
                    total_tokens = (
                        stream_usage.get("total_tokens") if isinstance(stream_usage, dict) else None
                    )
                    await usage_service.log_request(
                        model=model,
                        prompt_tokens=prompt_tokens,
                        completion_tokens=completion_tokens,
                        total_tokens=total_tokens,
                        latency_seconds=latency,
                        status="success",
                        endpoint="/chat/stream",
                    )
                    logger.info("LLM stream generated by model %s", model)
                    yield "complete", generated
                    return

                if not failure.retryable:
                    break
                if attempt >= settings.llm_max_retries:
                    break

                if emitted_delta:
                    yield "reset", ""
                logger.warning(
                    "Retrying LLM stream for model %s after attempt %s (%s)",
                    model,
                    attempt + 1,
                    (
                        "timeout"
                        if failure.timed_out
                        else f"HTTP {failure.status_code}"
                        if failure.status_code
                        else "network error"
                    ),
                )
                await asyncio.sleep(settings.llm_retry_delay_seconds * (2**attempt))

            if model_index + 1 < len(models):
                if emitted_delta:
                    yield "reset", ""
                logger.warning(
                    "Primary LLM model %s failed after retries; attempting configured fallback model %s",
                    model,
                    models[model_index + 1],
                )
                continue
            if last_error is not None:
                raise last_error

    raise AssertionError("unreachable")
