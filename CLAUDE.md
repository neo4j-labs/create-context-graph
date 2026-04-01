# CLAUDE.md — Create Context Graph

## Project Overview

Interactive CLI scaffolding tool that generates domain-specific context graph applications. Like `create-next-app` but for AI agents with graph memory. Invoked via `uvx create-context-graph` or `npx create-context-graph`.

Given a domain (e.g., "healthcare", "wildlife-management") and an agent framework (e.g., PydanticAI, Claude Agent SDK), it generates a complete full-stack application: FastAPI backend, Next.js + Chakra UI v3 + NVL frontend, Neo4j schema, synthetic data, and a configured AI agent with domain-specific tools.

**Status:** v0.7.1 in progress. 22 domains, 8 agent frameworks (7 working out of box — openai-agents requires OPENAI_API_KEY, google-adk requires GOOGLE_API_KEY with clear warnings), **streaming chat via Server-Sent Events** (token-by-token text in 6 frameworks + real-time tool call visualization with Timeline/Spinner/Collapsible), neo4j-agent-memory integration for multi-turn conversations (local sentence-transformers embeddings by default — no OpenAI key required; auto-upgrades to OpenAI embeddings if OPENAI_API_KEY is set), interactive NVL graph visualization (schema view, double-click expand, drag/zoom, property panel, agent-driven graph updates — now updated incrementally during streaming, node hover tooltips, "Ask about this" button), LLM-generated demo data (80-90 entities, 25+ documents, 8-12 decision traces per domain) with post-generation value clamping for 28 property types, markdown rendering in chat and document browser with ReactMarkdown, document browser with pagination, entity detail panel, decision trace viewer, 8 SaaS connectors (including Linear for real project data import), custom domain generation, Neo4j Aura .env import + neo4j-local support, Docusaurus documentation site (18 pages including quick-start, domain catalog, framework comparison, Neo4j Aura/Local guides, Docker guide, architecture diagram, and "Why Context Graphs?" explainer), graceful Neo4j degradation with /health endpoint (retry with backoff on initial load) and 503 guards on all endpoints, Cypher injection prevention, enum identifier sanitization, configurable CORS/model/timeouts, --dry-run/--verbose/--reset-database/--demo CLI flags, CLI auto-slug generation (PROJECT_NAME optional in non-interactive mode), CLI warnings for framework-specific API key requirements (openai-agents, google-adk), constants module, WCAG accessibility improvements, chat timeout/cancel with AbortController, mobile-responsive layout, .dockerignore for Docker builds, `make test-connection` target, framework-specific README sections, troubleshooting guide, thread-safe async bridging for sync frameworks (CrewAI/Strands), bounded agentic loops (max 15 iterations), domain-specific static name pools (1000+ names across 118 entity labels — all domain YAML labels covered) with domain-aware base entities, tool-use emphasis in all agent system prompts, domain-scoped chat history localStorage keys, SSR hydration fix, retry button on chat errors, PydanticAI tool serialization fix (JSON string return types), Google ADK API key support (--google-api-key flag) with AttributeError guard for SDK cleanup, Strands robust text extraction, CrewAI explicit Anthropic LLM config with `crewai[anthropic]` dependency, domain-scoped MERGE keys (`{name, domain}`) for cross-domain isolation when sharing a Neo4j instance, improved static data quality (22 domain-specific industry pools, POLE-type-aware entity descriptions with 5 label categories + 7 label-specific overrides, entity-derived document titles, realistic decision trace observations, 20+ domain-specific property pools, float value clamping, taxonomy class correction), agent thinking text collapsible filter with continuation pattern support, Cypher query validation tests across all domains, fixture cross-validation tests (schema alignment + data quality), proper Document/DecisionTrace node ingestion via --ingest, Chakra UI Pro-inspired chat input redesign, list/get-by-id agent tools for all 22 domains (7-8+ tools per domain), ON CREATE/MATCH SET for constraint-safe seeding, 705 passing tests.

## Quick Reference

