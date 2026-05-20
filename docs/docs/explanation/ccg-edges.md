---
title: How NAMS stores relationships (ccg-edges)
slug: /explanation/ccg-edges
---

# How NAMS stores relationships (`ccg-edges`)

The [Neo4j Agent Memory Service](https://memory.neo4jlabs.com) (NAMS) REST API as of this writing exposes `add_entity` but **does not yet expose `add_relationship`**. Bolt-backed scaffolds have always written real Neo4j relationships via `MERGE (a)-[:TYPE]->(b)` Cypher, but on NAMS scaffolds, that primitive doesn't exist.

To avoid silently dropping edges, `create-context-graph` encodes outbound relationships for each entity into the **source entity's `description`** as a fenced YAML block tagged `ccg-edges`.

## What it looks like

A `Person` entity named `Alice Park` whose ingest payload included two outbound edges — `(Alice Park)-[:MENTIONS]->(Market Opportunity)` and `(Alice Park)-[:AUTHORED]->(Q3 Strategy Memo)` — lands in NAMS as a single `long_term.add_entity(...)` call whose `description` looks like:

````markdown
Senior product manager focused on the early-stage market.

**Role**: Senior PM
**Department**: Product

_pole_type: PERSON_

```ccg-edges
- type: AUTHORED
  target: Q3 Strategy Memo
  target_label: Document
- type: MENTIONS
  target: Market Opportunity
  target_label: Concept
```
````

The block:

- Always starts with the opening fence `` ```ccg-edges `` on its own line.
- Lists each outbound edge as a YAML sequence item with `type`, `target`, and optionally `target_label`.
- Sorts deterministically by `(type, target)` so successive ingests produce byte-identical descriptions and the parity test can pin the format.
- Lives at the end of the description, after any human-readable prose and the `_pole_type:` marker.

## Where in the code

| Step | Source CLI (`src/create_context_graph/...`) | Scaffolded project (`templates/...`) |
|---|---|---|
| Build the block | `ingest.py::_build_ccg_edges_block` | `backend/connectors/import_data.py.j2::_build_ccg_edges_block` |
| Embed in description | `memory_adapter.py::_description_with_edges` | `backend/connectors/import_data.py.j2::_description_with_edges` |
| Strip the block when displaying preview | n/a | `backend/shared/memory_adapter.py.j2::_document_record_from_entity` |
| Parity contract | `tests/test_nams_ingest_parity.py` (pins the exact `add_entity` calls) | same |

The two writers — the CLI's demo-fixture seeder (`run_nams_ingest`) and the scaffolded connector ingest (`import_data.py`) — share the same encoding to guarantee the graph view shows the same edges regardless of how the data got in.

## Why not just call the parent and child separately?

You could imagine writing both `Alice Park` and `Q3 Strategy Memo` as separate `add_entity` calls and hoping NAMS's server-side extractor recognizes the relationship. In practice:

- The extractor is optimized for **prose mentions** ("Alice authored the Q3 memo"), not structured edges.
- Connector ingest data is **already structured** — the source system (Linear, GitHub, Google Workspace) gave us the edge explicitly, and asking the LLM extractor to rediscover it is lossy and expensive.
- We want a **stable round-trip**: re-ingesting the same fixture should produce the same NAMS state. The structured block guarantees that; relying on prose extraction does not.

## Fragility — what to know

- **If a user edits the description in NAMS Studio**, they may delete or corrupt the block. The frontend will silently lose those edges in the graph view, but the entity itself still exists. This is acceptable for a research / demo system; production deployments should treat descriptions as machine-managed.
- **If NAMS truncates very long descriptions**, edges at the end of large blocks could be cut off. We sort deterministically so truncation is at least predictable, but there's no hard cap today.
- **If you add an out-of-band edge in NAMS**, `create-context-graph` won't know about it — the next ingest will re-write the description with only the edges in the source fixture.

## Migration path

When NAMS gains a native `add_relationship` endpoint:

1. Add a one-shot migration script `scripts/migrate_ccg_edges_to_native.py` that walks every entity, parses any `ccg-edges` block out of its description, and replays each edge via the new endpoint.
2. Strip the block from the description in the same pass so descriptions read cleanly to the LLM.
3. Update `_build_ccg_edges_block` to a no-op (or remove the call sites) so new ingests use the native API directly.
4. Update `tests/test_nams_ingest_parity.py` to pin the new `add_relationship` call sequence.

Until then, `ccg-edges` is the contract. It is plain text, deterministically formatted, and grep-able — if you need to inspect what's in your NAMS graph, `client.long_term.search_entities(...)` returns the description verbatim and you can extract the YAML by hand.

## Related

- [Memory Backends — NAMS vs Self-Hosted](./memory-backends.md)
- [Three Memory Types](./three-memory-types.md)
- [Ontology YAML Schema reference](../reference/ontology-yaml-schema.md)
