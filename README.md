# Create Context Graph

[![Neo4j Labs](https://img.shields.io/badge/Neo4j_Labs-blue?logo=neo4j)](https://neo4j.com/labs/)
[![Docs](https://img.shields.io/badge/docs-docusaurus-green)](https://create-context-graph.dev/)

> **Neo4j Labs Project** — This project is part of [Neo4j Labs](https://neo4j.com/labs/). It is maintained by Neo4j staff and the community, but not officially supported. For help, use [GitHub Issues](https://github.com/neo4j-labs/create-context-graph/issues) or the [Neo4j Community Forum](https://community.neo4j.com/).

Interactive CLI scaffolding tool that generates fully-functional, domain-specific context graph applications. Pick your industry domain, pick your agent framework, and get a complete full-stack app in under 5 minutes.

<p align="center">
  <img src="docs/static/img/app-three-panel.png" alt="Generated app: chat interface, graph visualization, and document browser" width="800" />
</p>

```bash
# Python — NAMS-default (hosted memory)
uvx create-context-graph my-app --domain healthcare --framework strands --nams-api-key sk-nams-...

# Self-hosted Neo4j with full demo fixtures
uvx create-context-graph my-app --domain healthcare --framework pydanticai --self-hosted --demo

# Node.js / interactive wizard
npx create-context-graph
```

## What It Does

Create Context Graph walks you through an interactive wizard and generates a complete project:

- **FastAPI backend** with an AI agent configured for your domain, powered by [neo4j-agent-memory](https://github.com/neo4j-labs/agent-memory) v0.4 for multi-turn conversations with automatic entity extraction. Memory backend is configurable: hosted [NAMS](https://memory.neo4jlabs.com) (default) or self-hosted bolt Neo4j (`--self-hosted`).
- **LiteLLM provider injection** for the memory layer — pick any LLM + embedding provider via `MEMORY_LLM` / `MEMORY_EMBEDDING` env vars (Anthropic, OpenAI, Bedrock, Vertex AI, Ollama, Groq, Together, …). Native adapters resolve first; everything else routes through LiteLLM.
- **Next.js + Chakra UI v3 frontend** with streaming chat (Server-Sent Events), real-time tool call visualization (Timeline with live spinners), interactive graph visualization (schema view, double-click expand, drag/zoom, property panel), entity detail panel, document browser, and decision trace viewer
- **Neo4j schema** with domain-specific constraints, indexes, and GDS projections (self-hosted mode)
- **Rich demo data** — LLM-generated entities, relationships, professional documents (discharge summaries, trade confirmations, lab reports), and multi-step decision traces
- **SaaS data import** — connect GitHub, Slack, Gmail, Jira, Notion, Google Calendar, Salesforce, Linear, Google Workspace, Claude Code, Claude AI, ChatGPT, or local files
- **Custom domains** — describe your domain in plain English and the LLM generates a complete ontology
- **Domain-specific agent tools** with Cypher queries tailored to your industry
- **MCP server for Claude Desktop** — optionally generates an MCP server config so Claude Desktop can query the same knowledge graph (`--with-mcp`)

```
  Creating context graph application...

  Domain:     Wildlife Management
  Framework:  PydanticAI
  Data:       Demo (synthetic)
  Neo4j:      Docker (neo4j://localhost:7687)

  [1/6] Generating domain ontology...          ✓
  [2/6] Creating project scaffold...           ✓
  [3/6] Configuring agent tools & system prompt...  ✓
  [4/6] Generating synthetic documents (25 docs)... ✓
  [5/6] Writing fixture data...                ✓
  [6/6] Bundling project...                    ✓

  Done! Your context graph app is ready.

  cd my-app
  make install && make start
```

## Quick Start

There are two flows depending on what you want:

- **NAMS (default)** — hosted memory backend. No Neo4j to install or operate. Graph starts empty; the agent populates it as you chat.
- **Self-hosted** (`--self-hosted`) — bolt Neo4j you run yourself (Aura, Docker, neo4j-local). Full demo fixtures available via `make seed`.

### Prerequisites

- Python 3.11+ (with [uv](https://docs.astral.sh/uv/) recommended)
- Node.js 18+ (for the frontend)
- **NAMS path:** a NAMS API key from [memory.neo4jlabs.com](https://memory.neo4jlabs.com)
- **Self-hosted path:** Neo4j 5+ (Docker, Aura, or local install)
- **Either path:** `ANTHROPIC_API_KEY` for the agent (or `OPENAI_API_KEY`/`GOOGLE_API_KEY` depending on framework)

### NAMS path (default, hosted memory)

```bash
uvx create-context-graph my-app \
  --domain healthcare \
  --framework strands \
  --nams-api-key sk-nams-...

cd my-app
echo 'ANTHROPIC_API_KEY=sk-ant-...' >> .env   # Strands needs Anthropic
make install
make start
```

Open [http://localhost:3000](http://localhost:3000). Graph starts empty — chat with the agent and entities populate via auto-extraction.

### Self-hosted path (bolt Neo4j + full demo data)

```bash
uvx create-context-graph my-app \
  --domain healthcare \
  --framework pydanticai \
  --self-hosted \
  --demo

cd my-app
echo 'ANTHROPIC_API_KEY=sk-ant-...' >> .env
make install
make docker-up   # or: make neo4j-start  (for neo4j-local)
make seed
make start
```

Open [http://localhost:3000](http://localhost:3000). Pre-populated graph with ~85 entities, 180 relationships, 25 documents, and decision traces.

### Other scaffold patterns

```bash
# Interactive wizard (asks 6 prompts, autocomplete domain picker)
uvx create-context-graph

# Custom domain from description
uvx create-context-graph my-app \
  --custom-domain "veterinary clinic management" \
  --framework pydanticai \
  --self-hosted --demo \
  --anthropic-api-key $ANTHROPIC_API_KEY

# Import real data from SaaS services
uvx create-context-graph my-app \
  --domain personal-knowledge --framework pydanticai --self-hosted \
  --connector github --connector slack

# With MCP server for Claude Desktop (works on either backend)
uvx create-context-graph my-app \
  --domain healthcare --framework strands \
  --nams-api-key sk-nams-... --with-mcp

# Pick a specific LiteLLM provider for memory entity extraction
uvx create-context-graph my-app \
  --domain healthcare --framework strands --nams-api-key sk-nams-... \
  --memory-llm bedrock/anthropic.claude-3-haiku-20240307-v1:0 \
  --memory-embedding sentence-transformers/all-MiniLM-L6-v2
```

### Explore the running app

- **Frontend:** http://localhost:3000 — Chat with the AI agent, explore the knowledge graph
- **Backend API:** http://localhost:8000/docs — FastAPI auto-generated docs
- **Health endpoint:** http://localhost:8000/health — reports the active memory backend
- **NAMS dashboard:** [memory.neo4jlabs.com](https://memory.neo4jlabs.com) (NAMS path only)
- **Neo4j Browser:** http://localhost:7474 (self-hosted Docker / neo4j-local only)

### NAMS write-path caveats (v0.4)

The NAMS REST API has a narrower write surface than bolt Cypher. The CLI and the generated `import_data.py` work around it with a hybrid write shape:

- **Relationships encoded as `ccg-edges` YAML blocks** inside each source entity's `description`. The frontend graph view parses them out and renders edges; a future migration replays them as native edges when NAMS adds `add_relationship`.
- **Entity properties collapse into `description`** as a markdown block (NAMS REST accepts only `name`/`type`/`description`).
- **Documents are dual-tracked** — `long_term.add_entity(type=OBJECT)` (queryable, matches bolt `:Document`) AND `short_term.add_message(role="document")` (extraction fuel).
- **No preferences or facts** via REST. `auto_preferences` forced off on NAMS.
- **GDS endpoints** and arbitrary Cypher writes return 501 on NAMS.

For native graph edges + GDS + arbitrary Cypher, use `--self-hosted --demo`.

## Supported Domains

27 industry domains, each with a purpose-built ontology, sample data, agent tools, and demo scenarios:

| Domain | Key Entities | Domain | Key Entities |
|--------|-------------|--------|-------------|
| Financial Services | Account, Transaction, Decision, Policy | Real Estate | Property, Listing, Agent, Inspection |
| Healthcare | Patient, Provider, Diagnosis, Treatment | Vacation & Hospitality | Resort, Booking, Guest, Activity |
| Retail & E-Commerce | Customer, Product, Order, Review | Oil & Gas | Well, Reservoir, Equipment, Permit |
| Manufacturing | Machine, Part, WorkOrder, Supplier | Data Journalism | Source, Story, Claim, Investigation |
| Scientific Research | Researcher, Paper, Dataset, Grant | Trip Planning | Destination, Hotel, Activity, Itinerary |
| GenAI / LLM Ops | Model, Experiment, Prompt, Evaluation | GIS & Cartography | Feature, Layer, Survey, Boundary |
| Agent Memory | Agent, Conversation, Memory, ToolCall | Wildlife Management | Species, Sighting, Habitat, Camera |
| Gaming | Player, Character, Quest, Guild | Conservation | Site, Species, Program, Funding |
| Personal Knowledge | Note, Contact, Project, Topic | Golf & Sports Mgmt | Course, Player, Round, Tournament |
| Digital Twin | Asset, Sensor, Reading, Alert | Software Engineering | Repository, Issue, PR, Deployment |
| Product Management | Feature, Epic, UserPersona, Metric | Hospitality | Hotel, Room, Reservation, Service |
| Options Intelligence | Underlying, OptionsContract, Regime, KeyLevel | Legal | Case, Matter, Contract, Filing |
| Education | Student, Instructor, Course, Assessment | Cybersecurity | Asset, Vulnerability, Alert, Incident |
| Government | Agency, Program, Policy, Regulation | | |

```bash
# List all available domains
create-context-graph --list-domains
```

**Custom domains:** Don't see your industry? Select "Custom (describe your domain)" in the wizard or use `--custom-domain "your description"`. The LLM generates a complete ontology with entity types, relationships, agent tools, and more.

## SaaS Data Connectors

<p align="center">
  <img src="docs/static/img/connector-data-flow.png" alt="SaaS connector data flow into Neo4j knowledge graph" width="700" />
</p>

Import real data from your existing tools instead of (or in addition to) synthetic demo data:

| Service | What's Imported | Auth |
|---------|----------------|------|
| **GitHub** | Issues, PRs, commits, contributors | Personal access token |
| **Notion** | Pages, databases, users | Integration token |
| **Jira** | Issues, sprints, users | API token |
| **Slack** | Channel messages, threads, users | Bot OAuth token |
| **Gmail** | Emails (last 30 days) | Google Workspace CLI or OAuth2 |
| **Google Calendar** | Events, attendees (last 90 days) | Google Workspace CLI or OAuth2 |
| **Salesforce** | Accounts, contacts, opportunities | Username/password |
| **Linear** | Issues, projects, cycles, teams, users, labels, comments, milestones, initiatives, attachments + decision traces from history | Personal API key |
| **Google Workspace** | Drive files, comment threads (as decision traces), revisions, Drive Activity, Calendar events, Gmail metadata | Google OAuth 2.0 |
| **Claude Code** | Session history, messages, tool calls, files, decisions, preferences, errors | None (local files) |
| **Claude AI** | Conversations, messages, tool calls, thinking traces from Claude AI web/app export | None (local file) |
| **ChatGPT** | Conversations, messages, tool results from ChatGPT data export | None (local file) |

The **Google Workspace connector** extracts resolved comment threads from Google Docs as first-class decision traces — capturing the question, deliberation, resolution, and participants. Combined with Linear, it provides the full decision lifecycle: from meeting discussion to code execution.

The **Claude Code connector** reads your local session history from `~/.claude/projects/` — no API keys needed. It extracts decision traces from user corrections and error-resolution cycles, identifies developer preferences from explicit statements and behavioral patterns, and automatically redacts secrets before storage.

The **Claude AI** and **ChatGPT** connectors import your conversation exports directly from the official data export features. Export your data from Settings, pass the `.zip` file to the CLI with `--import-type claude-ai` or `--import-type chatgpt`, and get a fully populated context graph from your real conversations — no API keys needed.

Connectors run at scaffold time to populate initial data. They're also generated into your project so you can re-import with `make import`:

```bash
cd my-app
make import            # Re-import from connected services
make import-and-seed   # Import and seed into Neo4j
```

## Agent Frameworks

Select your preferred agent framework at project creation time:

| Framework | Description |
|-----------|-------------|
| **PydanticAI** | Structured tool definitions with Pydantic models and `RunContext` | Full streaming | `ANTHROPIC_API_KEY` |
| **Claude Agent SDK** | Anthropic tool-use with agentic loop | Full streaming | `ANTHROPIC_API_KEY` |
| **OpenAI Agents SDK** | `@function_tool` decorators with `Runner.run()` | Full streaming | `OPENAI_API_KEY` |
| **LangGraph** | Stateful graph-based agent workflow with `create_react_agent()` | Full streaming | `ANTHROPIC_API_KEY` |
| **CrewAI** | Multi-agent crew with role-based tools | Tool streaming | `ANTHROPIC_API_KEY` |
| **Strands** | Tool-use agents with Anthropic model | Tool streaming | `ANTHROPIC_API_KEY` |
| **Google ADK** | Gemini agents with `FunctionTool` calling | Full streaming | `GOOGLE_API_KEY` |
| **Anthropic Tools** | Modular tool registry with Anthropic API agentic loop | Full streaming | `ANTHROPIC_API_KEY` |

All frameworks share the same FastAPI HTTP layer, Neo4j client, and frontend. Only the agent implementation differs. "Full streaming" means token-by-token text + real-time tool calls. "Tool streaming" means real-time tool calls with text delivered at the end.

> **Note on memory providers:** Conversation memory uses local `sentence-transformers/all-MiniLM-L6-v2` embeddings by default — no API key required. Override with `MEMORY_EMBEDDING` (LiteLLM provider string) for OpenAI, Vertex AI, Bedrock, or others. The entity-extraction LLM defaults to `anthropic/claude-haiku-4-5` when `ANTHROPIC_API_KEY` is set, or `openai/gpt-4o-mini` if only `OPENAI_API_KEY` is set. Override with `MEMORY_LLM` for full control. See [Configure Memory Providers](docs/docs/how-to/configure-memory-providers.md).

## Generated Project Structure

<p align="center">
  <img src="docs/static/img/ontology-pipeline.png" alt="From domain YAML through Jinja2 templates to generated code" width="750" />
</p>

A single domain YAML drives the entire generated application — schema, models, agent tools, and visualization — through the Jinja2 template engine.

```
my-app/
├── backend/
│   ├── app/
│   │   ├── main.py                # FastAPI application
│   │   ├── agent.py               # AI agent (framework-specific)
│   │   ├── config.py              # Settings from .env
│   │   ├── routes.py              # REST API endpoints
│   │   ├── models.py              # Pydantic models (from ontology)
│   │   ├── context_graph_client.py # Neo4j CRUD operations
│   │   ├── memory.py              # Memory integration (MemoryIntegration)
│   │   ├── gds_client.py          # Graph Data Science algorithms
│   │   ├── vector_client.py       # Vector search
│   │   └── connectors/            # SaaS connectors (if selected)
│   ├── scripts/
│   │   ├── generate_data.py       # Data seeding script
│   │   └── import_data.py         # SaaS import script (if connectors selected)
│   └── pyproject.toml
├── frontend/
│   ├── app/                       # Next.js pages
│   ├── components/
│   │   ├── ChatInterface.tsx      # Streaming AI chat (SSE) with real-time tool calls + graph data flow
│   │   ├── ContextGraphView.tsx   # Interactive NVL graph (schema view, expand, drag/zoom, properties)
│   │   ├── DecisionTracePanel.tsx  # Reasoning trace viewer with step details
│   │   ├── DocumentBrowser.tsx    # Document browser with template filtering
│   │   └── Provider.tsx           # Chakra UI v3 provider
│   ├── lib/config.ts              # Domain configuration
│   ├── theme/index.ts             # Chakra theme with domain colors
│   └── package.json
├── cypher/
│   ├── schema.cypher              # Constraints & indexes
│   └── gds_projections.cypher     # GDS algorithm config
├── data/
│   ├── ontology.yaml              # Domain ontology definition
│   └── fixtures.json              # Pre-generated sample data
├── .env                           # Neo4j + API key configuration
├── .env.example                   # Configuration template (tracked in git)
├── .dockerignore                  # Docker build context exclusions
├── docker-compose.yml             # Local Neo4j instance (Docker mode only)
├── Makefile                       # start, seed, reset, install, test, test-connection, lint
├── mcp/                           # MCP server config (only if --with-mcp)
└── README.md                      # Domain-specific documentation (with framework docs + troubleshooting)
```

## CLI Reference

```bash
create-context-graph [PROJECT_NAME] [OPTIONS]

Arguments:
  PROJECT_NAME              Project name (optional — auto-generated from domain+framework if omitted)

Options:
  --domain TEXT             Domain ID (e.g., healthcare, gaming)
  --framework TEXT          Agent framework (strands [default], pydanticai, claude-agent-sdk, openai-agents, langgraph, crewai, google-adk, anthropic-tools)
  --self-hosted             Use self-hosted Neo4j (bolt) instead of NAMS hosted memory
  --nams-api-key TEXT       NAMS API key [env: MEMORY_API_KEY] — obtain at https://memory.neo4jlabs.com
  --nams-endpoint TEXT      Override NAMS endpoint URL (default: https://memory.neo4jlabs.com/v1)
  --memory-llm TEXT         LiteLLM provider string for memory entity extraction (e.g. anthropic/claude-haiku-4-5)
  --memory-embedding TEXT   LiteLLM provider string for memory embeddings (e.g. sentence-transformers/all-MiniLM-L6-v2)
  --demo-data               Generate synthetic demo data
  --custom-domain TEXT      Generate custom domain from description (requires --anthropic-api-key)
  --connector TEXT          SaaS connector to enable; repeatable (github, slack, jira, notion, gmail, gcal, salesforce, linear, google-workspace, claude-code, claude-ai, chatgpt)
  --import-type TEXT        Chat history import: claude-ai or chatgpt (requires --import-file)
  --import-file PATH        Path to chat export file (.zip, .json, .jsonl)
  --import-depth TEXT       Import extraction depth: fast (default) or deep
  --import-filter-after TEXT Only import conversations after this date (ISO 8601)
  --import-filter-before TEXT Only import conversations before this date (ISO 8601)
  --import-filter-title TEXT Only import conversations matching title pattern (regex)
  --import-max-conversations INT Max conversations to import, 0=all (default: 0)
  --linear-api-key TEXT    Linear API key (required for --connector linear) [env: LINEAR_API_KEY]
  --linear-team TEXT       Linear team key to filter import (e.g., ENG) [env: LINEAR_TEAM]
  --gws-folder-id TEXT     Google Drive folder ID to scope import [env: GWS_FOLDER_ID]
  --gws-include-comments / --gws-no-comments  Import comment threads (default: on)
  --gws-include-revisions / --gws-no-revisions  Import revision history (default: on)
  --gws-include-activity / --gws-no-activity  Import Drive Activity (default: on)
  --gws-include-calendar   Import Calendar events (default: off)
  --gws-include-gmail      Import Gmail thread metadata (default: off)
  --gws-since TEXT         Import data since date (ISO format, default: 90 days ago)
  --gws-mime-types TEXT    MIME types to include (default: docs,sheets,slides)
  --gws-max-files INT      Maximum files to import (default: 500)
  --claude-code-scope TEXT Import current project or all (default: current)
  --claude-code-project TEXT Explicit project path to import sessions for
  --claude-code-since TEXT Import sessions since date (ISO format)
  --claude-code-max-sessions INT Max sessions to import, 0=all (default: 0)
  --claude-code-content TEXT Content mode: truncated, full, none (default: truncated)
  --with-mcp                Generate MCP server configuration for Claude Desktop
  --mcp-profile TEXT        MCP tool profile: core (6 tools) or extended (16 tools, default)
  --session-strategy TEXT   Memory session strategy: per_conversation (default), per_day, persistent
  --auto-extract/--no-auto-extract  Auto-extract entities from messages (default: on)
  --auto-preferences/--no-auto-preferences  Auto-detect user preferences (default: on)
  --ingest                  Ingest data into Neo4j after generation
  --neo4j-uri TEXT          Neo4j connection URI [env: NEO4J_URI] (--self-hosted only)
  --neo4j-username TEXT     Neo4j username [env: NEO4J_USERNAME] (--self-hosted only)
  --neo4j-password TEXT     Neo4j password [env: NEO4J_PASSWORD] (--self-hosted only)
  --neo4j-aura-env PATH    Path to Neo4j Aura .env file with credentials (--self-hosted only)
  --neo4j-local             Use @johnymontana/neo4j-local for local Neo4j (--self-hosted only)
  --anthropic-api-key TEXT  Anthropic API key for LLM generation [env: ANTHROPIC_API_KEY]
  --openai-api-key TEXT    OpenAI API key for LLM generation [env: OPENAI_API_KEY]
  --google-api-key TEXT    Google/Gemini API key (required for google-adk) [env: GOOGLE_API_KEY]
  --output-dir PATH         Output directory (default: ./<project-name>)
  --demo                    Shortcut for --reset-database --demo-data --ingest
  --reset-database          Clear all Neo4j data before ingesting
  --dry-run                 Preview what would be generated without creating files
  --verbose                 Enable verbose debug output
  --list-domains            List available domains and exit
  --version                 Show version and exit
  --help                    Show help and exit
```

## Context Graph Architecture

<p align="center">
  <img src="docs/static/img/architecture-overview.png" alt="Architecture: generation pipeline and runtime components" width="800" />
</p>

Every generated app demonstrates the three-memory-type architecture from [neo4j-agent-memory](https://github.com/neo4j-labs/agent-memory):

<p align="center">
  <img src="docs/static/img/memory-architecture.png" alt="Three memory types: short-term, long-term, and reasoning memory in Neo4j" width="700" />
</p>

- **Short-term memory** — Conversation history and document content stored as messages
- **Long-term memory** — Entity knowledge graph built on the POLE+O model (Person, Organization, Location, Event, Object)
- **Reasoning memory** — Decision traces with full provenance: thought chains, tool calls, causal relationships

This is what makes context graphs different from simple RAG — the agent doesn't just retrieve text, it reasons over a structured knowledge graph with full decision traceability.

With `--with-mcp`, the generated project also includes an MCP server configuration that connects Claude Desktop to the same knowledge graph. This dual-interface architecture means the web app and Claude Desktop share one context graph — entities, conversations, and reasoning traces are available everywhere.

## Development

```bash
# Clone and install
git clone https://github.com/neo4j-labs/create-context-graph.git
cd create-context-graph
uv venv && uv pip install -e ".[dev]"

# Run tests (no Neo4j or API keys required)
source .venv/bin/activate
pytest tests/ -v               # Fast: 1,177 tests
pytest tests/ -v --slow        # Full: 1,398 tests (includes domain x framework matrix + perf + generated project tests)
pytest tests/ --integration    # Integration tests (requires running Neo4j)

# Test a specific scaffold
create-context-graph /tmp/test-app --domain software-engineering --framework pydanticai --demo-data
```

### Makefile Targets

| Target | Description | Requirements |
|--------|-------------|--------------|
| `make test` | Run fast unit tests (1,177 tests) | None |
| `make test-slow` | Full suite including matrix + perf + generated project tests (1,398 tests) | None |
| `make test-matrix` | Domain × framework matrix only (176 combos) | None |
| `make test-coverage` | Tests with HTML coverage report | None |
| `make smoke-test` | E2E smoke tests for 3 key frameworks | Neo4j + LLM API keys |
| `make lint` | Run ruff linter | ruff |
| `make scaffold` | Scaffold a test project to `/tmp/test-scaffold` | None |
| `make build` | Build Python package (sdist + wheel) | None |
| `make docs` | Start Docusaurus dev server | Node.js |

### E2E Smoke Tests

The smoke tests scaffold a real project, install dependencies, start the backend, and send chat prompts to verify the full pipeline works end-to-end. Pass `--backend nams` to test the hosted-memory path (requires `MEMORY_API_KEY` env); the default `bolt` exercises self-hosted Neo4j with full demo fixtures:

```bash
# Run all 3 smoke tests (requires Neo4j + at least one LLM API key)
make smoke-test

# Or run individual framework tests directly (default: --backend bolt)
python scripts/e2e_smoke_test.py --domain financial-services --framework pydanticai --quick
python scripts/e2e_smoke_test.py --domain real-estate --framework google-adk --quick
python scripts/e2e_smoke_test.py --domain trip-planning --framework strands --quick

# Test against NAMS hosted backend (requires MEMORY_API_KEY env)
python scripts/e2e_smoke_test.py --domain healthcare --framework strands --backend nams --quick

# Test all 27 domains with one framework
python scripts/e2e_smoke_test.py --all-domains --framework pydanticai --quick

# Full mode (all prompts per scenario, not just first)
python scripts/e2e_smoke_test.py --domain healthcare --framework claude-agent-sdk
```

**Required environment variables:**
- `NEO4J_URI`, `NEO4J_USERNAME`, `NEO4J_PASSWORD` — Neo4j connection (Aura, Docker, or local) for `--backend bolt`
- `MEMORY_API_KEY` — NAMS API key for `--backend nams`
- `ANTHROPIC_API_KEY` — for Claude-based frameworks (PydanticAI, Claude Agent SDK, Anthropic Tools, Strands, CrewAI)
- `OPENAI_API_KEY` — for OpenAI-based frameworks (OpenAI Agents, LangGraph)
- `GOOGLE_API_KEY` — for Google ADK (Gemini)

### CI Pipeline

GitHub Actions (`.github/workflows/ci.yml`) runs automatically:

| Job | Trigger | Description |
|-----|---------|-------------|
| **test** | All pushes + PRs | Unit tests on Python 3.11 and 3.12 (1,177 tests including security, doc snippets, frontend logic, NAMS adapter, wizard, route integration) |
| **lint** | All pushes + PRs | Ruff linter on `src/` and `tests/` |
| **matrix** | Push to `main` only | Full suite + 176 domain × framework matrix + perf + generated project tests (1,398 tests) |
| **smoke-test** | Push to `main` only | Neo4j integration tests + E2E for all 8 frameworks (scaffold → install → start → chat) |

The smoke-test CI job is gated behind a `SMOKE_TESTS_ENABLED` repository variable. To enable it:

1. Go to **Settings → Variables → Repository variables** and add `SMOKE_TESTS_ENABLED` = `true`
2. Go to **Settings → Secrets → Repository secrets** and add:
   - `NEO4J_URI` — e.g., `neo4j+s://xxxxx.databases.neo4j.io`
   - `NEO4J_USERNAME`
   - `NEO4J_PASSWORD`
   - `ANTHROPIC_API_KEY`
   - `OPENAI_API_KEY`
   - `GOOGLE_API_KEY`

The smoke-test job uses `fail-fast: false` so one framework failure doesn't block the others, and it only runs after the unit test job passes.


The npm package is a thin wrapper that delegates to the Python CLI via `uvx`, `pipx`, or `python3 -m`. It requires Python 3.11+ to be installed.

### Automated Publishing (GitHub Actions)

Both packages are published automatically when you push a version tag:

```bash
# 1. Update version in pyproject.toml and npm-wrapper/package.json
# 2. Commit the version bump (and any CHANGELOG.md update)
# 3. Tag and push
git tag v0.13.0
git push origin v0.13.0
```

This triggers a GitHub Actions workflow, `release.yml` with jobs:
- **publish-pypi** — Builds and publishes to PyPI
- **publish-npm** — Publishes the npm wrapper to npmjs.com
Both use trusted publishing/OIDC.

### Version Bumping

Both packages must use the same version. Update in two places:

1. `pyproject.toml` → `version = "X.Y.Z"`
2. `npm-wrapper/package.json` → `"version": "X.Y.Z"`

Note: a job called `validate-version-consistency` in `release.yml` ensures that the correct versions exist in both places.

## License

Apache-2.0
