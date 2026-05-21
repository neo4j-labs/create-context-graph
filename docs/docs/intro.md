---
sidebar_position: 1
title: Introduction
---

# Introduction

**Create Context Graph** is an interactive CLI scaffolding tool that generates complete, domain-specific context graph applications. Think of it as `create-next-app`, but for AI agents backed by graph memory.

Given a domain (like healthcare, financial services, or wildlife management) and an agent framework, it generates a full-stack application: a FastAPI backend with a configured AI agent, a Next.js + Chakra UI frontend with NVL graph visualization, a Neo4j schema with synthetic data, and domain-specific tools that let the agent query and reason over your knowledge graph.

<!-- TODO: Export from app-three-panel.excalidraw and replace placeholder -->
![The generated app's three-panel layout: chat interface, graph visualization, and document browser](/img/app-three-panel.png)

:::info What is POLE+O?
The **POLE+O** entity model is the foundation for all context graphs: **P**erson, **O**rganization, **L**ocation, **E**vent, plus **O**bject. Every domain ontology inherits these five base types and adds domain-specific subtypes. See [How Domain Ontologies Work](/docs/explanation/how-domain-ontologies-work) for details.
:::

## Key Features

- **NAMS by default** -- Generated projects target the hosted [Neo4j Agent Memory Service](https://memory.neo4jlabs.com) out of the box. `--self-hosted` preserves a fully-featured bolt-Neo4j path for offline / demo / regulated-data scenarios.
- **LiteLLM provider injection** -- The memory layer (entity extraction + embeddings) accepts LiteLLM-style provider strings via `MEMORY_LLM` / `MEMORY_EMBEDDING` env vars. Native adapters resolve first (Anthropic, OpenAI, Bedrock, Vertex AI, SentenceTransformers); everything else (Ollama, Groq, Together, …) routes through LiteLLM.
- **27 built-in domains** -- Healthcare, financial services, real estate, manufacturing, scientific research, software engineering, legal, education, cybersecurity, government, and more. Each ships with a complete ontology, agent tools, demo scenarios, and fixture data.
- **8 agent frameworks** -- AWS Strands (default), PydanticAI, Claude Agent SDK, OpenAI Agents SDK, LangGraph, CrewAI, Google ADK, and Anthropic Tools.
- **Multi-turn conversations** -- Every agent uses [neo4j-agent-memory](https://github.com/neo4j-labs/agent-memory) for conversation persistence with automatic entity extraction. Preference detection on the self-hosted path.
- **Graph-native AI agents** -- Cypher-powered tools (on bolt) or NAMS REST tools (on the hosted backend) for querying entities, relationships, and decision traces. Tool calls stream in real-time with live progress indicators.
- **Streaming chat** -- Token-by-token responses via Server-Sent Events. Tool calls appear as a live timeline with spinner indicators. Graph visualization updates incrementally after each tool completes.
- **Interactive graph visualization** -- NVL-powered graph explorer with entity detail panel, document browser with template filtering, and decision trace viewer.
- **Rich demo data** -- LLM-generated fixture data per domain: 80-90 entities, 25+ professional documents, and 3-5 multi-step decision traces. Loaded via `make seed`.
- **13 SaaS data connectors** -- GitHub (`github`), Slack (`slack`), Jira (`jira`), Notion (`notion`), Gmail (`gmail`), Google Calendar (`gcal`), Salesforce (`salesforce`), Linear (`linear`), Google Workspace (`google-workspace`), Claude Code (`claude-code`), Claude AI (`claude-ai`), ChatGPT (`chatgpt`), and local files (`local-file`). Use the ID in parentheses with `--connector`.
- **Custom domains** -- Describe your domain in natural language to generate a complete ontology, or write your own YAML definition.
- **MCP server for Claude Desktop** -- Optionally generate an MCP server config so Claude Desktop queries the same knowledge graph as your web app.

## Quick Install

No installation required. Run directly with `uvx` (Python) or `npx` (Node.js):

```bash
# Python (recommended)
uvx create-context-graph

# Node.js
npx create-context-graph
```

See the **[Quick Start](/docs/quick-start)** for a complete walkthrough, or skip the wizard with flags:

```bash
# NAMS-default (hosted memory)
uvx create-context-graph my-app --domain healthcare --framework strands --nams-api-key sk-nams-...

# Self-hosted (bolt Neo4j) with full demo fixtures
uvx create-context-graph my-app --domain healthcare --framework pydanticai --self-hosted --demo
```

## See All Available Domains

```bash
uvx create-context-graph --list-domains
```

## Architecture

<!-- TODO: Export from architecture-overview.excalidraw and replace with final PNG -->
![Architecture: generation pipeline (CLI → Jinja2 → backend + frontend + data) and runtime (frontend ↔ backend ↔ Neo4j)](/img/architecture-overview.png)

The top half shows **generation**: the CLI reads a domain ontology YAML and renders Jinja2 templates into a complete project (FastAPI backend, Next.js frontend, Cypher schema + fixture data). The bottom half shows the **running application**: the frontend streams chat responses via SSE, the backend agent executes Cypher tool calls against Neo4j, and the graph visualization updates incrementally as each tool completes.

## Reading Guide

Choose your path based on what you want to do:

- **New to context graphs?** Start with [Why Context Graphs](/docs/explanation/why-context-graphs), then follow the [Quick Start](/docs/quick-start).
- **Want to build your first app?** Follow the [First Context Graph App](/docs/tutorials/first-context-graph-app) tutorial (15-20 min).
- **Importing real data?** See [Import SaaS Data](/docs/how-to/import-saas-data) or the connector tutorials ([Linear](/docs/tutorials/linear-context-graph), [Google Workspace](/docs/tutorials/google-workspace-decisions), [Claude Code](/docs/tutorials/claude-code-sessions)).
- **Building a custom domain?** Read [How Domain Ontologies Work](/docs/explanation/how-domain-ontologies-work), then follow [Customizing Your Ontology](/docs/tutorials/customizing-domain-ontology).
- **Comparing frameworks?** See the [Framework Comparison](/docs/reference/framework-comparison) or [Switch Frameworks](/docs/how-to/switch-frameworks).

## What's Next

- **[Quick Start](/docs/quick-start)** -- get a running app in under 5 minutes.
- **[Your First Context Graph App](/docs/tutorials/first-context-graph-app)** -- step-by-step tutorial to create, run, and explore a generated application.
- **[Why Context Graphs](/docs/explanation/why-context-graphs)** -- understand the conceptual foundation behind graph-based agent memory.
- **[Three Memory Types](/docs/explanation/three-memory-types)** -- how short-term, long-term, and reasoning memory work together.
- **[Domain Catalog](/docs/reference/domain-catalog)** -- browse all 27 built-in domains with entity types and sample questions.
- **[Import SaaS Data](/docs/how-to/import-saas-data)** -- connect your existing tools to populate the knowledge graph.
- **[Switch Frameworks](/docs/how-to/switch-frameworks)** -- compare and switch between 8 agent frameworks.
