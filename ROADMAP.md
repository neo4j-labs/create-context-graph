# Roadmap — Create Context Graph

> Last updated: March 22, 2026

## Overview

Create Context Graph was built in 6 phases. The goal was to go from an empty repository to a published CLI tool that generates domain-specific context graph applications for 22 industry verticals with 8 agent framework options, powered by neo4j-agent-memory for multi-turn conversations.

---

## Phase 1: Core CLI & Template Engine — COMPLETE

**Timeline:** Weeks 1–3
**Status:** Done

Built the foundational scaffolding tool: Python package structure, CLI, interactive wizard, template engine, and initial templates.

### What was built

- **Python package** (`src/create_context_graph/`) with `hatchling` build, `src` layout, entry point via `create-context-graph` command
- **Click CLI** (`cli.py`) with both interactive and non-interactive (flag-based) modes
- **Interactive wizard** (`wizard.py`) — 7-step flow using Questionary + Rich: project name, data source, domain selection, agent framework, Neo4j connection, API keys, confirmation
- **ProjectConfig model** (`config.py`) — Pydantic model holding all wizard outputs, computed slug, framework display names and dependency mappings for all 8 planned frameworks
- **Domain ontology system** (`ontology.py`) — YAML loader with two-layer inheritance (`_base.yaml` + domain YAML), Pydantic validation models for all ontology sections, code generation helpers (Cypher schema, Pydantic models, NVL visualization config)
- **Jinja2 template engine** (`renderer.py`) — `PackageLoader`-based renderer with custom filters (`snake_case`, `camel_case`, `pascal_case`, `kebab_case`), renders full project directory from templates + ontology context
- **3 initial domain ontologies** — Financial Services, Healthcare, Software Engineering (complete with entity types, relationships, document templates, decision traces, demo scenarios, agent tools, system prompts, visualization config)
- **Backend templates** — FastAPI main, config, Neo4j client, GDS client, vector search client, Pydantic models, REST routes, pyproject.toml, data generation script, agent stub fallback
- **2 agent framework templates** — PydanticAI (structured tool definitions with `RunContext`) and Claude Agent SDK (Anthropic tool-use with agentic loop)
- **Frontend templates** — Next.js 15 + Chakra UI v3 + NVL: layout, page (3-panel), ChatInterface, ContextGraphView, DecisionTracePanel, Provider, domain config, theme
- **Base templates** — `.env`, `Makefile`, `docker-compose.yml`, `README.md`, `.gitignore`
- **Cypher templates** — Schema constraints/indexes from ontology, GDS graph projections
- **Neo4j connection validator** (`neo4j_validator.py`)

### Key design decisions made

- Templates are **domain-agnostic, data-driven** — no per-domain template directories; the ontology YAML drives all customization
- Only `agent.py` varies by framework; everything else is shared
- JSX/Python dict literals in templates use `{% raw %}...{% endraw %}` blocks to avoid Jinja2 conflicts
- Pre-built fixtures are bundled and copied into every generated project

---

## Phase 2: Domain Expansion & Document Generation — COMPLETE

**Timeline:** Weeks 4–6
**Status:** Done

Expanded from 3 domains to 22, built the synthetic data generation pipeline, and created the Neo4j ingestion system.

### What was built

- **19 additional domain ontology YAMLs** — All validated and scaffold-tested. Domains: Agent Memory, Conservation, Data Journalism, Digital Twin, Gaming, GenAI/LLM Ops, GIS & Cartography, Golf & Sports Mgmt, Hospitality, Manufacturing, Oil & Gas, Personal Knowledge, Product Management, Real Estate, Retail & E-Commerce, Scientific Research, Trip Planning, Vacation Industry, Wildlife Management
- **Synthetic data generation pipeline** (`generator.py`) — 4-stage pipeline:
  1. **Entity seeding** — LLM-powered or static fallback, generates 5+ entities per type with properties matching ontology schema
  2. **Relationship weaving** — Connects entities based on ontology relationship definitions, avoids self-relationships
  3. **Document generation** — Produces 25+ documents across all template types defined in the ontology (LLM-powered for realistic content, static fallback for offline use)
  4. **Decision trace injection** — Creates reasoning traces from ontology scenarios with thought/action/observation steps
- **LLM client abstraction** — Supports both Anthropic and OpenAI as generation providers, graceful fallback to static data when no API key is available
- **Data ingestion system** (`ingest.py`) — Dual-backend ingestion:
  - Primary: `neo4j-agent-memory` MemoryClient (long-term entities, short-term documents, reasoning traces — all three memory types)
  - Fallback: Direct `neo4j` driver when neo4j-agent-memory isn't installed
  - Schema application from generated Cypher
- **Pre-generated fixture files** — All 22 domains ship with static `fixtures/{domain-id}.json` files so projects work immediately without an LLM API key
- **CLI integration** — `--demo-data` flag triggers generation, `--ingest` flag triggers Neo4j ingestion, `--anthropic-api-key` enables LLM-powered generation, pre-built fixtures always copied into `data/fixtures.json`
- **Comprehensive test suite** (85 tests, all passing):
  - `test_config.py` — 10 unit tests for ProjectConfig
  - `test_ontology.py` — 20 unit tests including parametric validation of all 22 domains
  - `test_renderer.py` — 18 unit tests for rendering, file structure, framework selection, Python compile verification
  - `test_generator.py` — 14 unit tests for data generation across 6 domains
  - `test_cli.py` — 13 integration tests for CLI invocation, 6 domain/framework combinations

### Verified

- All 22 domains load and validate without errors
- 18/18 domain+framework combinations scaffold successfully (9 domains x 2 frameworks)
- Generated Python files pass `compile()` syntax check
- 85/85 tests pass in 3.4 seconds

---

## Phase 3: Framework Templates & Frontend — COMPLETE

**Timeline:** Weeks 7–8
**Status:** Done

Added all 8 agent framework templates, replaced NVL placeholder with real graph visualization, and expanded the test suite.

### What was built

- **6 new agent framework templates** — All in `templates/backend/agents/`, each generating valid Python with domain-specific tools from ontology:
  - **OpenAI Agents SDK** (`openai_agents/`) — `@function_tool` decorators + `Runner.run()`
  - **LangGraph** (`langgraph/`) — `@tool` + `create_react_agent()` with `ChatAnthropic`
  - **CrewAI** (`crewai/`) — `Agent` + `Task` + `Crew` with `@tool` decorator
  - **Strands** (`strands/`) — `Agent` with `@tool`, Anthropic model
  - **Google ADK** (`google_adk/`) — `Agent` + `FunctionTool`, Gemini model, async runner
  - **MAF** (`maf/`) — Modular tool registry with decorator pattern
- **NVL graph visualization** — Replaced placeholder in `ContextGraphView.tsx` with real `@neo4j-nvl/react` `InteractiveNvlWrapper` component: force-directed layout, domain-colored nodes via `NODE_COLORS`/`NODE_SIZES`, node click handler, color legend
- **Makefile improvements** — Added `make test` and `make lint` targets
- **Expanded test suite** (103 tests, all passing in 3.78s):
  - `TestAllFrameworksRender` — 8 parametric tests verifying each framework's agent.py compiles and contains framework-specific imports
  - `TestAllFrameworksRender` — 8 parametric tests verifying each framework's pyproject.toml contains correct dependencies
  - `TestMultipleDomainScaffolds` — Expanded from 6 to 8 domain/framework combinations covering all frameworks

### Verified

- All 8 frameworks scaffold, render, and compile without errors
- All 8 frameworks produce correct `pyproject.toml` dependencies
- Each framework's agent.py contains the expected framework marker (import/class name)
- 103/103 tests pass in 3.78 seconds

---

## Phase 4: SaaS Import & Custom Domains — COMPLETE

**Timeline:** Weeks 9–10
**Status:** Done

Implemented SaaS data connectors for 7 services and LLM-powered custom domain generation.

### What was built

#### SaaS data connectors

- **Connectors package** (`connectors/`) — `BaseConnector` ABC, `NormalizedData` Pydantic model matching fixture schema, connector registry with `@register_connector` decorator
- **7 service connectors**, each with `authenticate()`, `fetch()`, and `get_credential_prompts()`:

| Service | Connector | Auth Method | Dependencies |
|---------|-----------|-------------|-------------|
| GitHub | `github_connector.py` | Personal access token | PyGithub |
| Notion | `notion_connector.py` | Integration token | notion-client |
| Jira | `jira_connector.py` | API token | atlassian-python-api |
| Slack | `slack_connector.py` | Bot OAuth token | slack-sdk |
| Gmail | `gmail_connector.py` | gws CLI or OAuth2 | google-api-python-client, google-auth-oauthlib |
| Google Calendar | `gcal_connector.py` | gws CLI or OAuth2 | google-api-python-client, google-auth-oauthlib |
| Salesforce | `salesforce_connector.py` | Username/password + security token | simple-salesforce |

- **Google Workspace CLI (`gws`) integration** — Gmail and Google Calendar connectors detect `gws` on PATH, offer to install via npm if missing, fall back to Python OAuth2
- **OAuth2 local redirect flow** (`oauth.py`) — Temporary HTTP server on random port, browser consent, auth code capture, token exchange
- **Dual-purpose connectors** — Run at scaffold time to populate initial data AND generated into the scaffolded project for ongoing `make import` / `make import-and-seed` usage
- **Connector templates** — 7 standalone connector `.py.j2` templates + `import_data.py.j2` generated into scaffolded projects (only for selected connectors)
- **Makefile targets** — `make import` and `make import-and-seed` added to generated projects when SaaS connectors are selected
- **Wizard integration** — Checkbox selection of connectors, credential prompts, gws CLI detection and install prompt
- **CLI flags** — `--connector` (multiple) for non-interactive connector selection
- **Optional dependencies** — New `[connectors]` extra in pyproject.toml

#### Custom domain generation

- **`custom_domain.py`** — LLM-powered domain YAML generation:
  1. Loads `_base.yaml` + 2 reference domain YAMLs (healthcare, wildlife-management) as few-shot examples
  2. Builds prompt with complete YAML schema specification
  3. Calls LLM (Anthropic/OpenAI) via existing `generator.py` abstraction
  4. Parses YAML, validates against `DomainOntology` Pydantic model
  5. On validation failure, retries with error feedback (up to 3 attempts)
  6. Returns `(DomainOntology, raw_yaml_string)`
- **`ontology.py` extensions** — `load_domain_from_yaml_string()`, `load_domain_from_path()`, `list_available_domains()` now scans `~/.create-context-graph/custom-domains/`
- **Wizard integration** — Description prompt → LLM generation with spinner → Rich summary table → accept/regenerate/edit → optional save for reuse
- **CLI flag** — `--custom-domain "description"` for non-interactive custom domain generation
- **Renderer support** — Custom domain YAML written directly to `data/ontology.yaml`
- **Persistence** — Custom domains saved to `~/.create-context-graph/custom-domains/` and appear in future wizard runs

### Bug fixes

- Fixed `cli.py:73` — `data_source` was always `"demo"` regardless of flags

### Tests added (40 new tests)

- `test_custom_domain.py` — 17 tests: YAML string loading, base merge, validation errors, prompt construction, mocked LLM generation (success, retry, max retries), display, save, custom domain listing
- `test_connectors.py` — 23 tests: NormalizedData model, merge, registry (7 connectors), credential prompts, mocked fetch for GitHub/Notion/Jira/Slack/Gmail/GCal/Salesforce, OAuth helpers

### Verified

- All 7 connectors register and expose credential prompts
- Mocked connector fetches return valid NormalizedData
- Custom domain generation succeeds with mocked LLM
- Custom domain retry loop works on validation failure
- 182/182 tests pass in 5.2 seconds

---

## Phase 5: Polish, Testing & Launch — COMPLETE

**Timeline:** Weeks 11–12
**Status:** Done

Prepared for public release with Docusaurus documentation, Neo4j Labs compliance, enhanced testing, and version 0.2.0.

### What was built

#### Docusaurus documentation site

- **Docusaurus 3.x** site in `docs/` with TypeScript config, Diataxis-organized sidebar
- **11 documentation pages** following the Diataxis framework:
  - **Tutorials:** Your First Context Graph App, Customizing Your Domain Ontology
  - **How-To Guides:** Import Data from SaaS Services, Add a Custom Domain, Switch Agent Frameworks
  - **Reference:** CLI Options & Flags, Ontology YAML Schema, Generated Project Structure
  - **Explanation:** How Domain Ontologies Work, Why Context Graphs Need All Three Memory Types
- **GitHub Pages deployment** via `.github/workflows/deploy-docs.yml` (triggers on `docs/` changes to main)
- Site URL: `https://create-context-graph.vercel.app/`

#### Neo4j Labs compliance

- **Apache-2.0 license headers** added to all 32 Python source and test files
- **Labs badge** added to `README.md` and generated project README template
- **Community support disclaimer** updated to standard Neo4j Labs language
- **CONTRIBUTING.md** — Getting started, adding domains/frameworks/connectors, testing, PR process

#### Testing improvements

- **Cypher syntax validation** in `test_generated_project.py` — validates statement keywords and semicolons
- **Frontend syntax validation** — TSX files checked for imports and exports, `config.ts` validated for required exports
- **Timed performance test** (`test_performance.py`) — all 22 domains must scaffold in < 120 seconds each (slow marker)

#### Publishing

- **Version bumped to 0.2.0** across `pyproject.toml`, `npm-wrapper/package.json`, and `__init__.py`
- Publishing workflows already in place from prior phases (PyPI + npm on version tags)

### Success metrics achieved

| Metric | Target | Actual |
|--------|--------|--------|
| Time to running app | < 5 minutes | ~2 minutes (scaffold + install + start) |
| Domain coverage | 22 domains | 22 domains |
| Framework coverage | 8 agent frameworks | 8 agent frameworks |
| Generation success rate | >= 95% | 100% (176/176 matrix combos pass) |
| Test suite | 100+ tests | 262 tests (460 with slow matrix) |

---

## Post-Launch: Data Quality & UI Enhancements — COMPLETE

**Status:** Done

### Fixture data quality overhaul

- **`name_pools.py`** — Realistic name pools (25 person names, 20 org names, etc.) and contextual value generators (emails from names, realistic IDs, domain-appropriate ranges)
- **Improved static fallback** in `generator.py` — produces passable data without an LLM (realistic names, structured documents, interpolated trace outcomes)
- **`scripts/regenerate_fixtures.py`** — One-time script to regenerate all 22 fixtures using Claude API with coherent cross-entity prompts, validation, and retry logic
- **All 22 fixtures regenerated** with LLM-quality data: 80-90 entities, 160-280 relationships, 25+ documents (200-1600 words each), 3-5 decision traces with specific observations and outcomes
- **Fixture quality tests** — 66 parametrized tests across all 22 domains verify no placeholder names, documents >= 200 chars, no uninterpolated template variables

### Full fixture data utilization in generated apps

- **`generate_data.py.j2`** updated — `make seed` now loads all 4 data types: entities, relationships, documents (as `:Document` nodes with `:MENTIONS` entity links), and decision traces (as `:DecisionTrace` → `:HAS_STEP` → `:TraceStep` chains)
- **4 new API endpoints** in `routes.py.j2`:
  - `GET /documents` — list with template filter, previews, mentioned entities
  - `GET /documents/{title}` — full document content
  - `GET /traces` — traces with full reasoning steps
  - `GET /entities/{name}` — all properties, labels, and connections
- **Document browser** (`DocumentBrowser.tsx.j2`) — template type filter badges, scrollable list with previews, full document viewer with mentioned entity badges
- **Entity detail panel** in `ContextGraphView.tsx.j2` — click any graph node to see all properties, labels, and connections with relationship types/directions
- **Fixed DecisionTracePanel** — uses new `/traces` endpoint, loads steps with observations (was previously broken: wrong node label, empty steps array)
- **Tabbed right panel** in `page.tsx.j2` — Traces and Documents tabs using Chakra UI v3 compound Tabs components
- **Schema indexes** for `Document` and `DecisionTrace` nodes added to `generate_cypher_schema()`

---

## Graph Visualization & Agent Fixes — COMPLETE

**Status:** Done

### Interactive graph visualization

