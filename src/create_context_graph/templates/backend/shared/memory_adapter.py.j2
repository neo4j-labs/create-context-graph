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
      ``short_term.add_message(role="document")`` so the NAMS extractor
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

    # Documents → dual-tracked
    doc_session = f"docs-{domain_id}"
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
            await client.short_term.add_message(
                session_id=doc_session,
                role="document",
                content=content,
                metadata={
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
# The same content is mirrored into short_term as role="document" messages so
# the NAMS extractor can mine the prose, but the entity is the source of
# truth for the document browser (matches the bolt graph shape).
# ---------------------------------------------------------------------------


_DOCUMENT_QUERY_HINT = "Document"


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
    try:
        # Push the OBJECT filter to the server so the (skip + limit + 50)
        # buffer isn't eaten by unrelated PERSON/ORGANIZATION/LOCATION/EVENT
        # entities — that used to cause documents to be silently dropped on
        # busy NAMS instances.
        entities = await client.long_term.search_entities(
            query=_DOCUMENT_QUERY_HINT, entity_type="OBJECT", limit=skip + limit + 50,
        )
    except Exception as e:
        logger.info("list_documents_nams: search_entities failed: %s", e)
        return []

    docs: list[dict[str, Any]] = []
    for ent in entities:
        ent_type = getattr(ent, "entity_type", None) or getattr(ent, "type", None)
        # NAMS doesn't have a Document label; we stored docs as type=OBJECT
        # with the doc title as the entity name. Filter by description shape
        # — anything without prose is not a document.
        rec = _document_record_from_entity(ent)
        if rec is None:
            continue
        # Belt-and-suspenders client-side filter — server already restricted
        # to OBJECT, but legacy data may use the older DOCUMENT label.
        if ent_type and ent_type.upper() not in {"OBJECT", "DOCUMENT"}:
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
    try:
        entities = await client.long_term.search_entities(query="", limit=1000)
    except Exception as e:
        logger.info("schema_visualization_nams: search_entities failed: %s", e)
        return {"nodes": [], "relationships": []}

    by_type: dict[str, int] = {}
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
    inlined = getattr(entity, "relationships", None) or []
    connections: list[dict[str, Any]] = []
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
