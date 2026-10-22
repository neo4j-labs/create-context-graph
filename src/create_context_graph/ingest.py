# Copyright 2026 Neo4j Labs
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Data ingestion pipeline via neo4j-agent-memory.

Two backend-specific paths:

* **NAMS** (default) — entities via ``client.long_term.add_entity`` with all
  non-name properties serialized into the entity ``description`` field as a
  markdown block (NAMS REST drops free-form attributes). Connector
  relationships are encoded into the source entity description as a fenced
  ``ccg-edges`` YAML block — when neo4j-agent-memory exposes
  ``add_relationship`` against the NAMS REST API a one-shot migration can
  drain those blocks into native edges. Documents are dual-tracked:
  ``add_entity(Document, ...)`` for the queryable long-term node AND
  ``short_term.add_message`` (role="user", metadata kind="document",
  addressed to a server-created conversation id) to feed the NAMS extractor.
  Entity records whose connector declares a ``BODY_FIELDS`` mapping also
  have their body field sent through ``add_message`` for the same reason.
  Decision traces go through the reasoning REST API unchanged.

* **Bolt** (self-hosted) — full Cypher ingest. Entities via
  ``MemoryClient.long_term.add_entity`` with attributes, relationships via
  direct Cypher MERGE (native edges, no ccg-edges encoding), documents and
  decision traces likewise. The two backends produce structurally different
  graphs by design; the NAMS shape converges with bolt once
  ``add_relationship`` is available upstream.
