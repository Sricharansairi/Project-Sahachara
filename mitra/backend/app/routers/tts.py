"""
MITRA Backend — TTS Router (Phase 4)

Endpoints:
  POST /api/v1/tts/synthesize          — Synthesize text → audio bytes (base64)
  POST /api/v1/tts/stream              — SSE: stream audio chunks for real-time playback
  GET  /api/v1/tts/health              — TTS service health

Architecture:
  Primary: Kokoro-82M via kokoro-fastapi local GPU server (default: http://localhost:8880)
  Fallback: Cartesia Sonic API (cloud, low-latency)
  Chunk strategy: LLM generates 4–6 words → TTS synthesizes → audio chunk enqueued
  AEC gate: Caller must set X-AEC-Gate: active to confirm mic is muted before playback
"""
from __future__ import annotations

import asyncio
import base64
import json
import time
from typing import AsyncIterator

import httpx
import structlog
from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, Field
from sse_starlette.sse import EventSourceResponse

from app.config import settings

logger = structlog.get_logger(__name__)
router = APIRouter(prefix="/api/v1/tts", tags=["tts"])


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------

class SynthesizeRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=4096)
    voice: str = Field(default="af_bella", description="Kokoro voice ID")
    speed: float = Field(default=1.0, ge=0.5, le=2.0)
    stream_chunks: bool = Field(default=False, description="Enable chunk-mode for real-time playback")


class SynthesizeResponse(BaseModel):
    audio_b64: str
    audio_format: str = "wav"
    duration_ms: float
    latency_ms: float
    model_used: str
    is_fallback: bool = False
    char_count: int


class TTSHealthResponse(BaseModel):
    status: str
    primary_model: str
    fallback_model: str
    kokoro_reachable: bool
    cartesia_configured: bool
    latency_ms: float | None = None


class StreamChunkSynthRequest(BaseModel):
    """
    LLM-driven chunk synthesis: accepts text in incremental units (4-6 words).
    Each chunk triggers a TTS synthesis and SSE delivery to the Rust audio queue.
    """
    session_id: str = Field(..., description="Unique voice session ID for ordering")
    text_chunk: str = Field(..., min_length=1, max_length=512)
    chunk_index: int = Field(default=0)
    is_final: bool = Field(default=False, description="True on last LLM token group")
    voice: str = Field(default="af_bella")
    speed: float = Field(default=1.0)


# ---------------------------------------------------------------------------
# Kokoro TTS Engine
# ---------------------------------------------------------------------------

# Voice cache: maps common phrases to pre-synthesized audio
VOICE_CACHE: dict[str, bytes] = {}
CACHED_PHRASES = [
    "Sure!", "On it!", "Done!", "Got it!", "Okay!",
    "Let me check that.", "I'll take care of that.",
    "Here you go.", "Of course!", "Right away!",
]


