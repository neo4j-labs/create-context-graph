# CLAUDE.md — Create Context Graph

## Project Overview

Interactive CLI scaffolding tool that generates domain-specific context graph applications. Like `create-next-app` but for AI agents with graph memory. Invoked via `uvx create-context-graph` or `npx create-context-graph`.

Given a domain (e.g., "healthcare", "wildlife-management") and an agent framework (e.g., PydanticAI, Claude Agent SDK), it generates a complete full-stack application: FastAPI backend, Next.js + Chakra UI v3 + NVL frontend, Neo4j schema, synthetic data, and a configured AI agent with domain-specific tools.

**Status:** v0.9.5 in progress. 23 domains, 8 agent frameworks (7 working out of box — openai-agents requires OPENAI_API_KEY, google-adk requires GOOGLE_API_KEY with clear warnings), **streaming chat via Server-Sent Events** (token-by-token text in 6 frameworks + real-time tool call visualization with Timeline/Spinner/Collapsible + `entities_extracted` and `preferences_detected` SSE events displayed as badges), neo4j-agent-memory v0.1.0 MemoryIntegration for multi-turn conversations with automatic entity extraction and preference detection (local sentence-transformers embeddings by default — no OpenAI key required; auto-upgrades to OpenAI embeddings if OPENAI_API_KEY is set), MCP server generation for Claude Desktop (`--with-mcp` flag, `make mcp-server` target, dual-interface architecture), configurable session strategies (`per_conversation`/`per_day`/`persistent` via `SESSION_STRATEGY` env var), interactive NVL graph visualization (schema view, double-click expand, drag/zoom, property panel, agent-driven graph updates — now updated incrementally during streaming, node hover tooltips, "Ask about this" button), LLM-generated demo data (80-90 entities, 25+ documents, 8-12 decision traces per domain) with post-generation value clamping for 28 property types, markdown rendering in chat and document browser with ReactMarkdown, document browser with pagination, entity detail panel, decision trace viewer, 12 SaaS connectors (including Linear for real project data import, Google Workspace for decision trace extraction from comment threads, Claude Code for local session history import with decision/preference extraction, and Claude AI + ChatGPT for importing conversation exports from AI chat platforms), custom domain generation, Neo4j Aura .env import + neo4j-local support, Docusaurus documentation site (23 pages including quick-start, domain catalog, framework comparison, Neo4j Aura/Local guides, Docker guide, architecture diagram, "Why Context Graphs?" explainer, Google Workspace tutorial, decision trace explainer, GWS schema reference, chat history import tutorial, and chat import schema reference), graceful Neo4j degradation with /health endpoint (retry with backoff on initial load) and 503 guards on all endpoints, Cypher injection prevention, enum identifier sanitization, configurable CORS/model/timeouts, --dry-run/--verbose/--reset-database/--demo CLI flags, CLI auto-slug generation (PROJECT_NAME optional in non-interactive mode), CLI warnings for framework-specific API key requirements (openai-agents, google-adk), constants module, WCAG accessibility improvements, chat timeout/cancel with AbortController, mobile-responsive layout, .dockerignore for Docker builds, `make test-connection` target, framework-specific README sections, troubleshooting guide, thread-safe async bridging for sync frameworks (CrewAI/Strands), bounded agentic loops (max 15 iterations), domain-specific static name pools (1000+ names across 118 entity labels — all domain YAML labels covered) with domain-aware base entities, tool-use emphasis in all agent system prompts, domain-scoped chat history localStorage keys, SSR hydration fix, retry button on chat errors, PydanticAI tool serialization fix (JSON string return types), Google ADK API key support (--google-api-key flag) with AttributeError guard for SDK cleanup, Strands robust text extraction, CrewAI explicit Anthropic LLM config with `crewai[anthropic]` dependency, domain-scoped MERGE keys (`{name, domain}`) for cross-domain isolation when sharing a Neo4j instance, improved static data quality (22 domain-specific industry pools, POLE-type-aware entity descriptions with 5 label categories + 7 label-specific overrides, entity-derived document titles, realistic decision trace observations, 20+ domain-specific property pools, float value clamping, taxonomy class correction), agent thinking text collapsible filter with continuation pattern support, Cypher query validation tests across all domains, fixture cross-validation tests (schema alignment + data quality), proper Document/DecisionTrace node ingestion via --ingest, Chakra UI Pro-inspired chat input redesign, list/get-by-id agent tools for all 22 domains (7-8+ tools per domain), ON CREATE/MATCH SET for constraint-safe seeding, hardened Linear connector (named constants, structured logging, URLError/JSONDecodeError/429 handling with retry, pagination safety limits, null-safe field access, team key validation in authenticate(), incremental sync via updated_after, decision traces in generated template), optional credential prompts in interactive wizard, Google Workspace connector with decision trace extraction from 6 Google APIs (Drive Files, Comments, Revisions, Activity, Calendar, Gmail) with 10 decision-focused agent tools and cross-connector Linear linking, scaffolded Claude Code connector with full entity extraction (9 entity types, 14 relationship types, secret redaction, decision/preference extraction, language detection), connector-specific demo scenarios, 1,060 passing tests (1,266 collected including slow/integration).

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
├── connectors/         # SaaS data connectors (10 services)
│   ├── __init__.py     # BaseConnector ABC, NormalizedData model, registry
│   ├── github_connector.py
│   ├── notion_connector.py
│   ├── jira_connector.py
│   ├── slack_connector.py
│   ├── gmail_connector.py   # Prefers gws CLI, falls back to Python OAuth2
│   ├── gcal_connector.py    # Prefers gws CLI, falls back to Python OAuth2
│   ├── salesforce_connector.py
│   └── oauth.py        # Shared OAuth2 flow + gws CLI helpers
├── domains/            # 23 YAML ontology definitions + _base.yaml
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
- **Pre-generated fixtures** (shipped): All 23 domains ship with high-quality LLM-generated fixture data (80-90 entities, 160-280 relationships, 25+ documents at 200-1600 words, 3-5 decision traces with multi-step reasoning). Generated via `scripts/regenerate_fixtures.py` using Claude API.
- **Static fallback** (no LLM key at runtime): Uses domain-specific name pools (`name_pools.py`) with 1000+ names across 118 entity labels (all domain YAML labels covered — no more fallback to generic "Label 1" names), label-aware ID prefixes (PAT- for Patient, ACT- for Account), contextual property generators (emails from names, realistic IDs, domain-appropriate ranges), 22 domain-specific industry pools (`DOMAIN_INDUSTRY_POOL`), POLE-type-aware entity descriptions (`_generate_description` with 5 label categories: `_PERSON_LABELS`, `_ORGANIZATION_LABELS`, `_LOCATION_LABELS`, `_EVENT_LABELS`, `_OBJECT_LABELS` + 7 label-specific override templates), entity-derived document titles (reference primary entities instead of sequential numbers), Markdown-formatted document content, 12+ domain-specific property pools (currency codes, ticker symbols, drug classes, medical specialties, severities, etc.), float clamping for confidence/rating/efficiency fields, and realistic decision trace observations (reference entity names).
- **Post-generation validation** (`_validate_and_clamp()` in `generator.py`): LLM-generated entities are post-processed to clamp unrealistic numeric values (28 property range rules) and fix taxonomy class mismatches (species → correct class mapping).
- **LLM-powered** (with `--anthropic-api-key` at runtime): Generates realistic entities, documents, and decision traces via Anthropic or OpenAI APIs.
- **Data seeding** (`make seed`): Loads all four data types into Neo4j — entities, relationships, documents (as `:Document` nodes with `:MENTIONS` links to entities), and decision traces (as `:DecisionTrace` → `:HAS_STEP` → `:TraceStep` chains).

