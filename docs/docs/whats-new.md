---
sidebar_position: 3
title: "What's New"
---

# What's New

Recent additions and changes to create-context-graph and its documentation.

## v0.13.0 (Current) — v0.12.0 feedback report fixes

Addresses the May 19, 2026 v0.12.0 feedback report. The headline fix is a runtime bug on the `--self-hosted` connector ingest path that NAMS users never hit; everything else is a cluster of smaller-but-real frontend, backend, and documentation gaps. Test suite: 1,335 passing, 231 skipped (matrix/integration unchanged from baseline).

### Bug Fixes

- **`_ingest_via_bolt()` is now async.** The scaffolded `import_data.py` was calling `with driver.session()` and sync `session.run(...)` on an `AsyncDriver`, so every self-hosted `make import` crashed at runtime. The function is now `async def`, owns its own driver via `async with driver, driver.session()`, and `await`s every `session.run`. Both call sites in `main()` and `_retry_deadletter()` wrap with `asyncio.run(...)`. NAMS users were unaffected; bolt users were broken since v0.12.0.
- **ChatInterface "done" handler no longer reads stale streaming state.** Streaming entities/preferences moved from `useState` to `useRef`; the `done` SSE branch reads `.current` synchronously so accumulators populated during the same render tick can't be one render behind. Refs reset on done / error / sendMessage / startNewConversation.
- **`list_documents_nams` pushes the OBJECT filter server-side.** Previously the `skip + limit + 50` over-fetch could be exhausted by unrelated POLE+O entities, silently dropping documents on busy NAMS instances. Dead `template_id` filter at the same call site removed.
- **`externalInput` useEffect now depends on `loading`.** "Ask about this" clicks landing mid-stream are no longer silently dropped.

### Breaking Changes

- **`--framework maf` removed.** Use `--framework anthropic-tools`. Click rejects `maf` with the standard "Invalid value for '--framework'" error. `FRAMEWORK_ALIASES` and the `resolved_framework` property on `ProjectConfig` are gone — call sites use `config.framework` directly.

### Domains

- **Restored 4 domains as YAML definitions** (count: 23 → 27): `legal`, `education`, `cybersecurity`, `government`. Each ships with a full ontology (12+ entity types, 17+ relationships, 4 decision traces, 5 document templates) plus a deterministic static-fallback fixture and is wired into the scaffold matrix. See [Domain Catalog](/docs/reference/domain-catalog).

### New Documentation

- [How NAMS stores relationships (`ccg-edges`)](/docs/explanation/ccg-edges) — explains the fenced YAML block that encodes relationships into entity descriptions on NAMS, with the migration playbook for when NAMS adds a native `add_relationship` endpoint.
- [Add a Custom Domain](/docs/how-to/add-custom-domain) extended with the LLM generation pipeline internals, two worked examples (insurance claims, podcast production), and the path from `~/.create-context-graph/custom-domains/` to a permanent upstream contribution.

### Code Quality

- `key={i}` replaced with stable identifiers in 4 locations (`ChatInterface.tsx` prompts/entities/preferences, `DecisionTracePanel.tsx` trace steps).
- New `tests/test_bolt_ingest_parity.py` (8 tests) and `TestGeneratedImportDataAsyncShape` in `test_generated_project.py` (5 tests) pin the bolt write contract so neither the async shape nor the Cypher sequence can regress silently.

---

## v0.12.0 — NAMS-native connector ingest + `ccg-edges` relationship encoding

This release closes the loop on running SaaS connectors against the NAMS-default scaffold. Previously, `make import` in a NAMS project went through the bolt-Cypher fallback and effectively didn't work; now both the CLI demo-fixture seeder and the generated `import_data.py` share a NAMS-native write shape, pinned by a contract test.

### New Features

