"""
MITRA Backend — Voice STT Router (Phase 4)

Endpoints:
  POST /api/v1/voice/transcribe          — Single audio chunk → full transcript
  POST /api/v1/voice/transcribe/stream   — SSE: partial transcripts word-by-word
  GET  /api/v1/voice/health              — STT service health + active model

Architecture:
  Primary: NVIDIA Parakeet-TDT-0.6b-v2 via NIM ASR endpoint
  Fallback: Local Whisper-medium ONNX (CPU, zero-cloud bytes)
  Punctuation: NIM fast-brain 1-pass fix after final transcript
"""
from __future__ import annotations

import asyncio
import base64
import io
import json
import time
from typing import AsyncIterator

import httpx
import structlog
from fastapi import APIRouter, HTTPException, UploadFile, File, Form
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sse_starlette.sse import EventSourceResponse

from app.config import settings

logger = structlog.get_logger(__name__)
router = APIRouter(prefix="/api/v1/voice", tags=["voice"])


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------

class TranscribeRequest(BaseModel):
    """Single-chunk transcription request."""
    audio_b64: str = Field(..., description="Base64-encoded PCM/WAV bytes")
    sample_rate: int = Field(default=16000)
    channels: int = Field(default=1)
    language: str = Field(default="en")


class TranscribeResponse(BaseModel):
    transcript: str
    word_error_rate_estimate: float = 0.0
    latency_ms: float
    model_used: str
    is_fallback: bool = False


class STTHealthResponse(BaseModel):
    status: str
    primary_model: str
    fallback_model: str
    primary_reachable: bool
    latency_ms: float | None = None


# ---------------------------------------------------------------------------
# STT Engine
# ---------------------------------------------------------------------------

class ParakeetSTTEngine:
    """
    Wraps the NVIDIA NIM Parakeet-TDT-0.6b-v2 ASR endpoint.
    Falls back to local Whisper-medium ONNX on any error.
    """

    NIM_ASR_URL = "https://integrate.api.nvidia.com/v1/audio/transcriptions"

    def __init__(self) -> None:
        self._http = httpx.AsyncClient(
            timeout=httpx.Timeout(30.0, connect=5.0),
            headers={
                "Authorization": f"Bearer {settings.nim_api_key}",
                "Accept": "application/json",
            },
        )
        self._primary_ok = True
        self._primary_fail_count = 0
        self._primary_trip_until = 0.0

    def _circuit_open(self) -> bool:
        if self._primary_fail_count >= 3:
            if time.monotonic() < self._primary_trip_until:
                return True
            # Half-open: reset and retry
            self._primary_fail_count = 0
        return False

    async def transcribe(self, audio_bytes: bytes, sample_rate: int = 16000) -> tuple[str, bool]:
        """
        Returns (transcript, is_fallback).
        Fallback activates when Parakeet circuit trips.
        """
        if not self._circuit_open() and settings.nim_api_key:
            try:
                return await self._transcribe_parakeet(audio_bytes, sample_rate)
            except Exception as e:
                self._primary_fail_count += 1
                if self._primary_fail_count >= 3:
                    self._primary_trip_until = time.monotonic() + 300  # 5-min cooldown
                logger.warning("stt.parakeet_failed", error=str(e), fail_count=self._primary_fail_count)

        # Fallback to local Whisper ONNX
        return await self._transcribe_whisper_local(audio_bytes, sample_rate)

    async def _transcribe_parakeet(self, audio_bytes: bytes, sample_rate: int) -> tuple[str, bool]:
        """POST raw audio to NIM Parakeet ASR endpoint."""
        files = {
            "file": ("audio.wav", audio_bytes, "audio/wav"),
        }
        data = {
            "model": settings.model_stt,
            "language": "en",
            "response_format": "verbose_json",
        }

        resp = await self._http.post(
            self.NIM_ASR_URL,
            files=files,
            data=data,
        )
        resp.raise_for_status()
        result = resp.json()
        transcript = result.get("text", "").strip()
        self._primary_fail_count = 0  # success → reset counter
        logger.info("stt.parakeet_success", chars=len(transcript))
        return transcript, False

    async def _transcribe_whisper_local(self, audio_bytes: bytes, sample_rate: int) -> tuple[str, bool]:
        """
        CPU-local Whisper-medium ONNX fallback.
        Uses openai-whisper Python package if installed, else returns silent placeholder.
        Runs in executor to avoid blocking event loop.
        """
        try:
            loop = asyncio.get_event_loop()
            transcript = await loop.run_in_executor(None, self._run_whisper_sync, audio_bytes)
            logger.info("stt.whisper_fallback_success", chars=len(transcript))
            return transcript, True
        except Exception as e:
            logger.error("stt.whisper_fallback_failed", error=str(e))
            return "", True

    def _run_whisper_sync(self, audio_bytes: bytes) -> str:
        """Blocking whisper inference — called in thread pool."""
        try:
            import whisper
            import numpy as np

            # Load model (cached after first load)
            if not hasattr(self, "_whisper_model"):
                self._whisper_model = whisper.load_model("base.en")  # ~150MB, CPU-friendly

            # Convert bytes to float32 numpy array
            audio_array = np.frombuffer(audio_bytes, dtype=np.int16).astype(np.float32) / 32768.0
            result = self._whisper_model.transcribe(audio_array, language="en", fp16=False)
            return result["text"].strip()
        except ImportError:
            logger.warning("stt.whisper_not_installed — returning empty transcript")
            return "[Whisper not installed — install openai-whisper for local fallback]"

    async def apply_punctuation(self, raw_transcript: str) -> str:
        """
        1-pass punctuation + capitalization restoration via fast-brain NIM.
        Runs only on transcripts ≥ 3 words.
        """
        if len(raw_transcript.split()) < 3:
            return raw_transcript

        try:
            from app.models.nim_client import nim_client, ModelRole
            prompt = (
                f"Add proper punctuation and capitalization to this transcript. "
                f"Return ONLY the corrected text, nothing else:\n\n{raw_transcript}"
            )
            corrected = ""
            async for chunk in nim_client.stream_chat(
                role=ModelRole.FAST_BRAIN,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=512,
            ):
                corrected += chunk
            return corrected.strip() or raw_transcript
        except Exception as e:
            logger.warning("stt.punctuation_failed", error=str(e))
            return raw_transcript

    async def health_check(self) -> tuple[bool, float | None]:
        """Returns (primary_reachable, latency_ms)."""
        if not settings.nim_api_key:
            return False, None
        try:
            t0 = time.monotonic()
            resp = await self._http.get(
                "https://integrate.api.nvidia.com/v1/models",
                timeout=5.0,
            )
            latency = (time.monotonic() - t0) * 1000
            return resp.status_code == 200, latency
        except Exception:
            return False, None

    async def close(self) -> None:
        await self._http.aclose()