### Dual ingestion backends
`ingest.py` tries `neo4j-agent-memory` MemoryClient first, falls back to direct `neo4j` driver if the package isn't installed. Both paths create entities via MemoryClient or direct Cypher, plus create `:Document` and `:DecisionTrace`/`:TraceStep` nodes using direct Cypher (matching the `generate_data.py.j2` schema the frontend queries expect). Both paths tag all entities with a `domain` property for cross-domain isolation when sharing a Neo4j instance.

### Custom domain generation
`custom_domain.py` generates complete domain ontology YAMLs from natural language descriptions using LLM (Anthropic/OpenAI). Uses `_base.yaml` + 2 reference domain YAMLs as few-shot examples. Validates output against `DomainOntology` Pydantic model with retry loop (up to 3 attempts). Generated domains can be saved to `~/.create-context-graph/custom-domains/` for reuse.

### Streaming chat via Server-Sent Events (SSE)
The chat uses a streaming architecture where the backend emits SSE events as the agent executes. The `POST /chat/stream` endpoint creates an `asyncio.Queue` on the `CypherResultCollector` and launches the agent in a background task. As tools execute, the collector emits `tool_start` and `tool_end` events (with graph data). For frameworks that support it (PydanticAI, Anthropic Tools, Claude Agent SDK, OpenAI Agents, LangGraph), `text_delta` events stream tokens as they arrive. Other frameworks (CrewAI, Strands, Google ADK) emit tool events in real-time with text arriving at the end. Two additional event types support memory feedback: `entities_extracted` (emitted by `CypherResultCollector.emit_entities_extracted()` when entities are extracted from stored messages) and `preferences_detected` (emitted by `CypherResultCollector.emit_preferences_detected()` when preferences are detected). These are displayed as badges in the frontend. The frontend parses SSE via `fetch` + `ReadableStream` (not `EventSource`, which only supports GET). Tool calls render as a Chakra UI `Timeline` with live `Spinner` indicators. Text deltas are batched (~50ms) before updating ReactMarkdown to avoid excessive re-renders. Graph visualization updates incrementally after each `tool_end` event. The original `/chat` endpoint is preserved for backward compatibility. The SSE endpoint has a 120s per-event idle timeout and a 300s overall timeout.

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
Generated projects use `MemoryIntegration` from `neo4j-agent-memory` v0.1.0 for conversation memory with automatic entity extraction and preference detection. The `memory.py.j2` template generates a shared `backend/app/memory.py` module with `connect_memory()`, `close_memory()`, `store_message()`, `get_context()`, and `resolve_session_id()` functions. `context_graph_client.py.j2` delegates memory lifecycle to this module via `from app.memory import connect_memory, close_memory`. The `store_message()` return value includes extracted entities and detected preferences, which are emitted as SSE events (`entities_extracted`, `preferences_detected`) and displayed as badges in the frontend. Session identity is configurable via `SESSION_STRATEGY` env var: `per_conversation` (default), `per_day`, or `persistent`. The generated `pyproject.toml` includes `neo4j-agent-memory[spacy,gliner]>=0.1.0` plus `sentence-transformers>=2.0` so local embeddings work out of the box. All 8 agent frameworks import from `app.memory` and call `resolve_session_id()`, `store_message()`, and `get_context()` (which returns messages + entities + preferences + traces). The frontend `ChatInterface` captures `session_id` from the first SSE response and sends it in all subsequent requests.