```bash
# Setup
uv venv && uv pip install -e ".[dev]"

# Run tests
source .venv/bin/activate && pytest tests/ -v

# Test scaffold generation
create-context-graph my-app --domain financial-services --framework pydanticai --demo-data

# List available domains
create-context-graph --list-domains
```

## Architecture

```
src/create_context_graph/
├── cli.py              # Click CLI entry point (interactive + flag modes)
├── wizard.py           # 7-step Questionary interactive wizard
├── config.py           # ProjectConfig Pydantic model
├── ontology.py         # YAML domain ontology loader, validation, code generation
├── custom_domain.py    # LLM-powered custom domain YAML generation
├── renderer.py         # Jinja2 template engine (renders project scaffold)
├── generator.py        # LLM-powered synthetic data pipeline (4 stages)
├── name_pools.py       # Realistic name pools and value generators for static fallback
├── ingest.py           # Neo4j ingestion via neo4j-agent-memory or direct driver
├── neo4j_validator.py  # Neo4j connection testing
├── connectors/         # SaaS data connectors (7 services)
│   ├── __init__.py     # BaseConnector ABC, NormalizedData model, registry
│   ├── github_connector.py
│   ├── notion_connector.py
│   ├── jira_connector.py
│   ├── slack_connector.py
│   ├── gmail_connector.py   # Prefers gws CLI, falls back to Python OAuth2
│   ├── gcal_connector.py    # Prefers gws CLI, falls back to Python OAuth2
│   ├── salesforce_connector.py
│   └── oauth.py        # Shared OAuth2 flow + gws CLI helpers
├── domains/            # 22 YAML ontology definitions + _base.yaml
├── fixtures/           # 22 pre-generated JSON fixture files
└── templates/          # Jinja2 templates for generated projects
    ├── base/           # .env, .env.example, Makefile, docker-compose, README, .gitignore
    ├── backend/
    │   ├── shared/     # FastAPI main, config, neo4j client, GDS, vector, models, routes
    │   ├── agents/     # Per-framework agent.py (8 frameworks)
    │   └── connectors/ # Generated connector modules + import_data.py
    ├── frontend/       # Next.js + Chakra UI v3 + NVL components
    └── cypher/         # Schema constraints + GDS projections
```

## Key Design Decisions

### Templates are domain-agnostic, data-driven
No per-domain template directories. The ontology YAML drives all domain customization via Jinja2 context variables. Only `backend/agents/{framework}/agent.py.j2` varies by framework — everything else is shared.

### Jinja2 + JSX/Python escaping
Templates that contain JSX curly braces or Python dict literals must use `{% raw %}...{% endraw %}` blocks to avoid conflicts with Jinja2's `{{ }}` syntax. Break out of raw mode only for actual Jinja2 substitutions:
```
{% raw %}JSX code with {curly} braces{% endraw %}{{ jinja_var }}{% raw %}more JSX{% endraw %}
```

### Two-layer ontology inheritance
`_base.yaml` defines shared POLE+O entity types (Person, Organization, Location, Event, Object). Domain YAMLs declare `inherits: _base` and add domain-specific entity types. The `ontology.py` loader merges base entities/relationships into each domain.