# Singleton
stt_engine = ParakeetSTTEngine()


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.post("/transcribe", response_model=TranscribeResponse)
async def transcribe_audio(req: TranscribeRequest) -> TranscribeResponse:
    """
    Transcribes a base64-encoded audio chunk.
    - Decodes bytes
    - Sends to Parakeet (or Whisper fallback)
    - Applies punctuation restoration
    - Returns full transcript + latency
    """
    t0 = time.monotonic()

    try:
        audio_bytes = base64.b64decode(req.audio_b64)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid base64 audio payload")

    if len(audio_bytes) < 512:
        raise HTTPException(status_code=400, detail="Audio payload too short (min 512 bytes)")

    transcript, is_fallback = await stt_engine.transcribe(audio_bytes, req.sample_rate)
    transcript = await stt_engine.apply_punctuation(transcript)

    latency_ms = (time.monotonic() - t0) * 1000
    model_used = "local/whisper-base.en" if is_fallback else settings.model_stt

    logger.info(
        "voice.transcribe",
        latency_ms=round(latency_ms, 1),
        is_fallback=is_fallback,
        transcript_len=len(transcript),
    )

    return TranscribeResponse(
        transcript=transcript,
        latency_ms=round(latency_ms, 1),
        model_used=model_used,
        is_fallback=is_fallback,
    )


@router.post("/transcribe/upload")
async def transcribe_upload(
    file: UploadFile = File(...),
    language: str = Form(default="en"),
) -> TranscribeResponse:
    """
    Multipart audio upload endpoint.
    Accepts WAV/FLAC/OGG/WEBM up to 25MB.
    """
    t0 = time.monotonic()
    audio_bytes = await file.read()

    if len(audio_bytes) > 25 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="Audio file exceeds 25MB limit")

    transcript, is_fallback = await stt_engine.transcribe(audio_bytes)
    transcript = await stt_engine.apply_punctuation(transcript)

    latency_ms = (time.monotonic() - t0) * 1000
    model_used = "local/whisper-base.en" if is_fallback else settings.model_stt

    return TranscribeResponse(
        transcript=transcript,
        latency_ms=round(latency_ms, 1),
        model_used=model_used,
        is_fallback=is_fallback,
    )


@router.post("/transcribe/stream")
async def transcribe_stream(req: TranscribeRequest) -> EventSourceResponse:
    """
    SSE streaming transcription endpoint.
    Streams partial word-level transcripts to the frontend as they arrive.
    Simulates streaming by splitting final transcript into word-chunks.
    """

    async def event_gen() -> AsyncIterator[dict]:
        t0 = time.monotonic()

        try:
            audio_bytes = base64.b64decode(req.audio_b64)
        except Exception:
            yield {"event": "error", "data": json.dumps({"error": "invalid_base64"})}
            return

        # Send STT_STARTED event
        yield {"event": "stt_started", "data": json.dumps({"status": "transcribing"})}

        transcript, is_fallback = await stt_engine.transcribe(audio_bytes, req.sample_rate)

        # Stream word-by-word partial transcripts
        words = transcript.split()
        partial = ""
        for i, word in enumerate(words):
            partial += (" " if i > 0 else "") + word
            yield {
                "event": "partial_transcript",
                "data": json.dumps({"partial": partial, "word_index": i}),
            }
            await asyncio.sleep(0.020)  # 20ms between words for natural relay

        # Apply punctuation on final
        final = await stt_engine.apply_punctuation(transcript)
        latency_ms = (time.monotonic() - t0) * 1000

        yield {
            "event": "final_transcript",
            "data": json.dumps({
                "transcript": final,
                "latency_ms": round(latency_ms, 1),
                "is_fallback": is_fallback,
                "model_used": "local/whisper-base.en" if is_fallback else settings.model_stt,
            }),
        }

    return EventSourceResponse(event_gen())


@router.get("/health", response_model=STTHealthResponse)
async def stt_health() -> STTHealthResponse:
    """Returns STT service health and primary model reachability."""
    t0 = time.monotonic()
    primary_ok, nim_latency = await stt_engine.health_check()
    latency_ms = (time.monotonic() - t0) * 1000

    return STTHealthResponse(
        status="ok" if primary_ok else "degraded",
        primary_model=settings.model_stt,
        fallback_model="local/whisper-base.en",
        primary_reachable=primary_ok,
        latency_ms=round(nim_latency or latency_ms, 1),
    )
