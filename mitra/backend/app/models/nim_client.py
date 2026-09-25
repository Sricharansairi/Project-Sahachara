"""
MITRA Backend — NIM Client with Circuit Breaker & Fallback Routing

Architecture:
  - NIMClient wraps the openai SDK (NIM is OpenAI-compatible)
  - Per-role CircuitBreaker: after 3 consecutive failures → trip for 5 min
  - ModelRouter selects primary or fallback per role
  - Streaming SSE relay: NIM chunk stream → FastAPI EventSourceResponse
"""
from __future__ import annotations

import asyncio
import time
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from enum import Enum

import structlog
from openai import AsyncOpenAI, APIError, APIConnectionError, RateLimitError

from app.config import settings

logger = structlog.get_logger(__name__)


# ---------------------------------------------------------------------------
# Model Role Enum
# ---------------------------------------------------------------------------

class ModelRole(str, Enum):
    FAST_BRAIN = "fast_brain"
    DEEP_REASON = "deep_reason"
    VISION = "vision"
    OCR = "ocr"
    EMBED = "embed"
    SAFETY = "safety"
    STT = "stt"


# ---------------------------------------------------------------------------
# Routing Table — primary + fallback per role
# ---------------------------------------------------------------------------

ROUTING_TABLE: dict[ModelRole, tuple[str, str]] = {
    ModelRole.FAST_BRAIN:  (settings.model_fast_brain,   settings.model_fast_brain_fb),
    ModelRole.DEEP_REASON: (settings.model_deep_reason,  settings.model_deep_reason_fb),
    ModelRole.VISION:      (settings.model_vision,        settings.model_vision_fb),
    ModelRole.OCR:         (settings.model_ocr,           settings.model_vision),     # vision as ocr fb
    ModelRole.EMBED:       (settings.model_embed,         settings.model_embed_fb),
    ModelRole.SAFETY:      (settings.model_safety,        settings.model_safety_fb),
    ModelRole.STT:         (settings.model_stt,           "local/whisper-medium"),
}


# ---------------------------------------------------------------------------
# Circuit Breaker
# ---------------------------------------------------------------------------

@dataclass
class CircuitBreaker:
    role: ModelRole
    threshold: int = field(default_factory=lambda: settings.circuit_breaker_threshold)
    cooldown_s: int = field(default_factory=lambda: settings.circuit_breaker_cooldown_s)

    _failures: int = field(default=0, init=False)
    _tripped_at: float = field(default=0.0, init=False)
    _is_open: bool = field(default=False, init=False)

    def is_open(self) -> bool:
        """Return True if circuit is tripped (primary should be skipped)."""
        if self._is_open:
            elapsed = time.monotonic() - self._tripped_at
            if elapsed > self.cooldown_s:
                # Half-open: allow one probe
                logger.info("circuit_breaker.half_open", role=self.role, elapsed=elapsed)
                self._is_open = False
                self._failures = 0
        return self._is_open

    def record_success(self) -> None:
        self._failures = 0
        self._is_open = False

    def record_failure(self) -> None:
        self._failures += 1
        logger.warning("circuit_breaker.failure", role=self.role, failures=self._failures)
        if self._failures >= self.threshold:
            self._is_open = True
            self._tripped_at = time.monotonic()
            logger.error(
                "circuit_breaker.tripped",
                role=self.role,
                cooldown_s=self.cooldown_s,
            )


# ---------------------------------------------------------------------------
# NIM Client
# ---------------------------------------------------------------------------