- **Schema view on load** — Graph starts by calling `db.schema.visualization()` (via new `GET /schema/visualization` endpoint), showing entity type labels as nodes and relationship types as edges. No data query on initial load.
- **Agent-driven graph updates** — `CypherResultCollector` in `context_graph_client.py` captures all Cypher results from agent tool calls. The `/chat` endpoint drains collected results and attaches them as `graph_data` in the response. `ChatInterface` passes `graph_data` to `page.tsx` via `onGraphUpdate` callback, which flows to `ContextGraphView` as `externalGraphData`. Works for all 8 agent frameworks without modifying any agent template.
- **Double-click to expand** — Schema nodes load instances of that label (`MATCH (n:\`Label\`)-[r]-(m) RETURN n,r,m LIMIT 50`). Data nodes call new `POST /expand` endpoint to fetch neighbors. Expanded data is merged with deduplication.
- **NVL d3Force layout** — Replaced `InteractiveNvlWrapper` configuration: d3Force layout, zoom 0.1–5x, relationship thickness 2, dynamic import for SSR avoidance. Uses `mouseEventCallbacks` for node click, double-click, relationship click, canvas click.
- **Property details panel** — Click any node to see labels (color badges), all properties (key-value list), and metadata. Click relationships to see type and properties. Canvas click deselects.
- **UI overlays** — Color legend (top 6 node types), instructions overlay, loading spinner during expansion, back-to-schema button, schema/data mode indicator.
- **State management** — `page.tsx` lifts `graphData` state with `useState`/`useCallback`. Props flow down, callbacks flow up. No external state library.

### Neo4j driver serialization fix

- **`_serialize()` function** in `context_graph_client.py.j2` — Replaced `result.data()` (which strips metadata) with per-record iteration and custom serialization preserving Node (`elementId`, `labels`), Relationship (`elementId`, `type`, `startNodeElementId`, `endNodeElementId`), and Path objects.

### MAF agent template fix

- **Bug:** MAF agent used keyword-based tool dispatch (lines 75-114) that never called an LLM. Fallback echoed system prompt: `"I'm your {SYSTEM_PROMPT}... Available tools: ..."`.
- **Fix:** Rewrote `handle_message()` with Anthropic API tool-use loop (matching `claude_agent_sdk` pattern). Kept `TOOL_REGISTRY` + `@register_tool` decorator. Added `_build_tool_definitions()` that introspects registry via `inspect.signature` to generate Anthropic tool schemas. Added `anthropic>=0.30` to MAF framework dependencies.

### New backend endpoints

- `GET /schema/visualization` — Returns schema graph via `db.schema.visualization()` (with fallback to basic labels/types)
- `POST /expand` (body: `{element_id}`) — Returns immediate neighbors with nodes and relationships for graph expansion

### Files modified

- `config.py` — Added `anthropic>=0.30` to MAF deps
- `templates/backend/agents/maf/agent.py.j2` — Full rewrite
- `templates/backend/shared/context_graph_client.py.j2` — `_serialize()`, `CypherResultCollector`, `get_schema_visualization()`, `expand_node()`
- `templates/backend/shared/routes.py.j2` — New endpoints, collector integration in `/chat`
- `templates/frontend/components/ContextGraphView.tsx.j2` — Complete rewrite (~480 lines)
- `templates/frontend/components/ChatInterface.tsx.j2` — `onGraphUpdate` prop
- `templates/frontend/app/page.tsx.j2` — State lifting
- `templates/frontend/lib/config.ts.j2` — `GraphData` type, schema constants

---

## Phase 6: Memory Integration, Multi-Turn & DX — COMPLETE

**Status:** Done (v0.3.0)

Addressed all critical and high-priority feedback from the v0.2.0 product review. Core theme: make the generated apps actually use neo4j-agent-memory and deliver a compelling multi-turn conversation experience.

### Critical fixes

- **neo4j-agent-memory integration** — Generated `context_graph_client.py` now initializes `MemoryClient` alongside the Neo4j driver (with ImportError fallback). Exposes `get_conversation_history()` and `store_message()` functions used by all 8 agent frameworks for multi-turn conversation persistence.
- **Multi-turn conversations** — All 8 agent templates retrieve conversation history before each LLM call and store messages after. Frontend `ChatInterface` captures `session_id` from the first response and sends it in all subsequent requests. "New Conversation" button resets session state.
- **CrewAI/Strands/Google ADK async fix** — Added `nest_asyncio` to prevent `asyncio.run()` deadlocks inside FastAPI's async event loop. Added to `FRAMEWORK_DEPENDENCIES` for all three frameworks.
- **MAF → Anthropic Tools rebrand** — Renamed framework from `maf` to `anthropic-tools`. Template directory moved to `anthropic_tools/`. Old `maf` key supported as deprecated alias via `FRAMEWORK_ALIASES`. Updated all tests.

### High-priority fixes

- **GDS client** — Changed default label from hardcoded `"Entity"` to `"*"` (wildcard). Exposed `ENTITY_LABELS` list generated from domain ontology.
- **Markdown rendering** — Added `react-markdown` + `remark-gfm` to frontend. Assistant messages render through ReactMarkdown with CSS styles for headings, lists, code blocks, tables, blockquotes.
- **.env.example** — Generated alongside `.env` with placeholder values (`your-password-here`). Added to renderer and gitignore correctly.

### Neo4j setup options (new)

- **Neo4j Aura import** — New wizard option "Neo4j Aura (cloud — free tier available)" with signup instructions panel and `.env` file parser. CLI flag: `--neo4j-aura-env PATH`.
- **neo4j-local** — New wizard option "Local Neo4j via neo4j-local (no Docker required)". Generates `make neo4j-start/stop/status` targets using `npx @johnymontana/neo4j-local`. CLI flag: `--neo4j-local`.
- **`neo4j_type` expanded** — Config Literal from `"docker" | "existing"` to `"docker" | "existing" | "aura" | "local"`. Makefile, README, docker-compose all render conditionally based on type.

### Medium-priority fixes

- **Port configurability** — CORS reads from `settings.frontend_port`. Makefile uses `include .env` / `export` with `$${BACKEND_PORT:-8000}` and `$${FRONTEND_PORT:-3000}` defaults.
- **Process management** — `make start` uses `trap 'kill 0' EXIT` to clean up child processes on Ctrl+C.
- **Docker version pin** — `neo4j:5` → `neo4j:5.26.0` in docker-compose template.
- **README entity types** — Split into "Base POLE+O Entities" and "Domain-Specific Entities" subsections.
- **Vector index creation** — `create_vector_index()` called in app lifespan startup (try/except for Neo4j < 5.13).

### Enhancements

- **Tool call visualization** — `CypherResultCollector` extended with `tool_calls` tracking. `ChatResponse` includes `tool_calls` field. Frontend renders inline tool call cards (badge + abbreviated inputs) above assistant messages.
- **Test scaffold** — Generated projects include `backend/tests/test_routes.py` with `test_health()` and `test_scenarios()` tests using mocked Neo4j.

### Tests added (52 new tests → 314 total)

- **test_renderer.py** (+18): .env.example, session_id, ReactMarkdown, memory functions, GDS labels, tool calls, README sections, CORS, vector index, docker pin, trap cleanup, neo4j-local/aura Makefile targets, markdown CSS
- **test_generated_project.py** (+22): .env.example, ChatInterface features, memory integration, docker pin, neo4j type variations, test scaffold
- **test_config.py** (+9): aura/local neo4j types, framework alias resolution (maf→anthropic-tools)
- **test_cli.py** (+3): --neo4j-aura-env, --neo4j-local, maf alias backward compatibility

### Files modified

- `config.py` — SUPPORTED_FRAMEWORKS, FRAMEWORK_ALIASES, FRAMEWORK_DEPENDENCIES, neo4j_type Literal, resolved_framework property
- `cli.py` — --neo4j-aura-env, --neo4j-local flags, alias resolution
- `wizard.py` — 4 Neo4j options (Aura, local, Docker, existing), _parse_aura_env helper
- `renderer.py` — .env.example rendering, base/domain entity type partition, test scaffold rendering, resolved_framework in context
- `templates/backend/shared/context_graph_client.py.j2` — MemoryClient init, get_conversation_history(), store_message(), tool call collector
- `templates/backend/shared/routes.py.j2` — tool_calls in ChatResponse
- `templates/backend/shared/main.py.j2` — CORS from settings, vector index startup
- `templates/backend/shared/gds_client.py.j2` — wildcard label, ENTITY_LABELS
- `templates/backend/agents/*/agent.py.j2` — all 8 frameworks: multi-turn history, tool_name tracking
- `templates/backend/agents/maf/` → `templates/backend/agents/anthropic_tools/` — renamed
- `templates/frontend/components/ChatInterface.tsx.j2` — session_id, ReactMarkdown, tool call cards, new conversation button
- `templates/frontend/package.json.j2` — react-markdown, remark-gfm
- `templates/frontend/app/globals.css.j2` — .markdown-content styles
- `templates/base/Makefile.j2` — env vars, trap cleanup, neo4j-local targets
- `templates/base/docker-compose.yml.j2` — neo4j:5.26.0
- `templates/base/dot_env_example.j2` — new file
- `templates/base/README.md.j2` — entity sections, neo4j-type-aware instructions, .env.example docs
- `templates/backend/tests/test_routes.py.j2` — new test scaffold template

