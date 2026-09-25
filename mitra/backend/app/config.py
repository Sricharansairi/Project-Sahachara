"""
MITRA Backend — Pydantic Settings (Phase 4 — Voice Pipeline)
Loads configuration from environment variables / .env file.
"""
from __future__ import annotations

import os
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # App
    app_name: str = "MITRA Backend"
    environment: str = "development"

    # Backend server
    backend_host: str = "127.0.0.1"
    backend_port: int = 8766

    # NVIDIA NIM
    nim_api_key: str = os.getenv("NIM_API_KEY", "")
    nim_base_url: str = os.getenv("NIM_BASE_URL", "https://integrate.api.nvidia.com/v1")

    # Model identifiers — PRIMARY
    model_fast_brain: str = "nvidia/nemotron-super-49b-v1"
    model_deep_reason: str = "nvidia/llama-3.1-nemotron-ultra-253b-v1"
    model_vision: str = "meta/llama-3.2-11b-vision-instruct"
    model_ocr: str = "nvidia/llama-3.2-nv-embedqa-1b-v2"  # parse fallback
    model_embed: str = "nvidia/nv-embedqa-e5-v5"
    model_safety: str = "nvidia/llama-3.1-nemoguard-8b-content-safety"
    model_stt: str = "nvidia/parakeet-tdt-0.6b-v2"

    # Model identifiers — FALLBACK
    model_fast_brain_fb: str = "meta/llama-3.1-70b-instruct"
    model_deep_reason_fb: str = "google/gemma-3-27b-it"
    model_vision_fb: str = "microsoft/phi-3.5-vision-instruct"
    model_embed_fb: str = "baai/bge-m3"  # local BGE-M3 ONNX flag
    model_safety_fb: str = "local/regex-classifier"

    # Circuit breaker settings
    circuit_breaker_threshold: int = 3          # failures before trip
    circuit_breaker_cooldown_s: int = 300       # 5 minutes

    # Memory / RAG
    chroma_persist_dir: str = "./chroma_db"
    memory_l1_max_turns: int = 20

    # Database
    database_url: str = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///./mitra.db")

    # Prometheus metrics port
    metrics_port: int = 9090

    # Phase 4 — TTS: Kokoro-82M (primary, local)
    kokoro_base_url: str = os.getenv("KOKORO_BASE_URL", "http://localhost:8880")
    kokoro_voice_default: str = "af_bella"

    # Phase 4 — TTS: Cartesia Sonic (fallback, cloud)
    cartesia_api_key: str = os.getenv("CARTESIA_API_KEY", "")
    cartesia_voice_id: str = os.getenv("CARTESIA_VOICE_ID", "a0e99841-438c-4a64-b679-ae501e7d6091")

    # Phase 4 — Voice pipeline tuning
    tts_chunk_words: int = 5          # LLM→TTS chunk word count target
    aec_mute_on_tts: bool = True      # Mute mic during TTS playback (AEC)
    barge_in_threshold_ms: int = 200  # Time window to detect user barge-in


settings = Settings()
