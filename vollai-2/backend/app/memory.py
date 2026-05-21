"""Memory integration — powered by neo4j-agent-memory v0.1.0.

Provides MemoryIntegration for conversation memory with automatic
entity extraction and preference detection.
"""

from __future__ import annotations

import logging
import uuid

from app.config import settings

logger = logging.getLogger(__name__)

_memory = None  # MemoryIntegration | None


async def connect_memory() -> None:
    """Initialize MemoryIntegration. No-ops if package unavailable."""
    global _memory
    try:
        from neo4j_agent_memory import MemoryIntegration, SessionStrategy

        strategy_map = {
            "per_conversation": SessionStrategy.PER_CONVERSATION,
            "per_day": SessionStrategy.PER_DAY,
            "persistent": SessionStrategy.PERSISTENT,
        }
        _memory = MemoryIntegration(
            neo4j_uri=settings.neo4j_uri,
            neo4j_password=settings.neo4j_password,
            neo4j_user=settings.neo4j_username,
            session_strategy=strategy_map.get(
                settings.session_strategy, SessionStrategy.PER_CONVERSATION
            ),
            auto_extract=True,
            auto_preferences=True,
        )
        await _memory.connect()
        logger.info(
            "MemoryIntegration connected (strategy=%s, extract=%s, preferences=%s)",
            settings.session_strategy,
            True,
            True,
        )
    except ImportError:
        logger.info("neo4j-agent-memory not installed — memory disabled")
        _memory = None
    except Exception as e:
        logger.warning("MemoryIntegration init failed: %s", e)
        _memory = None


async def close_memory() -> None:
    """Shut down MemoryIntegration gracefully."""
    global _memory
    if _memory is not None:
        try:
            await _memory.close()
        except Exception:
            pass
        _memory = None


def get_memory():
    """Get the MemoryIntegration instance (may be None)."""
    return _memory


async def store_message(
    session_id: str, role: str, content: str
) -> dict | None:
    """Store a message and return extraction results (entities, preferences).

    Returns None if memory is unavailable.
    """
    if _memory is None:
        return None
    try:
        result = await _memory.store_message(role, content, session_id=session_id)
        return result
    except Exception as e:
        logger.warning("Failed to store message: %s", e)
        return None


async def get_context(
    session_id: str, query: str | None = None, max_items: int = 10
) -> dict:
    """Get rich context for a session.

    Returns a dict with keys: messages, entities, preferences, traces.
    Falls back to empty lists if memory is unavailable.
    """
    empty = {"messages": [], "entities": [], "preferences": [], "traces": []}
    if _memory is None:
        return empty
    try:
        return await _memory.get_context(
            session_id=session_id, query=query, max_items=max_items
        )
    except Exception as e:
        logger.warning("Failed to get context: %s", e)
        return empty


def resolve_session_id(hint: str | None = None) -> str:
    """Resolve session ID based on configured strategy."""
    if _memory is None:
        return hint or str(uuid.uuid4())
    return _memory.resolve_session_id(hint=hint)
