---
sidebar_position: 3
title: Switch Agent Frameworks
slug: switch-frameworks
---

# Switch Agent Frameworks

Create Context Graph supports 8 agent frameworks. The framework choice only affects `backend/app/agent.py` in the generated project -- everything else (FastAPI backend, Neo4j client, frontend, data) stays the same.

## Supported Frameworks

| Framework | Key | Description | Streaming |
|-----------|-----|-------------|-----------|
| **PydanticAI** | `pydanticai` | Type-safe agents with `@agent.tool` decorators and dependency injection via `RunContext` | Full |
| **Claude Agent SDK** | `claude-agent-sdk` | Anthropic's SDK with dict-based tool definitions and a bounded agentic loop (max 15 iterations) | Full |
| **OpenAI Agents SDK** | `openai-agents` | OpenAI's agent framework with `@function_tool` decorators and `Runner.run()` | Full |
| **LangGraph** | `langgraph` | LangChain's graph-based agent runtime with `@tool` and `create_react_agent()` | Full |
| **CrewAI** | `crewai` | Multi-agent framework with `Agent`, `Task`, and `Crew` abstractions (uses Anthropic LLM, thread-safe async bridging) | Full |
| **Strands** | `strands` | Agent framework using Anthropic models with `@tool` decorators (thread-safe async bridging) | Full |
| **Google ADK** | `google-adk` | Google's Agent Development Kit with `FunctionTool` and Gemini models (requires `GOOGLE_API_KEY`) | Full |
| **Anthropic Tools** | `anthropic-tools` | Modular agent framework with `@register_tool` registry and bounded Anthropic API agentic loop (max 15 iterations) | Full |

**Streaming column:** "Full" means token-by-token text streaming + real-time tool call events. All frameworks use the same SSE (Server-Sent Events) protocol; CrewAI and Strands run synchronously in a worker thread but stream both text and tool events via framework-specific hooks (`LLMStreamChunkEvent` and `agent.stream_async()`).

## Choosing a Framework During Scaffolding

### Interactive wizard

Run the CLI and select your framework at the relevant step:

```bash
create-context-graph my-app
```

### CLI flag

```bash
create-context-graph my-app --domain healthcare --framework langgraph
```

## Generating with a Different Framework

To create a second project with a different framework, re-run the CLI with a new output directory and `--framework` flag:

```bash
create-context-graph my-app-v2 --domain healthcare --framework crewai
```

The two projects will share the same schema, data, and frontend -- only `agent.py` and the agent-specific dependencies differ.

## What Changes

Only one file varies between frameworks: **`backend/app/agent.py`**. This file contains:

- The agent initialization and model configuration
- Tool definitions generated from your domain's `agent_tools` ontology
- The `handle_message()` async function that the FastAPI routes call
- The `handle_message_stream()` async function for SSE text streaming (all 8 frameworks)

Each framework template uses the framework's idiomatic patterns (decorators, classes, registries) but exposes the same interface.

## What Stays the Same

Regardless of which framework you choose, the generated project always includes:

- **FastAPI backend** (`main.py`, `config.py`, `routes.py`, `models.py`) -- identical across frameworks
- **Neo4j clients** (`context_graph_client.py`, `gds_client.py`, `vector_client.py`) -- shared graph access layer
- **Frontend** (Next.js + Chakra UI v3 + NVL graph visualization) -- framework-agnostic
- **Data and schema** (`cypher/schema.cypher`, fixture data, ontology YAML)
- **Infrastructure** (`docker-compose.yml`, `Makefile`, `.env`)

## Framework-Specific Dependencies

The generated `backend/pyproject.toml` includes only the dependencies needed for the chosen framework. For example:

- `pydanticai` adds `pydantic-ai`
- `langgraph` adds `langgraph`, `langchain-core`, `langchain-anthropic`
- `strands` adds `strands-agents`, `strands-agents-builder`, and configures Bedrock
- `google-adk` adds `google-adk`, `google-generativeai`

All frameworks share common dependencies: `fastapi`, `uvicorn`, `neo4j`, `pydantic`, and `python-dotenv`.

## Further Reading

- [Framework Comparison](/docs/reference/framework-comparison) -- detailed comparison table with performance notes
- [CLI Options](/docs/reference/cli-options) -- all `--framework` and API key flags
- [Generated Project Structure](/docs/reference/generated-project-structure) -- what each file in the generated project does