"""

from __future__ import annotations

import asyncio
import importlib.util
import json
import os
import re
from pathlib import Path
from typing import TYPE_CHECKING, Any

from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn

from create_context_graph.constants import DEFAULT_MEMORY_EMBEDDING_LOCAL
from create_context_graph.ontology import (
    DomainOntology,
    build_nams_ontology_document,
    generate_cypher_schema,
    split_cypher_statements,
)

if TYPE_CHECKING:
    from create_context_graph.config import ProjectConfig

console = Console()


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


_RESERVED_DESCRIPTION_KEYS = {"name", "description", "domain", "id", "uuid"}
_SAFE_CYPHER_IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def _format_attribute(key: str, value: Any) -> str | None:
    """Render one attribute as a human-readable phrase, or None to skip."""
    if value is None or value == "":
        return None
    if isinstance(value, (list, dict)):
        value = json.dumps(value, default=str)
    pretty_key = key.replace("_", " ").strip().capitalize()
    return f"**{pretty_key}**: {value}"


def _serialize_entity_to_description(
    item: dict[str, Any], label: str, pole_type: str
) -> str:
    """Build a markdown description that preserves entity attributes.

    NAMS REST drops everything except ``{name, type, description}`` on
    ``add_entity``. To keep the per-entity property pane in the frontend
    populated, we serialize the remaining ontology properties into a markdown
    block stuffed into ``description``.
    """
    parts: list[str] = []
    existing = (item.get("description") or "").strip()
    if existing:
        parts.append(existing)
    else:
        parts.append(f"{label}.")

    attr_lines: list[str] = []
    for key, value in item.items():
        if key in _RESERVED_DESCRIPTION_KEYS:
            continue
        line = _format_attribute(key, value)
        if line:
            attr_lines.append(line)

    if attr_lines:
        parts.append("")
        parts.extend(attr_lines)

    parts.append("")
    parts.append(f"_pole_type: {pole_type}_")
    return "\n".join(parts)


def _get_pole_type(label: str, ontology: DomainOntology) -> str:
    """Map an entity label to its POLE+O type."""
    for et in ontology.entity_types:
        if et.label == label:
            return et.pole_type
    return "OBJECT"


def _require_safe_cypher_identifier(value: str, kind: str) -> str:
    """Validate a dynamic Cypher identifier before string interpolation."""
    if isinstance(value, str) and _SAFE_CYPHER_IDENTIFIER_RE.fullmatch(value):
        return value
    raise ValueError(f"Unsafe Cypher {kind}: {value!r}")


# ---------------------------------------------------------------------------
# NAMS shared primitives — also used by the generated import_data.py.j2.
# A contract test (test_nams_ingest_parity.py) pins the call sequence so the
# two consumers don't drift; if you change behavior here, mirror it in the
# template and update the snapshot.
# ---------------------------------------------------------------------------


# Marker for the fenced YAML block we inject into entity descriptions to
# carry connector-emitted relationships. NAMS REST has no ``add_relationship``
# today, so edges live inside the source entity's ``description`` field; a
# future migration parses these blocks and replays them as native edges.
CCG_EDGES_OPEN = "```ccg-edges"
CCG_EDGES_CLOSE = "```"


def _build_ccg_edges_block(
    relationships: list[dict[str, Any]], source_name: str
) -> str:
    """Build a fenced ``ccg-edges`` block listing this entity's outbound edges.

    Returns empty string when ``source_name`` has no outbound edges. The block
    is deterministic (sorted by type then target) so contract tests can diff
    snapshots stably.
    """
    out: list[dict[str, str]] = []
    for rel in relationships:
        if rel.get("source_name") != source_name:
            continue
        out.append({
            "type": rel.get("type", ""),
            "target": rel.get("target_name", ""),
            "target_label": rel.get("target_label", ""),
        })
    if not out:
        return ""
    out.sort(key=lambda e: (e["type"], e["target"]))
    lines = [CCG_EDGES_OPEN]
    for edge in out:
        lines.append(f"- type: {edge['type']}")
        lines.append(f"  target: {edge['target']}")
        if edge["target_label"]:
            lines.append(f"  target_label: {edge['target_label']}")
    lines.append(CCG_EDGES_CLOSE)
    return "\n".join(lines)


def _description_with_edges(
    base_description: str,
    relationships: list[dict[str, Any]],
    source_name: str,
) -> str:
    """Append the ccg-edges block (if any) to ``base_description``."""
    block = _build_ccg_edges_block(relationships, source_name)
    if not block:
        return base_description
    return f"{base_description}\n\n{block}"


def _resolve_body(
    item: dict[str, Any], label: str, body_fields: dict[str, str]
) -> str | None:
    """Return the body text for an entity record, or None if it has no body.

    The connector declares ``BODY_FIELDS = {label: property_name}``. We look
    up the property; if it's a non-empty string, it's the body. Anything else
    (missing, empty, non-string) means this record skips the add_message
    channel.
    """
    field = body_fields.get(label)
    if not field:
        return None
    value = item.get(field)
    if not isinstance(value, str):
        return None
    stripped = value.strip()
    if not stripped:
        return None
    return value


# ---------------------------------------------------------------------------
# NAMS branch — typed entities + ccg-edges + dual-tracked documents
# ---------------------------------------------------------------------------


async def ensure_nams_ontology(
    client: Any,
    domain_id: str,
    ontology_document: dict | None = None,
) -> str:
    """Make the workspace's active NAMS ontology match ``domain_id``.

    NAMS auto-binds every workspace to the generic ``nams-default`` ontology
    until an explicit one is activated, and pre-registers an ontology for
    each bundled domain. Resolution order:

      1. already active            → ``"already-active"`` (no-op)
      2. catalog match by name     → activate its latest version (``"activated"``)
      3. ``ontology_document`` set → create it, then activate (``"created"`` —
         the custom-domain path; the document comes from
         :func:`build_nams_ontology_document`)

    Best-effort by design: returns ``"unavailable"`` on any failure or when
    nothing matches and no document was provided — memory writes still work
    against the default ontology, just without domain-shaped extraction.
    All calls use keyword arguments so the parity contract test can record
    them uniformly.
    """
    try:
        active = await client.ontology.get_active()
        active_domain = getattr(
            getattr(getattr(active, "document", None), "domain", None), "id", None
        )
        if active_domain == domain_id:
            return "already-active"

        summaries = await client.ontology.list()
        match = next(
            (s for s in summaries if getattr(s, "name", None) == domain_id), None
        )
        if match is not None:
            full = await client.ontology.get(ontology_id=match.id)
            versions = getattr(full, "versions", None) or []
            if versions:
                latest = max(versions, key=lambda v: getattr(v, "revision", 0) or 0)
                await client.ontology.activate(version_id=latest.id)
                return "activated"

        if ontology_document is not None:
            created = await client.ontology.create(
                name=domain_id, schema=ontology_document
            )
            await client.ontology.activate(version_id=created.id)
            return "created"
        return "unavailable"
    except Exception as e:  # noqa: BLE001 — ontology is an enhancement, not a gate
        console.print(f"  [yellow]NAMS ontology activation skipped:[/yellow] {e}")
        return "unavailable"


async def run_nams_ingest(
    client: Any,
    fixture_data: dict,
    ontology: DomainOntology,
    body_fields: dict[str, str] | None = None,
    on_event: Any = None,
) -> dict[str, int]:
    """Execute the NAMS write plan against an already-open MemoryClient.

    Exposed separately from ``_ingest_with_nams`` (which owns the client
    lifecycle and Rich progress UI) so the contract test and the scaffolded
    ``import_data.py`` can drive the same sequence against their own client.

    ``body_fields`` is the merged ``BODY_FIELDS`` from every active
    connector ({label: property_name}). ``on_event`` is an optional callable
    taking (stage: str, payload: dict) for progress reporting; pass None to
    silence.
    """
    body_fields = body_fields or {}
    domain_id = ontology.domain.id
    relationships = fixture_data.get("relationships", [])
    counts = {
        "entities": 0,
        "documents": 0,
        "bodies": 0,
        "traces": 0,
        "edges_encoded": 0,
        "failures": 0,
    }
    failures: list[dict[str, Any]] = []

    def _emit(stage: str, **payload: Any) -> None:
        if on_event is not None:
            on_event(stage, payload)

    # Stage 0: bind the workspace to the domain ontology (best-effort) so
    # data is stamped with — and extraction speaks — the domain vocabulary
    # instead of nams-default.
    ontology_status = await ensure_nams_ontology(
        client, domain_id, build_nams_ontology_document(ontology)
    )
    _emit("ontology", status=ontology_status)

    # NAMS only accepts messages addressed to conversation ids IT minted at
    # create time — posting to a client-chosen session string 404s with
    # "conversation not found". Channels are created lazily (one per message
    # stream) and the server-assigned id is what add_message must target.
    _channel_ids: dict[str, str | None] = {}

    async def _message_channel(session_hint: str) -> str | None:
        """Return the server conversation id for ``session_hint``, or None if
        the channel can't be created (message writes are then skipped)."""
        if session_hint not in _channel_ids:
            try:
                conv = await client.short_term.create_conversation(
                    session_id=session_hint
                )
                _channel_ids[session_hint] = str(getattr(conv, "id", "") or "") or None
            except Exception as exc:  # noqa: BLE001
                failures.append({
                    "kind": "conversation", "name": session_hint, "error": str(exc),
                })
                _channel_ids[session_hint] = None
        return _channel_ids[session_hint]

    # Stage 1: entities with ccg-edges encoded into description.
    entities = fixture_data.get("entities", {})
    for label, items in entities.items():
        pole_type = _get_pole_type(label, ontology)
        body_field = body_fields.get(label)
        for entity_index, item in enumerate(items):
            name = item.get("name") or f"{label}-{entity_index}"
            base = _serialize_entity_to_description(item, label, pole_type)
            description = _description_with_edges(base, relationships, name)
            if description is not base:
                counts["edges_encoded"] += 1
            try:
                await client.long_term.add_entity(
                    name=name,
                    entity_type=pole_type,
                    description=description,
                )
                counts["entities"] += 1
            except Exception as exc:  # noqa: BLE001 — surface to deadletter
                failures.append({"kind": "entity", "name": name, "error": str(exc)})
                counts["failures"] += 1
                continue

            # Hybrid: if this entity carries a body, feed it through
            # short_term.add_message so NAMS extracts secondary structure.
            if body_field is None:
                continue
            body = _resolve_body(item, label, body_fields)
            if body is None:
                continue
            try:
                channel = await _message_channel(f"bodies-{domain_id}")
                if channel is None:
                    raise RuntimeError("bodies conversation unavailable")
                # role must be user/assistant/system — NAMS rejects custom
                # roles; the metadata kind marks this as extraction fuel.
                await client.short_term.add_message(
                    session_id=channel,
                    role="user",
                    content=body,
                    metadata={
                        "kind": "entity-body",
                        "entity_name": name,
                        "entity_label": label,
                        "domain": domain_id,
                    },
                )
                counts["bodies"] += 1
            except Exception as exc:  # noqa: BLE001
                failures.append({"kind": "body", "name": name, "error": str(exc)})
                counts["failures"] += 1
    _emit("entities", count=counts["entities"], edges=counts["edges_encoded"])

    # Stage 2: documents — dual-tracked (long_term entity + short_term message).
    # Document MENTIONS edges to mentioned entities live in the same ccg-edges
    # YAML block as everything else; the document's outbound edges are
    # discovered via relationships[].source_name == document title.
    documents = fixture_data.get("documents", [])
    doc_session = f"docs-{domain_id}"
    for doc in documents:
        title = doc.get("title", "")
        if not title:
            counts["failures"] += 1
            failures.append({"kind": "document", "error": "missing title"})
            continue
        content = doc.get("content", "")
        doc_base = (
            f"{content}\n\n_pole_type: OBJECT_"
            if content
            else f"Document: {title}\n\n_pole_type: OBJECT_"
        )
        doc_description = _description_with_edges(doc_base, relationships, title)
        try:
            await client.long_term.add_entity(
                name=title,
                entity_type="OBJECT",
                description=doc_description,
            )
            channel = await _message_channel(doc_session)
            if channel is None:
                raise RuntimeError("docs conversation unavailable")
            await client.short_term.add_message(
                session_id=channel,
                role="user",
                content=content,
                metadata={
                    "kind": "document",
                    "title": title,
                    "template_id": doc.get("template_id", ""),
                    "template_name": doc.get("template_name", ""),
                    "domain": domain_id,
                },
            )
            counts["documents"] += 1
        except Exception as exc:  # noqa: BLE001
            failures.append({"kind": "document", "name": title, "error": str(exc)})
            counts["failures"] += 1
    _emit("documents", count=counts["documents"])

    # Stage 3: decision traces via reasoning API (unchanged).
    traces = fixture_data.get("traces", [])
    trace_session = f"traces-{domain_id}"
    for trace_data in traces:
        try:
            trace = await client.reasoning.start_trace(
                session_id=trace_session,
                task=trace_data.get("task", ""),
            )
            trace_id = getattr(trace, "id", None) or trace_data.get("id", "")
            for step in trace_data.get("steps", []):
                await client.reasoning.add_step(
                    trace_id=trace_id,
                    thought=step.get("thought", ""),
                    action=step.get("action", ""),
                    observation=step.get("observation", ""),
                )
            await client.reasoning.complete_trace(
                trace_id=trace_id,
                outcome=trace_data.get("outcome", ""),
                success=True,
            )
            counts["traces"] += 1
        except Exception as exc:  # noqa: BLE001
            failures.append({"kind": "trace", "id": trace_data.get("id", ""), "error": str(exc)})
            counts["failures"] += 1
    _emit("traces", count=counts["traces"])

    counts["failure_records"] = failures  # type: ignore[assignment]
    return counts


