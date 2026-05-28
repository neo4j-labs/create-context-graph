---
title: Configure Memory Providers (LiteLLM)
slug: /how-to/configure-memory-providers
---

# Configure Memory Providers (LiteLLM)

The generated memory layer (entity extraction + embeddings) accepts [LiteLLM](https://docs.litellm.ai/)-style provider strings via two env vars. Native adapters are resolved first; everything else routes through LiteLLM, giving you access to 100+ providers without code changes.

## The two env vars

```bash
# In .env
MEMORY_LLM=anthropic/claude-haiku-4-5
MEMORY_EMBEDDING=sentence-transformers/all-MiniLM-L6-v2
```

| Variable | Used for | Default fallback |
|---|---|---|
| `MEMORY_LLM` | Entity extraction from chat messages | `anthropic/claude-haiku-4-5` if `ANTHROPIC_API_KEY` is set → `openai/gpt-4o-mini` if `OPENAI_API_KEY` is set → `None` (extraction disabled with logged warning) |
| `MEMORY_EMBEDDING` | Vector embeddings for memory search | `sentence-transformers/all-MiniLM-L6-v2` (local, no API key needed) |

These are **memory-layer** providers — they're separate from the agent's LLM. Your agent framework (Strands, PydanticAI, Claude Agent SDK, …) has its own model configuration via `ANTHROPIC_API_KEY` / `OPENAI_API_KEY` / `GOOGLE_API_KEY`.

## Provider strings — native adapters

These resolve to native SDK calls (lower latency, prompt-caching where supported):

| Provider | LLM example | Embedding example |
|---|---|---|
| Anthropic | `anthropic/claude-haiku-4-5` | _(no embeddings)_ |
| OpenAI | `openai/gpt-4o-mini` | `openai/text-embedding-3-small` |
| AWS Bedrock | `bedrock/anthropic.claude-3-haiku-20240307-v1:0` | _(via LiteLLM)_ |
| Google Vertex AI | `vertex_ai/gemini-1.5-flash` | `vertex_ai/text-embedding-005` |
| SentenceTransformers (local) | _(N/A for LLM)_ | `sentence-transformers/all-MiniLM-L6-v2` |

## Provider strings — anything else via LiteLLM

If the provider isn't natively supported, the library routes the call through LiteLLM. Examples:

| Provider | Example |
|---|---|
| Ollama (local) | `ollama/llama3` |
| Groq | `groq/llama-3.1-70b-versatile` |
| Together AI | `together_ai/meta-llama/Llama-3-70b-chat-hf` |
| Mistral | `mistral/mistral-large-latest` |
| OpenRouter | `openrouter/anthropic/claude-3.5-sonnet` |
| Voyage | `voyage/voyage-3` |
| Cohere | `cohere/command-r-plus` |

Full provider list: [LiteLLM providers](https://docs.litellm.ai/docs/providers).

## Default fallback behavior (no env vars set)

If neither `MEMORY_LLM` nor `MEMORY_EMBEDDING` is set, the memory layer:

1. **Embeddings:** uses `sentence-transformers/all-MiniLM-L6-v2` (local, ~80 MB on first download). No API key required. Works offline.
2. **LLM (for entity extraction):**
   - If `ANTHROPIC_API_KEY` is set, defaults to `anthropic/claude-haiku-4-5`.
   - Else if `OPENAI_API_KEY` is set, defaults to `openai/gpt-4o-mini`.
   - Else extraction is disabled and a warning is logged.

This means a fresh scaffold works out of the box with just `ANTHROPIC_API_KEY` — no need to think about provider strings unless you want a different model.

## Provider-specific authentication

LiteLLM picks up provider credentials from standard env vars:

```bash
# Anthropic
ANTHROPIC_API_KEY=sk-ant-...

# OpenAI
OPENAI_API_KEY=sk-...

# AWS Bedrock (needs AWS creds)
AWS_ACCESS_KEY_ID=...
AWS_SECRET_ACCESS_KEY=...
AWS_REGION_NAME=us-east-1

# Google Vertex AI
GOOGLE_APPLICATION_CREDENTIALS=/path/to/service-account.json

# Groq
GROQ_API_KEY=gsk_...

# Ollama (assumes local ollama running on default port)
# No key needed
```

## Examples

### Use Ollama for both LLM and embeddings (fully local)

```bash
MEMORY_LLM=ollama/llama3
MEMORY_EMBEDDING=ollama/nomic-embed-text
```

### Use Bedrock for LLM, sentence-transformers for embeddings

```bash
MEMORY_LLM=bedrock/anthropic.claude-3-haiku-20240307-v1:0
MEMORY_EMBEDDING=sentence-transformers/all-MiniLM-L6-v2
AWS_ACCESS_KEY_ID=...
AWS_SECRET_ACCESS_KEY=...
AWS_REGION_NAME=us-east-1
```

### Use OpenAI embeddings (higher quality, paid)

```bash
MEMORY_EMBEDDING=openai/text-embedding-3-small
OPENAI_API_KEY=sk-...
# MEMORY_LLM left unset — falls back to Anthropic
```

## Where this gets applied

The provider strings are read by the generated `backend/app/memory.py`:

```python
# Simplified excerpt
from neo4j_agent_memory import MemorySettings

settings = MemorySettings(
    backend=...,
    llm=os.getenv("MEMORY_LLM"),          # → from_provider() internally
    embedding=os.getenv("MEMORY_EMBEDDING"),
)
```

The library's `from_provider()` factory handles the string → adapter mapping. See the [neo4j-agent-memory provider docs](https://github.com/neo4j-labs/agent-memory) for the full resolution algorithm.

## Troubleshooting

| Problem | Solution |
|---------|----------|
| Embedding download stalls on first run | First-time sentence-transformers model fetch is ~80 MB. Subsequent runs are cached. |
| `ProviderNotFoundError: anthropic/claude-xyz` | Provider string is wrong. Check [LiteLLM providers](https://docs.litellm.ai/docs/providers) for the correct identifier. |
| Memory layer makes no LLM calls | Verify the relevant API key env var is set. The default fallback only kicks in if `ANTHROPIC_API_KEY` or `OPENAI_API_KEY` is present. |
| Vector dimension mismatch on switch | If you change `MEMORY_EMBEDDING` to a different-dimension model, existing vector data is incompatible. Use `make reset` and re-ingest, or scope the change to new sessions only. |

## Further Reading

- [Memory Backends](/docs/explanation/memory-backends) — NAMS vs self-hosted
- [Use NAMS](/docs/how-to/use-nams) — hosted backend setup
- [LiteLLM docs](https://docs.litellm.ai/) — full provider catalog and auth details