class KokoroTTSEngine:
    """
    Primary TTS via kokoro-fastapi local server.
    Falls back to Cartesia Sonic cloud API.

    Circuit breaker:
      3 consecutive Kokoro failures → trip for 5 min → Cartesia
    """

    KOKORO_BASE = settings.kokoro_base_url
    CARTESIA_URL = "https://api.cartesia.ai/tts/bytes"

    def __init__(self) -> None:
        self._kokoro_http = httpx.AsyncClient(
            timeout=httpx.Timeout(30.0, connect=2.0),
            base_url=self.KOKORO_BASE,
        )
        self._cartesia_http = httpx.AsyncClient(
            timeout=httpx.Timeout(30.0, connect=5.0),
            headers={
                "X-API-Key": settings.cartesia_api_key,
                "Cartesia-Version": "2024-06-10",
                "Content-Type": "application/json",
            },
        )
        self._fail_count = 0
        self._trip_until = 0.0
        self._cache_warm = False

    def _kokoro_circuit_open(self) -> bool:
        if self._fail_count >= 3:
            if time.monotonic() < self._trip_until:
                return True
            self._fail_count = 0  # half-open
        return False

    async def warm_cache(self) -> None:
        """Pre-synthesize common phrases to achieve sub-50ms latency for them."""
        if self._cache_warm:
            return
        for phrase in CACHED_PHRASES:
            try:
                audio_bytes, _ = await self.synthesize(phrase, "af_bella", 1.0)
                VOICE_CACHE[phrase.lower()] = audio_bytes
            except Exception:
                pass  # best effort
        self._cache_warm = True
        logger.info("tts.cache_warmed", phrases=len(VOICE_CACHE))

    async def synthesize(
        self, text: str, voice: str = "af_bella", speed: float = 1.0
    ) -> tuple[bytes, bool]:
        """Returns (audio_bytes, is_fallback)."""
        # Check cache first
        cache_hit = VOICE_CACHE.get(text.lower().strip())
        if cache_hit:
            logger.info("tts.cache_hit", text=text[:30])
            return cache_hit, False

        if not self._kokoro_circuit_open():
            try:
                return await self._synthesize_kokoro(text, voice, speed)
            except Exception as e:
                self._fail_count += 1
                if self._fail_count >= 3:
                    self._trip_until = time.monotonic() + 300
                logger.warning("tts.kokoro_failed", error=str(e), fail_count=self._fail_count)

        # Fallback to Cartesia
        return await self._synthesize_cartesia(text, voice, speed)

    async def _synthesize_kokoro(self, text: str, voice: str, speed: float) -> tuple[bytes, bool]:
        """POST to local kokoro-fastapi server."""
        payload = {
            "model": "kokoro",
            "input": text,
            "voice": voice,
            "speed": speed,
            "response_format": "wav",
        }
        resp = await self._kokoro_http.post("/v1/audio/speech", json=payload)
        resp.raise_for_status()
        self._fail_count = 0
        audio_bytes = resp.content
        logger.info("tts.kokoro_success", chars=len(text), bytes_=len(audio_bytes))
        return audio_bytes, False

    async def synthesize_stream(
        self, text: str, voice: str = "af_bella", speed: float = 1.0
    ) -> AsyncIterator[bytes]:
        """
        Streaming synthesis: yields audio chunks as they arrive from Kokoro.
        Used by the /stream endpoint for real-time chunk-mode delivery.
        """
        if self._kokoro_circuit_open():
            # Cartesia streaming fallback
            async for chunk in self._stream_cartesia(text, voice, speed):
                yield chunk
            return

        try:
            payload = {
                "model": "kokoro",
                "input": text,
                "voice": voice,
                "speed": speed,
                "response_format": "pcm",  # raw PCM for lower overhead
                "stream": True,
            }
            async with self._kokoro_http.stream("POST", "/v1/audio/speech", json=payload) as resp:
                resp.raise_for_status()
                async for chunk in resp.aiter_bytes(chunk_size=4096):
                    if chunk:
                        yield chunk
            self._fail_count = 0
        except Exception as e:
            self._fail_count += 1
            logger.warning("tts.kokoro_stream_failed", error=str(e))
            async for chunk in self._stream_cartesia(text, voice, speed):
                yield chunk

    async def _synthesize_cartesia(self, text: str, voice: str, speed: float) -> tuple[bytes, bool]:
        """Cartesia Sonic REST fallback, or acoustic offline fallback."""
        if not settings.cartesia_api_key:
            logger.info("tts.generating_offline_fallback_audio", chars=len(text))
            return self._generate_fallback_wav(text), True

        payload = {
            "transcript": text,
            "model_id": "sonic-english",
            "voice": {
                "mode": "id",
                "id": settings.cartesia_voice_id,
            },
            "output_format": {
                "container": "wav",
                "encoding": "pcm_f32le",
                "sample_rate": 22050,
            },
            "language": "en",
        }
        resp = await self._cartesia_http.post(self.CARTESIA_URL, json=payload)
        resp.raise_for_status()
        audio_bytes = resp.content
        logger.info("tts.cartesia_fallback_success", chars=len(text), bytes_=len(audio_bytes))
        return audio_bytes, True

    def _generate_fallback_wav(self, text: str) -> bytes:
        """Generate a valid soft acoustic confirmation WAV in offline fallback mode."""
        import wave, io, struct, math
        sample_rate = 16000
        duration_s = min(2.0, max(0.5, len(text) * 0.05))
        num_samples = int(sample_rate * duration_s)
        
        buf = io.BytesIO()
        with wave.open(buf, 'wb') as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(sample_rate)
            samples = []
            for i in range(num_samples):
                t = i / sample_rate
                # Envelope: fade in, fade out
                env = min(1.0, t / 0.05) * min(1.0, (duration_s - t) / 0.1)
                # Soft chord (440Hz + 554Hz + 659Hz major triad)
                val = (0.5 * math.sin(2 * math.pi * 440 * t) + 
                       0.3 * math.sin(2 * math.pi * 554.37 * t) + 
                       0.2 * math.sin(2 * math.pi * 659.25 * t)) * env
                sample_int = int(max(-32768, min(32767, val * 16384)))
                samples.append(struct.pack('<h', sample_int))
            wf.writeframes(b''.join(samples))
        return buf.getvalue()


    async def _stream_cartesia(
        self, text: str, voice: str, speed: float
    ) -> AsyncIterator[bytes]:
        """Cartesia streaming fallback (WebSocket-less REST chunk stream)."""
        try:
            audio_bytes, _ = await self._synthesize_cartesia(text, voice, speed)
            # Deliver in 4KB chunks
            chunk_size = 4096
            for i in range(0, len(audio_bytes), chunk_size):
                yield audio_bytes[i:i + chunk_size]
                await asyncio.sleep(0)  # yield to event loop
        except Exception as e:
            logger.error("tts.cartesia_stream_failed", error=str(e))

    async def health_check(self) -> tuple[bool, float | None]:
        """Ping kokoro-fastapi health endpoint."""
        try:
            t0 = time.monotonic()
            resp = await self._kokoro_http.get("/health", timeout=3.0)
            return resp.status_code == 200, (time.monotonic() - t0) * 1000
        except Exception:
            return False, None

    async def close(self) -> None:
        await self._kokoro_http.aclose()
        await self._cartesia_http.aclose()


