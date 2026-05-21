---
title: Memory Backends — NAMS vs Self-Hosted
slug: /explanation/memory-backends
---

# Memory Backends — NAMS vs Self-Hosted

Every project scaffolded by create-context-graph picks **one of two memory backends**:

- **NAMS** — the hosted [Neo4j Agent Memory Service](https://memory.neo4jlabs.com). Memory state lives in the cloud. Accessed via REST.
- **Bolt** — a self-hosted Neo4j instance you own and operate. Memory state lives wherever your Neo4j runs (Aura, Docker, neo4j-local, on-prem). Accessed via the Bolt protocol with Cypher.

NAMS is the **default** as of v0.11. Use `--self-hosted` (or any explicit `--neo4j-*` flag) to opt into bolt.

## Why two backends?

Both backends present **the same agent abstractions** to your application code — the agent calls `client.long_term.add_entity(...)`, `client.short_term.add_message(...)`, `client.reasoning.start_trace(...)`, and so on. The library hides the protocol difference.

But the two backends have **different operational profiles**, and each makes sense in different scenarios.

## Trade-offs at a glance

| Concern | NAMS | Self-hosted bolt |
|---|---|---|
| **Setup time** | 30s (sign up, paste key) | 1–5 min (Aura signup or Docker pull) |
| **Operate Neo4j yourself?** | No | Yes |
| **Memory shared across processes** | Yes (web app + MCP + batch all hit the same cloud) | Yes, but everyone must point at the same Neo4j |
| **Demo data ingest (`make seed`)** | Best-effort (entities only — see limits below) | Full (entities, relationships, properties, documents, traces) |
| **Arbitrary Cypher reads** | Yes (`client.query.cypher`, read-only) | Yes |
| **Arbitrary Cypher writes** | No (REST enforces read-only) | Yes |
| **GDS algorithms** | No (501 Not Implemented) | Yes |
| **`make reset`** | Slow (per-entity REST delete) | Fast (`MATCH (n) DETACH DELETE n`) |
| **Data residency** | Hosted by Neo4j Labs | Wherever your Neo4j runs |
| **Offline development** | No (needs network) | Yes (with Docker / neo4j-local) |

## NAMS write-path limits (v0.4)

The most important asymmetry today is what NAMS REST **doesn't** expose. The library raises `NotSupportedError` on these:

- `add_relationship(...)` — no REST endpoint yet for native edges between domain entities.
- `add_preference(...)` / `add_fact(...)` — preferences and facts have no REST endpoints.
- Arbitrary Cypher writes via `client.query.cypher(...)` — read-only on NAMS.
- Schema DDL (`CREATE CONSTRAINT`, `CREATE INDEX`) — NAMS owns its schema.

The CLI and the generated `import_data.py` use a hybrid write shape that captures everything connectors emit without losing structure:

- **Entities** — `add_entity`. NAMS REST accepts only `{name, type, description}`; both ingestors serialize other properties into `description` as markdown so the property pane stays useful.
- **Relationships** — **encoded** into the source entity's `description` as a fenced ```ccg-edges``` YAML block (deterministic, distinctively marked). The frontend graph view parses these out and renders edges. A one-shot migration replays them as native edges when NAMS adds `add_relationship` — the seam is `_build_ccg_edges_block` in `ingest.py`.
- **Documents** — **dual-tracked**: `long_term.add_entity(name=title, type=OBJECT)` so the doc is a queryable entity (matches the bolt `:Document` shape), plus `short_term.add_message(role="document")` so the NAMS extractor can mine the prose. The `/documents` endpoint reads from long_term entities; short-term entries are extraction fuel, not the source of truth.
- **Entity bodies** — connectors declare a `BODY_FIELDS = {label: property}` map; the named body field is also fed through `add_message` so the extractor sees comment bodies, issue descriptions, etc. Pure-metadata entities (Person, Project, Label) skip this channel.
- **Decision traces** — `reasoning.start_trace / add_step / complete_trace` (unchanged).
- **Preferences / facts** — still unsupported on NAMS REST. `auto_preferences` is forced off on NAMS; `auto_extract` runs but extracted edges are dropped (the encoded `ccg-edges` block covers structured edges instead).

These limits reflect the current state of NAMS REST (v0.4) and will narrow as upstream adds endpoints. The contract test `tests/test_nams_ingest_parity.py` pins the CLI and the scaffolded importer to the same NAMS call sequence so the two paths can't drift.

## Choosing per-project

A rule of thumb:

- **Demo, workshop, screen recording, "look how rich this is" first impression** → `--self-hosted --demo`. Full graph from frame one.
- **Hosted production agent, multi-instance deployment, share memory between web app and MCP, "we don't want to operate Neo4j"** → NAMS default.
- **Air-gapped, regulated data, compliance constraints** → `--self-hosted`. NAMS is a hosted SaaS.
- **GDS workflows (community detection, PageRank, etc.)** → `--self-hosted`.

## Switching after scaffold

The backend is a runtime choice, not a scaffold-time lock-in. Edit `.env`:

```bash
# Switch from NAMS to bolt
MEMORY_BACKEND=bolt
NEO4J_URI=neo4j://localhost:7687
NEO4J_PASSWORD=...
```

…and restart. The generated `backend/app/memory.py` branches on `settings.memory_backend` at startup.

One caveat: the generated `pyproject.toml` includes backend-appropriate extras. NAMS scaffolds skip `[extraction,fuzzy]` (extraction happens server-side); self-hosted scaffolds include them. If you switch a NAMS scaffold to bolt and enable `auto_extract=True`, install the missing extras:

```bash
cd backend
uv pip install 'neo4j-agent-memory[litellm,sentence-transformers,extraction,fuzzy]>=0.4.0,<0.6.0'
```

## How the frontend handles the difference

The same Next.js + Chakra UI frontend works against both backends. The backend's `routes.py` dispatches each endpoint to a NAMS adapter (`memory_adapter.py`) or the existing bolt-Cypher implementation based on `settings.memory_backend`:

- `/expand`, `/documents`, `/traces`, `/schema/visualization`, `/entities/{name}`, `/search` — adapted on NAMS.
- `/gds/*` — returns 501 on NAMS (the frontend hides GDS UI when this happens).
- `/cypher` — read-only on NAMS via `client.query.cypher`.

Schema visualization on NAMS synthesizes a node-count view from `list_entities` (no edges — relationships aren't writable yet). On bolt, the full `db.schema.visualization()` is used.

## Further Reading

- [Use NAMS](/docs/how-to/use-nams) — sign-up, configuration, troubleshooting
- [Configure Memory Providers](/docs/how-to/configure-memory-providers) — LiteLLM provider strings
- [Three Memory Types](/docs/explanation/three-memory-types) — short-term, long-term, reasoning memory
- [neo4j-agent-memory CHANGELOG](https://github.com/neo4j-labs/agent-memory/blob/main/CHANGELOG.md) — track upstream NAMS endpoint additions