async def _ingest_with_nams(
    fixture_data: dict,
    ontology: DomainOntology,
    api_key: str,
    endpoint: str,
    body_fields: dict[str, str] | None = None,
) -> None:
    """Ingest fixture data through the NAMS REST client.

    Wraps :func:`run_nams_ingest` with client lifecycle + Rich progress. See
    that function's docstring for the per-stage semantics.
    """
    from neo4j_agent_memory import MemoryClient, MemorySettings, NamsConfig
    from pydantic import SecretStr

    settings = MemorySettings(
        backend="nams",
        nams=NamsConfig(api_key=SecretStr(api_key), endpoint=endpoint),
    )

    async with MemoryClient(settings) as client:
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console,
        ) as progress:
            console.print(
                "  [dim][1/3] NAMS owns schema — skipping CREATE CONSTRAINT statements[/dim]"
            )
            task = progress.add_task("[2/3] Ingesting entities + documents (NAMS)...", total=None)

            def _on_stage(stage: str, payload: dict) -> None:
                if stage == "ontology":
                    label = {
                        "already-active": "domain ontology already active",
                        "activated": "activated domain ontology",
                        "created": "created + activated custom domain ontology",
                        "unavailable": "using NAMS default ontology",
                    }.get(payload.get("status", ""), payload.get("status", ""))
                    console.print(
                        f"  [dim][0/3] {label} ({ontology.domain.id})[/dim]"
                    )

            counts = await run_nams_ingest(
                client=client,
                fixture_data=fixture_data,
                ontology=ontology,
                body_fields=body_fields,
                on_event=_on_stage,
            )
            progress.update(
                task,
                description=(
                    f"[2/3] Ingested {counts['entities']} entities "
                    f"({counts['edges_encoded']} with ccg-edges), "
                    f"{counts['documents']} documents, "
                    f"{counts['bodies']} entity bodies"
                ),
            )
            progress.update(
                progress.add_task(
                    f"[3/3] Ingested {counts['traces']} decision traces",
                    total=None,
                ),
                completed=1,
            )

    rel_total = len(fixture_data.get("relationships", []))
    console.print(
        f"\n  [green]NAMS ingestion complete:[/green] {counts['entities']} entities, "
        f"{counts['documents']} documents, {counts['traces']} traces "
        f"([dim]{rel_total} relationships encoded into "
        f"{counts['edges_encoded']} entity descriptions as ccg-edges blocks; "
        f"will migrate to native edges when NAMS add_relationship is available[/dim])"
    )
    if counts["failures"]:
        console.print(
            f"  [yellow]{counts['failures']} record(s) failed — see logs for details.[/yellow]"
        )