### Rich fixture data pipeline
- **Pre-generated fixtures** (shipped): All 22 domains ship with high-quality LLM-generated fixture data (80-90 entities, 160-280 relationships, 25+ documents at 200-1600 words, 3-5 decision traces with multi-step reasoning). Generated via `scripts/regenerate_fixtures.py` using Claude API.
- **Static fallback** (no LLM key at runtime): Uses domain-specific name pools (`name_pools.py`) with 1000+ names across 118 entity labels (all domain YAML labels covered — no more fallback to generic "Label 1" names), label-aware ID prefixes (PAT- for Patient, ACT- for Account), contextual property generators (emails from names, realistic IDs, domain-appropriate ranges), 22 domain-specific industry pools (`DOMAIN_INDUSTRY_POOL`), POLE-type-aware entity descriptions (`_generate_description` with 5 label categories: `_PERSON_LABELS`, `_ORGANIZATION_LABELS`, `_LOCATION_LABELS`, `_EVENT_LABELS`, `_OBJECT_LABELS` + 7 label-specific override templates), entity-derived document titles (reference primary entities instead of sequential numbers), Markdown-formatted document content, 12+ domain-specific property pools (currency codes, ticker symbols, drug classes, medical specialties, severities, etc.), float clamping for confidence/rating/efficiency fields, and realistic decision trace observations (reference entity names).
- **Post-generation validation** (`_validate_and_clamp()` in `generator.py`): LLM-generated entities are post-processed to clamp unrealistic numeric values (28 property range rules) and fix taxonomy class mismatches (species → correct class mapping).
- **LLM-powered** (with `--anthropic-api-key` at runtime): Generates realistic entities, documents, and decision traces via Anthropic or OpenAI APIs.
- **Data seeding** (`make seed`): Loads all four data types into Neo4j — entities, relationships, documents (as `:Document` nodes with `:MENTIONS` links to entities), and decision traces (as `:DecisionTrace` → `:HAS_STEP` → `:TraceStep` chains).

### Dual ingestion backends
`ingest.py` tries `neo4j-agent-memory` MemoryClient first, falls back to direct `neo4j` driver if the package isn't installed. Both paths create entities via MemoryClient or direct Cypher, plus create `:Document` and `:DecisionTrace`/`:TraceStep` nodes using direct Cypher (matching the `generate_data.py.j2` schema the frontend queries expect). Both paths tag all entities with a `domain` property for cross-domain isolation when sharing a Neo4j instance.

### Custom domain generation
`custom_domain.py` generates complete domain ontology YAMLs from natural language descriptions using LLM (Anthropic/OpenAI). Uses `_base.yaml` + 2 reference domain YAMLs as few-shot examples. Validates output against `DomainOntology` Pydantic model with retry loop (up to 3 attempts). Generated domains can be saved to `~/.create-context-graph/custom-domains/` for reuse.

### Streaming chat via Server-Sent Events (SSE)
The chat uses a streaming architecture where the backend emits SSE events as the agent executes. The `POST /chat/stream` endpoint creates an `asyncio.Queue` on the `CypherResultCollector` and launches the agent in a background task. As tools execute, the collector emits `tool_start` and `tool_end` events (with graph data). For frameworks that support it (PydanticAI, Anthropic Tools, Claude Agent SDK, OpenAI Agents, LangGraph), `text_delta` events stream tokens as they arrive. Other frameworks (CrewAI, Strands, Google ADK) emit tool events in real-time with text arriving at the end. The frontend parses SSE via `fetch` + `ReadableStream` (not `EventSource`, which only supports GET). Tool calls render as a Chakra UI `Timeline` with live `Spinner` indicators. Text deltas are batched (~50ms) before updating ReactMarkdown to avoid excessive re-renders. Graph visualization updates incrementally after each `tool_end` event. The original `/chat` endpoint is preserved for backward compatibility. The SSE endpoint has a 120s per-event idle timeout and a 300s overall timeout.

### Thread-safe async bridging for sync frameworks
CrewAI and Strands are synchronous frameworks that run in worker threads via `asyncio.to_thread()`. Their tools need to call async `execute_cypher()`. The `_run_sync()` helper uses `asyncio.run_coroutine_threadsafe()` to schedule coroutines on the main event loop (captured via `_capture_loop()` before `to_thread`), with a 30s timeout. The `CypherResultCollector._push_event()` is also thread-safe — it detects worker threads and uses `loop.call_soon_threadsafe()` instead of direct `put_nowait()`. Google ADK uses `nest_asyncio` for same-thread reentrant calls with a cross-thread `run_coroutine_threadsafe` fallback.

### Bounded agentic loops
Claude Agent SDK and Anthropic Tools use agentic `while` loops that process tool calls until the model stops. These loops are bounded to 15 iterations (`for _iteration in range(max_iterations)`) with a 60s timeout on each API call. If max iterations is exceeded, a fallback message is returned instead of hanging indefinitely.

