---
sidebar_position: 2
title: Quick Start
slug: /quick-start
---

# Quick Start

Get a context graph app running in under 5 minutes.

This page walks the **NAMS-default flow** — your project's memory lives in the hosted [Neo4j Agent Memory Service](https://memory.neo4jlabs.com). For the offline / fixture-rich demo experience, jump to [Self-hosted Neo4j](#self-hosted-alternative-full-demo-fixtures) below.

## Prerequisites

- **Python 3.11+** -- verify with `python3 --version`
- **Node.js 18+** -- verify with `node --version` (required for the Next.js frontend)
- **NAMS API key** -- sign up at [memory.neo4jlabs.com](https://memory.neo4jlabs.com) and provision a key
- **Anthropic API key** -- for the AI agent ([get one here](https://console.anthropic.com))

## 1. Scaffold (~30 seconds)

```bash
uvx create-context-graph my-app \
  --domain healthcare \
  --framework strands \
  --nams-api-key sk-nams-...
```

This generates a complete project in `./my-app/`, configured to read and write memory through NAMS.

:::tip Interactive mode
If you omit flags (`uvx create-context-graph`), the wizard walks you through 6 prompts: project name, domain (autocomplete), framework, NAMS API key, session strategy, data source. Advanced settings are gated behind a single Y/N.
:::

## 2. Configure (~30 seconds)

```bash
cd my-app
# .env was generated with your NAMS API key already populated.
# You only need to set ANTHROPIC_API_KEY for the agent to chat.
echo 'ANTHROPIC_API_KEY=sk-ant-...' >> .env
```

## 3. Install & Start (~1 minute)

```bash
make install   # installs backend + frontend deps
make start     # runs both
```

Open [http://localhost:3000](http://localhost:3000) and chat with your healthcare context graph. The graph starts **empty** — as you talk to the agent, entities are extracted from your messages and stored in NAMS.

```
You:    "Track a patient: Alice Park, age 67, prescribed metformin."
Agent:  Logged Alice Park (Patient) with prescription metformin.
        Graph now contains 1 entity.
```

## What you can do

- **Chat** — questions like *"Who's prescribed metformin?"* trigger Cypher tools against the memory graph.
- **Inspect the graph** — the visualization panel shows every entity NAMS has ingested so far. Click any node to see its properties (rendered from the description field).
- **Watch decision traces** — multi-step reasoning is captured by the agent and viewable in the Decision Trace panel.

:::warning NAMS write-path limits (v0.4)
NAMS REST does not yet expose `add_relationship` or per-entity properties beyond `{name, type, description}`. The graph view shows entities but no edges, and properties live in a markdown block inside `description`. For the full relationship-rich demo experience, use the **self-hosted alternative** below.
:::

---

## Self-hosted alternative: full demo fixtures

If you want the workshop / demo experience with 80+ pre-populated entities, 180+ relationships, 25+ documents, and 4 decision traces visible from the first frame:

```bash
uvx create-context-graph my-app \
  --domain healthcare \
  --framework pydanticai \
  --self-hosted \
  --demo
```

The `--demo` flag is shorthand for `--reset-database --demo-data --ingest`. Set up Neo4j with one of:

**Option A: Neo4j Aura (easiest)**

1. Create a free instance at [console.neo4j.io](https://console.neo4j.io)
2. Download the `.env` credentials file
3. Pass it during scaffold: `--neo4j-aura-env path/to/Neo4j-credentials.env`

**Option B: Docker**

```bash
cd my-app && docker compose up -d neo4j
```

**Option C: neo4j-local**

```bash
npx @johnymontana/neo4j-local
```

Then:

```bash
cd my-app
cp .env.example .env  # set ANTHROPIC_API_KEY
make install
make seed
make start
```

You'll see:

```
Creating schema constraints...
Loading fixture data...
✓ Seeded 85 entities, 180 relationships, 25 documents, 4 decision traces
```

## With MCP Server for Claude Desktop

Either flow supports `--with-mcp`:

```bash
uvx create-context-graph my-app \
  --domain healthcare \
  --framework strands \
  --nams-api-key sk-nams-... \
  --with-mcp
```

After scaffold, copy `mcp/claude_desktop_config.json` into your Claude Desktop config to query the same memory graph from Claude. See [Connect Claude Desktop](/docs/how-to/connect-claude-desktop).

## Troubleshooting

| Problem | Solution |
|---------|----------|
| `python3: command not found` | Install Python 3.11+ from [python.org](https://www.python.org/downloads/) or via your package manager |
| `node: command not found` | Install Node.js 18+ from [nodejs.org](https://nodejs.org/) |
| `ANTHROPIC_API_KEY not set` at chat time | Add your key to `.env`: `ANTHROPIC_API_KEY=sk-ant-...` |
| NAMS authentication failure | Verify your API key is current. Regenerate at [memory.neo4jlabs.com](https://memory.neo4jlabs.com) |
| Graph view shows no edges (NAMS) | Expected — NAMS REST does not yet expose relationship writes. Use `--self-hosted` for the full graph experience |
| `make seed` fails with connection error (self-hosted) | Ensure Neo4j is running and `.env` credentials are correct. Check with `make test-connection` |
| Port 8000 or 3000 already in use | Stop the other process or change the port in `.env` (`BACKEND_PORT`, `FRONTEND_PORT`) |

## What's Next?

- [Use NAMS](/docs/how-to/use-nams) -- detailed NAMS setup and switching between backends
- [Configure Memory Providers](/docs/how-to/configure-memory-providers) -- LiteLLM, native adapters, default fallback
- [Memory Backends](/docs/explanation/memory-backends) -- conceptual NAMS vs self-hosted comparison
- [First Tutorial](/docs/tutorials/first-context-graph-app) -- 15-minute walkthrough
- [CLI Reference](/docs/reference/cli-options) -- all available flags
- [Domain Catalog](/docs/reference/domain-catalog) -- browse all 23 built-in domains