# ---------------------------------------------------------------------------
# Bolt branch — full ingest via MemoryClient (writes Cypher under the hood)
# ---------------------------------------------------------------------------


async def _ingest_with_memory_client(
    fixture_data: dict,
    ontology: DomainOntology,
    neo4j_uri: str,
    neo4j_username: str,
    neo4j_password: str,
    neo4j_database: str = "",
) -> None:
    """Ingest data using neo4j-agent-memory MemoryClient (bolt backend).

    ``neo4j_database`` of ``""`` defers to the library default ("neo4j");
    set it for instances whose database isn't literally named "neo4j".
    """
    from pydantic import SecretStr
    from neo4j_agent_memory import MemoryClient, MemorySettings

    neo4j_config: dict = {
        "uri": neo4j_uri,
        "username": neo4j_username,
        "password": SecretStr(neo4j_password),
    }
    if neo4j_database:
        neo4j_config["database"] = neo4j_database

    # The CLI only writes fixture entities; it never runs entity extraction,
    # so disable the extraction pipeline (avoids importing spacy/gliner/torch).
    # Embeddings: neo4j-agent-memory defaults to OpenAI and embeds *before*
    # writing, so without a key every add_entity would fail silently. Prefer a
    # local sentence-transformers embedder when installed, OpenAI when a key
    # is present, and otherwise write entities without embeddings.
    settings_kwargs: dict = {"neo4j": neo4j_config}
    try:
        from neo4j_agent_memory import ExtractionConfig, ExtractorType

        settings_kwargs["extraction"] = ExtractionConfig(extractor_type=ExtractorType.NONE)
    except ImportError:
        pass
    generate_embedding = True
    if os.environ.get("OPENAI_API_KEY"):
        pass  # library default: openai/text-embedding-3-small
    elif importlib.util.find_spec("sentence_transformers") is not None:
        settings_kwargs["embedding"] = DEFAULT_MEMORY_EMBEDDING_LOCAL
    else:
        generate_embedding = False
        console.print(
            "  [yellow]Note:[/yellow] no embedding provider available "
            "(set OPENAI_API_KEY or install sentence-transformers) — "
            "entities are written without embeddings; vector search will be empty."
        )

    settings = MemorySettings(**settings_kwargs)

    async with MemoryClient(settings) as client:
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console,
        ) as progress:

            # Step 1: Apply schema
            task = progress.add_task("[1/4] Applying schema...", total=None)
            cypher_schema = generate_cypher_schema(ontology)
            for stmt in split_cypher_statements(cypher_schema):
                try:
                    await client.graph.execute_write(stmt)
                except Exception as e:
                    if "already exists" not in str(e).lower():
                        console.print(f"  [yellow]Warning:[/yellow] Schema: {e}")
            progress.update(task, description="[1/4] Schema applied")

            # Step 2: Ingest entities
            task = progress.add_task("[2/4] Ingesting entities...", total=None)
            entity_count = 0
            entities = fixture_data.get("entities", {})
            for label, items in entities.items():
                pole_type = _get_pole_type(label, ontology)
                for item in items:
                    name = item.get("name", f"{label}-{entity_count}")
                    try:
                        attrs = {**item, "domain": ontology.domain.id}
                        await client.long_term.add_entity(
                            name=name,
                            entity_type=pole_type,
                            description=item.get("description", f"{label}: {name}"),
                            attributes=attrs,
                            generate_embedding=generate_embedding,
                        )
                        entity_count += 1
                    except Exception as e:
                        console.print(f"  [yellow]Warning:[/yellow] Entity {name}: {e}")
            progress.update(task, description=f"[2/4] Ingested {entity_count} entities")

            # Step 2b: relationships via Cypher
            relationships = fixture_data.get("relationships", [])
            rel_count = 0
            for rel in relationships:
                try:
                    rel_type = _require_safe_cypher_identifier(
                        rel.get("type", ""), "relationship type",
                    )
                    cypher = f"""
                    MATCH (a {{name: $source_name}})
                    MATCH (b {{name: $target_name}})
                    MERGE (a)-[r:{rel_type}]->(b)
                    RETURN type(r)
                    """
                    await client.graph.execute_write(
                        cypher,
                        {
                            "source_name": rel["source_name"],
                            "target_name": rel["target_name"],
                        },
                    )
                    rel_count += 1
                except Exception as e:
                    console.print(f"  [yellow]Warning:[/yellow] Relationship {rel.get('type', '?')}: {e}")
            console.print(f"  Created {rel_count} relationships")

            # Step 3: documents
            task = progress.add_task("[3/4] Ingesting documents...", total=None)
            doc_count = 0
            documents = fixture_data.get("documents", [])
            for doc in documents:
                try:
                    cypher = """
                    MERGE (d:Document {title: $title})
                    SET d.content = $content,
                        d.template_id = $template_id,
                        d.template_name = $template_name,
                        d.domain = $domain
                    """
                    await client.graph.execute_write(
                        cypher,
                        {
                            "title": doc.get("title", ""),
                            "content": doc.get("content", ""),
                            "template_id": doc.get("template_id", ""),
                            "template_name": doc.get("template_name", ""),
                            "domain": ontology.domain.id,
                        },
                    )
                    doc_count += 1
                except Exception as e:
                    console.print(f"  [yellow]Warning:[/yellow] Document: {e}")
            if doc_count > 0:
                try:
                    link_cypher = """
                    MATCH (d:Document) WHERE d.domain = $domain
                    MATCH (e) WHERE e.name IS NOT NULL
                      AND NOT 'Document' IN labels(e)
                      AND NOT 'DecisionTrace' IN labels(e)
                      AND NOT 'TraceStep' IN labels(e)
                      AND (e.domain IS NULL OR e.domain = $domain)
                      AND d.content CONTAINS e.name
                    MERGE (d)-[:MENTIONS]->(e)
                    """
                    await client.graph.execute_write(
                        link_cypher, {"domain": ontology.domain.id}
                    )
                except Exception as e:
                    console.print(f"  [yellow]Warning:[/yellow] Document links: {e}")
            progress.update(task, description=f"[3/4] Ingested {doc_count} documents")

            # Step 4: decision traces
            task = progress.add_task("[4/4] Ingesting decision traces...", total=None)
            trace_count = 0
            traces = fixture_data.get("traces", [])
            for trace_data in traces:
                try:
                    await client.graph.execute_write(
                        "MERGE (t:DecisionTrace {id: $id}) "
                        "SET t.task = $task, t.outcome = $outcome, t.domain = $domain",
                        {
                            "id": trace_data.get("id", ""),
                            "task": trace_data.get("task", ""),
                            "outcome": trace_data.get("outcome", ""),
                            "domain": ontology.domain.id,
                        },
                    )
                    for i, step in enumerate(trace_data.get("steps", [])):
                        await client.graph.execute_write(
                            "MATCH (t:DecisionTrace {id: $trace_id}) "
                            "MERGE (s:TraceStep {trace_id: $trace_id, step_number: $step_number}) "
                            "SET s.thought = $thought, s.action = $action, s.observation = $observation "
                            "MERGE (t)-[:HAS_STEP]->(s)",
                            {
                                "trace_id": trace_data.get("id", ""),
                                "step_number": i + 1,
                                "thought": step.get("thought", ""),
                                "action": step.get("action", ""),
                                "observation": step.get("observation", ""),
                            },
                        )
                    trace_count += 1
                except Exception as e:
                    console.print(f"  [yellow]Warning:[/yellow] Trace: {e}")
            progress.update(task, description=f"[4/4] Ingested {trace_count} decision traces")

    console.print(
        f"\n  [green]Ingestion complete:[/green] {entity_count} entities, "
        f"{rel_count} relationships, {doc_count} documents, {trace_count} traces"
    )


