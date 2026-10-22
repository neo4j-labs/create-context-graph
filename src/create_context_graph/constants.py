"""Project-wide constants: default model identifiers.

Model ids are dependencies with retirement dates and no resolver to warn you.
Every hard-coded model id in the CLI and in the generated templates resolves
through this module so that a provider retirement is a one-line change here.
Generated projects can override each default at runtime via environment
variables (``ANTHROPIC_MODEL``, ``OPENAI_MODEL``, ``GEMINI_MODEL``,
``MEMORY_LLM``, ``MEMORY_EMBEDDING``) read by ``backend/app/config.py``.
"""

from __future__ import annotations

# Anthropic: ``claude-sonnet-4-20250514`` was deprecated 2026-04-14 and retired
# 2026-06-15; Anthropic's deprecation table names ``claude-sonnet-4-6`` as the
# replacement. Used by the CLI's LLM data generation and by every
# Anthropic-backed agent template.
DEFAULT_ANTHROPIC_MODEL = "claude-sonnet-4-6"

# OpenAI: chat-completions model used by the CLI's data generation fallback.
DEFAULT_OPENAI_MODEL = "gpt-4o-mini"

# OpenAI Agents SDK: pinned explicitly because the SDK's implicit default has
# changed three times in 2026 (gpt-4.1 -> gpt-5.4-mini -> gpt-5.6-luna).
DEFAULT_OPENAI_AGENT_MODEL = "gpt-5.6-luna"

# Google: ``gemini-2.0-flash`` was shut down 2026-06-01; the deprecation table
# names ``gemini-3.6-flash`` as its replacement.
DEFAULT_GEMINI_MODEL = "gemini-3.6-flash"

# Memory layer (neo4j-agent-memory) provider strings.
DEFAULT_MEMORY_LLM_ANTHROPIC = "anthropic/claude-haiku-4-5"
DEFAULT_MEMORY_LLM_OPENAI = "openai/gpt-4o-mini"
DEFAULT_MEMORY_EMBEDDING_LOCAL = "sentence-transformers/all-MiniLM-L6-v2"
DEFAULT_MEMORY_EMBEDDING_OPENAI = "openai/text-embedding-3-small"
# Example strings shown in .env.example / docs for LiteLLM-routed providers.
EXAMPLE_MEMORY_LLM_BEDROCK = "bedrock/anthropic.claude-haiku-4-5-20251001-v1:0"
EXAMPLE_MEMORY_LLM_VERTEX = f"vertex_ai/{DEFAULT_GEMINI_MODEL}"

MODEL_DEFAULTS: dict[str, str] = {
    "anthropic": DEFAULT_ANTHROPIC_MODEL,
    "openai": DEFAULT_OPENAI_MODEL,
    "openai_agent": DEFAULT_OPENAI_AGENT_MODEL,
    "gemini": DEFAULT_GEMINI_MODEL,
    "memory_llm_anthropic": DEFAULT_MEMORY_LLM_ANTHROPIC,
    "memory_llm_openai": DEFAULT_MEMORY_LLM_OPENAI,
    "memory_embedding_local": DEFAULT_MEMORY_EMBEDDING_LOCAL,
    "memory_embedding_openai": DEFAULT_MEMORY_EMBEDDING_OPENAI,
    "memory_llm_bedrock_example": EXAMPLE_MEMORY_LLM_BEDROCK,
    "memory_llm_vertex_example": EXAMPLE_MEMORY_LLM_VERTEX,
}

# Ids that providers have retired or shut down. Nothing rendered by the CLI may
# reference these; ``tests/test_model_defaults.py`` enforces it.
RETIRED_MODEL_IDS: tuple[str, ...] = (
    "claude-sonnet-4-20250514",
    "claude-opus-4-20250514",
    "claude-3-haiku-20240307",
    "gemini-2.0-flash",
    "gemini-1.5-flash",
    "gemini-1.5-pro",
)