---

## Phase 7 — Hardening, Security & DX (v0.4.0)

Based on comprehensive QA testing of all 176 domain-framework combinations.

### Bug Fixes
- **B-01** (Critical): Enum identifier sanitization — `A+`, `A-`, `3d_model` now generate valid Python identifiers (`A_PLUS`, `A_MINUS`, `_3D_MODEL`) with value aliases
- **B-02** (Critical): Graceful degradation when Neo4j is unavailable — backend starts in degraded mode with `/health` endpoint reporting status
- **B-03** (High): Cypher injection prevention in `gds_client.py` — label parameters validated against generated `ENTITY_LABELS` whitelist
- **B-04** (High): CrewAI async/sync fix — replaced bare `asyncio.run()` with `_run_sync()` helper using `nest_asyncio`, crew runs in thread via `asyncio.to_thread()`
- **B-05** (High): Claude Agent SDK model now configurable via `ANTHROPIC_MODEL` environment variable
- **B-06** (Medium): Silent exception swallowing replaced with structured warnings in `ingest.py` and `vector_client.py`
- **B-07** (Medium): JSON parsing error handling added to all 8 agent framework templates
- **B-08** (Medium): Input validation (`max_length`) on chat and search request models
- **B-09/B-10** (Low): CLI validates empty project names, adds `--dry-run` and `--verbose` flags

### Security
- CORS origins configurable via `CORS_ORIGINS` environment variable
- Credential warnings in `.env.example`
- Query timeouts (30s default) on all Neo4j operations

### Code Quality
- Magic strings extracted to `constants.py` module (index names, graph projections, embedding dimensions)
- Frontend error messages: parse HTTP error responses, show actionable guidance
- Document browser pagination (page size 20)
- Semantic HTML landmarks (`<main>`, `<section>`, `<aside>`) and ARIA labels
- 365 passing tests (51 new)

---

## Phase 8 — Streaming Chat & Real-Time Tool Visualization (v0.5.0)

### Streaming Architecture (SSE)
- **Event-driven CypherResultCollector** — added `asyncio.Queue`-based event system to the global collector. When a streaming session is active, `tool_start`, `tool_end`, `text_delta`, and `done` events are pushed to the queue automatically as tools execute and text streams in
- **`POST /chat/stream` endpoint** — new SSE endpoint alongside existing `/chat` (backward compatible). Uses `StreamingResponse` with `text/event-stream` content type. Emits `session_id` first, then tool and text events, terminated by `done` or `error`
- **`execute_cypher()` emits `tool_start`** before query execution when `tool_name` is set — all 8 frameworks get real-time tool events with zero agent template changes

### Text Streaming (5 of 8 frameworks)
- **Full streaming** (`handle_message_stream()` added): PydanticAI (`agent.run_stream()`), Claude Agent SDK (`client.messages.stream()`), OpenAI Agents SDK (`Runner.run_streamed()`), LangGraph (`graph.astream_events()`), Anthropic Tools (`client.messages.stream()`)
- **Tool-only streaming** (no agent changes): CrewAI, Strands, Google ADK — tool call events fire in real-time via the collector; text arrives at the end. The `/chat/stream` route auto-detects and falls back gracefully

### Frontend Streaming UI
- **SSE client** — `fetch` + `ReadableStream` + `TextDecoder` for POST-based SSE (not `EventSource` which only supports GET)
- **Chakra UI Timeline** — tool calls displayed as a vertical timeline with `Spinner` for running tools, checkmark `Check` icon for complete tools
- **Collapsible tool details** — expandable view of tool inputs and output preview
- **Skeleton loading** — `Skeleton` placeholders while waiting for first content
- **Throttled ReactMarkdown** — text deltas batched at ~50ms to avoid excessive re-renders
- **Incremental graph updates** — `onGraphUpdate` called on each `tool_end` event, so the NVL visualization updates after each tool completes rather than all at once

### Tests added (23 new → 388 total)
- `TestStreamingEndpoint` — `/chat/stream` endpoint, `StreamingResponse`, backward compat
- `TestCollectorEventQueue` — event queue methods on CypherResultCollector
- `TestStreamingAgentTemplates` — `handle_message_stream` presence in 5 frameworks, absence in 3
- `TestStreamingFrontend` — Timeline, Skeleton, Collapsible, SSE parsing in ChatInterface
- End-to-end validation: 8 frameworks × 3 domains + all 22 domains = 46 scaffold validations

### Files modified
- `templates/backend/shared/context_graph_client.py.j2` — event queue on CypherResultCollector
- `templates/backend/shared/routes.py.j2` — `/chat/stream` SSE endpoint
- `templates/frontend/components/ChatInterface.tsx.j2` — SSE client + Timeline/Collapsible/Skeleton UI
- `templates/backend/agents/anthropic_tools/agent.py.j2` — `handle_message_stream()`
- `templates/backend/agents/claude_agent_sdk/agent.py.j2` — `handle_message_stream()`
- `templates/backend/agents/pydanticai/agent.py.j2` — `handle_message_stream()`
- `templates/backend/agents/openai_agents/agent.py.j2` — `handle_message_stream()`
- `templates/backend/agents/langgraph/agent.py.j2` — `handle_message_stream()`
- `tests/test_generated_project.py` — 23 new streaming tests

---

## Phase 9 — QA Hardening & DX Polish (v0.5.0)

Comprehensive QA pass across all 176 domain/framework combinations. 15 bugs fixed, 3 false alarms identified, 21 new tests added (409 total).

### Critical Fixes
- **Settings `extra: "ignore"`** — Neo4j Aura `.env` files with extra variables (NEO4J_DATABASE, AURA_INSTANCEID) no longer cause ValidationError
- **`is_connected()` state flag** — replaced broken sync `verify_connectivity()` on AsyncDriver with tracked `_connected` flag set during `connect_neo4j()`/`close_neo4j()`
- **503 guards on all endpoints** — added `_require_neo4j()` guard to all 15 Neo4j-dependent routes (was only on `/chat` and `/chat/stream`); `/cypher` now returns 503 for connection errors, 400 for syntax errors

### Async Safety
- **Removed `nest_asyncio`** from Strands and CrewAI templates — replaced with `asyncio.to_thread()` + clean `asyncio.run()` in worker threads. Google ADK keeps `nest_asyncio` (needed for sync tools within async `run_async()`)

### Conversation History
- **Structured format** — replaced flat `"Previous conversation:\n"` string concatenation with `<conversation_history>[ROLE]\ncontent</conversation_history>` format in OpenAI Agents, Strands, CrewAI, and Google ADK
- **ADK session leverage** — Google ADK skips history injection for existing sessions (ADK manages multi-turn internally), only injects persisted history for new sessions after server restart

### Streaming
- **Google ADK full streaming** — added `handle_message_stream()` that emits `text_delta` events from `runner.run_async()` events. Google ADK promoted from "tools only" to "full streaming" (6 of 8 frameworks now stream)

### Frontend Fixes
- **Unique message IDs** — `crypto.randomUUID()` for React keys instead of array indices
- **Loading fallback** — `Spinner` component in dynamic `ContextGraphView` import
- **Storage warning** — `console.warn()` on sessionStorage failures

### Domain & Build Fixes
- **Color collision resolution** — fixed 12 entity color collisions across 7 domains (entities sharing hex colors with base POLE+O types)
- **LIMIT clause** — added `LIMIT 100` to software-engineering default Cypher query
- **ESLint dependencies** — added `eslint` and `eslint-config-next` to frontend devDependencies
- **`.dockerignore`** — new template excluding node_modules, .venv, .git, __pycache__ from Docker builds
- **CrewAI Python 3.11+** — conditional `requires-python = ">=3.11"` in generated pyproject.toml

