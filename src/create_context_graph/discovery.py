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

"""Neo4j schema discovery and ontology construction helpers."""

from __future__ import annotations

import re
from typing import Any

from neo4j import GraphDatabase
from neo4j.exceptions import AuthError, ServiceUnavailable

from create_context_graph.ontology import DomainOntology


_NEO4J_TYPE_MAP = {
    "String": "string",
    "Long": "integer",
    "Integer": "integer",
    "Short": "integer",
    "Byte": "integer",
    "Double": "float",
    "Float": "float",
    "Boolean": "boolean",
    "Date": "date",
    "DateTime": "datetime",
    "LocalDateTime": "datetime",
    "Time": "datetime",
    "LocalTime": "datetime",
    "Duration": "string",
    "Point": "point",
}

_PERSON_KEYWORDS = {
    "person",
    "people",
    "user",
    "member",
    "employee",
    "customer",
    "client",
    "patient",
    "provider",
    "doctor",
    "nurse",
    "player",
    "coach",
    "author",
    "owner",
    "manager",
    "contact",
}
_ORG_KEYWORDS = {
    "organization",
    "organisation",
    "org",
    "company",
    "business",
    "vendor",
    "supplier",
    "team",
    "league",
    "club",
    "department",
    "group",
    "agency",
    "institution",
    "facility",
}
_LOCATION_KEYWORDS = {
    "location",
    "place",
    "venue",
    "stadium",
    "arena",
    "site",
    "office",
    "city",
    "country",
    "region",
    "address",
    "building",
}
_EVENT_KEYWORDS = {
    "event",
    "meeting",
    "session",
    "appointment",
    "encounter",
    "match",
    "game",
    "tournament",
    "visit",
    "incident",
    "transaction",
    "order",
    "treatment",
}

_COLOR_PALETTE = [
    "#2563eb",
    "#dc2626",
    "#16a34a",
    "#9333ea",
    "#ea580c",
    "#0891b2",
    "#be123c",
    "#4f46e5",
    "#65a30d",
    "#c026d3",
    "#0d9488",
    "#ca8a04",
    "#7c3aed",
    "#0284c7",
    "#db2777",
    "#059669",
    "#b45309",
    "#475569",
    "#e11d48",
    "#0f766e",
]


def discover_ontology_from_database(
    neo4j_uri: str,
    neo4j_username: str,
    neo4j_password: str,
) -> dict:
    """Inspect an existing Neo4j database and return normalized schema metadata."""
    try:
        driver = GraphDatabase.driver(
            neo4j_uri,
            auth=(neo4j_username, neo4j_password),
        )
        try:
            if hasattr(driver, "verify_connectivity"):
                driver.verify_connectivity()
            with driver.session() as session:
                labels = _discover_labels(session)
                relationship_types = _discover_relationship_types(session)

                properties = _discover_node_properties(session, labels)
                rel_properties = _run_optional(
                    lambda: _discover_relationship_properties(session),
                    {},
                )
                schema_graph = _run_optional(
                    lambda: _discover_schema_graph(session),
                    [],
                )
                constraints = _run_optional(
                    lambda: _run_query(session, "SHOW CONSTRAINTS"),
                    [],
                )
                indexes = _run_optional(
                    lambda: _run_query(session, "SHOW INDEXES"),
                    [],
                )
                sample_counts = _run_optional(
                    lambda: _discover_sample_counts(session, labels),
                    {},
                )
        finally:
            driver.close()
    except AuthError as exc:
        msg = "Authentication failed while connecting to Neo4j"
        raise ConnectionError(msg) from exc
    except ServiceUnavailable as exc:
        raise ConnectionError("Cannot connect to Neo4j database") from exc

    return {
        "labels": labels,
        "relationship_types": relationship_types,
        "properties": properties,
        "rel_properties": rel_properties,
        "constraints": constraints,
        "indexes": indexes,
        "schema_graph": schema_graph,
        "sample_counts": sample_counts,
    }


