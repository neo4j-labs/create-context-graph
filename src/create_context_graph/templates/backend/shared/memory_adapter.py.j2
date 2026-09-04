"""Backend-aware adapters for graph endpoints + fixture ingestion.

When ``settings.memory_backend == "nams"`` the NAMS REST API has a restricted
surface compared to bolt Cypher — these helpers translate REST responses into
the shape the frontend expects, and provide a NAMS-flavored ``make seed``
implementation.

When ``settings.memory_backend == "bolt"`` the helpers delegate to the existing
Cypher-based functions in ``app.context_graph_client``.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from app.config import settings
from app.memory import get_client

logger = logging.getLogger(__name__)


_RESERVED_DESCRIPTION_KEYS = {"name", "description", "domain", "id", "uuid"}
CCG_EDGES_OPEN = "```ccg-edges"
CCG_EDGES_CLOSE = "```"


def _format_attribute(key: str, value: Any) -> str | None:
    if value is None or value == "":
        return None
    if isinstance(value, (list, dict)):
        value = json.dumps(value, default=str)
    pretty_key = key.replace("_", " ").strip().capitalize()
    return f"**{pretty_key}**: {value}"


def _serialize_entity_to_description(item: dict[str, Any], label: str, pole_type: str) -> str:
    parts: list[str] = []
    existing = (item.get("description") or "").strip()
    if existing:
        parts.append(existing)
    else:
        parts.append(f"{label}.")
    attr_lines = []
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


def _build_ccg_edges_block(relationships: list[dict[str, Any]], source_name: str) -> str:
    """Encode outbound edges from ``source_name`` as a fenced YAML block.

    NAMS REST has no add_relationship today; the block embeds enough info
    (type, target, target_label) for a future migration to read it back and
    call add_relationship per entry. Deterministically sorted for stable
    parity tests.
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


def _description_with_edges(base: str, relationships: list[dict[str, Any]], source_name: str) -> str:
    block = _build_ccg_edges_block(relationships, source_name)
    return f"{base}\n\n{block}" if block else base


# ---------------------------------------------------------------------------
# Fixture ingestion (NAMS)
# ---------------------------------------------------------------------------


_POLE_TYPE_HINTS = {
    # Best-effort name → POLE+O mapping used when an entity lacks an explicit type
    "Person": "PERSON", "Organization": "ORGANIZATION", "Location": "LOCATION",
    "Event": "EVENT", "Object": "OBJECT",
}