### Developer Experience
- **`make test-connection`** — Makefile target to validate Neo4j credentials
- **README troubleshooting** — common issues with Neo4j connection, port conflicts, API keys (conditional on neo4j_type)
- **Framework-specific README** — each generated README documents the chosen framework's architecture, streaming support, and required API keys

### Tests added (21 new → 409 total)
- `TestQABugFixes` — config extra ignore, connected flag, endpoint guards, cypher 503, message IDs, storage warning, loading fallback, ESLint deps, dockerignore
- `TestDeferredBugFixes` — structured history format, ADK session reuse, ADK streaming, CrewAI Python version, strands deps
- `test_no_color_collisions_with_base` — validates all 22 domains have unique entity colors
- `test_all_domains_default_cypher_has_limit` — validates LIMIT clause in all domains

### Files modified
- `templates/backend/shared/config.py.j2` — `extra: "ignore"`
- `templates/backend/shared/context_graph_client.py.j2` — `_connected` flag
- `templates/backend/shared/routes.py.j2` — `_require_neo4j()` guard
- `templates/backend/shared/pyproject.toml.j2` — conditional Python version
- `templates/backend/agents/{strands,crewai,google_adk,openai_agents}/agent.py.j2` — async safety, history format, streaming
- `templates/frontend/components/ChatInterface.tsx.j2` — message IDs, storage warning
- `templates/frontend/app/page.tsx.j2` — loading fallback
- `templates/frontend/package.json.j2` — ESLint deps
- `templates/base/Makefile.j2` — `test-connection` target
- `templates/base/README.md.j2` — troubleshooting, framework sections
- `templates/base/dockerignore.j2` — new file
- `src/create_context_graph/config.py` — remove nest-asyncio from deps
- `src/create_context_graph/renderer.py` — register dockerignore template
- `src/create_context_graph/domains/*.yaml` — color fixes (7 domains), LIMIT clause (1 domain)
- `tests/test_generated_project.py` — 19 new tests
- `tests/test_ontology.py` — 2 new tests

---

## Phase 10 — Framework Reliability, Data Quality & UX (v0.5.1)

Comprehensive testing of v0.4.6 revealed that 6 of 9 agent frameworks were non-functional (hanging or not executing tools), plus frontend UX bugs and static data quality issues. This phase addresses all feedback.

### Critical: Fix Hanging Frameworks

- **Thread-safe CypherResultCollector**: `_push_event()` now detects worker threads and uses `loop.call_soon_threadsafe()` instead of direct `put_nowait()` on the asyncio.Queue. Captures `self._loop` in `set_event_queue()`.
- **CrewAI/Strands async bridging**: Replaced `asyncio.run()` in `_run_sync()` with `asyncio.run_coroutine_threadsafe(coro, _main_loop)`. Added `_capture_loop()` called before `asyncio.to_thread()` to capture the main event loop. 30s timeout per tool call.
- **Google ADK async bridging**: Improved `_run_sync()` with cross-thread `run_coroutine_threadsafe` fallback alongside existing `nest_asyncio` for same-thread reentrant calls.
- **Bounded agentic loops**: Anthropic Tools and Claude Agent SDK `while True:` loops replaced with `for _iteration in range(15):`. Added `timeout=60.0` to API calls. Fallback message when max iterations exceeded.

### Critical: Fix Tool Execution

- **Tool-use emphasis**: All 8 agent templates now append "IMPORTANT: You MUST use the available tools to query the knowledge graph..." to the domain system prompt.
- **PydanticAI**: Added `retries=2` to Agent constructor for transient failure recovery.
- **OpenAI Agents JSON leak**: Streaming now filters `response.output_text.delta` events only, skipping `response.function_call_arguments.delta` that leaked raw JSON into the text stream.

### Frontend Fixes

- **Chat history scoping**: `STORAGE_KEY` and `SESSION_KEY` now include `DOMAIN.id` to prevent cross-app pollution when running multiple domain apps.
- **SSR hydration fix**: Deferred `sessionStorage` reads to `useEffect` instead of `useState` initializer. Added `hydrated` state.
- **Send button**: Increased from `size="sm"` to `size="md"` with `colorPalette="blue"`.
- **Timeout feedback**: Added elapsed time counter (shown after 3s), reduced visible timeout from 120s to 60s.
- **Retry button**: Error messages now include a "Retry" button that resends the original message.

### Dependencies & CLI

- **neo4j-agent-memory[openai]**: Added `[openai]` extra to fix "OpenAI package not installed" error on `store_message()`.
- **`--reset-database` flag**: New CLI flag that runs `MATCH (n) DETACH DELETE n` before ingestion. Added `reset_neo4j()` to `ingest.py`.

### Static Demo Data Quality

- **Domain-specific name pools**: Added 200+ names across 50+ entity labels (medical diagnoses, financial instruments, software repos, gaming items, etc.) in `LABEL_NAMES` dict in `name_pools.py`.
- **Label-aware ID prefixes**: `LABEL_ID_PREFIXES` maps labels to domain-appropriate prefixes (PAT-, DX-, ACT-, REPO-, etc.).
- **`get_names_for_label()`**: New function that checks `LABEL_NAMES` first, falls back to POLE+O pools.
- **Generator updated**: `_generate_static_entities()` now uses `get_names_for_label()` instead of `get_names_for_pole_type()`.

### Decision Traces Expansion

- **All 22 domains**: Expanded from 3-5 to 8-12 decision traces each. Added ~130 new traces total with domain-specific multi-step reasoning scenarios.

### Streaming Endpoint

- **Overall timeout**: SSE endpoint now has a 300s overall timeout alongside the 120s per-event idle timeout.

### Tests added (26 new → 435 total)

- `TestAsyncBridgingFixes` — CrewAI/Strands use `run_coroutine_threadsafe`, no bare `asyncio.run()`
- `TestMaxIterationGuards` — Anthropic Tools/Claude Agent SDK have bounded iterations
- `TestOpenAIStreamFiltering` — OpenAI agents filter tool argument deltas
- `TestCollectorThreadSafety` — Collector uses `call_soon_threadsafe` and `threading`
- `TestToolPromptSuffix` — All 8 frameworks include tool-use emphasis
- `TestChatHistoryScoping` — Storage keys include `DOMAIN.id`
- `TestHydrationFix` — No direct `sessionStorage` in `useState`, has `hydrated` state
- `TestNeo4jAgentMemoryDeps` — pyproject includes `[openai]` extra
- `TestStreamingEndpointTimeout` — Routes have `overall_timeout`
- `TestDomainSpecificNamePools` — Label names exist and are used correctly

### Files modified

- `src/create_context_graph/templates/backend/shared/context_graph_client.py.j2` — thread-safe collector
- `src/create_context_graph/templates/backend/agents/crewai/agent.py.j2` — async bridging + tool prompt
- `src/create_context_graph/templates/backend/agents/strands/agent.py.j2` — async bridging + tool prompt
- `src/create_context_graph/templates/backend/agents/google_adk/agent.py.j2` — async bridging + tool prompt
- `src/create_context_graph/templates/backend/agents/anthropic_tools/agent.py.j2` — max iterations + tool prompt
- `src/create_context_graph/templates/backend/agents/claude_agent_sdk/agent.py.j2` — max iterations + tool prompt
- `src/create_context_graph/templates/backend/agents/pydanticai/agent.py.j2` — tool prompt + retries
- `src/create_context_graph/templates/backend/agents/openai_agents/agent.py.j2` — JSON leak fix + tool prompt
- `src/create_context_graph/templates/backend/agents/langgraph/agent.py.j2` — tool prompt
- `src/create_context_graph/templates/frontend/components/ChatInterface.tsx.j2` — history scoping, hydration, retry, timeout, send button
- `src/create_context_graph/templates/backend/shared/pyproject.toml.j2` — openai extra
- `src/create_context_graph/templates/backend/shared/routes.py.j2` — overall timeout
- `src/create_context_graph/name_pools.py` — domain-specific name pools
- `src/create_context_graph/generator.py` — label-aware naming
- `src/create_context_graph/cli.py` — `--reset-database` flag
- `src/create_context_graph/ingest.py` — `reset_neo4j()` function
- `src/create_context_graph/domains/*.yaml` — ~130 new decision traces across all 22 domains
- `tests/test_generated_project.py` — 26 new tests

---

## Phase 11 — v0.5.1 Testing Feedback Fixes

Comprehensive end-to-end testing of v0.5.0 across all 9 framework/domain combinations revealed 3 critical framework bugs, data quality issues, and UX improvements. This phase addresses all actionable findings from the testing feedback.