class NIMClient:
    """Async OpenAI-compatible client pointing at NVIDIA NIM."""

    def __init__(self) -> None:
        if not settings.nim_api_key:
            logger.warning("nim.no_api_key", msg="NIM_API_KEY not set — will use fallback / mock")

        self._client = AsyncOpenAI(
            api_key=settings.nim_api_key or "dummy",
            base_url=settings.nim_base_url,
        )
        self._breakers: dict[ModelRole, CircuitBreaker] = {
            role: CircuitBreaker(role=role) for role in ModelRole
        }

    def _select_model(self, role: ModelRole) -> str:
        primary, fallback = ROUTING_TABLE[role]
        if self._breakers[role].is_open():
            logger.info("nim.using_fallback", role=role, model=fallback)
            return fallback
        return primary

    async def chat_complete(
        self,
        role: ModelRole,
        messages: list[dict],
        *,
        max_tokens: int = 1024,
        temperature: float = 0.7,
    ) -> str:
        """Non-streaming chat completion with automatic fallback."""
        model = self._select_model(role)
        try:
            response = await self._client.chat.completions.create(
                model=model,
                messages=messages,  # type: ignore[arg-type]
                max_tokens=max_tokens,
                temperature=temperature,
            )
            self._breakers[role].record_success()
            content = response.choices[0].message.content or ""
            logger.info("nim.complete", role=role, model=model, tokens=response.usage.total_tokens if response.usage else None)
            return content
        except (APIError, APIConnectionError, RateLimitError) as exc:
            self._breakers[role].record_failure()
            logger.error("nim.error", role=role, model=model, error=str(exc))
            # Retry with fallback
            _, fallback = ROUTING_TABLE[role]
            if model != fallback:
                logger.info("nim.fallback_retry", role=role, fallback=fallback)
                return await self._chat_complete_model(role, fallback, messages, max_tokens, temperature)
            raise

    async def _chat_complete_model(
        self,
        role: ModelRole,
        model: str,
        messages: list[dict],
        max_tokens: int,
        temperature: float,
    ) -> str:
        response = await self._client.chat.completions.create(
            model=model,
            messages=messages,  # type: ignore[arg-type]
            max_tokens=max_tokens,
            temperature=temperature,
        )
        content = response.choices[0].message.content or ""
        return content

    async def stream_chat(
        self,
        role: ModelRole,
        messages: list[dict],
        *,
        max_tokens: int = 2048,
        temperature: float = 0.7,
    ) -> AsyncIterator[str]:
        """Streaming chat — yields text delta chunks."""
        model = self._select_model(role)
        t_start = time.monotonic()
        first_token = True
        try:
            async with self._client.chat.completions.stream(
                model=model,
                messages=messages,  # type: ignore[arg-type]
                max_tokens=max_tokens,
                temperature=temperature,
            ) as stream:
                async for chunk in stream:
                    delta = chunk.choices[0].delta.content if chunk.choices else None
                    if delta:
                        if first_token:
                            ttft = (time.monotonic() - t_start) * 1000
                            logger.info("nim.ttft_ms", role=role, model=model, ttft_ms=ttft)
                            first_token = False
                        yield delta
            self._breakers[role].record_success()
        except (APIError, APIConnectionError, RateLimitError) as exc:
            self._breakers[role].record_failure()
            logger.error("nim.stream_error", role=role, model=model, error=str(exc))
            # Fallback to non-streaming on error
            _, fallback = ROUTING_TABLE[role]
            if model != fallback:
                content = await self._chat_complete_model(role, fallback, messages, max_tokens, temperature)
                yield content
            else:
                raise

    async def embed(self, role: ModelRole, texts: list[str]) -> list[list[float]]:
        """Generate embeddings for a list of texts."""
        model = self._select_model(role)
        try:
            response = await self._client.embeddings.create(model=model, input=texts)
            self._breakers[role].record_success()
            return [item.embedding for item in response.data]
        except (APIError, APIConnectionError, RateLimitError) as exc:
            self._breakers[role].record_failure()
            logger.error("nim.embed_error", role=role, error=str(exc))
            raise

    def get_breaker_status(self) -> dict[str, dict]:
        """Return current status of all circuit breakers (for /health endpoint)."""
        return {
            role.value: {
                "is_open": cb.is_open(),
                "failures": cb._failures,
            }
            for role, cb in self._breakers.items()
        }


# Singleton
nim_client = NIMClient()