async def _ingest_with_driver(
    fixture_data: dict,
    ontology: DomainOntology,
    neo4j_uri: str,
    neo4j_username: str,
    neo4j_password: str,
    neo4j_database: str = "",
) -> None:
    """Fallback: ingest using neo4j driver directly (no neo4j-agent-memory)."""
    from neo4j import AsyncGraphDatabase

    driver = AsyncGraphDatabase.driver(
        neo4j_uri,
        auth=(neo4j_username, neo4j_password),
    )
    # None defers to the server default database ("neo4j" unless reconfigured).
    session_db = neo4j_database or None

    try:
        await driver.verify_connectivity()
    except Exception as e:
        console.print(f"  [red]Cannot connect to Neo4j:[/red] {e}")
        await driver.close()
        return

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:

        task = progress.add_task("[1/5] Applying schema...", total=None)
        cypher_schema = generate_cypher_schema(ontology)
        async with driver.session(database=session_db) as session:
            for stmt in split_cypher_statements(cypher_schema):
                try:
                    await session.run(stmt)
                except Exception as e:
                    if "already exists" not in str(e).lower():
                        console.print(f"  [yellow]Warning:[/yellow] Schema: {e}")
        progress.update(task, description="[1/5] Schema applied")

        task = progress.add_task("[2/5] Creating entities...", total=None)
        entity_count = 0
        entities = fixture_data.get("entities", {})
        async with driver.session(database=session_db) as session:
            for label, items in entities.items():
                try:
                    safe_label = _require_safe_cypher_identifier(label, "label")
                except ValueError as e:
                    console.print(f"  [yellow]Warning:[/yellow] Label {label!r}: {e}")
                    continue
                for item in items:
                    enriched = {**item, "domain": ontology.domain.id}
                    set_clauses = ", ".join(f"n.{k} = ${k}" for k in enriched.keys())
                    cypher = f"MERGE (n:{safe_label} {{name: $name, domain: $domain}}) SET {set_clauses}"
                    try:
                        await session.run(cypher, enriched)
                        entity_count += 1
                    except Exception as e:
                        console.print(f"  [yellow]Warning:[/yellow] Entity {item.get('name', '?')}: {e}")
        progress.update(task, description=f"[2/5] Created {entity_count} entities")

        task = progress.add_task("[3/5] Creating relationships...", total=None)
        rel_count = 0
        relationships = fixture_data.get("relationships", [])
        async with driver.session(database=session_db) as session:
            for rel in relationships:
                try:
                    source_label = _require_safe_cypher_identifier(
                        rel.get("source_label", ""), "source label",
                    )
                    target_label = _require_safe_cypher_identifier(
                        rel.get("target_label", ""), "target label",
                    )
                    rel_type = _require_safe_cypher_identifier(
                        rel.get("type", ""), "relationship type",
                    )
                    cypher = f"""
                    MATCH (a:{source_label} {{name: $source_name}})
                    MATCH (b:{target_label} {{name: $target_name}})
                    MERGE (a)-[r:{rel_type}]->(b)
                    """
                    await session.run(cypher, {
                        "source_name": rel["source_name"],
                        "target_name": rel["target_name"],
                    })
                    rel_count += 1
                except Exception as e:
                    console.print(f"  [yellow]Warning:[/yellow] Relationship {rel.get('type', '?')}: {e}")
        progress.update(task, description=f"[3/5] Created {rel_count} relationships")

        task = progress.add_task("[4/5] Creating documents...", total=None)
        doc_count = 0
        documents = fixture_data.get("documents", [])
        async with driver.session(database=session_db) as session:
            for doc in documents:
                try:
                    await session.run(
                        "MERGE (d:Document {title: $title}) "
                        "SET d.content = $content, d.template_id = $template_id, "
                        "d.template_name = $template_name, d.domain = $domain",
                        {
                            "title": doc.get("title", ""),
                            "content": doc.get("content", ""),
                            "template_id": doc.get("template_id", ""),
                            "template_name": doc.get("template_name", ""),
                            "domain": ontology.domain.id,
                        },
                    )
                    doc_count += 1
                except Exception as e:
                    console.print(f"  [yellow]Warning:[/yellow] Document: {e}")
            if doc_count > 0:
                try:
                    await session.run(
                        "MATCH (d:Document) WHERE d.domain = $domain "
                        "MATCH (e) WHERE e.name IS NOT NULL "
                        "AND NOT 'Document' IN labels(e) "
                        "AND NOT 'DecisionTrace' IN labels(e) "
                        "AND NOT 'TraceStep' IN labels(e) "
                        "AND (e.domain IS NULL OR e.domain = $domain) "
                        "AND d.content CONTAINS e.name "
                        "MERGE (d)-[:MENTIONS]->(e)",
                        {"domain": ontology.domain.id},
                    )
                except Exception as e:
                    console.print(f"  [yellow]Warning:[/yellow] Document links: {e}")
        progress.update(task, description=f"[4/5] Created {doc_count} documents")

        task = progress.add_task("[5/5] Creating decision traces...", total=None)
        trace_count = 0
        traces = fixture_data.get("traces", [])
        async with driver.session(database=session_db) as session:
            for trace_data in traces:
                try:
                    await session.run(
                        "MERGE (t:DecisionTrace {id: $id}) "
                        "SET t.task = $task, t.outcome = $outcome, t.domain = $domain",
                        {
                            "id": trace_data.get("id", ""),
                            "task": trace_data.get("task", ""),
                            "outcome": trace_data.get("outcome", ""),
                            "domain": ontology.domain.id,
                        },
                    )
                    for i, step in enumerate(trace_data.get("steps", [])):
                        await session.run(
                            "MATCH (t:DecisionTrace {id: $trace_id}) "
                            "MERGE (s:TraceStep {trace_id: $trace_id, step_number: $step_number}) "
                            "SET s.thought = $thought, s.action = $action, s.observation = $observation "
                            "MERGE (t)-[:HAS_STEP]->(s)",
                            {
                                "trace_id": trace_data.get("id", ""),
                                "step_number": i + 1,
                                "thought": step.get("thought", ""),
                                "action": step.get("action", ""),
                                "observation": step.get("observation", ""),
                            },
                        )
                    trace_count += 1
                except Exception as e:
                    console.print(f"  [yellow]Warning:[/yellow] Trace: {e}")
        progress.update(task, description=f"[5/5] Created {trace_count} decision traces")

    await driver.close()
    console.print(
        f"\n  [green]Ingestion complete:[/green] {entity_count} entities, "
        f"{rel_count} relationships, {doc_count} documents, {trace_count} traces"
    )