### Tool-use emphasis in system prompts
All 8 agent templates append a tool-use emphasis suffix to the domain system prompt: "IMPORTANT: You MUST use the available tools to query the knowledge graph before answering any question about the data." This ensures agents consistently invoke their tools rather than generating ungrounded answers.

### Agent tool return type convention
All agent tools must return `str` (JSON-serialized via `json.dumps(result, default=str)`), not raw `list[dict]`. PydanticAI, CrewAI, Strands, Google ADK, and other frameworks need to serialize tool outputs to send them back to the LLM. Raw Neo4j Node/Relationship objects cause silent serialization failures. The `default=str` handler ensures Neo4j-specific types (datetime, spatial) serialize correctly.

### Agent thinking text filter
The frontend `ChatInterface` includes a `splitThinkingAndResponse()` function that detects agent "thinking" patterns (lines starting with "Let me", "I'll", "First, I need to", etc.) and renders them in a collapsible "Show reasoning" section. `CONTINUATION_PATTERNS` catch multi-sentence thinking blocks (lines starting with "and", "also", "then", "so", "because", etc.) that follow an initial thinking line. Lines with markdown formatting (`#`, `-`, `*`, `|`) break out of thinking mode. This keeps the primary response focused while making the full reasoning chain available on demand.

### Interactive graph visualization with agent integration
The frontend `ContextGraphView` starts in **schema view** (calls `db.schema.visualization()` via `GET /schema/visualization`) showing entity types as nodes and relationship types as edges. When the user interacts with the agent chat, tool call results flow to the graph automatically via the `CypherResultCollector` in `context_graph_client.py`. In streaming mode, graph data arrives incrementally with each `tool_end` SSE event — the `ChatInterface` calls `onGraphUpdate` for each tool completion, so the graph updates as each tool finishes rather than all at once. The `page.tsx` passes data to `ContextGraphView` as `externalGraphData`. Double-clicking a schema node loads instances of that label; double-clicking a data node calls `POST /expand` to fetch neighbors (deduplicated merge). NVL uses d3Force layout with drag/zoom/pan, click for property details, and canvas click to deselect. Nodes have hover tooltips showing full name, labels, and top 5 properties. Clicking a node reveals an "Ask about [entity]" button that sends a chat query via the `onAskAbout` → `externalInput` → `ChatInterface` callback chain.

### neo4j-agent-memory integration
Generated projects use `MemoryClient` from `neo4j-agent-memory` for multi-turn conversation persistence. The `context_graph_client.py.j2` template initializes the MemoryClient alongside the Neo4j driver (with ImportError fallback) and exposes `get_conversation_history()` and `store_message()`. The embedding provider is configured automatically: if `OPENAI_API_KEY` is set, uses OpenAI `text-embedding-3-small` (1536 dims); otherwise defaults to local `sentence-transformers` with `all-MiniLM-L6-v2` (384 dims). The generated `pyproject.toml` includes `neo4j-agent-memory[spacy,gliner]` (without `[openai]` extra) plus `sentence-transformers>=2.0` so local embeddings work out of the box with no API key. All 8 agent frameworks call these to retrieve history before each LLM call and store messages after. The frontend `ChatInterface` captures `session_id` from the first response and sends it in all subsequent requests.

### Neo4j driver serialization
`context_graph_client.py.j2` uses a custom `_serialize()` function instead of the driver's `.data()` method. This preserves Neo4j Node metadata (`elementId`, `labels`), Relationship metadata (`elementId`, `type`, `startNodeElementId`, `endNodeElementId`), and Path expansion. Without this, the frontend graph visualization and agent tools receive flat property dicts with no type information.