### Critical: Framework Bug Fixes

- **PydanticAI tool serialization**: Changed all `@agent.tool` return types from `list[dict]` to `str` with `json.dumps(result, default=str)`. PydanticAI was the only framework returning raw Neo4j objects, causing silent serialization failures that prevented the LLM from seeing tool results.
- **Google ADK agent name sanitization**: Added `| replace('-', '_')` to the agent name template. Hyphenated domain IDs (e.g., `real-estate`, `financial-services`) produced invalid Python identifiers like `real-estate_agent`, crashing ADK's `LlmAgent` validator.
- **Strands max_tokens configuration**: Added `max_tokens=4096` to `AnthropicModel()` initialization. The Anthropic API requires this parameter; without it, Strands returned a `'max_tokens'` KeyError.

### Cross-Domain Data Isolation

- **Domain property on entities**: Both ingestion paths (MemoryClient and direct driver) now add `domain=ontology.domain.id` to all entity nodes. Enables future domain-scoped queries when sharing a Neo4j instance.
- **CLI ingestion tip**: After `--ingest`, prints "Tip: Use --reset-database if you previously ingested a different domain into this Neo4j instance."
- **Conditional make seed messaging**: Post-scaffold instructions now distinguish between "Seed sample data" (no `--ingest`) and "Re-seed sample data (already ingested)" (with `--ingest`).

### Static Data Quality Improvements

- **12 new property-specific value pools** in `name_pools.py`: `_CURRENCY_POOL` (USD, EUR, GBP...), `_TICKER_POOL` (AAPL, MSFT...), `_DRUG_CLASS_POOL` (Biguanide, ACE Inhibitor...), `_STATUS_POOL`, `_SEVERITY_POOL`, `_LANGUAGE_POOL`, `_COUNTRY_POOL`, `_COMPLAINT_POOL`, `_DISPOSITION_POOL`, `_SPECIALTY_POOL`, plus blood_type and gender handling.
- **Float value clamping**: `confidence`/`score`/`rating` fields clamped to 0.0-1.0 range. `efficiency`/`accuracy`/`utilization` clamped to 60-99%. Prevents absurd values like confidence=552.92.
- **Improved description templates**: Replaced generic "X record for Y. Created as part of the Z management workflow." with varied, natural-sounding descriptions.

### Frontend UX

- **Agent thinking text filter**: New `splitThinkingAndResponse()` function in `ChatInterface.tsx.j2` detects "thinking" patterns (lines starting with "Let me", "I'll", "First, I need to", etc.) and renders them in a collapsible "Show reasoning" `<Collapsible>` section, keeping responses focused.

### Developer Experience

- **HuggingFace warning suppression**: Added `HF_HUB_DISABLE_TELEMETRY=1` to `.env` and `.env.example` templates to suppress unauthenticated Hub warnings on backend startup.

### Tests added (75 new → 510 total)

- `TestCypherQueryValidation` — 66 tests: validates node labels, relationship types, and deprecated syntax across all 22 domain YAMLs' agent_tools Cypher queries
- `TestV051Regressions` — 9 tests: PydanticAI returns `str` not `list[dict]`, Google ADK agent names have no hyphens, Strands has max_tokens, .env has HF telemetry setting, confidence/currency/ticker values are realistic, descriptions have no boilerplate, ChatInterface has thinking filter

### Files modified

- `src/create_context_graph/templates/backend/agents/pydanticai/agent.py.j2` — tool return type `str` + `json.dumps()`
- `src/create_context_graph/templates/backend/agents/google_adk/agent.py.j2` — agent name hyphen sanitization
- `src/create_context_graph/templates/backend/agents/strands/agent.py.j2` — `max_tokens=4096`
- `src/create_context_graph/name_pools.py` — 12 new property pools, float clamping, description improvements
- `src/create_context_graph/ingest.py` — `domain` property on all entities (both ingestion paths)
- `src/create_context_graph/cli.py` — post-ingest tip, conditional `make seed` messaging
- `src/create_context_graph/templates/frontend/components/ChatInterface.tsx.j2` — thinking text filter with collapsible reasoning
- `src/create_context_graph/templates/base/dot_env.j2` — `HF_HUB_DISABLE_TELEMETRY=1`
- `src/create_context_graph/templates/base/dot_env_example.j2` — HF telemetry + token guidance
- `tests/test_ontology.py` — `TestCypherQueryValidation` class (66 tests)
- `tests/test_generated_project.py` — `TestV051Regressions` class (9 tests)

## Phase 12 — v0.6.0 Comprehensive Testing Feedback Fixes

End-to-end testing of v0.5.3 across 9 framework/domain combinations (6 working, 3 broken) revealed framework bugs, data ingestion issues, data quality gaps, and UI/UX improvements. This phase addresses all P0-P2 findings.

### Critical: Framework Fixes

- **CrewAI hanging fix**: Added explicit `llm="anthropic/claude-sonnet-4-20250514"` to `Agent()` constructor — CrewAI was defaulting to OpenAI and hanging when no `OPENAI_API_KEY` was set. Added `ANTHROPIC_API_KEY` environment setup, request-level logging, and reduced timeout from 90s to 60s.
- **Strands serialization fix**: Added `_extract_text()` helper that tries `.text`, `.message.content`, and `str()` fallbacks — handles `ParsedTextBlock` serialization issues from newer Anthropic SDK versions.
- **Google ADK API key support**: Added `google_api_key` field to `ProjectConfig`, `--google-api-key` CLI flag with `GOOGLE_API_KEY` env, wizard prompt when google-adk is selected, and warning when google-adk used without key.

### Critical: Document & Trace Ingestion Fix

The Documents panel and Decision Traces panel appeared empty when using `--ingest` because the two ingestion paths created incompatible node structures:

- **Root cause**: `_ingest_with_memory_client()` stored documents as conversation messages (short-term memory) and traces via the reasoning API, creating different node structures than the `:Document` and `:DecisionTrace`/`:TraceStep` nodes the frontend queries for.
- **Fix**: Both ingestion paths (`_ingest_with_memory_client` and `_ingest_with_driver`) now create `:Document` and `:DecisionTrace`/`:TraceStep` nodes using direct Cypher, matching the `generate_data.py.j2` pattern.
- **Entity MERGE fix**: Direct driver path changed from `MERGE (n:Label {all_props})` to `MERGE (n:Label {name: $name}) SET ...` to prevent duplicate nodes from property mismatches.

### Data Quality

- **Domain-aware base entity pools**: Added `DOMAIN_PERSON_NAMES`, `DOMAIN_ORGANIZATION_NAMES`, `DOMAIN_LOCATION_NAMES`, `DOMAIN_EVENT_NAMES`, `DOMAIN_OBJECT_NAMES`, and `DOMAIN_ROLE_POOL` for 6 domains (healthcare, financial-services, gaming, software-engineering, conservation, data-journalism).
- **Fixed templated property values**: Added property pools for `contraindications`, `dosage_form`, `allergies`, `sector`, `lead_reporter`, `manufacturer`, `mechanism_of_action`, `population_trend`, `habitat` — replacing `"{entity_name} - {PropertyName}"` template pattern.
- **Domain-aware role generation**: `generate_property_value()` for `role`/`title` now checks `DOMAIN_ROLE_POOL` before falling back to generic roles.

### Frontend UI Improvements

- **Chat input redesign**: Bordered container with focus highlight, keyboard shortcut hint ("Enter to send, Shift+Enter for new line"), compact send button (Chakra UI Pro AI template pattern).
- **Suggested questions**: Flat wrapped HStack of pill-shaped buttons with full text (no 60-char truncation), "Try these" label with Sparkles icon.
- **Message avatars**: User/assistant Circle avatars with User/Bot lucide-react icons.
- **Tool progress counter**: Shows "Running tool N of M..." instead of generic "Generating response..."

### CLI

- **`--demo` convenience flag**: Shortcut for `--reset-database --demo-data --ingest`
- **`--google-api-key` flag**: New CLI flag with `GOOGLE_API_KEY` env variable support

### Tests added (35 new → 545 total)

- `TestV060GoogleApiKey` — 2 tests: .env and .env.example include GOOGLE_API_KEY
- `TestV060CrewAIFix` — 2 tests: explicit LLM config, logging
- `TestV060StrandsFix` — 1 test: _extract_text helper
- `TestV060DomainAwareNamePools` — 8 tests: healthcare person names, contraindications, dosage_form, allergies, sector, domain roles, population_trend
- `TestV060ChatInterfaceUI` — 5 tests: avatars, keyboard hints, no truncation, sparkles icon, tool progress
- `TestGoogleApiKey` in test_config.py — 2 tests