# ---------------------------------------------------------------------------
# Reset helpers
# ---------------------------------------------------------------------------


def reset_neo4j(
    neo4j_uri: str,
    neo4j_username: str,
    neo4j_password: str,
    neo4j_database: str = "",
) -> None:
    """Clear all data from Neo4j (bolt backend)."""
    from neo4j import GraphDatabase

    with GraphDatabase.driver(neo4j_uri, auth=(neo4j_username, neo4j_password)) as driver:
        with driver.session(database=neo4j_database or None) as session:
            session.run("MATCH (n) DETACH DELETE n")


async def _reset_nams(api_key: str, endpoint: str) -> None:
    """Report what a NAMS reset *would* remove — deletion isn't possible.

    Neither the NAMS REST API nor neo4j-agent-memory (through 0.5.x) exposes
    an entity delete endpoint (``long_term.delete_entity`` does not exist,
    and the cypher API is read-only). Earlier versions of this function
    silently reported "0 entities removed" by swallowing AttributeErrors;
    being honest beats pretending.
    """
    from neo4j_agent_memory import MemoryClient, MemorySettings, NamsConfig
    from pydantic import SecretStr

    settings = MemorySettings(
        backend="nams",
        nams=NamsConfig(api_key=SecretStr(api_key), endpoint=endpoint),
    )
    entity_count: int | None = None
    async with MemoryClient(settings) as client:
        try:
            rows = await client.query.cypher(
                "MATCH (n) WHERE n.id IS NOT NULL RETURN count(n) AS n", {}
            )
            if rows and isinstance(rows[0], dict):
                entity_count = int(rows[0].get("n", 0))
        except Exception:
            pass
    counted = f"{entity_count} stored entities" if entity_count is not None else "stored data"
    console.print(
        f"  [yellow]NAMS reset is not available:[/yellow] the NAMS REST API "
        f"(and neo4j-agent-memory 0.5.x) exposes no delete endpoint, so the "
        f"CLI cannot remove {counted}."
    )
    console.print(
        "  Manage stored data at https://memory.neo4jlabs.com, or use a "
        "--self-hosted scaffold for full control."
    )