### SaaS connectors
`connectors/` package with 8 service connectors (GitHub, Notion, Jira, Slack, Gmail, Google Calendar, Salesforce, Linear). Each connector implements `BaseConnector` ABC with `authenticate()`, `fetch()`, and `get_credential_prompts()` methods. Returns `NormalizedData` matching the fixture schema so `ingest.py` works unchanged. Gmail/Google Calendar prefer the Google Workspace CLI (`gws`) if available, with Python OAuth2 fallback. The Linear connector uses GraphQL with cursor-based pagination and rate limiting against `https://api.linear.app/graphql`, mapping issues, projects, cycles, teams, users, labels, and workflow states to the POLE+O entity model with 16 relationship types. Connectors run at scaffold time AND are generated into the project with `make import` / `make import-and-seed` targets.

## Domain Ontology YAML Schema

Each domain YAML file must contain:
- `inherits: _base` — merge base POLE+O types
- `domain:` — id, name, description, tagline, emoji
- `entity_types:` — label, pole_type (PERSON/ORGANIZATION/LOCATION/EVENT/OBJECT), subtype, color (hex), icon, properties (name, type, required, unique, enum)
- `relationships:` — type, source, target
- `document_templates:` — id, name, description, count, prompt_template, required_entities
- `decision_traces:` — id, task, steps (thought/action), outcome_template
- `demo_scenarios:` — name, prompts list
- `agent_tools:` — name, description, cypher query, parameters
- `system_prompt:` — multi-line agent system prompt
- `visualization:` — node_colors, node_sizes, default_cypher

Property types: `string`, `integer`, `float`, `boolean`, `date`, `datetime`, `point`
YAML booleans in enum values must be quoted: `enum: ["true", "false"]` not `enum: [true, false]`

## Generated Project Structure

When a user runs the CLI, the output is:
```
my-app/
├── backend/app/          # FastAPI + chosen agent framework
│   ├── main.py, config.py, routes.py, models.py
│   ├── agent.py          # Framework-specific (8 frameworks available)
│   ├── context_graph_client.py, gds_client.py, vector_client.py
│   ├── connectors/       # Only if SaaS connectors selected
│   │   ├── __init__.py
│   │   └── {service}_connector.py  # One per selected service
│   └── __init__.py
├── backend/tests/
│   ├── __init__.py
│   └── test_routes.py    # Generated test scaffold (health, scenarios)
├── backend/scripts/
│   ├── generate_data.py
│   └── import_data.py    # Only if SaaS connectors selected
├── backend/pyproject.toml
├── frontend/             # Next.js + Chakra UI v3 + NVL
│   ├── app/ (layout.tsx, page.tsx, globals.css)
│   ├── components/ (ChatInterface, ContextGraphView, DecisionTracePanel, DocumentBrowser, Provider)
│   ├── lib/config.ts, theme/index.ts
│   └── package.json, next.config.ts, tsconfig.json
├── cypher/ (schema.cypher, gds_projections.cypher)
├── data/ (ontology.yaml, _base.yaml, fixtures.json, documents/)
├── .env, .env.example, Makefile, docker-compose.yml, README.md, .gitignore
```

## Testing

### Unit Tests

```bash
pytest tests/ -v                    # All 705 tests (900+ with slow matrix)
pytest tests/test_config.py         # Config model + framework alias + google api key + crewai anthropic extra tests (22)
pytest tests/test_ontology.py       # Ontology loading + all 22 domains validate + enum sanitization + color collision checks + Cypher query validation (128)
pytest tests/test_renderer.py       # Template rendering + all 8 frameworks + v0.3.0 features (52)
pytest tests/test_generator.py      # Data generation pipeline (14)
pytest tests/test_cli.py            # CLI integration + 8 domain/framework combos + neo4j types + validation + auto-slug (21)
pytest tests/test_custom_domain.py  # Custom domain generation with mocked LLM (17)
pytest tests/test_connectors.py     # SaaS connectors with mocked APIs (37, includes 14 Linear tests)
pytest tests/test_generated_project.py # Deep validation: Python/TS/Cypher syntax, memory, neo4j types, streaming, QA fixes, async bridging, thread safety, tool prompts, embeddings config (189)
pytest tests/test_fixtures.py       # Cross-validation: schema alignment, agent tool property refs, data quality ranges (88)
pytest tests/test_performance.py    # Timed generation tests (slow, 22 domains)
```