def build_ontology_from_discovery(
    discovered: dict,
    domain_id: str,
    domain_name: str | None = None,
    domain_description: str | None = None,
    system_prompt: str | None = None,
) -> DomainOntology:
    """Build a validated DomainOntology from discovered Neo4j schema metadata."""
    labels = list(discovered.get("labels") or [])
    relationships = _build_relationships(discovered.get("schema_graph") or [])
    node_colors = {
        label: _COLOR_PALETTE[index % len(_COLOR_PALETTE)]
        for index, label in enumerate(labels)
    }

    entity_types = []
    for label in labels:
        entity_types.append({
            "label": label,
            "pole_type": _classify_pole_type(label),
            "subtype": _to_subtype(label),
            "color": node_colors[label],
            "icon": _icon_for_pole_type(_classify_pole_type(label)),
            "properties": _build_properties(
                label,
                discovered.get("properties", {}).get(label, []),
                discovered.get("constraints", []),
            ),
        })

    prompt = system_prompt or _generate_system_prompt(discovered, labels, relationships)

    data = {
        "domain": {
            "id": domain_id,
            "name": domain_name or _title_from_id(domain_id),
            "description": domain_description
            or "Ontology discovered from an existing Neo4j database",
            "tagline": "AI-powered graph intelligence",
            "emoji": "",
        },
        "entity_types": entity_types,
        "relationships": relationships,
        "demo_scenarios": _build_demo_scenarios(
            labels,
            discovered.get("relationship_types") or [],
        ),
        "agent_tools": [],
        "visualization": {
            "node_colors": node_colors,
            "node_sizes": {label: 20 for label in labels},
            "default_cypher": _default_visualization_cypher(labels, relationships),
        },
        "system_prompt": prompt,
    }
    return DomainOntology.model_validate(data)


def refine_system_prompt(
    user_input: str,
    discovered_schema: dict,
    api_key: str,
    feedback: str | None = None,
) -> str:
    """Refine a rough user description into a system prompt using Anthropic."""
    import anthropic

    schema_summary = _schema_summary_for_prompt(discovered_schema)
    refinement = f"\n\nRefinement instruction:\n{feedback}" if feedback else ""
    prompt = f"""Refine the user's rough assistant description into a concise
system prompt.

The assistant will operate over this discovered Neo4j schema:

{schema_summary}

User description:
{user_input}
{refinement}

Return only the final system prompt text. It should mention the discovered graph
domain, describe how to use schema-grounded answers, and reference available
tools such as run_cypher, get_schema, and create_chart where useful.
"""
    client = anthropic.Anthropic(api_key=api_key)
    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=1200,
        messages=[{"role": "user", "content": prompt}],
    )
    return response.content[0].text.strip()


def _discover_labels(session: Any) -> list[str]:
    rows = _run_query(
        session,
        "CALL db.labels() YIELD label RETURN label ORDER BY label",
    )
    return sorted(str(row["label"]) for row in rows if row.get("label"))


def _discover_relationship_types(session: Any) -> list[str]:
    rows = _run_query(
        session,
        "CALL db.relationshipTypes() "
        "YIELD relationshipType RETURN relationshipType ORDER BY relationshipType",
    )
    return sorted(
        str(row["relationshipType"])
        for row in rows
        if row.get("relationshipType")
    )


def _discover_node_properties(session: Any, labels: list[str]) -> dict[str, list[dict]]:
    try:
        rows = _run_query(session, "CALL db.schema.nodeTypeProperties()")
        return _group_node_properties(rows)
    except (AuthError, ServiceUnavailable):
        raise
    except Exception:
        return _sample_node_properties(session, labels)


def _discover_relationship_properties(session: Any) -> dict[str, list[dict]]:
    rows = _run_query(session, "CALL db.schema.relTypeProperties()")
    grouped: dict[str, list[dict]] = {}
    for row in rows:
        rel_type = _clean_schema_name(row.get("relType") or row.get("relationshipType"))
        property_name = row.get("propertyName")
        if not rel_type or not property_name:
            continue
        grouped.setdefault(rel_type, []).append({
            "name": property_name,
            "types": row.get("propertyTypes") or row.get("propertyType") or [],
            "mandatory": bool(row.get("mandatory", False)),
        })
    return grouped


def _discover_schema_graph(session: Any) -> list[dict]:
    rows = _run_query(session, "CALL db.schema.visualization()")
    schema_graph: list[dict] = []
    seen: set[tuple[str, str, str]] = set()
    for row in rows:
        for relationship in row.get("relationships") or []:
            rel_type = _relationship_type(relationship)
            start_label = _node_label(_relationship_endpoint(relationship, "start"))
            end_label = _node_label(_relationship_endpoint(relationship, "end"))
            if not rel_type or not start_label or not end_label:
                continue
            key = (start_label, rel_type, end_label)
            if key in seen:
                continue
            seen.add(key)
            schema_graph.append({
                "start_label": start_label,
                "rel_type": rel_type,
                "end_label": end_label,
            })
    return schema_graph


