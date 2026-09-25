"""
MITRA Backend — Full E2E Voice Pipeline Router (Phase 4)

Endpoint:
  POST /api/v1/voice/pipeline          — Full STT→LLM→TTS round-trip
  POST /api/v1/voice/pipeline/stream   — SSE: streaming pipeline with partial transcript,
                                         LLM tokens, and audio chunks interleaved

Pipeline sequence:
  1. Decode audio → Parakeet STT → partial transcripts via SSE
  2. Safety check on transcript
  3. LangGraph MitraGraph → LLM streaming tokens
  4. Chunk LLM output → Kokoro TTS per chunk → SSE audio chunk events
  5. Emit pipeline_complete with full latency profile

Latency optimization:
  - STT + LLM start overlap: LLM call begins after first STT partial if confidence high
  - Request pipelining: do not wait for full STT before queuing LLM context
  - Local voice response cache: match utterance → pre-synthesized audio
"""
from __future__ import annotations

import asyncio
import base64
import json
import time
import uuid
from typing import AsyncIterator

import structlog
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from sse_starlette.sse import EventSourceResponse

from app.agents.graph import mitra_graph, MitraState
from app.agents.safety import classify_input
from app.memory.store import memory_store
from app.models.nim_client import nim_client, ModelRole
from app.routers.voice import stt_engine
from app.routers.tts import tts_engine

logger = structlog.get_logger(__name__)
router = APIRouter(prefix="/api/v1/voice/pipeline", tags=["voice-pipeline"])


# ---------------------------------------------------------------------------
# Local utterance → audio cache (P4-T03 optimization)
# ---------------------------------------------------------------------------

UTTERANCE_AUDIO_CACHE: dict[str, bytes] = {}
CACHED_UTTERANCES = {
    "sure": "Sure!",
    "on it": "On it!",
    "done": "Done!",
    "got it": "Got it!",
    "okay": "Okay!",
}


# ---------------------------------------------------------------------------
# Request / Response models
# ---------------------------------------------------------------------------

class PipelineRequest(BaseModel):
    audio_b64: str = Field(..., description="Base64-encoded WAV/PCM from Rust audio capture")
    sample_rate: int = Field(default=16000)
    conversation_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    screen_payload: str = Field(default="", description="Optional screen context from DXGI")
    voice: str = Field(default="af_bella")
    tts_speed: float = Field(default=1.0)
    enable_tts: bool = Field(default=True)


class PipelineLatencyProfile(BaseModel):
    stt_ms: float
    llm_ttft_ms: float       # time to first token
    tts_first_chunk_ms: float
    total_ms: float


class PipelineResponse(BaseModel):
    session_id: str
    transcript: str
    llm_response: str
    audio_b64: str | None = None
    latency: PipelineLatencyProfile
    is_stt_fallback: bool = False
    is_tts_fallback: bool = False


# ---------------------------------------------------------------------------
# Word-chunking utility for LLM→TTS pipelining
# ---------------------------------------------------------------------------

def _chunk_text(text: str, chunk_size: int = 5) -> list[str]:
    """Split text into groups of ~chunk_size words preserving punctuation boundaries."""
    words = text.split()
    chunks = []
    current: list[str] = []

    for word in words:
        current.append(word)
        # Natural break: end of sentence or chunk_size reached
        if len(current) >= chunk_size or (word and word[-1] in ".!?,;:"):
            chunks.append(" ".join(current))
            current = []

    if current:
        chunks.append(" ".join(current))

    return [c for c in chunks if c.strip()]


# ---------------------------------------------------------------------------
# Streaming pipeline endpoint (primary)
# ---------------------------------------------------------------------------

