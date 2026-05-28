---
title: Use the Neo4j Agent Memory Service (NAMS)
slug: /how-to/use-nams
---

# Use the Neo4j Agent Memory Service (NAMS)

NAMS is the **default memory backend** for projects scaffolded by create-context-graph. Memory state lives in the cloud and is shared across processes (web app, MCP server, batch ingestion).

## When to use NAMS

- You want to deploy your context graph without provisioning and operating a Neo4j instance.
- You want the web app and `make mcp-server` to share the same memory graph across machines.
- You're building toward a production agent and want hosted memory from day one.

## When to use `--self-hosted` instead

- **Workshop / demo / screen recording** — you want the full pre-populated 80-entity, 180-relationship demo experience.
- **Air-gapped or regulated data** — NAMS is a hosted service; data leaves the local machine.
- **Custom Cypher writes** — your code needs to write arbitrary Cypher (not currently supported by NAMS REST).
- **GDS algorithms** — community detection, PageRank, and other GDS calls require bolt.

## Setting up NAMS

### 1. Provision an API key

Sign up at [memory.neo4jlabs.com](https://memory.neo4jlabs.com). Provision an API key from your dashboard.

:::note
At the time of writing, NAMS does not offer device-code or browser-based OAuth. API key paste is the only supported flow. We'll update this page once additional auth flows ship.
:::

### 2. Scaffold a project

```bash
uvx create-context-graph my-app \
  --domain healthcare \
  --framework strands \
  --nams-api-key sk-nams-...
```

Or pass via env:

```bash
export MEMORY_API_KEY=sk-nams-...
uvx create-context-graph my-app --domain healthcare --framework strands
```

### 3. Use the project

```bash
cd my-app
# ANTHROPIC_API_KEY is needed for the agent — set it in .env
echo 'ANTHROPIC_API_KEY=sk-ant-...' >> .env
make install
make start
```

The agent populates memory through conversation. There's no separate seeding step on NAMS.

## What's in your `.env`

```bash
MEMORY_BACKEND=nams
MEMORY_API_KEY=sk-nams-...
# MEMORY_NAMS_ENDPOINT=https://memory.neo4jlabs.com/v1   # override if pointing at a self-hosted gateway
```

When `MEMORY_API_KEY` is set, the library auto-selects the NAMS backend even if `MEMORY_BACKEND` is unset.

## NAMS write-path limits (v0.4)

The NAMS REST API exposes a narrower write surface than bolt Cypher. The CLI does best-effort ingest with these documented gaps:

| Operation | NAMS | Self-hosted bolt |
|---|---|---|
| Entity create (`add_entity`) | ✅ name + type + description only — other properties dropped | ✅ full properties |
| Entity properties | ⚠️ Serialized into `description` field as markdown | ✅ first-class on the node |
| Relationships | ⚠️ Encoded into source entity's `description` as a fenced `ccg-edges` YAML block (migrates to native edges when NAMS adds `add_relationship`) | ✅ Cypher MERGE |
| Preferences / facts | ❌ Not yet exposed | ✅ `add_preference`, `add_fact` |
| Decision traces | ✅ via `reasoning.start_trace` | ✅ via Cypher |
| Documents | ✅ dual-tracked: `long_term.add_entity(type=OBJECT)` + `short_term.add_message(role="document")` | ✅ as `:Document` nodes |
| Schema DDL | ❌ NAMS owns schema | ✅ `CREATE CONSTRAINT` etc. |
| GDS algorithms | ❌ 501 Not Implemented | ✅ |
| Arbitrary Cypher writes | ❌ Read-only | ✅ |

The frontend handles these gaps transparently — the graph view shows entities and parses `ccg-edges` blocks out of descriptions to display edges, the document browser reads from long-term `Document` entities, and the decision trace panel reads via the NAMS reasoning API.

## Seeding a relationship-rich graph for a NAMS project

NAMS REST has no `add_relationship` endpoint yet, so on NAMS scaffolds the ingest pipeline encodes each entity's outbound edges into a fenced `ccg-edges` YAML block appended to its `description`:

```ccg-edges
- type: TREATED_AT
  target: Mercy General
  target_label: Hospital
```

The graph view recognizes this marker and renders the edges. The agent reads them out of the entity description naturally. When NAMS gains `add_relationship`, a one-shot migration parses these blocks and replays them as native edges — no schema change.

If you'd rather have native graph edges today (for `expand_node`, GDS algorithms, or arbitrary Cypher traversal), scaffold with `--self-hosted`:

```bash
uvx create-context-graph my-app --domain healthcare \
  --framework strands --self-hosted --demo
```

The `--demo` flag triggers `--reset-database --demo-data --ingest`, which seeds the full 80-entity / 180-edge demo graph into your local Neo4j via native Cypher MERGE — no `ccg-edges` encoding because bolt can write real edges. You can develop against the bolt graph and later promote to NAMS by flipping `MEMORY_BACKEND` in `.env`.

### When NAMS adds relationship writes

Both `ingest.py` and the generated `import_data.py` emit relationships via the shared `ccg-edges` marker. When the upstream library ships `MemoryClient.add_relationship`, the encoding logic in `_build_ccg_edges_block` is the single seam to replace — both consumers update via the contract test in `tests/test_nams_ingest_parity.py`.

## Switching backends after scaffold

The memory backend is a runtime choice driven by `MEMORY_BACKEND` and `MEMORY_API_KEY`. To switch a project from NAMS to self-hosted (or vice versa):

1. Update `.env`:
   ```bash
   MEMORY_BACKEND=bolt
   NEO4J_URI=neo4j://localhost:7687
   NEO4J_PASSWORD=...
   ```
2. Restart the backend.

Note: the generated `pyproject.toml` ships with NAMS-appropriate extras by default. To enable local entity extraction on the bolt path, you'll also need to install `neo4j-agent-memory[extraction,fuzzy]`:

```bash
cd backend
uv pip install 'neo4j-agent-memory[litellm,sentence-transformers,extraction,fuzzy]>=0.4.0,<0.6.0'
```

## Resetting NAMS state

`make reset` on a NAMS project enumerates all entities via REST and deletes them one by one. Slow but correct:

```bash
make reset
```

For fast resets, use a self-hosted scaffold — `MATCH (n) DETACH DELETE n` runs in milliseconds.

## Troubleshooting

| Problem | Solution |
|---------|----------|
| `MEMORY_BACKEND=nams but MEMORY_API_KEY is not set` | Set `MEMORY_API_KEY` in `.env` or export it. |
| 401 Unauthorized from NAMS | Verify the key is current. Regenerate at the [dashboard](https://memory.neo4jlabs.com). |
| Graph view shows no edges | Expected — NAMS REST does not yet expose `add_relationship`. Use `--self-hosted` for the relationship-rich demo. |
| Entity property pane is just one markdown block | Expected — NAMS REST stores only `description`. The CLI serializes other properties as markdown so they remain readable. |
| `/gds/*` endpoints return 501 | GDS requires bolt. Use `--self-hosted` for GDS workflows. |

## Further Reading

- [Memory Backends](/docs/explanation/memory-backends) — conceptual NAMS vs self-hosted comparison
- [Configure Memory Providers](/docs/how-to/configure-memory-providers) — LiteLLM, native adapters
- [Connect Claude Desktop](/docs/how-to/connect-claude-desktop) — MCP server (NAMS shape included)
