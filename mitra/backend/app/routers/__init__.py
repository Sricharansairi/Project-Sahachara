"""routers package — Phase 5 connectors and intelligence added."""
from app.routers.chat import router as chat_router
from app.routers.tools import router as tools_router
from app.routers.webhooks import router as webhooks_router
from app.routers.voice import router as voice_router
from app.routers.tts import router as tts_router
from app.routers.pipeline import router as pipeline_router
from app.routers.connectors import router as connectors_router
from app.routers.intelligence import router as intelligence_router

__all__ = [
    "chat_router",
    "tools_router",
    "webhooks_router",
    "voice_router",
    "tts_router",
    "pipeline_router",
    "connectors_router",
    "intelligence_router",
]