def _discover_sample_counts(session: Any, labels: list[str]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for label in labels:
        rows = _run_query(
            session,
            f"MATCH (n:`{_escape_label(label)}`) RETURN count(n) AS count",
        )
        count = rows[0].get("count", 0) if rows else 0
        counts[label] = int(count)
    return counts


def _group_node_properties(rows: list[dict]) -> dict[str, list[dict]]:
    grouped: dict[str, list[dict]] = {}
    for row in rows:
        property_name = row.get("propertyName")
        if not property_name:
            continue
        labels = row.get("nodeLabels") or [_clean_schema_name(row.get("nodeType"))]
        for label in labels:
            if not label:
                continue
            grouped.setdefault(str(label), []).append({
                "name": property_name,
                "types": row.get("propertyTypes") or row.get("propertyType") or [],
                "mandatory": bool(row.get("mandatory", False)),
            })
    return grouped


def _sample_node_properties(session: Any, labels: list[str]) -> dict[str, list[dict]]:
    sampled: dict[str, list[dict]] = {}
    for label in labels:
        try:
            rows = _run_query(
                session,
                f"MATCH (n:`{_escape_label(label)}`) "
                "RETURN properties(n) AS properties LIMIT 5",
            )
        except (AuthError, ServiceUnavailable):
            raise
        except Exception:
            sampled[label] = []
            continue

        discovered: dict[str, str] = {}
        for row in rows:
            for key, value in (row.get("properties") or {}).items():
                discovered.setdefault(key, _infer_neo4j_type(value))
        sampled[label] = [
            {"name": name, "types": [type_name], "mandatory": False}
            for name, type_name in sorted(discovered.items())
        ]
    return sampled


def _run_optional(callback: Any, default: Any) -> Any:
    try:
        return callback()
    except (AuthError, ServiceUnavailable):
        raise
    except Exception:
        return default


def _run_query(session: Any, query: str) -> list[dict]:
    return [_record_to_dict(record) for record in session.run(query)]


def _record_to_dict(record: Any) -> dict:
    if isinstance(record, dict):
        return dict(record)
    if hasattr(record, "data"):
        return record.data()
    if hasattr(record, "keys"):
        return {key: record[key] for key in record.keys()}
    return {}


def _build_properties(
    label: str,
    raw_properties: list[dict],
    constraints: list[dict],
) -> list[dict]:
    properties = []
    seen: set[str] = set()
    for raw in raw_properties:
        name = raw.get("name") or raw.get("propertyName")
        if not name or name in seen:
            continue
        seen.add(name)
        properties.append({
            "name": name,
            "type": _map_neo4j_type(raw.get("types") or raw.get("propertyTypes")),
            "required": bool(raw.get("mandatory", False)),
            "unique": _is_unique_property(label, name, constraints),
            "description": "",
        })
    return properties


def _build_relationships(schema_graph: list[dict]) -> list[dict]:
    relationships = []
    seen: set[tuple[str, str, str]] = set()
    for entry in schema_graph:
        source = entry.get("start_label")
        rel_type = entry.get("rel_type")
        target = entry.get("end_label")
        if not source or not rel_type or not target:
            continue
        key = (source, rel_type, target)
        if key in seen:
            continue
        seen.add(key)
        relationships.append({
            "type": rel_type,
            "source": source,
            "target": target,
            "properties": [],
        })
    return relationships


def _map_neo4j_type(neo4j_types: Any) -> str:
    if not neo4j_types:
        return "string"
    if isinstance(neo4j_types, str):
        candidates = [neo4j_types]
    else:
        candidates = list(neo4j_types)
    for candidate in candidates:
        if not candidate:
            continue
        normalized = str(candidate).replace("?", "").strip()
        normalized = re.sub(r"^LIST OF ", "", normalized, flags=re.IGNORECASE)
        for neo4j_type, ontology_type in _NEO4J_TYPE_MAP.items():
            if normalized.lower() == neo4j_type.lower():
                return ontology_type
    return "string"


def _is_unique_property(
    label: str,
    property_name: str,
    constraints: list[dict],
) -> bool:
    for constraint in constraints:
        entity_type = str(constraint.get("entityType") or "").upper()
        labels_or_types = constraint.get("labelsOrTypes") or []
        properties = constraint.get("properties") or []
        if (
            entity_type == "NODE"
            and label in labels_or_types
            and property_name in properties
        ):
            return True
    return property_name == f"{_to_snake_case(label)}_id"


def _classify_pole_type(label: str) -> str:
    words = _label_words(label)
    if words & _PERSON_KEYWORDS:
        return "PERSON"
    if words & _ORG_KEYWORDS:
        return "ORGANIZATION"
    if words & _LOCATION_KEYWORDS:
        return "LOCATION"
    if words & _EVENT_KEYWORDS:
        return "EVENT"
    return "OBJECT"


def _label_words(label: str) -> set[str]:
    spaced = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", label)
    return {
        word.lower()
        for word in re.split(r"[^A-Za-z0-9]+", spaced)
        if word
    }


def _icon_for_pole_type(pole_type: str) -> str:
    return {
        "PERSON": "user",
        "ORGANIZATION": "building",
        "LOCATION": "map-pin",
        "EVENT": "calendar",
        "OBJECT": "circle",
    }.get(pole_type, "circle")


def _generate_system_prompt(
    discovered: dict,
    labels: list[str],
    relationships: list[dict],
) -> str:
    label_text = ", ".join(labels) if labels else "no node labels"
    rel_types = sorted(
        {rel["type"] for rel in relationships}
        | set(discovered.get("relationship_types") or [])
    )
    rel_text = ", ".join(rel_types) if rel_types else "no relationship types"
    return f"""You are an AI graph assistant for a Neo4j database discovered at
scaffold time.

The discovered node labels are: {label_text}.
The discovered relationship types are: {rel_text}.

Use the available tools to answer questions from the graph:
- run_cypher for safe read-only Cypher queries
- get_schema to inspect labels, relationships, and properties
- create_chart to turn query results into visualizations

Ground every answer in the discovered schema and explain when the database does
not contain enough information to answer confidently.
"""


def _build_demo_scenarios(
    labels: list[str],
    relationship_types: list[str],
) -> list[dict]:
    if not labels:
        return []
    primary = labels[0]
    prompts = [
        f"Show me a few {primary} records and summarize the key properties.",
        f"What relationships connect {primary} to other labels in this graph?",
    ]
    if len(labels) > 1:
        prompts.append(
            f"Compare {primary} with {labels[1]} using available relationships."
        )
    if relationship_types:
        prompts.append(
            f"Find examples that use the {relationship_types[0]} relationship."
        )
    return [{"name": "Explore discovered graph", "prompts": prompts}]


def _schema_summary_for_prompt(discovered_schema: dict) -> str:
    labels = discovered_schema.get("labels") or []
    relationship_types = discovered_schema.get("relationship_types") or []
    properties = discovered_schema.get("properties") or {}
    counts = discovered_schema.get("sample_counts") or {}

    lines = [
        f"Labels: {', '.join(labels) if labels else '(none)'}",
        "Relationship types: "
        f"{', '.join(relationship_types) if relationship_types else '(none)'}",
        "Properties and counts:",
    ]
    for label in labels:
        prop_names = [
            prop.get("name") or prop.get("propertyName")
            for prop in properties.get(label, [])
            if prop.get("name") or prop.get("propertyName")
        ]
        lines.append(
            f"- {label} ({counts.get(label, 0)} nodes): "
            f"{', '.join(prop_names) if prop_names else '(no properties discovered)'}"
        )
    return "\n".join(lines)


def _clean_schema_name(value: Any) -> str:
    if not value:
        return ""
    text = str(value)
    return text.replace(":", "").replace("`", "").strip()


def _relationship_type(relationship: Any) -> str:
    if isinstance(relationship, dict):
        return str(relationship.get("rel_type") or relationship.get("type") or "")
    rel_type = (
        getattr(relationship, "type", None)
        or getattr(relationship, "type_", None)
    )
    return str(rel_type or "")


def _relationship_endpoint(relationship: Any, endpoint: str) -> Any:
    if isinstance(relationship, dict):
        keys = ["start_label", "start", "start_node"] if endpoint == "start" else [
            "end_label",
            "end",
            "end_node",
        ]
        for key in keys:
            if key in relationship:
                return relationship[key]
        return None
    if endpoint == "start":
        return getattr(relationship, "start_node", None)
    return getattr(relationship, "end_node", None)


def _node_label(node: Any) -> str:
    if isinstance(node, str):
        return node
    if isinstance(node, dict):
        if node.get("label"):
            return str(node["label"])
        if node.get("name"):
            return str(node["name"])
        labels = node.get("labels")
        if labels:
            return str(next(iter(labels)))
    labels = getattr(node, "labels", None)
    if labels:
        return str(next(iter(labels)))
    if hasattr(node, "get"):
        name = node.get("name")
        if name:
            return str(name)
    return ""


def _infer_neo4j_type(value: Any) -> str:
    if isinstance(value, bool):
        return "Boolean"
    if isinstance(value, int):
        return "Long"
    if isinstance(value, float):
        return "Double"
    return "String"


def _escape_label(label: str) -> str:
    return label.replace("`", "``")


def _title_from_id(domain_id: str) -> str:
    return domain_id.replace("_", "-").replace("-", " ").title()


def _to_subtype(label: str) -> str:
    return _to_snake_case(label).upper()


def _to_snake_case(value: str) -> str:
    value = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", value)
    value = re.sub(r"[^A-Za-z0-9]+", "_", value)
    return value.strip("_").lower()


def _default_visualization_cypher(labels: list[str], relationships: list[dict]) -> str:
    if relationships:
        return "MATCH (n)-[r]->(m) RETURN n, r, m LIMIT 100"
    if labels:
        return f"MATCH (n:`{_escape_label(labels[0])}`) RETURN n LIMIT 100"
    return "MATCH (n) RETURN n LIMIT 100"