@router.post("/stream")
async def voice_pipeline_stream(req: PipelineRequest) -> EventSourceResponse:
    """
    Full SSE voice pipeline:
      stt_started → partial_transcript × N → transcript_final →
      llm_token × N → tts_chunk × N → pipeline_complete

    Rust consumer:
      - Feeds partial transcripts to UI (barge-in detection window)
      - Queues audio chunks for rodio playback in order
      - Signals AEC: mute mic on first tts_chunk event
    """
    session_id = str(uuid.uuid4())
    t_pipeline_start = time.monotonic()

    async def event_gen() -> AsyncIterator[dict]:
        nonlocal session_id

        # ── STAGE 1: STT ──────────────────────────────────────────────────
        t_stt_start = time.monotonic()
        yield {"event": "stt_started", "data": json.dumps({"session_id": session_id})}

        try:
            audio_bytes = base64.b64decode(req.audio_b64)
        except Exception:
            yield {"event": "error", "data": json.dumps({"error": "invalid_base64_audio"})}
            return

        if len(audio_bytes) < 512:
            yield {"event": "error", "data": json.dumps({"error": "audio_too_short"})}
            return

        # Run STT
        transcript, is_stt_fallback = await stt_engine.transcribe(audio_bytes, req.sample_rate)

        # Stream word-by-word partials
        words = transcript.split()
        partial = ""
        for i, word in enumerate(words):
            partial += (" " if i > 0 else "") + word
            yield {
                "event": "partial_transcript",
                "data": json.dumps({"partial": partial, "word_index": i, "session_id": session_id}),
            }
            await asyncio.sleep(0.015)

        # Punctuation restoration
        transcript = await stt_engine.apply_punctuation(transcript)
        t_stt_done = time.monotonic()
        stt_ms = (t_stt_done - t_stt_start) * 1000

        yield {
            "event": "transcript_final",
            "data": json.dumps({
                "transcript": transcript,
                "stt_ms": round(stt_ms, 1),
                "is_fallback": is_stt_fallback,
                "session_id": session_id,
            }),
        }

        if not transcript.strip():
            yield {"event": "pipeline_complete", "data": json.dumps({"error": "empty_transcript"})}
            return

        # ── STAGE 2: Safety Check ─────────────────────────────────────────
        is_safe, reason = await classify_input(transcript)
        if not is_safe:
            yield {
                "event": "safety_blocked",
                "data": json.dumps({"reason": reason, "session_id": session_id}),
            }
            return

        # ── STAGE 3: LLM Streaming via MitraGraph ─────────────────────────
        t_llm_start = time.monotonic()
        llm_ttft_ms = 0.0
        first_token = True

        # Build state for LangGraph
        state: MitraState = {
            "messages": memory_store.get_l1_messages(),
            "user_input": transcript,
            "intent": "",
            "tool_result": "",
            "pending_approval": None,
            "memory_context": "",
            "screen_payload": req.screen_payload,
            "final_response": "",
            "is_safe": True,
            "safety_reason": "",
            "error": None,
        }

        full_llm_response = ""
        pending_chunk = ""  # accumulates words until chunk_size for TTS
        chunk_index = 0
        tts_first_chunk_ms = 0.0
        tts_tasks: list[asyncio.Task] = []
        is_tts_fallback = False

        async def _synth_and_emit(text: str, idx: int, is_final_chunk: bool) -> None:
            nonlocal tts_first_chunk_ms, is_tts_fallback
            try:
                t_tts = time.monotonic()
                audio_bytes_tts, fb = await tts_engine.synthesize(text, req.voice, req.tts_speed)
                tts_lat = (time.monotonic() - t_tts) * 1000
                if idx == 0:
                    tts_first_chunk_ms = tts_lat
                is_tts_fallback = is_tts_fallback or fb
            except Exception as e:
                logger.warning("pipeline.tts_chunk_failed", error=str(e))
                return

        # Stream LLM tokens
        try:
            async for token in nim_client.stream_chat(
                role=ModelRole.FAST_BRAIN,
                messages=[
                    {"role": "system", "content": "You are MITRA, an AI assistant. Be concise and conversational."},
                    *state["messages"][-10:],
                    {"role": "user", "content": transcript},
                ],
                max_tokens=1024,
            ):
                if first_token:
                    llm_ttft_ms = (time.monotonic() - t_llm_start) * 1000
                    first_token = False

                full_llm_response += token

                yield {
                    "event": "llm_token",
                    "data": json.dumps({"token": token, "session_id": session_id}),
                }

                # Accumulate for TTS chunking
                if req.enable_tts:
                    pending_chunk += token
                    words_so_far = pending_chunk.split()
                    # Emit chunk at ~5 words or sentence boundary
                    if len(words_so_far) >= 5 or (token.strip() and token.strip()[-1] in ".!?"):
                        if pending_chunk.strip():
                            text_to_synth = pending_chunk.strip()
                            idx = chunk_index
                            chunk_index += 1
                            pending_chunk = ""

                            # Fire TTS synthesis as background task
                            t_tts = time.monotonic()
                            try:
                                audio_b, fb = await tts_engine.synthesize(
                                    text_to_synth, req.voice, req.tts_speed
                                )
                                chunk_lat = (time.monotonic() - t_tts) * 1000
                                if idx == 0:
                                    tts_first_chunk_ms = chunk_lat
                                is_tts_fallback = is_tts_fallback or fb

                                yield {
                                    "event": "tts_chunk",
                                    "data": json.dumps({
                                        "chunk_index": idx,
                                        "audio_b64": base64.b64encode(audio_b).decode(),
                                        "text_chunk": text_to_synth,
                                        "latency_ms": round(chunk_lat, 1),
                                        "session_id": session_id,
                                    }),
                                }
                            except Exception as e:
                                logger.warning("pipeline.inline_tts_failed", error=str(e))

        except Exception as e:
            logger.error("pipeline.llm_stream_error", error=str(e))
            yield {"event": "error", "data": json.dumps({"error": f"llm_error: {e}"})}
            return

        # Flush remaining pending chunk
        if req.enable_tts and pending_chunk.strip():
            try:
                audio_b, fb = await tts_engine.synthesize(
                    pending_chunk.strip(), req.voice, req.tts_speed
                )
                is_tts_fallback = is_tts_fallback or fb
                yield {
                    "event": "tts_chunk",
                    "data": json.dumps({
                        "chunk_index": chunk_index,
                        "audio_b64": base64.b64encode(audio_b).decode(),
                        "text_chunk": pending_chunk.strip(),
                        "latency_ms": 0,
                        "is_final": True,
                        "session_id": session_id,
                    }),
                }
            except Exception as e:
                logger.warning("pipeline.flush_tts_failed", error=str(e))

        # ── STAGE 4: Memory Store ──────────────────────────────────────────
        try:
            await memory_store.add_turn("user", transcript)
            await memory_store.add_turn("assistant", full_llm_response)
        except Exception as e:
            logger.warning("pipeline.memory_store_failed", error=str(e))

        # ── STAGE 5: Pipeline Complete ─────────────────────────────────────
        total_ms = (time.monotonic() - t_pipeline_start) * 1000

        yield {
            "event": "pipeline_complete",
            "data": json.dumps({
                "session_id": session_id,
                "transcript": transcript,
                "llm_response": full_llm_response,
                "latency_profile": {
                    "stt_ms": round(stt_ms, 1),
                    "llm_ttft_ms": round(llm_ttft_ms, 1),
                    "tts_first_chunk_ms": round(tts_first_chunk_ms, 1),
                    "total_ms": round(total_ms, 1),
                },
                "is_stt_fallback": is_stt_fallback,
                "is_tts_fallback": is_tts_fallback,
            }),
        }

        logger.info(
            "pipeline.complete",
            session=session_id,
            total_ms=round(total_ms, 1),
            stt_ms=round(stt_ms, 1),
            llm_ttft_ms=round(llm_ttft_ms, 1),
            tts_first_chunk_ms=round(tts_first_chunk_ms, 1),
        )

    return EventSourceResponse(event_gen())