def reset_memory_store(config: "ProjectConfig") -> None:
    """Backend-aware reset entry point."""
    if config.is_nams:
        if not config.nams_api_key:
            console.print("  [red]No NAMS API key available — set MEMORY_API_KEY to reset.[/red]")
            return
        asyncio.run(_reset_nams(config.nams_api_key, config.nams_endpoint))
    else:
        reset_neo4j(
            config.neo4j_uri,
            config.neo4j_username,
            config.neo4j_password,
            config.neo4j_database,
        )


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def _coerce_ingest_config(
    ontology: DomainOntology,
    config_or_uri: "ProjectConfig | str",
    neo4j_username: str | None,
    neo4j_password: str | None,
) -> "ProjectConfig":
    """Accept either a ProjectConfig or the legacy bolt Neo4j credentials."""
    from create_context_graph.config import ProjectConfig

    if isinstance(config_or_uri, ProjectConfig):
        return config_or_uri

    if neo4j_username is None or neo4j_password is None:
        raise TypeError(
            "ingest_data() requires neo4j_username and neo4j_password when called "
            "with the legacy (neo4j_uri, neo4j_username, neo4j_password) signature"
        )

    return ProjectConfig(
        project_name=ontology.domain.name,
        domain=ontology.domain.id,
        memory_backend="bolt",
        neo4j_uri=config_or_uri,
        neo4j_username=neo4j_username,
        neo4j_password=neo4j_password,
    )