- **`ccg-edges` encoding for relationships on NAMS.** NAMS REST has no `add_relationship` endpoint yet, so outbound edges from each entity are encoded into the source entity's `description` as a fenced ```ccg-edges``` YAML block. The frontend parses these out and renders edges in the graph view; the agent reads them as part of the description. When NAMS adds `add_relationship`, a one-shot migration replays the blocks as native edges — `_build_ccg_edges_block()` is the seam.
- **Dual-tracked documents on NAMS.** Documents now land as both `long_term.add_entity(type=OBJECT)` (queryable source of truth — matches the bolt `:Document` shape) and `short_term.add_message(role="document")` (extraction fuel). The `/documents` route reads from long-term entities; preview content strips the `ccg-edges` and `_pole_type:` markers.
- **Per-connector `BODY_FIELDS` mapping.** Each connector declares which entity-type → property carries the prose body; that body is also fed through `add_message` so the NAMS extractor sees comment bodies, issue descriptions, section text, etc. Pure-metadata entities opt out by omission.
- **Idempotent connector imports.** Generated `import_data.py` tracks per-connector watermarks in `.context-graph/watermarks.json` so re-runs only fetch deltas. Failures go to `.context-graph/deadletter.jsonl` and the watermark only advances on a clean run. New `make import-dry-run` and `make import-retry` targets. `make import` is now both fetch + ingest in one idempotent step on either backend.
- **`run_nams_ingest()` extracted as a reusable async function** in `ingest.py`. Both the CLI Rich-progress path and the generated `import_data.py` drive the same call sequence, pinned by `tests/test_nams_ingest_parity.py`.

### Breaking Changes

- **`make import-and-seed` removed** — `make import` now fetches AND ingests in one step on both backends.
- **`/documents?template_id=...` returns HTTP 501 on NAMS** — template filtering relied on `MENTIONS` edges that NAMS doesn't have. Un-filtered `GET /documents` works on both backends.

### Bug Fixes

- `ingest_data()` legacy bolt signature `(neo4j_uri, neo4j_username, neo4j_password)` restored — v0.11.0 had broken library callers by switching to `ProjectConfig`-only.
- Cypher identifier injection guards on the bolt fallback (`_require_safe_cypher_identifier`) — relationship types and labels are validated against `[A-Za-z_][A-Za-z0-9_]*` before string-interpolation.
- Labeled `MATCH` on bolt relationship ingest — previously falling back to label-less `MATCH (a {name: $name})` which could silently mis-merge across labels.
- Deadletter retry on partial-failure imports — failed records are kept for inspection rather than dropped, and `make import-retry` replays them.

### New Documentation

- [Memory Backends](/docs/explanation/memory-backends) — replaced the "B-partial port" framing with the actual hybrid write shape (`ccg-edges`, dual-tracked documents, `BODY_FIELDS`).
- [Use NAMS](/docs/how-to/use-nams) — "Seeding a relationship-rich graph" rewritten to reflect that NAMS scaffolds now encode relationships into descriptions rather than dropping them.

---

## v0.11.3 — Streaming for CrewAI/Strands + NAMS hardening

This release brings the last two agent frameworks onto full text streaming (CrewAI and Strands now stream both text and tool events via SSE — previously they streamed tool events only), adds a classified error path for NAMS failures so the frontend can surface useful diagnostics, and ships memory-backend auto-detection so the CLI does the right thing when your `.env` credentials and `MEMORY_BACKEND` don't line up.

### New Features

