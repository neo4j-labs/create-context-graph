---
sidebar_position: 7
title: Connect Claude Desktop
---

# Connect Claude Desktop via MCP

Generated projects can optionally include an MCP (Model Context Protocol) server configuration that lets Claude Desktop query the same knowledge graph as your web application.

## Prerequisites

- A scaffolded project with `--with-mcp` enabled
- [Claude Desktop](https://claude.ai/download) installed
- Neo4j running with seeded data

## 1. Scaffold with MCP

```bash
uvx create-context-graph my-app \
  --domain healthcare \
  --framework pydanticai \
  --demo-data \
  --with-mcp
```

This generates a `mcp/` directory alongside your project with:
- `claude_desktop_config.json` — pre-configured MCP server config
- `README.md` — detailed setup instructions

## 2. Install and Seed

```bash
cd my-app
make install
make docker-up    # or your preferred Neo4j setup
make seed
```

## 3. Configure Claude Desktop

Copy the MCP config into Claude Desktop's configuration:

**macOS:**
```bash
# Merge the contents of mcp/claude_desktop_config.json into:
~/Library/Application Support/Claude/claude_desktop_config.json
```

**Windows:**
```
%APPDATA%\Claude\claude_desktop_config.json
```

:::tip
If you already have other MCP servers configured, merge the `mcpServers` object — don't overwrite the entire file. Before copying, replace any `${NEO4J_URI}` and `${NEO4J_PASSWORD}` placeholders with your actual values from `.env`.
:::

## 4. Restart Claude Desktop

After updating the config, restart Claude Desktop. You should see your project's memory server in the MCP server list (look for the hammer icon in the chat input).

## 5. Query the Knowledge Graph

Ask Claude about your domain data:

> "What patients are in the knowledge graph?"
> "Show me the relationships between Dr. Smith and her patients"
> "What decision traces exist for treatment planning?"

Claude will use the MCP tools to query Neo4j directly — the same data your web application uses.

## Tool Profiles

The `--mcp-profile` flag controls which tools are available:

### Core Profile (6 tools)
Basic memory operations: search, get context, store messages, add entities, preferences, and facts.

```bash
uvx create-context-graph my-app --with-mcp --mcp-profile core ...
```

### Extended Profile (16 tools, default)
Full access including conversation history, session management, entity details, graph export, relationship creation, reasoning traces, and custom Cypher queries.

```bash
uvx create-context-graph my-app --with-mcp --mcp-profile extended ...
```

## Testing the MCP Server

Start the server manually to verify it works:

```bash
make mcp-server
```

Or use the [MCP Inspector](https://github.com/modelcontextprotocol/inspector):

```bash
npx @modelcontextprotocol/inspector uv run --directory ./backend \
  neo4j-agent-memory mcp serve --backend nams
```

## Dual-Interface Architecture

```mermaid
graph LR
    Browser["Browser\nlocalhost:3000"] --> NextJS["Next.js\nFrontend"]
    NextJS --> FastAPI["FastAPI\nBackend"]
    FastAPI --> Neo4j[("Neo4j\nKnowledge Graph")]
    Claude["Claude Desktop"] --> MCP["MCP Server\n(neo4j-agent-memory)"]
    MCP --> Neo4j
```

With MCP enabled, your project has two interfaces to one knowledge graph:

1. **Web app** (http://localhost:3000) — interactive chat with streaming, graph visualization, document browser
2. **Claude Desktop** — natural language queries via MCP tools, integrated into your Claude workflow

Both interfaces read from and write to the same Neo4j instance. Entities, conversations, and reasoning traces are shared.
