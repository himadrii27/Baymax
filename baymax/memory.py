"""
memory.py — Mem0 wrapper for persistent semantic memory.

Mem0 automatically:
  - Extracts facts from conversations using LLM
  - Deduplicates + updates existing memories
  - Stores as vectors in Supabase pgvector
  - Ranks by relevance on retrieval
"""
from __future__ import annotations
import os
import warnings
warnings.filterwarnings("ignore", category=DeprecationWarning)
from mem0 import Memory

USER_ID = "baymax_user"

_mem: Memory | None = None


def _get_mem() -> Memory | None:
    global _mem
    if _mem is None:
        # Use mem0 cloud if API key is set — no DB password needed
        mem0_api_key = os.environ.get("MEM0_API_KEY", "").strip()
        if mem0_api_key:
            try:
                from mem0 import MemoryClient
                _mem = MemoryClient(api_key=mem0_api_key)
                return _mem
            except Exception as e:
                pass  # fall through to self-hosted

        # Fallback: self-hosted with Supabase pgvector
        config = {
            "llm": {
                "provider": "gemini",
                "config": {
                    "model": "gemini-2.5-flash",
                    "api_key": os.environ["GEMINI_API_KEY"],
                },
            },
            "embedder": {
                "provider": "gemini",
                "config": {
                    "model": "models/text-embedding-004",
                    "api_key": os.environ["GEMINI_API_KEY"],
                },
            },
            "vector_store": {
                "provider": "supabase",
                "config": {
                    "connection_string": os.environ["SUPABASE_DB_URL"],
                    "collection_name": "baymax_memories",
                },
            },
        }
        try:
            _mem = Memory.from_config(config)
        except Exception as e:
            pass
            _mem = None
    return _mem


def search(query: str, limit: int = 5, user_id: str = USER_ID) -> list[dict]:
    """Retrieve top-k memories relevant to the query."""
    mem = _get_mem()
    if mem is None:
        return []
    try:
        from mem0 import MemoryClient
        if isinstance(mem, MemoryClient):
            results = mem.search(query, user_id=user_id, filters={"user_id": user_id})
        else:
            results = mem.search(query, user_id=user_id, limit=limit)
        return results.get("results", [])
    except Exception:
        return []


def add_from_messages(messages: list[dict], user_id: str = USER_ID) -> None:
    """Extract and store facts from a conversation exchange."""
    mem = _get_mem()
    if mem is None:
        return
    try:
        mem.add(messages, user_id=user_id)
    except Exception:
        pass


def add_explicit(fact: str, user_id: str = USER_ID) -> None:
    """Explicitly store a fact the user said to remember."""
    mem = _get_mem()
    if mem is None:
        return
    try:
        mem.add(fact, user_id=user_id)
    except Exception:
        pass


def list_all(limit: int = 50, user_id: str = USER_ID) -> list[dict]:
    """List all stored memories."""
    mem = _get_mem()
    if mem is None:
        return []
    try:
        results = mem.get_all(user_id=user_id)
        return results.get("results", [])[:limit]
    except Exception:
        return []


def forget(memory_id: str) -> None:
    """Delete a specific memory by ID."""
    mem = _get_mem()
    if mem is None:
        return
    try:
        mem.delete(memory_id)
    except Exception:
        pass


def format_for_prompt(memories: list[dict]) -> str:
    """Format memory results into a prompt-ready string."""
    if not memories:
        return "No specific memories retrieved."
    lines = []
    for m in memories:
        score = m.get("score", 0)
        text = m.get("memory", "")
        lines.append(f"- {text} (relevance: {score:.2f})")
    return "\n".join(lines)
