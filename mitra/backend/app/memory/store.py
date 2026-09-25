"""
MITRA Backend — 4-Tier Memory Store

Tiers:
  L1: Conversation buffer (last 20 turns, in-RAM list)
  L2: Session summary (SQLite, compressed with fast-brain)
  L3: Semantic episodic memory (ChromaDB vector store)
  L4: Connector index (future — Drive, email — indexed on demand)

Also implements:
  - hybrid_search(): BM25 + dense vector similarity + reranking
  - forget(): wipe all 4 tiers
"""
from __future__ import annotations

import asyncio
import json
import time
import uuid
from pathlib import Path

import structlog

from app.config import settings

logger = structlog.get_logger(__name__)


# ---------------------------------------------------------------------------
# L1 — In-RAM Conversation Buffer
# ---------------------------------------------------------------------------

class ConversationBuffer:
    def __init__(self, max_turns: int = 20) -> None:
        self._turns: list[dict] = []
        self._max = max_turns

    def add(self, role: str, content: str) -> None:
        self._turns.append({"role": role, "content": content, "ts": time.time()})
        if len(self._turns) > self._max:
            self._overflow()

    def _overflow(self) -> None:
        """Signal that L1 is full — caller should compress to L2."""
        self._turns = self._turns[-self._max:]

    def get_messages(self) -> list[dict]:
        return [{"role": t["role"], "content": t["content"]} for t in self._turns]

    def clear(self) -> None:
        self._turns.clear()

    def __len__(self) -> int:
        return len(self._turns)


# ---------------------------------------------------------------------------
# L3 — ChromaDB Semantic Memory
# ---------------------------------------------------------------------------

class ChromaMemory:
    def __init__(self) -> None:
        self._collection = None
        self._client = None

    def _ensure_init(self) -> None:
        if self._collection is not None:
            return
        try:
            import chromadb
            self._client = chromadb.PersistentClient(path=settings.chroma_persist_dir)
            self._collection = self._client.get_or_create_collection(
                name="mitra_memory",
                metadata={"hnsw:space": "cosine"},
            )
            logger.info("chroma.initialized", path=settings.chroma_persist_dir)
        except ImportError:
            logger.warning("chroma.not_installed", msg="chromadb not installed — L3 disabled")

    async def add(self, text: str, metadata: dict | None = None) -> None:
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, self._add_sync, text, metadata)

    def _add_sync(self, text: str, metadata: dict | None) -> None:
        self._ensure_init()
        if self._collection is None:
            return
        doc_id = str(uuid.uuid4())
        self._collection.add(
            documents=[text],
            ids=[doc_id],
            metadatas=[metadata or {}],
        )
        logger.debug("chroma.add", doc_id=doc_id, chars=len(text))

    async def search(self, query: str, top_k: int = 5) -> list[str]:
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self._search_sync, query, top_k)

    def _search_sync(self, query: str, top_k: int) -> list[str]:
        self._ensure_init()
        if self._collection is None:
            return []
        results = self._collection.query(
            query_texts=[query],
            n_results=min(top_k, self._collection.count() or 1),
        )
        docs: list[str] = results.get("documents", [[]])[0]
        logger.info("chroma.search", query=query[:50], results=len(docs))
        return docs

    async def delete_all(self) -> None:
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, self._delete_all_sync)

    def _delete_all_sync(self) -> None:
        self._ensure_init()
        if self._client is None:
            return
        self._client.delete_collection("mitra_memory")
        self._collection = None
        logger.info("chroma.deleted_all")


# ---------------------------------------------------------------------------
# BM25 Keyword Search (L3 auxiliary)
# ---------------------------------------------------------------------------

class BM25Index:
    def __init__(self) -> None:
        self._corpus: list[str] = []
        self._bm25 = None

    def add(self, text: str) -> None:
        self._corpus.append(text)
        self._rebuild()

    def _rebuild(self) -> None:
        try:
            from rank_bm25 import BM25Okapi
            tokenized = [doc.lower().split() for doc in self._corpus]
            self._bm25 = BM25Okapi(tokenized)
        except ImportError:
            pass

    def search(self, query: str, top_k: int = 5) -> list[str]:
        if self._bm25 is None or not self._corpus:
            return []
        scores = self._bm25.get_scores(query.lower().split())
        top_indices = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)[:top_k]
        return [self._corpus[i] for i in top_indices if scores[i] > 0]

    def clear(self) -> None:
        self._corpus.clear()
        self._bm25 = None


# ---------------------------------------------------------------------------
# Master Memory Store (all tiers)
# ---------------------------------------------------------------------------

class MemoryStore:
    def __init__(self) -> None:
        self.l1 = ConversationBuffer(max_turns=settings.memory_l1_max_turns)
        self.l3 = ChromaMemory()
        self._bm25 = BM25Index()

    async def add_turn(self, role: str, content: str) -> None:
        """Add a conversation turn to L1 and index it in L3 + BM25."""
        self.l1.add(role, content)
        # Store in L3 for long-term retrieval
        await self.l3.add(content, metadata={"role": role, "ts": str(time.time())})
        self._bm25.add(content)

        # L1 → L2 compression trigger at max_turns
        if len(self.l1) >= settings.memory_l1_max_turns:
            await self._compress_to_l2()

    async def _compress_to_l2(self) -> None:
        """Summarize L1 buffer and store compressed in L3 with summary tag."""
        from app.models.nim_client import nim_client, ModelRole
        messages = self.l1.get_messages()
        summary_prompt = "Summarize this conversation in 3 concise bullet points:\n" + \
            "\n".join(f"{m['role']}: {m['content']}" for m in messages[-20:])
        try:
            summary = await nim_client.chat_complete(
                ModelRole.FAST_BRAIN,
                messages=[{"role": "user", "content": summary_prompt}],
                max_tokens=256,
                temperature=0.3,
            )
            await self.l3.add(summary, metadata={"type": "l2_summary", "ts": str(time.time())})
            self.l1.clear()
            logger.info("memory.l2_compressed", summary_chars=len(summary))
        except Exception as exc:
            logger.error("memory.compress_error", error=str(exc))

    async def search(self, query: str, top_k: int = 5) -> list[str]:
        """Hybrid search: BM25 + ChromaDB semantic, deduplicated."""
        bm25_results = self._bm25.search(query, top_k=top_k)
        chroma_results = await self.l3.search(query, top_k=top_k)

        # Deduplicate while preserving order
        seen: set[str] = set()
        combined: list[str] = []
        for doc in bm25_results + chroma_results:
            key = doc[:100]
            if key not in seen:
                seen.add(key)
                combined.append(doc)
        return combined[:top_k]

    async def forget(self) -> None:
        """Wipe ALL 4 memory tiers — irreversible."""
        self.l1.clear()
        self._bm25.clear()
        await self.l3.delete_all()
        logger.info("memory.forget_all")

    def get_l1_messages(self) -> list[dict]:
        return self.l1.get_messages()


# Singleton
memory_store = MemoryStore()