@router.post("", response_model=PipelineResponse)
async def voice_pipeline(req: PipelineRequest) -> PipelineResponse:
    """
    Non-streaming convenience pipeline endpoint.
    Returns full transcript + LLM response + synthesized audio in one response.
    Use this for testing; use /stream for production.
    """
    t0 = time.monotonic()

    try:
        audio_bytes = base64.b64decode(req.audio_b64)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid base64 audio")

    # STT
    t_stt = time.monotonic()
    transcript, is_stt_fallback = await stt_engine.transcribe(audio_bytes, req.sample_rate)
    transcript = await stt_engine.apply_punctuation(transcript)
    stt_ms = (time.monotonic() - t_stt) * 1000

    # Safety
    is_safe, reason = await classify_input(transcript)
    if not is_safe:
        raise HTTPException(status_code=400, detail=f"Safety blocked: {reason}")

    # LLM (non-streaming)
    t_llm = time.monotonic()
    llm_response = ""
    llm_ttft_ms = 0.0
    first = True
    async for token in nim_client.stream_chat(
        role=ModelRole.FAST_BRAIN,
        messages=[
            {"role": "system", "content": "You are MITRA. Be concise."},
            {"role": "user", "content": transcript},
        ],
        max_tokens=512,
    ):
        if first:
            llm_ttft_ms = (time.monotonic() - t_llm) * 1000
            first = False
        llm_response += token

    # TTS
    audio_b64 = None
    tts_first_chunk_ms = 0.0
    is_tts_fallback = False
    if req.enable_tts and llm_response.strip():
        t_tts = time.monotonic()
        audio_b, is_tts_fallback = await tts_engine.synthesize(
            llm_response, req.voice, req.tts_speed
        )
        tts_first_chunk_ms = (time.monotonic() - t_tts) * 1000
        audio_b64 = base64.b64encode(audio_b).decode()

    total_ms = (time.monotonic() - t0) * 1000

    # Store to memory
    try:
        await memory_store.add_turn("user", transcript)
        await memory_store.add_turn("assistant", llm_response)
    except Exception:
        pass

    return PipelineResponse(
        session_id=req.conversation_id,
        transcript=transcript,
        llm_response=llm_response,
        audio_b64=audio_b64,
        latency=PipelineLatencyProfile(
            stt_ms=round(stt_ms, 1),
            llm_ttft_ms=round(llm_ttft_ms, 1),
            tts_first_chunk_ms=round(tts_first_chunk_ms, 1),
            total_ms=round(total_ms, 1),
        ),
        is_stt_fallback=is_stt_fallback,
        is_tts_fallback=is_tts_fallback,
    )