Unit tests do NOT require Neo4j or any API keys. All tests use `tmp_path` fixtures for output.

### E2E Smoke Tests

Full-stack integration tests that scaffold a project, install dependencies, start the backend, and send chat prompts. Requires a running Neo4j instance and LLM API keys.

```bash
make smoke-test                     # Run 3 key framework tests (pydanticai, google-adk, strands)

# Or run directly with more control:
python scripts/e2e_smoke_test.py --domain healthcare --framework pydanticai --quick
python scripts/e2e_smoke_test.py --all-domains --framework claude-agent-sdk --quick
python scripts/e2e_smoke_test.py --domain gaming --framework openai-agents  # full mode (all prompts)
```

Required env vars: `NEO4J_URI`, `NEO4J_USERNAME`, `NEO4J_PASSWORD`, plus `ANTHROPIC_API_KEY` and/or `OPENAI_API_KEY` and/or `GOOGLE_API_KEY` depending on framework.

### Makefile Targets

| Target | Description |
|--------|-------------|
| `make test` | Fast unit tests (691 tests, no external deps) |
| `make test-slow` | Full suite including matrix + perf (900+ tests) |
| `make test-matrix` | Domain × framework matrix only (176 combos) |
| `make test-coverage` | Tests with HTML coverage report |
| `make smoke-test` | E2E smoke tests for 3 key frameworks (requires Neo4j + API keys) |
| `make lint` | Run ruff linter on `src/` and `tests/` |
| `make scaffold` | Scaffold a test project to `/tmp/test-scaffold` |

## Adding a New Domain

1. Create `src/create_context_graph/domains/{domain-id}.yaml` following the schema above
2. Generate fixture data: run the CLI with `--demo-data` or use `generator.py` directly
3. Copy the fixture to `src/create_context_graph/fixtures/{domain-id}.json`
4. Verify: `pytest tests/test_ontology.py::TestLoadAllDomains -v`

## Adding a New Agent Framework

1. Create `src/create_context_graph/templates/backend/agents/{framework_key}/agent.py.j2` (use underscores for directory name; hyphens in config key are auto-converted via `fw_key = framework.replace("-", "_")`)
2. Add the framework key to `SUPPORTED_FRAMEWORKS`, `FRAMEWORK_DISPLAY_NAMES`, and `FRAMEWORK_DEPENDENCIES` in `config.py`
3. Template must export `async def handle_message(message: str, session_id: str | None = None) -> dict` returning `{"response": str, "session_id": str, "graph_data": dict | None}`
4. Import `get_conversation_history, store_message` from `context_graph_client` and call them in `handle_message()` for multi-turn conversation support
5. Pass `tool_name=` kwarg to `execute_cypher()` calls for tool call visualization
6. Use `{% raw %}...{% endraw %}` blocks for Python dict literals in the template
7. Use `{% for tool in agent_tools %}` to generate domain-specific tools from ontology
8. The template receives full ontology context: `domain`, `agent_tools`, `system_prompt`, `framework_display_name`, etc.
9. **(Optional) Add `handle_message_stream()` for text streaming**: Import `get_collector` from `context_graph_client`, use the framework's streaming API to iterate text chunks, call `collector.emit_text_delta(chunk)` for each, and `collector.emit_done(response_text, session_id)` at the end. Tool call events fire automatically via `execute_cypher`. If not provided, the `/chat/stream` route falls back to `handle_message()` with tool events still streaming in real-time.
10. Add tests to `TestAllFrameworksRender` in `test_renderer.py`, `TestMultipleDomainScaffolds` in `test_cli.py`, and `TestStreamingAgentTemplates` in `test_generated_project.py`

