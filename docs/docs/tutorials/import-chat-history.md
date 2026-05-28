---
sidebar_position: 6
title: "Import Your AI Chat History into a Context Graph"
---

# Import Your AI Chat History into a Context Graph

This tutorial walks you through importing your Claude AI or ChatGPT conversation history into a Neo4j context graph. Months or years of real AI conversations become a connected, queryable knowledge graph -- entities, relationships, topics, and reasoning traces extracted from your actual interactions.

By the end, you'll have an AI agent that can answer questions like "What topics do I ask about most?", "Show me conversations where I discussed Neo4j", and "What tools did the assistant use in my conversations about Python?".

## What you'll build

A full-stack application that:

- Imports your **Claude AI** data export (`.zip` containing `conversations.jsonl`) or **ChatGPT** data export (`.zip` containing `conversations.json`) into Neo4j
- Creates **Conversation** and **Message** entities with temporal ordering (`NEXT` relationships)
- Generates searchable **documents** from each conversation for full-text search and RAG
- Extracts **tool call traces** as decision traces (deep mode) showing how the assistant reasoned through tasks
- Supports **date and title filtering** so you can import specific time ranges or conversation topics
- Handles **large exports** (1GB+) with streaming JSONL parsing -- never loads the entire file into memory

## Prerequisites

Before you begin, make sure you have:

- **Python 3.11+** -- check with `python --version`
- **Node.js 18+** -- check with `node --version`
- **Neo4j** -- one of:
  - [Neo4j Aura](https://console.neo4j.io) (free cloud instance)
  - Docker: `docker run -p 7474:7474 -p 7687:7687 -e NEO4J_AUTH=neo4j/password neo4j:5`
  - neo4j-local: `npx @johnymontana/neo4j-local`
- **uv** (recommended) -- install with `curl -LsSf https://astral.sh/uv/install.sh | sh`
- **An LLM API key** -- `ANTHROPIC_API_KEY` (for most frameworks) or `OPENAI_API_KEY` / `GOOGLE_API_KEY` depending on your framework choice
- **A chat history export** from Claude AI or ChatGPT (see below)

## Step 1: Export your chat history

### Exporting from Claude AI

1. Open [claude.ai](https://claude.ai) and sign in to your account.
2. Click your profile icon in the bottom-left corner, then select **Settings**.
3. Navigate to the **Account** tab.
4. Scroll down and click **Export Data**.
5. Confirm the export request. Claude will send an email to your registered address with a download link.
6. Download the `.zip` file from the email. It contains a single `conversations.jsonl` file with all your conversations.

:::tip
The export email typically arrives within a few minutes. Check your spam folder if you don't see it. The file can range from a few MB to several hundred MB depending on how many conversations you've had.
:::

### Exporting from ChatGPT

1. Open [chatgpt.com](https://chatgpt.com) and sign in to your account.
2. Click your profile icon in the top-right corner, then select **Settings**.
3. Navigate to **Data Controls**.
4. Click **Export data** and confirm.
5. OpenAI will send an email with a download link. Download the `.zip` file.
6. The zip contains `conversations.json` (all your conversations), plus `chat.html`, `user.json`, and any generated images.

:::tip
ChatGPT exports include DALL-E generated images and uploaded files alongside the conversation JSON. The import process only reads `conversations.json` -- image files are ignored.
:::

## Step 1.5: Preview your export (optional, recommended)

Before scaffolding a full project, you can preview what will be imported. This parses the export file and prints a summary (conversation count, date range, sample titles) without creating any files or writing to Neo4j — useful for sanity-checking a multi-GB export before committing to a long ingest:

```bash
uvx create-context-graph \
  --import-preview \
  --import-type claude-ai \
  --import-file ~/Downloads/claude-export.zip
```

The same flag works for ChatGPT exports — swap `--import-type chatgpt` and point `--import-file` at the ChatGPT `.zip`. Combine with any of the `--import-filter-*` flags below to preview a filtered subset.

## Step 2: Scaffold the project

Run the CLI with the `--import-type` and `--import-file` flags:

### Claude AI

```bash
uvx create-context-graph my-chat-graph \
  --domain personal-knowledge \
  --framework pydanticai \
  --import-type claude-ai \
  --import-file ~/Downloads/claude-export.zip \
  --demo-data \
  --ingest \
  --neo4j-uri neo4j://localhost:7687
```

### ChatGPT

```bash
uvx create-context-graph my-chat-graph \
  --domain personal-knowledge \
  --framework pydanticai \
  --import-type chatgpt \
  --import-file ~/Downloads/chatgpt-export.zip \
  --demo-data \
  --ingest \
  --neo4j-uri neo4j://localhost:7687
```

This scaffolds a full-stack application, imports your conversations into the graph data, generates demo data, and ingests everything into Neo4j.

:::caution
The `--import-file` path must point to the actual `.zip` file you downloaded. You can also pass an extracted `.jsonl` file (Claude AI) or `.json` file (ChatGPT) directly.
:::

## Step 3: Customize the import

### Filter by date

Only import conversations from the last 6 months:

```bash
uvx create-context-graph my-chat-graph \
  --domain personal-knowledge \
  --framework pydanticai \
  --import-type claude-ai \
  --import-file ~/Downloads/claude-export.zip \
  --import-filter-after 2025-10-01
```

### Filter by title

Only import conversations whose titles match a pattern:

```bash
uvx create-context-graph my-chat-graph \
  --domain personal-knowledge \
  --framework pydanticai \
  --import-type chatgpt \
  --import-file ~/Downloads/chatgpt-export.zip \
  --import-filter-title "python|neo4j|graph"
```

### Limit the number of conversations

Import only your most recent 100 conversations:

```bash
uvx create-context-graph my-chat-graph \
  --domain personal-knowledge \
  --framework pydanticai \
  --import-type claude-ai \
  --import-file ~/Downloads/claude-export.zip \
  --import-max-conversations 100
```

### Import depth

Control how much data is extracted with `--import-depth`:

| Depth | What's extracted | Speed | LLM Cost |
|-------|-----------------|-------|----------|
| `fast` (default) | Conversation + Message entities, documents, relationships | Very fast | Zero |
| `deep` | All of the above + tool call decision traces | Fast | Zero |

```bash
# Extract tool call traces as decision traces
uvx create-context-graph my-chat-graph \
  --domain personal-knowledge \
  --framework pydanticai \
  --import-type claude-ai \
  --import-file ~/Downloads/claude-export.zip \
  --import-depth deep
```

### Import flags reference

| Flag | Type | Default | Description |
|------|------|---------|-------------|
| `--import-preview` | `flag` | `false` | Parse the export file and print a summary without scaffolding or ingesting. Requires `--import-type` and `--import-file`. |
| `--import-type` | `choice` | -- | Import source: `claude-ai` or `chatgpt` |
| `--import-file` | `path` | -- | Path to export file (`.zip`, `.json`, `.jsonl`) |
| `--import-depth` | `choice` | `fast` | Extraction depth: `fast` or `deep` |
| `--import-filter-after` | `string` | -- | Only import conversations created after this date (ISO 8601) |
| `--import-filter-before` | `string` | -- | Only import conversations created before this date |
| `--import-filter-title` | `string` | -- | Only import conversations matching this title pattern (regex) |
| `--import-max-conversations` | `int` | `0` (all) | Maximum conversations to import |

## Step 4: Start the application

```bash
cd my-chat-graph
make install   # Install backend + frontend dependencies
make start     # Start both backend and frontend
```

Open [http://localhost:3000](http://localhost:3000) in your browser.

<details>
<summary>Alternative: manual startup (useful for debugging)</summary>

```bash
# Terminal 1: Backend
cd backend && uv venv && uv pip install -e ".[dev]"
source .venv/bin/activate
uvicorn app.main:app --reload --port 8000

# Terminal 2: Frontend
cd frontend && npm install && npm run dev
```

</details>

## Step 5: Explore your chat history

### In the chat interface

Try asking the agent about your conversation history:

- **"What topics do I discuss most frequently?"**
- **"Show me conversations about Python"**
- **"When did I first ask about Neo4j?"**
- **"What tools were used in my conversations about data analysis?"**

The agent uses the context graph tools to query your imported conversation data and provide grounded answers.

### In the graph visualization

Click on the graph panel to explore:

- **Schema view** shows Conversation and Message node types with their relationships
- **Double-click a Conversation node** to expand and see its messages
- **Double-click a Message node** to see connected conversations and adjacent messages

### In Neo4j Browser

Open [http://localhost:7474](http://localhost:7474) and try these Cypher queries:

**Browse your conversations:**
```cypher
MATCH (c:Conversation)
WHERE c.source = 'claude-ai'
RETURN c.name AS title, c.message_count AS messages, c.created_at AS date
ORDER BY c.created_at DESC
LIMIT 20
```

**Find conversations by topic:**
```cypher
MATCH (d:Document)
WHERE d.content CONTAINS 'Neo4j'
RETURN d.title, d.created_at
ORDER BY d.created_at DESC
```

**Trace a conversation's message flow:**
```cypher
MATCH (c:Conversation {name: 'Help with Python decorators'})-[:HAS_MESSAGE]->(m:Message)
OPTIONAL MATCH (m)-[:NEXT]->(next:Message)
RETURN m.role, left(m.content, 100) AS preview, next.role AS next_role
ORDER BY m.created_at
```

**Count messages by role:**
```cypher
MATCH (m:Message)
RETURN m.role, count(m) AS message_count
ORDER BY message_count DESC
```

**Find your longest conversations:**
```cypher
MATCH (c:Conversation)
WHERE c.message_count > 10
RETURN c.name, c.message_count, c.created_at
ORDER BY c.message_count DESC
LIMIT 10
```

**Conversations with tool usage (deep mode):**
```cypher
MATCH (m:Message {has_tool_calls: true})
MATCH (c:Conversation)-[:HAS_MESSAGE]->(m)
RETURN DISTINCT c.name, count(m) AS tool_messages
ORDER BY tool_messages DESC
LIMIT 10
```

**Browse decision traces (deep mode):**
```cypher
MATCH (dt:DecisionTrace)-[:HAS_STEP]->(ts:TraceStep)
WHERE dt.id STARTS WITH 'claude-ai-trace'
RETURN dt.task, collect(ts.action) AS actions
LIMIT 5
```

## Understanding the graph schema

### Entity types

| Entity | Source | Key Properties | Description |
|--------|--------|---------------|-------------|
| **Conversation** | Both | `name`, `conversation_id`, `source`, `created_at`, `updated_at`, `message_count` | One node per conversation from the export |
| **Message** | Both | `name`, `role`, `content`, `created_at`, `conversation_id`, `has_tool_calls` | Individual messages within a conversation |
| **Document** | Both | `title`, `content`, `source`, `conversation_id`, `created_at` | Full conversation text for search/RAG |
| **DecisionTrace** | Deep mode | `id`, `task`, `outcome` | Tool call sequences captured as reasoning traces |
| **TraceStep** | Deep mode | `thought`, `action`, `observation` | Individual steps within a decision trace |

### Relationships

| Relationship | From | To | Description |
|-------------|------|-----|-------------|
| `HAS_MESSAGE` | Conversation | Message | Conversation contains this message |
| `NEXT` | Message | Message | Sequential ordering of messages within a conversation |
| `HAS_STEP` | DecisionTrace | TraceStep | Trace contains this reasoning step |

### Platform-specific features

| Feature | Claude AI | ChatGPT |
|---------|-----------|---------|
| Message structure | Flat `chat_messages` array | Tree-structured `mapping` (branches follow last child) |
| Tool calls | `content` blocks with `type: tool_use` | `tool` role messages with `execution_output` |
| Thinking/reasoning | `type: thinking` content blocks | Not exported |
| Branching | Not present in export | Follows main conversation path |
| Hidden messages | N/A | Filtered out (`is_visually_hidden_from_conversation`) |

## Privacy and data handling

- **All processing is local.** Your conversation data is read from the export file on your machine and written directly to your Neo4j instance. No data is sent to external services during the `fast` import depth.
- **Message content is truncated** to 2,000 characters per message entity by default. Full conversation text is preserved in Document entities for search.
- **No images or files are imported** from ChatGPT exports. Only conversation text and metadata are processed.
- **Filtering reduces scope.** Use `--import-filter-after`, `--import-filter-before`, and `--import-filter-title` to control exactly which conversations enter the graph.

## Combining with other connectors

You can combine chat history import with other connectors for a richer graph:

```bash
# Import Claude AI history alongside your Claude Code sessions
uvx create-context-graph my-full-graph \
  --domain personal-knowledge \
  --framework pydanticai \
  --import-type claude-ai \
  --import-file ~/Downloads/claude-export.zip \
  --connector claude-code \
  --claude-code-scope all
```

This creates a unified graph where your Claude AI web conversations and Claude Code coding sessions coexist, sharing entity types like `Conversation`/`Session` and `Message`.

## Next steps

- **Explore more domains:** Try importing into a `software-engineering` or `knowledge-management` domain for different agent tools and system prompts
- **Switch frameworks:** Use `--framework claude-agent-sdk` or `--framework langgraph` for different agent capabilities. See [Switch Agent Frameworks](/docs/how-to/switch-frameworks)
- **Add more data sources:** Connect GitHub, Linear, or Slack data alongside your chat history. See [Import Data from SaaS Services](/docs/how-to/import-saas-data)
- **Use Neo4j Aura:** Deploy your graph to the cloud with [Neo4j Aura](/docs/how-to/use-neo4j-aura)

:::info Completed all tutorials?
Explore the [How-To Guides](/docs/how-to/import-saas-data) for specific tasks, or dive into the [Explanation](/docs/explanation/why-context-graphs) section to understand the concepts behind context graphs.
:::