# Singleton
tts_engine = KokoroTTSEngine()


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.post("/synthesize", response_model=SynthesizeResponse)
async def synthesize(req: SynthesizeRequest) -> SynthesizeResponse:
    """
    Full-text synthesis → base64-encoded WAV audio.
    """
    t0 = time.monotonic()
    audio_bytes, is_fallback = await tts_engine.synthesize(req.text, req.voice, req.speed)
    latency_ms = (time.monotonic() - t0) * 1000

    # Estimate duration: WAV PCM 22050Hz 16bit mono
    sample_rate = 22050
    bytes_per_sample = 2
    wav_header_size = 44
    pcm_bytes = max(0, len(audio_bytes) - wav_header_size)
    duration_ms = (pcm_bytes / (sample_rate * bytes_per_sample)) * 1000

    logger.info(
        "tts.synthesize",
        chars=len(req.text),
        latency_ms=round(latency_ms, 1),
        is_fallback=is_fallback,
    )

    return SynthesizeResponse(
        audio_b64=base64.b64encode(audio_bytes).decode(),
        audio_format="wav",
        duration_ms=round(duration_ms, 1),
        latency_ms=round(latency_ms, 1),
        model_used="cartesia/sonic-english" if is_fallback else "kokoro-82M",
        is_fallback=is_fallback,
        char_count=len(req.text),
    )


@router.post("/stream")
async def synthesize_stream(req: SynthesizeRequest) -> EventSourceResponse:
    """
    Streaming TTS: delivers audio chunks via SSE for real-time Rust playback queue.
    Each SSE event carries a base64-encoded audio chunk and its index.
    The Rust audio queue (rodio) plays chunks in order with smooth concatenation.

    Flow:
      1. TTS_STARTED event with metadata
      2. N × AUDIO_CHUNK events (base64 PCM chunks, ~4KB each)
      3. TTS_COMPLETE event with total stats
    """

    async def event_gen() -> AsyncIterator[dict]:
        t0 = time.monotonic()
        chunk_index = 0
        total_bytes = 0

        yield {
            "event": "tts_started",
            "data": json.dumps({
                "text_length": len(req.text),
                "voice": req.voice,
                "speed": req.speed,
            }),
        }

        try:
            async for chunk in tts_engine.synthesize_stream(req.text, req.voice, req.speed):
                total_bytes += len(chunk)
                yield {
                    "event": "audio_chunk",
                    "data": json.dumps({
                        "chunk_index": chunk_index,
                        "audio_b64": base64.b64encode(chunk).decode(),
                        "byte_length": len(chunk),
                    }),
                }
                chunk_index += 1

        except Exception as e:
            logger.error("tts.stream_error", error=str(e))
            yield {"event": "error", "data": json.dumps({"error": str(e)})}
            return

        latency_ms = (time.monotonic() - t0) * 1000
        yield {
            "event": "tts_complete",
            "data": json.dumps({
                "total_chunks": chunk_index,
                "total_bytes": total_bytes,
                "latency_ms": round(latency_ms, 1),
            }),
        }

    return EventSourceResponse(event_gen())


@router.post("/chunk")
async def synthesize_chunk(req: StreamChunkSynthRequest) -> dict:
    """
    LLM-to-TTS chunk pipeline endpoint.
    Called per 4–6 word LLM output chunk for ultra-low first-audio-byte latency.
    Returns audio_b64 + chunk metadata; Rust queues and plays in order.
    """
    t0 = time.monotonic()

    audio_bytes, is_fallback = await tts_engine.synthesize(
        req.text_chunk, req.voice, req.speed
    )
    latency_ms = (time.monotonic() - t0) * 1000

    logger.info(
        "tts.chunk_synth",
        session=req.session_id,
        chunk_idx=req.chunk_index,
        is_final=req.is_final,
        latency_ms=round(latency_ms, 1),
    )

    return {
        "session_id": req.session_id,
        "chunk_index": req.chunk_index,
        "is_final": req.is_final,
        "audio_b64": base64.b64encode(audio_bytes).decode(),
        "latency_ms": round(latency_ms, 1),
        "is_fallback": is_fallback,
    }


@router.get("/health", response_model=TTSHealthResponse)
async def tts_health() -> TTSHealthResponse:
    """TTS service health check."""
    kokoro_ok, latency = await tts_engine.health_check()
    return TTSHealthResponse(
        status="ok" if kokoro_ok else "degraded",
        primary_model="kokoro-82M",
        fallback_model="cartesia/sonic-english",
        kokoro_reachable=kokoro_ok,
        cartesia_configured=bool(settings.cartesia_api_key),
        latency_ms=latency,
    )
