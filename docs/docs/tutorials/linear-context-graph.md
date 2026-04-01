---
sidebar_position: 3
title: "Building Your First Linear Context Graph"
---

# Building Your First Linear Context Graph

This tutorial walks you through importing your real Linear workspace data into a Neo4j context graph and querying it with an AI agent. By the end, you'll have a running app where you can ask natural language questions about your issues, projects, cycles, and team workload -- backed by a connected graph of your actual project data.

## What you'll build

A full-stack application that:

- Imports your Linear issues, projects, cycles, teams, users, labels, and workflow states into Neo4j
- Maps all Linear relationships (issue assignments, project membership, cycle tracking, sub-issue hierarchies) into graph edges
- Provides an AI agent that can traverse the graph to answer questions like "What's blocking the v2 launch?" or "Who has bandwidth this cycle?"
- Visualizes the graph interactively with the NVL graph component

## Prerequisites

Before you begin, make sure you have:

- **Python 3.11+** -- check with `python --version`
- **Node.js 18+** -- check with `node --version`
- **Neo4j** -- one of:
  - [Neo4j Aura](https://console.neo4j.io) (free cloud instance)
  - Docker: `docker run -p 7474:7474 -p 7687:7687 -e NEO4J_AUTH=neo4j/password neo4j:5`
  - neo4j-local: `npx @johnymontana/neo4j-local`
- **uv** (recommended) -- install with `curl -LsSf https://astral.sh/uv/install.sh | sh`
- **A Linear API key** -- see Step 1 below
- **An LLM API key** -- `ANTHROPIC_API_KEY` (for most frameworks) or `OPENAI_API_KEY` / `GOOGLE_API_KEY` depending on your framework choice

## Step 1: Create a Linear API Key

1. Open Linear and go to **Settings > Security & Access > API** (or navigate directly to `linear.app/settings/api`).
2. Click **Create key** to generate a personal API key.
3. Copy the key -- it starts with `lin_api_`. You'll use this in the next step.

:::tip
Linear API keys have read access to your entire workspace. The import is read-only -- nothing is written back to Linear.
:::

## Step 2: Scaffold the Project

Run the CLI with the `--connector linear` flag:

```bash
uvx create-context-graph my-linear-app \
  --domain software-engineering \
  --framework pydanticai \
  --connector linear \
  --linear-api-key lin_api_xxxxx
```

Replace `lin_api_xxxxx` with your actual API key. You can also set it as an environment variable:

```bash
export LINEAR_API_KEY=lin_api_xxxxx
uvx create-context-graph my-linear-app \
  --domain software-engineering \
  --framework pydanticai \
  --connector linear
```

### Filtering by team

If your workspace has multiple teams and you only want to import one, add the `--linear-team` flag with the team's URL key (the short code you see in Linear URLs, like `ENG` or `PROD`):

```bash
uvx create-context-graph my-linear-app \
  --domain software-engineering \
  --framework pydanticai \
  --connector linear \
  --linear-team ENG
```

### What happens during scaffolding

The CLI will:

1. **Validate your API key** by calling Linear's `viewer` query
2. **Fetch your workspace data** -- teams, users, labels, projects, cycles, and issues (with cursor-based pagination for large workspaces)
3. **Transform the data** into the POLE+O entity model used by neo4j-agent-memory
4. **Write it to `data/fixtures.json`** in the generated project
5. **Generate the full application** -- FastAPI backend, Next.js frontend, Neo4j schema, and AI agent

You'll see output like:

```
Importing data from connected services...
  Connecting to Linear...
  Fetching data from Linear...
  ✓ Linear: 342 entities, 89 documents
```

## Step 3: Start Neo4j and Seed the Data

Navigate to your project and seed the data into Neo4j:

```bash
cd my-linear-app
make seed
```

This loads entities, relationships, and documents from `data/fixtures.json` into your Neo4j instance. If you need to configure Neo4j connection details, edit the `.env` file first:

```bash
# .env
NEO4J_URI=neo4j://localhost:7687
NEO4J_USERNAME=neo4j
NEO4J_PASSWORD=password
```

## Step 4: Start the Application

Start both the backend and frontend:

```bash
make start
```

This runs the FastAPI backend on port 8000 and the Next.js frontend on port 3000. Open [http://localhost:3000](http://localhost:3000) in your browser.

## Step 5: Explore Your Linear Data as a Graph

### Schema view

When the app loads, you'll see the **graph schema view** showing the entity types and relationships imported from Linear:

- **Issue** nodes connected to **Person** (via ASSIGNED_TO, CREATED_BY), **Project** (via BELONGS_TO_PROJECT), **Cycle** (via IN_CYCLE), **Team** (via BELONGS_TO_TEAM), **Label** (via HAS_LABEL), and **WorkflowState** (via HAS_STATE)
- **Person** nodes connected to **Team** and **Project** (via MEMBER_OF)
- Sub-issue hierarchies visible as **CHILD_OF** edges between Issue nodes

Double-click any schema node to load actual instances of that type.

### Ask the agent

Try these questions in the chat panel:

- **"What issues are assigned to [your name]?"** -- Finds your open assignments
- **"Show me all issues in the current cycle"** -- Traverses Cycle relationships
- **"What's the status of the [project name] project?"** -- Aggregates issue states for a project
- **"Find all issues labeled Bug with High priority"** -- Filters by label and priority
- **"What issues are blocking [issue identifier]?"** -- Traverses CHILD_OF hierarchy
- **"Who is working on the most issues right now?"** -- Aggregates assignments across team members

The agent uses Cypher queries to traverse your graph, so it can answer multi-hop questions that would require clicking through multiple Linear views.

### Graph visualization

As you chat with the agent, the graph visualization updates in real-time. Each tool call result flows into the graph view, showing the nodes and relationships that the agent queried. You can:

- **Double-click** a node to expand its neighbors
- **Drag** nodes to rearrange the layout
- **Click** a node to see its properties
- Use the **"Ask about this"** button to send a query about a specific entity

## Understanding the Graph Schema

The Linear connector maps your data to these graph labels:

| Linear Concept | Graph Label | POLE Type | Example Properties |
|---|---|---|---|
| Issue | `Issue` | Object | identifier, title, priority, stateType, dueDate |
| Project | `Project` | Organization | name, state, progress, targetDate |
| Cycle (Sprint) | `Cycle` | Event | name, number, startsAt, endsAt, progress |
| Team | `Team` | Organization | name, key |
| User | `Person` | Person | name, email, displayName |
| Label | `Label` | Object | name, color |
| Workflow State | `WorkflowState` | Object | name, type (triage/backlog/started/completed) |

Issue names follow the format `"ENG-101 Fix login bug"` (identifier + title) so they're easy to reference in queries.

## Re-importing Updated Data

As your Linear workspace changes, you can re-import to keep the graph current:

```bash
# Re-import from Linear
make import

# Re-import and seed into Neo4j
make import-and-seed
```

These targets read credentials from your `.env` file:

```bash
# .env
LINEAR_API_KEY=lin_api_xxxxx
LINEAR_TEAM=ENG  # optional
```

## Example Cypher Queries

Once your data is in Neo4j, you can also run raw Cypher queries via the agent's `run_cypher` tool or directly in Neo4j Browser (`http://localhost:7474`):

### Find all issues related to an issue by shared labels

```cypher
MATCH (i:Issue {identifier: 'ENG-101'})-[:HAS_LABEL]->(l)<-[:HAS_LABEL]-(related:Issue)
WHERE related <> i
RETURN related.identifier, related.title, l.name AS shared_label
```

### Team workload by assignee

```cypher
MATCH (p:Person)-[:MEMBER_OF]->(t:Team {name: 'Engineering'})
OPTIONAL MATCH (i:Issue)-[:ASSIGNED_TO]->(p)
WHERE i.stateType IN ['started', 'unstarted']
RETURN p.name, count(i) AS open_issues
ORDER BY open_issues DESC
```

### Current cycle progress

```cypher
MATCH (i:Issue)-[:IN_CYCLE]->(c:Cycle)
WHERE c.endsAt > datetime().epochMillis
RETURN c.name, i.stateType, count(*) AS issue_count
ORDER BY c.name, i.stateType
```

### Sub-issue hierarchy

```cypher
MATCH path = (child:Issue)-[:CHILD_OF*]->(parent:Issue)
WHERE parent.identifier = 'ENG-100'
RETURN [n IN nodes(path) | n.identifier] AS hierarchy
```

## Next Steps

- **Add more connectors** -- Combine Linear with GitHub (`--connector linear --connector github`) to create a unified development graph linking issues to PRs and commits
- **Customize the domain** -- Edit `data/ontology.yaml` to add domain-specific entity types and tools
- **Build custom agent tools** -- Add Cypher-powered tools to the agent for your specific workflow patterns
- **Set up periodic sync** -- Run `make import-and-seed` on a schedule to keep the graph fresh