### Files modified

- `src/create_context_graph/config.py` — `google_api_key` field
- `src/create_context_graph/cli.py` — `--google-api-key`, `--demo` flags, google-adk warning
- `src/create_context_graph/wizard.py` — Google API key prompt, summary display
- `src/create_context_graph/renderer.py` — pass `google_api_key` to template context
- `src/create_context_graph/ingest.py` — direct Cypher for documents/traces in both paths, entity MERGE fix
- `src/create_context_graph/name_pools.py` — domain-aware base pools, 9 new property pools, domain-aware roles
- `src/create_context_graph/generator.py` — pass `domain_id` to name pool functions
- `src/create_context_graph/templates/backend/agents/strands/agent.py.j2` — `_extract_text()` helper
- `src/create_context_graph/templates/backend/agents/crewai/agent.py.j2` — explicit LLM, env setup, logging
- `src/create_context_graph/templates/base/dot_env.j2` — `GOOGLE_API_KEY`
- `src/create_context_graph/templates/base/dot_env_example.j2` — `GOOGLE_API_KEY` with comment
- `src/create_context_graph/templates/frontend/components/ChatInterface.tsx.j2` — avatars, input redesign, suggested questions, progress counter
- `tests/test_config.py` — `TestGoogleApiKey`
- `tests/test_generated_project.py` — 5 new test classes

## Phase 13 — v0.6.1 Stability, Data Quality & Tool Coverage

Comprehensive v0.6.0 testing revealed dependency issues, data quality gaps, missing tool archetypes, and frontend UX improvements. This phase addresses all findings across v0.6.1 (bug fixes), v0.6.2 (data quality), and v0.7.0 (features + docs) in a single release.

### Critical Bug Fixes

- **CrewAI `[anthropic]` dependency**: Changed `crewai>=0.1` to `crewai[anthropic]>=0.1` in `config.py` FRAMEWORK_DEPENDENCIES. The crewai agent template uses Anthropic's Claude model, which requires the extra.
- **CLI auto-slug without PROJECT_NAME**: When `--domain` and `--framework` flags are provided without a positional project name, the CLI now auto-generates a slug (e.g., `healthcare-pydanticai-app`). Added TTY detection with helpful error messages for CI/CD.

### Data Quality

- **Document Markdown format**: Static document content now uses `## Heading` instead of RST `===`/`---`. DocumentBrowser renders with ReactMarkdown.
- **Entity-derived document titles**: Titles reference primary entities ("Discharge Summary: Maria Elena Gonzalez") instead of sequential numbers.
- **POLE-type-aware entity descriptions**: Replaced "Comprehensive patient profile for..." with role/industry-specific descriptions using domain pools.
- **Domain-aware Organization.industry**: Added `DOMAIN_INDUSTRY_POOL` for all 22 domains (healthcare → "Hospital Systems", not "Technology").
- **Realistic decision trace observations**: Now reference actual entity names and vary by action type.
- **Improved thinking text filter**: Added `CONTINUATION_PATTERNS` to catch multi-sentence thinking blocks.

### Agent Tool Coverage

- **`list_*` and `get_*_by_id` tools for all 22 domains**: Every domain now has aggregate listing and direct ID lookup tools alongside existing search/analysis tools. Each domain has 7-8+ tools (up from 5-6).
- **Gaming `get_top_players`**: Domain-specific aggregate tool sorting by level.

### Frontend Features

- **"Ask about this" button**: Clicking a graph node shows a button that sends "Tell me about {entity}" to the chat. Wired via `externalInput` prop from ContextGraphView → page.tsx → ChatInterface.
- **Node hover tooltips**: Full name, labels, and top 5 properties shown on hover.
- **Health polling 30s → 60s**: Reduced unnecessary traffic.
- **Mobile-responsive hint text**: Keyboard shortcut hint hidden on small screens.
- **Suggested question maxW**: Pill buttons capped at 320px.
- **Scrollable label badges**: Label filter badges scroll when they overflow (maxH 180px).
- **Seed constraint fix**: `generate_data.py.j2` uses `ON CREATE SET / ON MATCH SET` to avoid constraint violations.

### Documentation

- **4 new docs pages**: `use-neo4j-aura.md`, `use-docker.md`, `why-context-graphs.md`, `framework-comparison.md`
- **Updated sidebars.ts**: All new pages added to Docusaurus navigation.

### Tests added (57 new → 602 total)

- `test_crewai_includes_anthropic_extra` — verifies crewai dependency has anthropic extra
- `test_no_project_name_auto_generates_slug` — verifies CLI auto-slug generation

### Files modified

- `src/create_context_graph/config.py` — crewai[anthropic] dependency
- `src/create_context_graph/cli.py` — auto-slug generation, TTY detection
- `src/create_context_graph/generator.py` — Markdown documents, entity-derived titles, realistic observations
- `src/create_context_graph/name_pools.py` — DOMAIN_INDUSTRY_POOL, _generate_description, _PERSON_LABELS, _ORGANIZATION_LABELS
- `src/create_context_graph/templates/backend/shared/generate_data.py.j2` — ON CREATE/MATCH SET
- `src/create_context_graph/templates/frontend/components/ChatInterface.tsx.j2` — thinking filter, externalInput, responsive hint
- `src/create_context_graph/templates/frontend/components/ContextGraphView.tsx.j2` — tooltips, ask-about button, scrollable badges
- `src/create_context_graph/templates/frontend/components/DocumentBrowser.tsx.j2` — ReactMarkdown rendering
- `src/create_context_graph/templates/frontend/app/page.tsx.j2` — askAbout wiring, 60s health polling
- All 22 domain YAML files — list_* and get_*_by_id tools added
- `docs/sidebars.ts` — 4 new pages
- `docs/docs/how-to/use-neo4j-aura.md` — new
- `docs/docs/how-to/use-docker.md` — new
- `docs/docs/explanation/why-context-graphs.md` — new
- `docs/docs/reference/framework-comparison.md` — new

---

## Phase 14 — v0.7.1 Testing Feedback: Embedding Regression, Data Quality & Docs

Comprehensive v0.7.0 testing revealed 2 critical regressions, data quality gaps, missing documentation, and UX improvements. This phase addresses all findings.

### Critical Fixes (P0)

- **neo4j-agent-memory embedding regression**: Removed `[openai]` extra from generated `pyproject.toml`, added `sentence-transformers>=2.0` dependency. `MemorySettings` now auto-detects: uses local `sentence_transformers`/`all-MiniLM-L6-v2` (384 dims) by default, upgrades to OpenAI `text-embedding-3-small` (1536 dims) if `OPENAI_API_KEY` is set. Conversation memory works out of the box with no API key.
- **openai-agents API key warning**: CLI now warns when `--framework openai-agents` is used without `--openai-api-key`. Wizard prompt text updated to indicate "required" for this framework.

### Data Quality (P1)

- **67 missing LABEL_NAMES**: Added name pools for all 67 entity labels that were falling back to generic "Label 1" names. `LABEL_NAMES` now has 118 entries (up from 51) covering every entity type across all 22 domain YAMLs.
- **Post-generation value clamping**: Added `_validate_and_clamp()` in `generator.py` with 28 property range rules (price_per_night: $30-$2000, duration_hours: 0.25-24, etc.) and taxonomy class correction (species → correct class mapping).
- **POLE-type entity descriptions**: Added `_LOCATION_LABELS`, `_EVENT_LABELS`, `_OBJECT_LABELS` sets (parallel to existing Person/Organization) plus 7 label-specific description overrides (Medication, Permit, Sensor, Equipment, Paper, Model, Species).
- **digital-twin fixture fix**: Fixed label casing (UPPERCASE → PascalCase) to match YAML schema.
- **Domain-scoped MERGE keys**: Changed entity MERGE from `{name: $name}` to `{name: $name, domain: $domain}` in both `generate_data.py.j2` and `ingest.py` to prevent constraint violations when sharing a Neo4j instance across domains.

### google-adk Error Guard (P2)

- Added `try/except AttributeError` around `runner.run_async()` in both `handle_message` and `handle_message_stream` to handle SDK cleanup errors when `_async_httpx_client` was never initialized.

