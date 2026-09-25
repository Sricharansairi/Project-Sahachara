"""
MITRA Backend — Chat Router

Endpoints:
  POST /api/v1/chat/stream  — SSE streaming chat via LangGraph MitraGraph
  POST /api/v1/chat/message — Non-streaming convenience endpoint
  POST /api/v1/memory/forget — Wipe all memory tiers
"""
from __future__ import annotations

import json
import time
from typing import AsyncIterator

import structlog
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sse_starlette.sse import EventSourceResponse

from app.agents.graph import mitra_graph, MitraState
from app.agents.safety import classify_input
from app.memory.store import memory_store
from app.models.nim_client import nim_client, ModelRole

logger = structlog.get_logger(__name__)
router = APIRouter(prefix="/api/v1/chat", tags=["chat"])


# ---------------------------------------------------------------------------
# Request / Response models
# ---------------------------------------------------------------------------

class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=8192)
    screen_payload: str = Field(default="", description="Untrusted visual payload from DXGI capture")
    conversation_id: str = Field(default="default")


class ChatResponse(BaseModel):
    response: str
    intent: str
    pending_approval: dict | None = None
    memory_chunks_used: int = 0
    latency_ms: float


class ForgetResponse(BaseModel):
    status: str = "ok"
    message: str = "All memory tiers wiped"


# ---------------------------------------------------------------------------
# Streaming chat endpoint
# ---------------------------------------------------------------------------

@router.post("/stream")
async def stream_chat(req: ChatRequest) -> EventSourceResponse:
    """
    SSE streaming endpoint:
      - Runs safety check first
      - Runs MitraGraph for intent + tool routing
      - Streams tokens via NIM SSE relay
      - Stores conversation turn in memory
    """
    t_start = time.monotonic()

    async def event_generator() -> AsyncIterator[dict]:
        # Safety pre-check
        is_safe, reason = await classify_input(req.message)
        if not is_safe:
            yield {"event": "error", "data": json.dumps({"error": "safety_blocked", "reason": reason})}
            return

        # Build initial state
        state: MitraState = {
            "messages": memory_store.get_l1_messages(),
            "user_input": req.message,
            "intent": "",
            "tool_result": "",
            "pending_approval": None,
            "memory_context": "",
            "screen_payload": req.screen_payload,
            "final_response": "",
            "is_safe": True,
            "safety_reason": "ok",
            "error": None,
        }

        # Run the graph (non-streaming node processing)
        try:
            final_state = await mitra_graph.ainvoke(state)
        except Exception as exc:
            logger.error("graph.invoke_error", error=str(exc))
            yield {"event": "error", "data": json.dumps({"error": str(exc)})}
            return

        # If approval needed, send approval event
        if final_state.get("pending_approval"):
            approval_data = json.dumps(final_state["pending_approval"])
            yield {"event": "approval", "data": approval_data}
            # Also stream a summary message
            summary = f"I've prepared: {final_state['pending_approval'].get('description', 'an action')} — please review and approve."
            yield {"event": "delta", "data": json.dumps({"text": summary})}
            # Store in memory
            await memory_store.add_turn("user", req.message)
            await memory_store.add_turn("assistant", summary)
            latency_ms = (time.monotonic() - t_start) * 1000
            yield {"event": "done", "data": json.dumps({"latency_ms": latency_ms, "intent": final_state.get("intent", "")})}
            return

        # Stream final response token by token via NIM
        response_parts: list[str] = []
        system_msg = "You are MITRA, a highly capable AI companion. Respond based on the context provided."
        if final_state.get("memory_context"):
            system_msg += f"\n\nRelevant memory:\n{final_state['memory_context']}"

        async for chunk in nim_client.stream_chat(
            ModelRole.FAST_BRAIN,
            messages=[
                {"role": "system", "content": system_msg},
                *memory_store.get_l1_messages(),
                {"role": "user", "content": req.message},
            ],
            max_tokens=2048,
        ):
            response_parts.append(chunk)
            yield {"event": "delta", "data": json.dumps({"text": chunk})}

        full_response = "".join(response_parts)
        await memory_store.add_turn("user", req.message)
        await memory_store.add_turn("assistant", full_response)

        latency_ms = (time.monotonic() - t_start) * 1000
        yield {
            "event": "done",
            "data": json.dumps({
                "latency_ms": latency_ms,
                "intent": final_state.get("intent", ""),
            }),
        }

    return EventSourceResponse(event_generator())


# ---------------------------------------------------------------------------
# Non-streaming convenience endpoint
# ---------------------------------------------------------------------------

@router.post("/message", response_model=ChatResponse)
async def chat_message(req: ChatRequest) -> ChatResponse:
    """Non-streaming chat for testing and simple integrations."""
    t_start = time.monotonic()

    is_safe, reason = await classify_input(req.message)
    if not is_safe:
        raise HTTPException(status_code=400, detail=f"safety_blocked: {reason}")

    memory_context = await memory_store.search(req.message, top_k=5)

    state: MitraState = {
        "messages": memory_store.get_l1_messages(),
        "user_input": req.message,
        "intent": "",
        "tool_result": "",
        "pending_approval": None,
        "memory_context": "\n".join(memory_context),
        "screen_payload": req.screen_payload,
        "final_response": "",
        "is_safe": True,
        "safety_reason": "ok",
        "error": None,
    }

    final_state = await mitra_graph.ainvoke(state)

    response_text = final_state.get("final_response", "") or final_state.get("tool_result", "")
    if not response_text:
        response_text = await nim_client.chat_complete(
            ModelRole.FAST_BRAIN,
            messages=[
                {"role": "system", "content": "You are MITRA, a helpful AI companion."},
                {"role": "user", "content": req.message},
            ],
        )

    await memory_store.add_turn("user", req.message)
    await memory_store.add_turn("assistant", response_text)

    return ChatResponse(
        response=response_text,
        intent=final_state.get("intent", ""),
        pending_approval=final_state.get("pending_approval"),
        memory_chunks_used=len(memory_context),
        latency_ms=(time.monotonic() - t_start) * 1000,
    )


# ---------------------------------------------------------------------------
# Memory forget endpoint
# ---------------------------------------------------------------------------

@router.post("/forget", response_model=ForgetResponse)
async def forget_memory() -> ForgetResponse:
    """Wipe all 4 memory tiers — irreversible per user request."""
    await memory_store.forget()
    return ForgetResponse()