async def ingest_fixtures_nams(fixture_data: dict[str, Any], domain_id: str) -> None:
    """Ingest ``data/fixtures.json`` into NAMS using the hybrid write shape.

    * Entities → ``long_term.add_entity`` with attributes serialized into
      ``description`` and outbound relationships encoded as a fenced
      ``ccg-edges`` YAML block (migrates to native edges when NAMS gains
      ``add_relationship``).
    * Documents → dual-tracked: ``add_entity(name=title, type=OBJECT)`` so
      the document is a queryable long-term entity AND
      ``short_term.add_message`` (role="user", metadata kind="document",
      addressed to a server-created conversation) so the NAMS extractor
      sees the prose.
    * Decision traces use the reasoning REST API.
    """
    client = get_client()
    if client is None:
        print("  [warn] NAMS client not connected. Run from inside the FastAPI lifespan or set MEMORY_API_KEY.")
        return

    relationships = fixture_data.get("relationships", [])
    entities = fixture_data.get("entities", {})
    entity_count = 0
    fallback_name_index = 0
    edges_encoded = 0
    for label, items in entities.items():
        pole_type = _POLE_TYPE_HINTS.get(label, "OBJECT")
        for item in items:
            name = item.get("name")
            if not name:
                name = f"{label}-{fallback_name_index}"
                fallback_name_index += 1
            base = _serialize_entity_to_description(item, label, pole_type)
            description = _description_with_edges(base, relationships, name)
            if description is not base:
                edges_encoded += 1
            try:
                await client.long_term.add_entity(
                    name=name,
                    entity_type=pole_type,
                    description=description,
                )
                entity_count += 1
            except Exception as e:
                print(f"  [warn] Entity {name}: {e}")
    print(f"  [1/3] Ingested {entity_count} entities ({edges_encoded} with ccg-edges)")

    # Documents → dual-tracked. NAMS only accepts messages addressed to a
    # conversation id IT minted — create the channel once and target that id;
    # role must be user/assistant/system (custom roles are rejected).
    doc_channel = None
    try:
        conv = await client.short_term.create_conversation(session_id=f"docs-{domain_id}")
        doc_channel = str(getattr(conv, "id", "") or "") or None
    except Exception as e:
        print(f"  [warn] docs conversation unavailable ({e}) — storing entities only")
    doc_count = 0
    for doc in fixture_data.get("documents", []):
        title = doc.get("title", "")
        if not title:
            continue
        content = doc.get("content", "")
        base = (
            f"{content}\n\n_pole_type: OBJECT_"
            if content else f"Document: {title}\n\n_pole_type: OBJECT_"
        )
        description = _description_with_edges(base, relationships, title)
        try:
            await client.long_term.add_entity(
                name=title, entity_type="OBJECT", description=description,
            )
            if doc_channel is not None:
                await client.short_term.add_message(
                    session_id=doc_channel,
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
            doc_count += 1
        except Exception as e:
            print(f"  [warn] Document {title}: {e}")
    print(f"  [2/3] Ingested {doc_count} documents (dual-tracked: entity + message)")

    # 4. Decision traces via reasoning API
    trace_session = f"traces-{domain_id}"
    trace_count = 0
    for trace_data in fixture_data.get("traces", []):
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
            trace_count += 1
        except Exception as e:
            print(f"  [warn] Trace: {e}")
    print(f"  [3/3] Ingested {trace_count} decision traces")


# ---------------------------------------------------------------------------
# Documents — on NAMS, stored as long-term Document entities (queryable).
# The same content is mirrored into short_term as kind="document" messages so
# the NAMS extractor can mine the prose, but the entity is the source of
# truth for the document browser (matches the bolt graph shape).
# ---------------------------------------------------------------------------


_DOCUMENT_QUERY_HINT = "Document"
# Written into every document description by the seed/import pipelines; the
# service-independent signal that an entity is a document.
_DOCUMENT_MARKER = "_pole_type: OBJECT_"


def _document_record_from_fields(name: str, description: str) -> dict[str, Any] | None:
    """Build the doc-browser record from raw name/description fields."""
    content = description
    if CCG_EDGES_OPEN in content:
        content = content.split(CCG_EDGES_OPEN, 1)[0].rstrip()
    if "_pole_type:" in content:
        content = content.rsplit("_pole_type:", 1)[0].rstrip()
    if not content.strip():
        return None
    return {
        "title": name,
        "content": content,
        "preview": content[:200],
    }


def _document_record_from_entity(entity: Any) -> dict[str, Any] | None:
    """Convert a long_term entity record into the doc-browser shape, or None
    if the entity doesn't look like a Document (missing/empty description)."""
    name = getattr(entity, "name", None) or getattr(entity, "entity_name", None)
    if not name:
        return None
    description = getattr(entity, "description", "") or ""
    # Strip the ccg-edges YAML block and the trailing _pole_type: marker
    # before returning a clean preview.
    content = description
    if CCG_EDGES_OPEN in content:
        content = content.split(CCG_EDGES_OPEN, 1)[0].rstrip()
    if "_pole_type:" in content:
        content = content.rsplit("_pole_type:", 1)[0].rstrip()
    if not content.strip():
        return None
    return {
        "title": name,
        "content": content,
        "preview": content[:200],
    }


async def list_documents_nams(
    skip: int, limit: int
) -> list[dict[str, Any]]:
    client = get_client()
    if client is None:
        return []
    # Preferred: enumerate via the cypher API using the _pole_type marker —
    # the live NAMS service coerces unknown entity_type values (like OBJECT)
    # to "custom", so a server-side type filter finds nothing. The marker is
    # this scaffold's own write contract and survives that coercion.
    try:
        rows = await client.query.cypher(
            "MATCH (n) WHERE n.description CONTAINS $marker "
            "RETURN n.name AS name, n.description AS description "
            "ORDER BY n.name SKIP $skip LIMIT $limit",
            {"marker": _DOCUMENT_MARKER, "skip": skip, "limit": limit},
        )
        docs = []
        for row in rows or []:
            if not isinstance(row, dict) or not row.get("name"):
                continue
            rec = _document_record_from_fields(row["name"], row.get("description") or "")
            if rec is None:
                continue
            rec["template_id"] = ""
            rec["template_name"] = ""
            rec["mentioned_entities"] = []
            docs.append(rec)
        return docs
    except Exception as e:
        logger.info("list_documents_nams: cypher path failed (%s) — using search", e)

    # Fallback: search API. Try the server-side OBJECT filter first (honored
    # by older services), then unfiltered with client-side marker matching.
    entities = []
    for kwargs in ({"entity_type": "OBJECT"}, {}):
        try:
            entities = await client.long_term.search_entities(
                query=_DOCUMENT_QUERY_HINT, limit=skip + limit + 50, **kwargs,
            )
        except Exception as e:
            logger.info("list_documents_nams: search_entities failed: %s", e)
            entities = []
        if entities:
            break

    docs = []
    for ent in entities:
        ent_type = getattr(ent, "entity_type", None) or getattr(ent, "type", None)
        description = getattr(ent, "description", "") or ""
        # Accept anything carrying our document marker; keep the legacy
        # type-based acceptance for pre-marker data.
        is_marked = _DOCUMENT_MARKER in description
        is_legacy_typed = bool(ent_type) and ent_type.upper() in {"OBJECT", "DOCUMENT"}
        if not (is_marked or is_legacy_typed):
            continue
        rec = _document_record_from_entity(ent)
        if rec is None:
            continue
        rec["template_id"] = ""
        rec["template_name"] = ""
        rec["mentioned_entities"] = []
        docs.append(rec)

    docs.sort(key=lambda d: d.get("title", ""))
    return docs[skip : skip + limit]


async def get_document_nams(title: str) -> dict[str, Any] | None:
    client = get_client()
    if client is None:
        return None
    try:
        entities = await client.long_term.search_entities(query=title, limit=20)
    except Exception:
        return None

    for ent in entities:
        name = getattr(ent, "name", None) or getattr(ent, "entity_name", None)
        if name != title:
            continue
        rec = _document_record_from_entity(ent)
        if rec is None:
            return None
        return {
            "document": {
                "title": title,
                "content": rec["content"],
                "template_id": "",
                "template_name": "",
            },
            "mentioned_entities": [],
        }
    return None


# ---------------------------------------------------------------------------
# Decision traces — NAMS reasoning API
# ---------------------------------------------------------------------------


async def list_traces_nams() -> list[dict[str, Any]]:
    client = get_client()
    if client is None:
        return []
    try:
        traces = await client.reasoning.list_traces()
    except Exception as e:
        logger.info("list_traces_nams: list_traces failed: %s", e)
        return []

    results: list[dict[str, Any]] = []
    for trace in traces:
        trace_id = getattr(trace, "id", None) or getattr(trace, "trace_id", None)
        if trace_id is None:
            continue
        try:
            full = await client.reasoning.get_trace_with_steps(trace_id)
        except Exception:
            continue
        if full is None:
            continue
        steps_raw = getattr(full, "steps", []) or []
        steps = [
            {
                "step_number": idx + 1,
                "thought": getattr(s, "thought", "") or "",
                "action": getattr(s, "action", "") or "",
                "observation": getattr(s, "observation", "") or "",
            }
            for idx, s in enumerate(steps_raw)
        ]
        results.append(
            {
                "id": str(trace_id),
                "task": getattr(full, "task", "") or "",
                "outcome": getattr(full, "outcome", "") or "",
                "steps": steps,
            }
        )
    return results


# ---------------------------------------------------------------------------
# Entity expansion — NAMS get_entity inlines relationships
# ---------------------------------------------------------------------------


async def expand_node_nams(element_id: str) -> dict[str, Any]:
    client = get_client()
    if client is None:
        return {"nodes": [], "relationships": []}

    # Preferred: the cypher API. neo4j-agent-memory 0.5.x has no
    # ``long_term.get_entity(id)`` — id-addressed lookups only exist through
    # cypher, which also returns the server-side relationships (e.g. the
    # SAME_AS edges NAMS entity resolution creates).
    try:
        rows = await client.query.cypher(
            "MATCH (n) WHERE n.id = $id "
            "OPTIONAL MATCH (n)-[r]-(m) "
            "RETURN n.id AS id, n.name AS name, n.type AS type, "
            "n.description AS description, type(r) AS rel_type, "
            "m.id AS other_id, m.name AS other_name, m.type AS other_type, "
            "m.description AS other_description, "
            "CASE WHEN r IS NULL THEN NULL WHEN startNode(r).id = n.id THEN true ELSE false END AS outgoing",
            {"id": element_id},
        )
        if rows:
            nodes: dict[str, dict[str, Any]] = {}
            rels: list[dict[str, Any]] = []
            for row in rows:
                if not isinstance(row, dict) or not row.get("id"):
                    continue
                nodes.setdefault(str(row["id"]), {
                    "elementId": str(row["id"]),
                    "labels": [row.get("type") or "Entity"],
                    "name": row.get("name") or "",
                    "description": row.get("description") or "",
                })
                other_id = row.get("other_id")
                if not other_id or not row.get("rel_type"):
                    continue
                nodes.setdefault(str(other_id), {
                    "elementId": str(other_id),
                    "labels": [row.get("other_type") or "Entity"],
                    "name": row.get("other_name") or "",
                    "description": row.get("other_description") or "",
                })
                start, end = (
                    (str(row["id"]), str(other_id))
                    if row.get("outgoing") in (True, None)
                    else (str(other_id), str(row["id"]))
                )
                rels.append({
                    "elementId": f"{start}-{row['rel_type']}-{end}",
                    "type": row["rel_type"],
                    "startNodeElementId": start,
                    "endNodeElementId": end,
                })
            return {"nodes": list(nodes.values()), "relationships": rels}
    except Exception as e:
        logger.info("expand_node_nams: cypher path failed (%s) — using REST", e)

    # Fallback: REST get_entity with inlined relationships (older lib/service).
    try:
        entity = await client.long_term.get_entity(element_id)
    except Exception as e:
        logger.info("expand_node_nams: get_entity(%s) failed: %s", element_id, e)
        return {"nodes": [], "relationships": []}

    nodes = [_entity_to_node(entity)]
    rels: list[dict[str, Any]] = []
    inlined = getattr(entity, "relationships", None) or []
    for rel in inlined:
        target_id = getattr(rel, "target_id", None) or getattr(rel, "target", None)
        if target_id is None:
            continue
        rels.append(
            {
                "elementId": getattr(rel, "id", "") or f"{element_id}-{target_id}",
                "type": getattr(rel, "type", "RELATED_TO"),
                "startNodeElementId": element_id,
                "endNodeElementId": str(target_id),
            }
        )
        try:
            target = await client.long_term.get_entity(target_id)
            nodes.append(_entity_to_node(target))
        except Exception:
            continue
    return {"nodes": nodes, "relationships": rels}


def _entity_to_node(entity: Any) -> dict[str, Any]:
    entity_id = getattr(entity, "id", None) or getattr(entity, "entity_id", None) or ""
    return {
        "elementId": str(entity_id),
        "labels": [getattr(entity, "type", "Entity") or "Entity"],
        "name": getattr(entity, "name", "") or "",
        "description": getattr(entity, "description", "") or "",
    }


# ---------------------------------------------------------------------------
# Schema visualization fallback
# ---------------------------------------------------------------------------


async def schema_visualization_nams() -> dict[str, Any]:
    """Synthesize a schema view from NAMS list_entities (no relationships)."""
    client = get_client()
    if client is None:
        return {"nodes": [], "relationships": []}
    by_type: dict[str, int] = {}
    # Preferred: aggregate via the cypher API. The search API cannot list
    # everything — the live service rejects an empty query outright.
    try:
        rows = await client.query.cypher(
            "MATCH (n) WHERE n.type IS NOT NULL "
            "RETURN n.type AS type, count(n) AS count ORDER BY count DESC",
            {},
        )
        for row in rows or []:
            if isinstance(row, dict) and row.get("type"):
                by_type[str(row["type"])] = int(row.get("count", 0))
    except Exception as e:
        logger.info("schema_visualization_nams: cypher path failed (%s) — using search", e)
        try:
            entities = await client.long_term.search_entities(query="entity", limit=1000)
        except Exception as e2:
            logger.info("schema_visualization_nams: search_entities failed: %s", e2)
            return {"nodes": [], "relationships": []}
        for ent in entities:
            t = getattr(ent, "type", "Entity") or "Entity"
            by_type[t] = by_type.get(t, 0) + 1

    nodes = [
        {
            "elementId": f"schema-{label}",
            "labels": [label],
            "name": label,
            "count": count,
        }
        for label, count in by_type.items()
    ]
    return {"nodes": nodes, "relationships": []}


# ---------------------------------------------------------------------------
# Entity detail
# ---------------------------------------------------------------------------


async def get_entity_detail_nams(name: str) -> dict[str, Any] | None:
    client = get_client()
    if client is None:
        return None
    try:
        entity = await client.long_term.get_entity_by_name(name)
    except Exception:
        entity = None
    if entity is None:
        return None
    entity_id = getattr(entity, "id", None) or getattr(entity, "entity_id", None)
    connections: list[dict[str, Any]] = []
    # Preferred: cypher — id-addressed neighbor lookup doesn't exist on the
    # 0.5.x REST client, and this also surfaces server-created edges.
    if entity_id:
        try:
            rows = await client.query.cypher(
                "MATCH (n) WHERE n.id = $id MATCH (n)-[r]-(m) "
                "RETURN type(r) AS rel_type, m.name AS name, m.type AS type, "
                "CASE WHEN startNode(r).id = n.id THEN 'outgoing' ELSE 'incoming' END AS direction",
                {"id": str(entity_id)},
            )
            for row in rows or []:
                if not isinstance(row, dict) or not row.get("name"):
                    continue
                connections.append({
                    "name": row["name"],
                    "labels": [row.get("type") or "Entity"],
                    "relationship": row.get("rel_type") or "RELATED_TO",
                    "direction": row.get("direction") or "outgoing",
                })
        except Exception as e:
            logger.info("get_entity_detail_nams: cypher connections failed: %s", e)
    if not connections:
        # Fallback: inlined relationships from the REST response (older lib).
        inlined = getattr(entity, "relationships", None) or []
        for rel in inlined:
            target_id = getattr(rel, "target_id", None) or getattr(rel, "target", None)
            if target_id is None:
                continue
            try:
                target = await client.long_term.get_entity(target_id)
            except Exception:
                continue
            connections.append(
                {
                    "name": getattr(target, "name", "") or "",
                    "labels": [getattr(target, "type", "Entity") or "Entity"],
                    "relationship": getattr(rel, "type", "RELATED_TO"),
                    "direction": "outgoing",
                }
            )
    return {
        "entity": {
            "name": getattr(entity, "name", "") or "",
            "_labels": [getattr(entity, "type", "Entity") or "Entity"],
            "description": getattr(entity, "description", "") or "",
            "_id": str(entity_id) if entity_id else "",
        },
        "connections": connections,
    }


# ---------------------------------------------------------------------------
# Search
# ---------------------------------------------------------------------------


async def search_entities_nams(
    query: str, label: str | None, limit: int
) -> list[dict[str, Any]]:
    client = get_client()
    if client is None:
        return []
    try:
        entities = await client.long_term.search_entities(
            query=query, entity_type=label, limit=limit
        )
    except Exception as e:
        logger.info("search_entities_nams failed: %s", e)
        return []
    return [_entity_to_node(e) for e in entities]