### Documentation

- **Quick-Start page** (`docs/docs/quick-start.md`): 5-step guide with sidebar link.
- **use-neo4j-local guide** (`docs/docs/how-to/use-neo4j-local.md`): 3 setup options (npx, Desktop, Docker).
- **switch-frameworks slug fix**: Added `slug: switch-frameworks` to fix 404.
- **Domain catalog** (`docs/docs/reference/domain-catalog.md`): Auto-generated table of all 22 domains with entity types, tool counts, sample questions.
- **Architecture diagram**: Mermaid flowchart added to `docs/docs/intro.md`.
- **Updated sidebars.ts**: Added quick-start, use-neo4j-local, domain-catalog to navigation.

### Frontend UX

- **Status indicator**: Enlarged from 8px to 12px, added text label ("Connected"/"Degraded"/"Offline").
- **Health check retry**: Initial load retries 3 times with exponential backoff (1s/2s/4s) to prevent "Internal Server Error" on first page load.
- **Empty graph state**: Larger icon, descriptive heading ("Your knowledge graph will appear here"), actionable guidance text.

### Tests added (89 new → 691 total)

- `tests/test_fixtures.py` (88 tests): Fixture schema alignment (required properties, agent tool property references, label coverage), data quality validation (numeric ranges)
- `test_pyproject_has_sentence_transformers` — verifies no `[openai]` extra
- `test_context_graph_client_has_embedding_config` — verifies embedding provider selection logic

### Files modified

- `src/create_context_graph/templates/backend/shared/pyproject.toml.j2` — removed `[openai]` extra, added sentence-transformers
- `src/create_context_graph/templates/backend/shared/context_graph_client.py.j2` — embedding provider auto-detection
- `src/create_context_graph/templates/base/dot_env_example.j2` — clarified OPENAI_API_KEY is optional
- `src/create_context_graph/cli.py` — openai-agents warning
- `src/create_context_graph/wizard.py` — framework-specific OpenAI key prompt
- `src/create_context_graph/name_pools.py` — 67 new LABEL_NAMES, 3 new label sets, 7 description overrides
- `src/create_context_graph/generator.py` — `_validate_and_clamp()`, `_PROPERTY_CLAMP_RANGES`, `_TAXONOMY_CLASS_MAP`
- `src/create_context_graph/ingest.py` — domain-scoped MERGE keys
- `src/create_context_graph/templates/backend/shared/generate_data.py.j2` — domain-scoped MERGE keys
- `src/create_context_graph/templates/backend/agents/google_adk/agent.py.j2` — AttributeError guard
- `src/create_context_graph/templates/frontend/app/page.tsx.j2` — health retry, larger status dot
- `src/create_context_graph/templates/frontend/components/ContextGraphView.tsx.j2` — improved empty state
- `src/create_context_graph/fixtures/digital-twin.json` — fixed label casing
- `tests/test_generated_project.py` — updated embedding tests
- `tests/test_fixtures.py` — new cross-validation test suite
- `docs/docs/quick-start.md` — new
- `docs/docs/how-to/use-neo4j-local.md` — new
- `docs/docs/reference/domain-catalog.md` — new
- `docs/docs/how-to/switch-agent-frameworks.md` — slug fix
- `docs/docs/intro.md` — architecture diagram, updated links
- `docs/sidebars.ts` — 3 new pages

---

## Phase 15 — Linear Data Import Connector (v0.8.2)

Real-world project data import from Linear. First connector to import graph-native project management data (issues, projects, cycles, teams, users, labels, workflow states) with full relationship fidelity.

### What was built

#### Linear connector
- `linear_connector.py` implementing `BaseConnector` ABC with GraphQL client
- Cursor-based pagination against Linear's GraphQL API (`https://api.linear.app/graphql`)
- Rate limiting via `X-RateLimit-Requests-Remaining` header with adaptive sleep
- 8 entity types mapped to POLE+O model (Issue, Project, Cycle, Team, Person, Label, WorkflowState, Comment)
- 16 relationship types (ASSIGNED_TO, CREATED_BY, BELONGS_TO_PROJECT, BELONGS_TO_TEAM, IN_CYCLE, HAS_STATE, HAS_LABEL, CHILD_OF, HAS_COMMENT, AUTHORED_BY, MEMBER_OF, LEADS, CONTRIBUTED_BY, CYCLE_FOR, STATE_OF)
- Issue descriptions exported as documents for RAG/vector search
- Deduplication of users, labels, and workflow states across paginated issue responses
- Optional comment import (gated behind `include_comments` kwarg)
- Team key filtering (`--linear-team ENG` imports only that team's data)
- No external dependency — uses `urllib.request` from stdlib

#### CLI integration
- `--connector linear` flag (works with existing `--connector` multiple=True pattern)
- `--linear-api-key` flag (envvar `LINEAR_API_KEY`)
- `--linear-team` flag (envvar `LINEAR_TEAM`) for team filtering
- Warning when `--connector linear` is used without an API key

#### Generated project integration
- `linear_connector.py.j2` Jinja2 template for standalone connector in generated projects
- `import_data.py.j2` updated with Linear credential wiring
- `.env` and `.env.example` templates include `LINEAR_API_KEY` and `LINEAR_TEAM` (conditional)
- `config.py.j2` includes `linear_api_key` and `linear_team` settings fields (conditional)

### Tests added (14 new → 705 total)

- `test_credential_prompts` — verify api_key and team_key prompts
- `test_authenticate_success/missing_key/invalid_key` — auth validation
- `test_fetch_entity_mapping` — verify all 7 entity labels present
- `test_fetch_entity_counts` — correct counts for mocked workspace
- `test_fetch_relationships` — verify all relationship types
- `test_fetch_child_of_relationship` — sub-issue hierarchy
- `test_fetch_documents` — issue descriptions as documents
- `test_fetch_deduplication` — users/labels not duplicated
- `test_fetch_team_filter/team_filter_not_found` — team key filtering
- `test_issue_name_format` — `"ENG-101 Fix login bug"` format
- `test_priority_labels` — priority mapping (0-4 → human-readable)

### Files created

- `src/create_context_graph/connectors/linear_connector.py`
- `src/create_context_graph/templates/backend/connectors/linear_connector.py.j2`

### Files modified

- `src/create_context_graph/connectors/__init__.py` — register LinearConnector
- `src/create_context_graph/cli.py` — `--linear-api-key`, `--linear-team` flags + credential wiring
- `src/create_context_graph/renderer.py` — add linear to connector_templates
- `src/create_context_graph/templates/backend/connectors/import_data.py.j2` — Linear block
- `src/create_context_graph/templates/base/dot_env.j2` — conditional Linear env vars
- `src/create_context_graph/templates/base/dot_env_example.j2` — Linear env vars with docs
- `src/create_context_graph/templates/backend/shared/config.py.j2` — Linear settings fields
- `tests/test_connectors.py` — 14 new tests, registry counts 7→8

---

## Summary

| Phase | Description | Status | Tests |
|-------|-------------|--------|-------|
| 1 | Core CLI & Template Engine | **Complete** | 691 passing |
| 2 | Domain Expansion & Data Generation | **Complete** | (included above) |
| 3 | Framework Templates & Frontend | **Complete** | (included above) |
| 4 | SaaS Import & Custom Domains | **Complete** | (included above) |
| 5 | Polish, Testing & Launch | **Complete** | (included above) |
| — | Data Quality & UI Enhancements | **Complete** | (included above) |
| — | Graph Visualization & Agent Fixes | **Complete** | (included above) |
| 6 | Memory Integration, Multi-Turn & DX | **Complete** | (included above) |
| 7 | Hardening, Security & DX | **Complete** | (included above) |
| 8 | Streaming Chat & Real-Time Tool Viz | **Complete** | (included above) |
| 9 | QA Hardening & DX Polish | **Complete** | (included above) |
| 10 | Framework Reliability, Data Quality & UX | **Complete** | (included above) |
| 11 | v0.5.1 Testing Feedback Fixes | **Complete** | (included above) |
| 12 | v0.6.0 Comprehensive Testing Feedback | **Complete** | (included above) |
| 13 | v0.6.1 Stability, Data Quality & Tools | **Complete** | (included above) |
| 14 | v0.7.1 Embedding Regression, Data Quality & Docs | **Complete** | (included above) |
| 15 | Linear Data Import Connector | **Complete** | 705 passing |