### MCP server generation
Generated projects optionally include an MCP (Model Context Protocol) server configuration for Claude Desktop. When `--with-mcp` is passed (or selected in the wizard), the scaffold generates `mcp/claude_desktop_config.json` (pre-configured for the project's Neo4j instance), `mcp/README.md` (setup instructions), and a `make mcp-server` Makefile target. The MCP server runs `neo4j-agent-memory`'s built-in MCP server with 16 tools (extended profile) or 6 tools (core profile, via `--mcp-profile core`). This creates a dual-interface architecture: the web app and Claude Desktop both query the same knowledge graph.

### Neo4j driver serialization
`context_graph_client.py.j2` uses a custom `_serialize()` function instead of the driver's `.data()` method. This preserves Neo4j Node metadata (`elementId`, `labels`), Relationship metadata (`elementId`, `type`, `startNodeElementId`, `endNodeElementId`), and Path expansion. Without this, the frontend graph visualization and agent tools receive flat property dicts with no type information.

### SaaS connectors
`connectors/` package with 12 service connectors (GitHub, Notion, Jira, Slack, Gmail, Google Calendar, Salesforce, Linear, Google Workspace, Claude Code, Claude AI, ChatGPT). Each connector implements `BaseConnector` ABC with `authenticate()`, `fetch()`, and `get_credential_prompts()` methods. Credential prompts support an `optional` flag — the wizard skips blank optional fields instead of aborting. Returns `NormalizedData` matching the fixture schema so `ingest.py` works unchanged. Gmail/Google Calendar prefer the Google Workspace CLI (`gws`) if available, with Python OAuth2 fallback. The Linear connector uses GraphQL with cursor-based pagination and rate limiting against `https://api.linear.app/graphql`, mapping 12 entity types (Issue, Project, Cycle, Team, Person, Label, WorkflowState, Comment, ProjectUpdate, ProjectMilestone, Initiative, Attachment) to the POLE+O entity model with 26 relationship types. Imports issue relations (BLOCKS, BLOCKED_BY, RELATED_TO, DUPLICATE_OF), threaded comments with resolution tracking (REPLY_TO, RESOLVED_BY), project updates with health status, milestones, initiatives, attachments, and Linear Docs. Issue history entries are transformed into decision traces (DecisionTrace → TraceStep chains) capturing state transitions, assignment changes, and priority changes with actor attribution. The Linear connector includes structured logging (`logging.getLogger(__name__)`), named constants for all page sizes and limits, error handling for `URLError`/`JSONDecodeError`/GraphQL errors, HTTP 429 retry with exponential backoff, pagination safety limits (`MAX_PAGES`), null-safe field access via `_safe_nodes()` helper, team key validation during `authenticate()` (lists available keys on mismatch), incremental sync via `fetch(updated_after="ISO8601")`, and truncation warnings when comments or history exceed page limits. The generated template (`linear_connector.py.j2`) has full parity with the source connector including decision trace generation. The Google Workspace connector imports from 6 Google APIs (Drive Files, Drive Comments, Drive Revisions, Drive Activity, Calendar, Gmail) with OAuth2 authentication and dynamic scope building. Its defining feature is **decision trace extraction**: resolved comment threads in Google Docs become `DecisionThread` graph nodes with question, deliberation, resolution, and participants — linked to documents, people, meetings, and email threads. Includes 10 decision-focused agent tools (`find_decisions`, `decision_context`, `who_decided`, `document_timeline`, `open_questions`, `meeting_decisions`, `knowledge_contributors`, `trace_decision_to_source`, `stale_documents`, `cross_reference`) injected via the renderer when the connector is active. Cross-connector linking detects Linear issue references (e.g., ENG-123) in comment bodies, doc names, email subjects, and meeting descriptions, creating `RELATES_TO_ISSUE` relationships. Rate limiting enforces 950 queries/100s with exponential backoff. 9 CLI flags (`--gws-folder-id`, `--gws-include-comments`, `--gws-include-revisions`, `--gws-include-activity`, `--gws-include-calendar`, `--gws-include-gmail`, `--gws-since`, `--gws-mime-types`, `--gws-max-files`). The generated template (`google_workspace_connector.py.j2`) has full parity with the source connector: all 7 stages (Files, Comments, Revisions, Activity, Calendar, Gmail, Cross-references) are included, using OAuth2 only (no gws CLI fallback). The Claude Code connector reads local session JSONL files from `~/.claude/projects/` — no authentication or API keys required. Parses user/assistant messages, tool_use/tool_result blocks, and progress entries. Extracts 7 entity types (Project, Session, Message, ToolCall, File, GitBranch, Error) with 10 relationship types (HAS_SESSION, HAS_MESSAGE, NEXT, USED_TOOL, MODIFIED_FILE, READ_FILE, PRECEDED_BY, ON_BRANCH, ENCOUNTERED_ERROR, RESOLVED_BY). Includes heuristic **decision extraction** (user corrections, deliberation markers, error-resolution cycles, dependency changes) producing Decision/Alternative entities and traces, and **preference extraction** (explicit statements, package frequency) producing Preference entities. Secret redaction (API keys, tokens, passwords, connection strings) is applied by default. 8 session intelligence agent tools (`search_sessions`, `decision_history`, `file_timeline`, `error_patterns`, `tool_usage_stats`, `my_preferences`, `project_overview`, `reasoning_trace`) injected via the renderer. 5 CLI flags (`--claude-code-scope`, `--claude-code-project`, `--claude-code-since`, `--claude-code-max-sessions`, `--claude-code-content`). Implementation split into `connectors/claude_code_connector.py` (main connector) and `connectors/_claude_code/` subpackage (parser.py, redactor.py, decision_extractor.py, preference_extractor.py). The Claude AI connector imports conversations from the official Claude AI data export (Settings > Account > Export Data). Parses `conversations.jsonl` from `.zip` or raw `.jsonl` with streaming line-by-line processing for memory efficiency on large exports (1GB+). Extracts content from structured content blocks (`text`, `tool_use`, `tool_result`, `thinking`). Normalizes sender values (`human` → `user`). Creates Conversation, Message entities with HAS_MESSAGE/NEXT relationships. Generates Document per conversation for search/RAG. Deep mode extracts tool call sequences as DecisionTrace nodes. 7 CLI flags (`--import-type`, `--import-file`, `--import-depth`, `--import-filter-after`, `--import-filter-before`, `--import-filter-title`, `--import-max-conversations`). Implementation split into `connectors/claude_ai_connector.py` (main connector) and `connectors/_claude_ai/` subpackage (parser.py). Shared data models and zip utilities in `connectors/_chat_import/` subpackage (models.py, zip_reader.py). The ChatGPT connector imports conversations from the official ChatGPT data export (Settings > Data Controls > Export Data). Parses `conversations.json` from `.zip` or raw `.json`. Handles tree-structured `mapping` field with parent/children references — walks depth-first following last child at branch points. Filters out system messages and hidden messages (`is_visually_hidden_from_conversation`). Converts Unix float timestamps to ISO 8601. Handles content types: `text`, `code`, `execution_output`, `multimodal_text`. Tool-role messages captured with execution output as tool results. Same entity schema and CLI flags as Claude AI connector. Implementation in `connectors/chatgpt_connector.py` and `connectors/_chatgpt/` subpackage (parser.py). Connectors run at scaffold time AND are generated into the project with `make import` / `make import-and-seed` targets.

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
│   ├── main.py, config.py, memory.py, routes.py, models.py
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
├── mcp/                 # MCP server config (only if --with-mcp)
├── .env, .env.example, Makefile, docker-compose.yml, README.md, .gitignore
```

## Testing

### Unit Tests

```bash
pytest tests/ -v                    # All 1,060 tests (1,266 collected with slow/integration)
pytest tests/test_config.py         # Config model + framework alias + google api key + crewai anthropic extra tests (26)
pytest tests/test_ontology.py       # Ontology loading + all 23 domains validate + enum sanitization + color collision checks + Cypher query validation
pytest tests/test_renderer.py       # Template rendering + all 8 frameworks + v0.3.0 features (64)
pytest tests/test_generator.py      # Data generation pipeline (14)
pytest tests/test_cli.py            # CLI integration + 8 domain/framework combos + neo4j types + validation + auto-slug + Linear + Google Workspace + Claude Code connectors (54)
pytest tests/test_custom_domain.py  # Custom domain generation with mocked LLM (17)
pytest tests/test_connectors.py     # SaaS connectors with mocked APIs (125, includes 58 Linear + 28 Google Workspace + 38 Claude Code tests)
pytest tests/test_chat_import.py    # Chat history import: Claude AI + ChatGPT parsers, connectors, CLI flags (78)
pytest tests/test_generated_project.py # Deep validation: Python/TS/Cypher syntax, memory, neo4j types, streaming, QA fixes, async bridging, thread safety, tool prompts, embeddings config (192)
pytest tests/test_fixtures.py       # Cross-validation: schema alignment, agent tool property refs, data quality ranges (88)
pytest tests/test_security.py       # Cypher injection prevention: parameterization across 23 domains, generated code static analysis, run_cypher tool safety
pytest tests/test_doc_snippets.py   # Documentation validation: YAML examples parse, CLI flags exist, Cypher snippets valid, Make targets exist (8)
pytest tests/test_frontend_logic.py # Frontend logic: SSE event parsing, thinking/response split, backend/frontend event type contract (25)
pytest tests/test_performance.py    # Timed generation tests (slow, 23 domains)
pytest tests/test_generated_tests.py # Scaffold + install + run generated project test suite for 4 frameworks (slow, 5)
pytest tests/test_integration.py --integration  # Neo4j integration: schema DDL, fixture ingestion, agent tool queries, domain scoping (7)
```

Unit tests do NOT require Neo4j or any API keys. All tests use `tmp_path` fixtures for output. Integration tests require `--integration` flag and a running Neo4j instance (`NEO4J_URI`, `NEO4J_USERNAME`, `NEO4J_PASSWORD`).

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
| `make test` | Fast unit tests (955 tests, no external deps) |
| `make test-slow` | Full suite including matrix + perf + generated project tests (1,165 tests) |
| `make test-matrix` | Domain × framework matrix only (176 combos) |
| `make test-coverage` | Tests with HTML coverage report |
| `make test-functional` | Functional test ingesting `tests/fixtures/local_file_vault/` end-to-end through the local-file connector (see `tests/fixtures/local_file_vault_TESTING.md` for the edge-case checklist) |
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
3. Template must export `async def handle_message(message: str, session_id: str | None = None) -> dict` returning `{"response": str, "session_id": str, "graph_data": dict | None, "entities_extracted": list, "preferences_detected": list}`
4. Import `store_message, get_context, resolve_session_id` from `app.memory` and call them in `handle_message()` for multi-turn conversation support with entity extraction
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
| Google Workspace | `google-workspace` | Google OAuth 2.0 | *(stdlib only — urllib.request)* |
| Claude Code | `claude-code` | None (local files) | *(stdlib only — reads ~/.claude/projects/ JSONL)* |
| Claude AI | `claude-ai` | None (local file) | *(stdlib only — reads conversations.jsonl from export zip)* |
| ChatGPT | `chatgpt` | None (local file) | *(stdlib only — reads conversations.json from export zip)* |

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
| **test** | All pushes + PRs | Unit tests on Python 3.11 and 3.12 (955 tests including security, doc snippets, frontend logic) |
| **lint** | All pushes + PRs | Ruff linter on `src/` and `tests/` |
| **matrix** | Push to `main` only | Full suite + 176 domain × framework matrix + 22 perf tests + generated project tests (1,165 tests) |
| **smoke-test** | Push to `main` only | Neo4j integration tests + E2E: scaffold → install → start → chat for all 8 frameworks |

The smoke-test job is gated behind `vars.SMOKE_TESTS_ENABLED == 'true'` (repository variable) and requires these repository secrets: `NEO4J_URI`, `NEO4J_USERNAME`, `NEO4J_PASSWORD`, `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, `GOOGLE_API_KEY`. It runs `test_integration.py --integration` before the E2E smoke tests. Uses `fail-fast: false` so one framework failure doesn't block others, and depends on the `test` job passing first.

Separate publish workflows (`publish-pypi.yml`, `publish-npm.yml`) trigger on version tags (`v*`).

## What's Not Yet Implemented

- TypeScript compilation validation in CI (requires Node.js in test environment)