def ingest_data(
    fixture_path: Path,
    ontology: DomainOntology,
    config_or_uri: "ProjectConfig | str",
    neo4j_username: str | None = None,
    neo4j_password: str | None = None,
    body_fields: dict[str, str] | None = None,
) -> None:
    """Ingest fixture data into the configured memory backend.

    Accepts either a ``ProjectConfig`` or the legacy bolt-only
    ``(neo4j_uri, neo4j_username, neo4j_password)`` arguments.

    Examples:
        ingest_data(fixture_path, ontology, config)
        ingest_data(fixture_path, ontology, neo4j_uri, neo4j_username, neo4j_password)

    ``body_fields`` is the union of every active connector's ``BODY_FIELDS``
    map; the demo fixture path passes ``None``/``{}`` because pre-generated
    fixtures don't carry connector-specific body conventions.
    """
    config = _coerce_ingest_config(
        ontology, config_or_uri, neo4j_username, neo4j_password
    )

    if not fixture_path.exists():
        console.print(f"[red]Fixture file not found:[/red] {fixture_path}")
        return

    fixture_data = json.loads(fixture_path.read_text())

    console.print(f"\n  Ingesting {ontology.domain.name} data into {config.memory_backend}...")

    if config.is_nams:
        if not config.nams_api_key:
            console.print(
                "  [red]Cannot ingest into NAMS: no API key. "
                "Set MEMORY_API_KEY or pass --nams-api-key.[/red]"
            )
            return
        asyncio.run(
            _ingest_with_nams(
                fixture_data, ontology, config.nams_api_key, config.nams_endpoint,
                body_fields=body_fields,
            )
        )
        return

    # Bolt path: try MemoryClient first, fall back to direct driver
    try:
        import neo4j_agent_memory  # noqa: F401
        asyncio.run(
            _ingest_with_memory_client(
                fixture_data, ontology,
                config.neo4j_uri, config.neo4j_username, config.neo4j_password,
                neo4j_database=config.neo4j_database,
            )
        )
    except ImportError:
        console.print("  [yellow]neo4j-agent-memory not installed, using direct driver[/yellow]")
        asyncio.run(
            _ingest_with_driver(
                fixture_data, ontology,
                config.neo4j_uri, config.neo4j_username, config.neo4j_password,
                neo4j_database=config.neo4j_database,
            )
        )