- **All 8 frameworks now stream text** — CrewAI gains streaming via the `LLMStreamChunkEvent` event bus; Strands gains streaming via `agent.stream_async()`. Both still run synchronously in a worker thread, with thread-safe text and tool events streamed through the `CypherResultCollector`. See [Framework Comparison](/docs/reference/framework-comparison).
- **`--import-preview` flag** — parse a Claude AI / ChatGPT export file and print a sanity-check summary (conversation count, date range, sample titles) without scaffolding or ingesting. Useful before committing to a multi-GB import. See [Import Chat History](/docs/tutorials/import-chat-history).
- **Classified NAMS errors in `/health`** — when the memory layer fails to connect, `/health` now returns `nams_error` (one of `auth` / `rate_limit` / `network` / `config` / `unknown`), `nams_error_message` (human-readable), `nams_error_detail`, and `nams_dashboard` — so the frontend can show a useful diagnostic instead of a generic "memory unavailable".
- **Memory-backend auto-detection** — the generated `config.py` reconciles `MEMORY_BACKEND` with the credentials actually present in `.env`: flips `nams → bolt` if `MEMORY_API_KEY` is blank but `NEO4J_URI` is set, and vice-versa, with a warning. An explicit `MEMORY_BACKEND` env var still wins.
- **Lighter NAMS dependency footprint** — generated NAMS scaffolds no longer pull `sentence-transformers` (and therefore `torch`), since NAMS does embeddings server-side. The `neo4j-agent-memory` extras shrink from `[litellm,sentence-transformers]` to `[litellm]`.

### Bug Fixes