### Current frameworks and their patterns
| Framework | Directory | Pattern | Streaming |
|-----------|-----------|---------|-----------|
| PydanticAI | `pydanticai/` | `@agent.tool` decorator + `RunContext[AgentDeps]` | Full (`agent.run_stream()`) |
| Claude Agent SDK | `claude_agent_sdk/` | Dict-based TOOLS list + bounded agentic loop (max 15 iterations) | Full (`client.messages.stream()`) |
| OpenAI Agents SDK | `openai_agents/` | `@function_tool` decorator + `Runner.run()` | Full (`Runner.run_streamed()`) |
| LangGraph | `langgraph/` | `@tool` + `create_react_agent()` | Full (`graph.astream_events()`) |
| CrewAI | `crewai/` | `Agent` + `Task` + `Crew` with `@tool`, `run_coroutine_threadsafe` bridging | Tools only |
| Strands | `strands/` | `Agent` with `@tool`, Anthropic model, `run_coroutine_threadsafe` bridging | Tools only |
| Google ADK | `google_adk/` | `Agent` + `FunctionTool`, Gemini model | Full (`runner.run_async()`) |
| Anthropic Tools | `anthropic_tools/` | Modular `@register_tool` registry + bounded Anthropic API agentic loop (max 15 iterations) | Full (`client.messages.stream()`) |

## Adding a New SaaS Connector

1. Create `src/create_context_graph/connectors/{service}_connector.py` implementing `BaseConnector`
2. Use `@register_connector("service-id")` decorator to register it
3. Implement `authenticate(credentials)`, `fetch(**kwargs) -> NormalizedData`, and `get_credential_prompts()`
4. Add the import to `connectors/__init__.py`
5. Create `src/create_context_graph/templates/backend/connectors/{service}_connector.py.j2` (standalone version for generated projects)
6. Update `import_data.py.j2` to handle the new connector
7. Add tests to `test_connectors.py`

### Current connectors
| Service | Connector ID | Auth | Dependencies |
|---------|-------------|------|-------------|
| GitHub | `github` | Personal access token | PyGithub |
| Notion | `notion` | Integration token | notion-client |
| Jira | `jira` | API token | atlassian-python-api |
| Slack | `slack` | Bot OAuth token | slack-sdk |
| Gmail | `gmail` | gws CLI or OAuth2 | google-api-python-client, google-auth-oauthlib |
| Google Calendar | `gcal` | gws CLI or OAuth2 | google-api-python-client, google-auth-oauthlib |
| Salesforce | `salesforce` | Username/password | simple-salesforce |
| Linear | `linear` | Personal API key | *(stdlib only — urllib.request)* |

## Dependencies

**Core:** click, questionary, rich, jinja2, pyyaml, pydantic, neo4j
**Optional:** anthropic, openai (for LLM data generation), neo4j-agent-memory (for memory-aware ingestion)
**Connectors (optional):** PyGithub, notion-client, atlassian-python-api, slack-sdk, google-api-python-client, google-auth-oauthlib, simple-salesforce (Linear connector uses stdlib only)
**Dev:** pytest, pytest-cov, pytest-asyncio
**Build:** hatchling (src layout, bundles YAML/JSON/Jinja2 files automatically)

## CI Pipeline

GitHub Actions (`.github/workflows/ci.yml`) runs on push to `main` and all PRs:

| Job | Trigger | Description |
|-----|---------|-------------|
| **test** | All pushes + PRs | Unit tests on Python 3.11 and 3.12 (705 tests) |
| **lint** | All pushes + PRs | Ruff linter on `src/` and `tests/` |
| **matrix** | Push to `main` only | Full suite + 176 domain × framework matrix + 22 perf tests (900+ tests) |
| **smoke-test** | Push to `main` only | E2E: scaffold → install → start → chat for all 8 frameworks |

The smoke-test job is gated behind `vars.SMOKE_TESTS_ENABLED == 'true'` (repository variable) and requires these repository secrets: `NEO4J_URI`, `NEO4J_USERNAME`, `NEO4J_PASSWORD`, `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, `GOOGLE_API_KEY`. It uses `fail-fast: false` so one framework failure doesn't block others, and depends on the `test` job passing first.

Separate publish workflows (`publish-pypi.yml`, `publish-npm.yml`) trigger on version tags (`v*`).

## What's Not Yet Implemented

- TypeScript compilation validation in CI (requires Node.js in test environment)