- Agent-template degradations fixed across all 8 frameworks (Jinja `param.default is defined` guards; silent render-failure fallback removed so scaffold errors surface instead of producing stub code).
- Custom-domain generation now detects LLM-truncated ontologies via `stop_reason` and validates completeness (non-empty `system_prompt` / `visualization` / `agent_tools`) before writing.
- Strands and CrewAI now return accumulated text deltas on streaming errors instead of discarding them.
- NAMS Docker images no longer fail to build on the `spacy download` step (the spacy guard from v0.11.2's `Makefile` is now mirrored in `Dockerfile.backend`).

### New Documentation

- New **"Seeding a relationship-rich graph"** section in [Use NAMS](/docs/how-to/use-nams) — explains how to seed with `--self-hosted --demo` (which writes the full demo graph including relationships) and then flip `MEMORY_BACKEND=nams` once `add_relationship` lands in the NAMS REST API.

---

## v0.11.0 — NAMS by default + LiteLLM

This release flips the default memory backend from self-hosted Neo4j to the hosted **Neo4j Agent Memory Service (NAMS)** and adds **LiteLLM** provider injection for the memory layer.

### New Features

- **NAMS as default backend** — `create-context-graph my-app` now scaffolds against the hosted NAMS service by default. The CLI prompts for a NAMS API key during the interactive wizard. Sign up at [memory.neo4jlabs.com](https://memory.neo4jlabs.com).
- **`--self-hosted` flag** — preserves the legacy bolt-Neo4j path with full demo fixtures and relationship-rich graph. Recommended for workshops, screen recordings, and offline demos.
- **LiteLLM provider injection** — the generated memory layer accepts `MEMORY_LLM` and `MEMORY_EMBEDDING` env vars with LiteLLM-style provider strings (e.g. `anthropic/claude-haiku-4-5`, `bedrock/...`, `ollama/llama3`). Native adapters resolve first; everything else routes through LiteLLM. See [Configure Memory Providers](/docs/how-to/configure-memory-providers).
- **Streamlined 6-prompt wizard** — collapsed from 11 prompts. Domain picker switched to autocomplete. Anthropic key collection deferred to post-scaffold `.env` editing. Advanced settings (MCP, extraction toggles, extra API keys) hidden behind a single Y/N gate.
- **Default agent framework: Strands** — was previously unselected; now `strands` is the suggested default in the wizard.
- **Backend-aware route adapters** — `/expand`, `/documents`, `/traces`, `/schema/visualization`, `/entities/{name}`, `/search` dispatch to NAMS REST adapters or bolt Cypher based on `MEMORY_BACKEND`.

### Breaking Changes

- **`neo4j-agent-memory` version pin bumped to `>=0.4.0,<0.6.0`** in generated `pyproject.toml`. Existing scaffolds on `>=0.1.0` are unaffected; only newly generated projects pick up the bump.
- **`ingest_data()` signature changed** — now takes a `ProjectConfig` instead of separate Neo4j credentials. CLI users see no change; library users of the `create_context_graph` package should update their callers.
- **`MEMORY_API_KEY` env var** — generated `.env` files include this; auto-routes to NAMS when set.

### NAMS write-path limits to be aware of

The NAMS REST API (v0.4) exposes a narrower write surface than bolt Cypher. The CLI does best-effort ingest with these documented gaps:

- **Relationships between domain entities are not persisted** — NAMS does not yet expose `add_relationship`. Bundled demo entities load successfully but the graph view shows no edges.
- **Entity properties are collapsed into `description`** — NAMS accepts only `{name, type, description}` per entity. The CLI serializes all other properties into a markdown block in the description field so the property pane stays readable.
- **No preferences or facts** — `auto_preferences` is forced off on NAMS.
- **GDS endpoints return 501** — community detection and PageRank require bolt.

For the full demo experience, scaffold with `--self-hosted --demo`.

### New Documentation Pages

- [Use NAMS](/docs/how-to/use-nams) — sign-up, API key, switching between NAMS and self-hosted
- [Configure Memory Providers](/docs/how-to/configure-memory-providers) — LiteLLM provider strings, native adapters, default fallback behavior
- [Memory Backends](/docs/explanation/memory-backends) — NAMS vs self-hosted, when to pick which

---

## v0.9.0

### New Features

- **MCP Server Integration** -- Generated projects can include an MCP server for Claude Desktop, enabling a dual-interface architecture where both the web app and Claude Desktop query the same knowledge graph. See [Connect Claude Desktop](/docs/how-to/connect-claude-desktop).
- **Chat History Import** -- Import your Claude AI or ChatGPT conversation exports into a context graph. Supports date/title filtering, deep mode for tool call decision traces, and streaming parsing for large exports (1GB+). See [Import Chat History](/docs/tutorials/import-chat-history).
- **12 SaaS Connectors** -- Added Claude Code, Claude AI, ChatGPT, and Google Workspace connectors alongside the existing GitHub, Notion, Jira, Slack, Gmail, Google Calendar, Salesforce, and Linear connectors. See [Import SaaS Data](/docs/how-to/import-saas-data).
- **22 Built-in Domains** -- Complete ontology catalog with pre-generated fixture data, domain-specific agent tools, and demo scenarios for every domain. See [Domain Catalog](/docs/reference/domain-catalog).
- **8 Agent Frameworks** -- PydanticAI, Claude Agent SDK, OpenAI Agents SDK, LangGraph, Anthropic Tools, Strands, CrewAI, and Google ADK. See [Framework Comparison](/docs/reference/framework-comparison).
- **Custom Domain Generation** -- Generate complete domain ontology YAMLs from natural language descriptions using LLM. See [Add Custom Domain](/docs/how-to/add-custom-domain).
- **Streaming Chat via SSE** -- Token-by-token text streaming with real-time tool call visualization across 6 frameworks.
- **neo4j-agent-memory Integration** -- Multi-turn conversation memory with automatic entity extraction and preference detection.

### New Documentation Pages

- [Connect Claude Desktop](/docs/how-to/connect-claude-desktop) -- MCP server setup and dual-interface architecture
- [Customizing Your Domain Ontology](/docs/tutorials/customizing-domain-ontology) -- Tutorial for modifying and creating domain ontologies
- [Import Your AI Chat History](/docs/tutorials/import-chat-history) -- Claude AI and ChatGPT import tutorial
- [Chat Import Schema](/docs/reference/chat-import-schema) -- Graph schema reference for chat history imports

### Documentation Improvements

- Full-text search across all documentation pages
- Version banner indicating current documentation version
- Troubleshooting sections added to every tutorial and how-to guide
- Time and difficulty estimates on all tutorials
- Mermaid diagrams for visual explanations
- Expanded cross-linking and "Further Reading" sections throughout
