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

"""Domain ontology loading, validation, and code generation."""

from __future__ import annotations

from importlib.resources import files
from pathlib import Path

import yaml
from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Pydantic models for the ontology YAML schema
# ---------------------------------------------------------------------------


class PropertyDef(BaseModel):
    """A property on a node or relationship."""

    name: str
    type: str = "string"
    required: bool = False
    unique: bool = False
    enum: list[str] | None = None
    default: str | int | float | bool | None = None
    description: str = ""


class EntityTypeDef(BaseModel):
    """A domain entity type (maps to a Neo4j node label)."""

    label: str
    pole_type: str = Field(description="POLE+O category: PERSON, ORGANIZATION, LOCATION, EVENT, OBJECT")
    subtype: str | None = None
    color: str = "#6366f1"
    icon: str = "circle"
    properties: list[PropertyDef] = Field(default_factory=list)


class RelationshipDef(BaseModel):
    """A relationship type between entity types."""

    type: str
    source: str
    target: str
    properties: list[PropertyDef] = Field(default_factory=list)


class DocumentTemplateDef(BaseModel):
    """A template for generating synthetic documents."""

    id: str
    name: str
    description: str = ""
    count: int = 5
    prompt_template: str = ""
    required_entities: list[str] = Field(default_factory=list)


class DecisionTraceStep(BaseModel):
    """A step in a decision trace scenario."""

    thought: str
    action: str
    observation: str | None = None


class DecisionTraceDef(BaseModel):
    """A decision trace scenario for generating reasoning memory."""

    id: str
    task: str
    steps: list[DecisionTraceStep] = Field(default_factory=list)
    outcome_template: str = ""


class DemoScenario(BaseModel):
    """A pre-built demo chat scenario."""

    name: str
    prompts: list[str] = Field(default_factory=list)


class AgentToolDef(BaseModel):
    """A domain-specific agent tool with Cypher query."""

    name: str
    description: str
    cypher: str = ""
    parameters: list[PropertyDef] = Field(default_factory=list)


class VisualizationConfig(BaseModel):
    """NVL visualization configuration."""

    node_colors: dict[str, str] = Field(default_factory=dict)
    node_sizes: dict[str, int] = Field(default_factory=dict)
    default_cypher: str = "MATCH (n)-[r]->(m) RETURN n, r, m LIMIT 100"


class DomainInfo(BaseModel):
    """Domain metadata."""

    id: str
    name: str
    description: str = ""
    tagline: str = ""
    emoji: str = ""


class DomainOntology(BaseModel):
    """Complete domain ontology definition."""

    domain: DomainInfo
    entity_types: list[EntityTypeDef] = Field(default_factory=list)
    relationships: list[RelationshipDef] = Field(default_factory=list)
    document_templates: list[DocumentTemplateDef] = Field(default_factory=list)
    decision_traces: list[DecisionTraceDef] = Field(default_factory=list)
    demo_scenarios: list[DemoScenario] = Field(default_factory=list)
    agent_tools: list[AgentToolDef] = Field(default_factory=list)
    visualization: VisualizationConfig = Field(default_factory=VisualizationConfig)
    system_prompt: str = ""


# ---------------------------------------------------------------------------
# Loading helpers
# ---------------------------------------------------------------------------

def _get_domains_path() -> Path:
    """Return the path to the bundled domains directory."""
    return Path(str(files("create_context_graph") / "domains"))


def _get_custom_domains_path() -> Path:
    """Return the path to the user-local custom domains directory."""
    return Path.home() / ".create-context-graph" / "custom-domains"


def list_available_domains() -> list[dict[str, str]]:
    """Return list of available domain IDs and display names.

    Scans both bundled domains and user-local custom domains in
    ~/.create-context-graph/custom-domains/.

    Returns a list of dicts with 'id' and 'name' keys, sorted by name.
    """
    results = []
    seen_ids: set[str] = set()

    for domains_dir in [_get_domains_path(), _get_custom_domains_path()]:
        if not domains_dir.exists():
            continue
        for path in sorted(domains_dir.glob("*.yaml")):
            if path.stem.startswith("_"):
                continue
            try:
                with open(path) as f:
                    data = yaml.safe_load(f)
                domain_info = data.get("domain", {})
                domain_id = domain_info.get("id", path.stem)
                if domain_id in seen_ids:
                    continue
                seen_ids.add(domain_id)
                results.append({
                    "id": domain_id,
                    "name": domain_info.get("name", path.stem.replace("-", " ").title()),
                })
            except Exception:
                if path.stem not in seen_ids:
                    seen_ids.add(path.stem)
                    results.append({"id": path.stem, "name": path.stem.replace("-", " ").title()})
    return sorted(results, key=lambda d: d["name"])


def _load_base() -> dict:
    """Load the base POLE+O ontology definitions."""
    base_path = _get_domains_path() / "_base.yaml"
    if not base_path.exists():
        return {}
    with open(base_path) as f:
        return yaml.safe_load(f) or {}


def _merge_base(base: dict, domain_data: dict) -> dict:
    """Merge base entity types into domain data.

    Base entity types are prepended to the domain's entity_types list
    unless the domain already defines an entity with the same label.
    Base relationships are similarly merged.
    """
    domain_labels = {et.get("label") for et in domain_data.get("entity_types", [])}
    base_entities = base.get("base_entity_types", {})

    merged_entities = []
    for label, defn in base_entities.items():
        if label not in domain_labels:
            merged_entities.append({
                "label": label,
                "pole_type": defn.get("pole_type", "OBJECT"),
                "color": defn.get("color", "#6366f1"),
                "icon": defn.get("icon", "circle"),
                "properties": defn.get("base_properties", []),
            })
    merged_entities.extend(domain_data.get("entity_types", []))
    domain_data["entity_types"] = merged_entities

    # Merge base relationships
    domain_rel_types = {r.get("type") for r in domain_data.get("relationships", [])}
    base_rels = base.get("base_relationships", {})
    merged_rels = []
    for rel_type, defn in base_rels.items():
        if rel_type not in domain_rel_types:
            merged_rels.append({
                "type": rel_type,
                "source": defn.get("source", "*"),
                "target": defn.get("target", "*"),
                "properties": defn.get("properties", []),
            })
    merged_rels.extend(domain_data.get("relationships", []))
    domain_data["relationships"] = merged_rels

    return domain_data


def load_domain(domain_id: str) -> DomainOntology:
    """Load a domain ontology by ID, merging with base definitions."""
    domains_dir = _get_domains_path()
    domain_path = domains_dir / f"{domain_id}.yaml"

    if not domain_path.exists():
        raise FileNotFoundError(f"Domain ontology not found: {domain_id}")

    with open(domain_path) as f:
        data = yaml.safe_load(f)

    # Merge base if domain declares inheritance
    if data.get("inherits") == "_base" or data.get("domain", {}).get("inherits") == "_base":
        base = _load_base()
        data = _merge_base(base, data)

    # Remove the inherits key before parsing
    data.pop("inherits", None)
    if "domain" in data and isinstance(data["domain"], dict):
        data["domain"].pop("inherits", None)

    return DomainOntology.model_validate(data)


def load_domain_from_yaml_string(yaml_content: str) -> DomainOntology:
    """Load a domain ontology from a raw YAML string, merging with base definitions.

    Useful for validating LLM-generated domain ontologies without writing to disk.
    """
    data = yaml.safe_load(yaml_content)
    if not data or not isinstance(data, dict):
        raise ValueError("Invalid YAML: expected a mapping")

    # Merge base if domain declares inheritance
    if data.get("inherits") == "_base" or data.get("domain", {}).get("inherits") == "_base":
        base = _load_base()
        data = _merge_base(base, data)

    # Remove the inherits key before parsing
    data.pop("inherits", None)
    if "domain" in data and isinstance(data["domain"], dict):
        data["domain"].pop("inherits", None)

    return DomainOntology.model_validate(data)


def load_domain_from_path(path: Path) -> DomainOntology:
    """Load a domain ontology from an arbitrary filesystem path."""
    if not path.exists():
        raise FileNotFoundError(f"Domain ontology not found: {path}")

    with open(path) as f:
        data = yaml.safe_load(f)

    if data.get("inherits") == "_base" or data.get("domain", {}).get("inherits") == "_base":
        base = _load_base()
        data = _merge_base(base, data)

    data.pop("inherits", None)
    if "domain" in data and isinstance(data["domain"], dict):
        data["domain"].pop("inherits", None)

    return DomainOntology.model_validate(data)


# ---------------------------------------------------------------------------
# Code generation helpers
# ---------------------------------------------------------------------------

_PYTHON_TYPE_MAP = {
    "string": "str",
    "str": "str",
    "integer": "int",
    "int": "int",
    "float": "float",
    "boolean": "bool",
    "bool": "bool",
    "date": "date",
    "datetime": "datetime",
    "point": "str",
}

_NEO4J_TYPE_MAP = {
    "string": "STRING",
    "str": "STRING",
    "integer": "INTEGER",
    "int": "INTEGER",
    "float": "FLOAT",
    "boolean": "BOOLEAN",
    "bool": "BOOLEAN",
    "date": "DATE",
    "datetime": "DATETIME",
    "point": "POINT",
}


def generate_cypher_schema(ontology: DomainOntology) -> str:
    """Generate Cypher constraints and indexes from the ontology."""
    lines = [
        "// Auto-generated schema for domain: " + ontology.domain.name,
        "// Generated by create-context-graph",
        "",
    ]

    for et in ontology.entity_types:
        for prop in et.properties:
            if prop.unique:
                constraint_name = f"{et.label.lower()}_{prop.name}_unique"
                lines.append(
                    f"CREATE CONSTRAINT {constraint_name} IF NOT EXISTS "
                    f"FOR (n:{et.label}) REQUIRE n.{prop.name} IS UNIQUE;"
                )

        # Create index on label for common lookups
        lines.append(
            f"CREATE INDEX {et.label.lower()}_name IF NOT EXISTS "
            f"FOR (n:{et.label}) ON (n.name);"
        )
        lines.append("")

    # Infrastructure indexes for Documents and Decision Traces
    lines.append("// Infrastructure: Document and Decision Trace indexes")
    lines.append("CREATE INDEX document_title IF NOT EXISTS FOR (n:Document) ON (n.title);")
    lines.append("CREATE INDEX document_template_id IF NOT EXISTS FOR (n:Document) ON (n.template_id);")
    lines.append("CREATE CONSTRAINT decision_trace_id_unique IF NOT EXISTS FOR (n:DecisionTrace) REQUIRE n.id IS UNIQUE;")
    lines.append("")

    # Local-file connector: constraints and indexes for Document + Section nodes
    lines.append("// Local-file connector: Document + Section node constraints and indexes")
    lines.append("CREATE CONSTRAINT document_name_unique IF NOT EXISTS FOR (n:Document) REQUIRE n.name IS UNIQUE;")
    lines.append("CREATE CONSTRAINT section_name_unique IF NOT EXISTS FOR (n:Section) REQUIRE n.name IS UNIQUE;")
    lines.append("")
    lines.append("// Range indexes for pre-filtering on both node types")
    lines.append("CREATE INDEX document_domain IF NOT EXISTS FOR (n:Document) ON (n.domain);")
    lines.append("CREATE INDEX document_source_type IF NOT EXISTS FOR (n:Document) ON (n.sourceType);")
    lines.append("CREATE INDEX document_file_extension IF NOT EXISTS FOR (n:Document) ON (n.fileExtension);")
    lines.append("CREATE INDEX document_language IF NOT EXISTS FOR (n:Document) ON (n.language);")
    lines.append("CREATE INDEX document_loaded_at IF NOT EXISTS FOR (n:Document) ON (n.loadedAt);")
    lines.append("CREATE INDEX document_created_at IF NOT EXISTS FOR (n:Document) ON (n.createdAt);")
    lines.append("CREATE INDEX document_modified_at IF NOT EXISTS FOR (n:Document) ON (n.modifiedAt);")
    lines.append("CREATE INDEX document_file_size IF NOT EXISTS FOR (n:Document) ON (n.fileSize);")
    lines.append("CREATE INDEX document_page_count IF NOT EXISTS FOR (n:Document) ON (n.pageCount);")
    lines.append("CREATE INDEX section_domain IF NOT EXISTS FOR (n:Section) ON (n.domain);")
    lines.append("CREATE INDEX section_file_extension IF NOT EXISTS FOR (n:Section) ON (n.fileExtension);")
    lines.append("CREATE INDEX section_heading_level IF NOT EXISTS FOR (n:Section) ON (n.headingLevel);")
    lines.append("CREATE INDEX section_loaded_at IF NOT EXISTS FOR (n:Section) ON (n.loadedAt);")
    lines.append("")
    lines.append("// Full-text index for keyword search over Document + Section titles and bodies")
    lines.append("CREATE FULLTEXT INDEX local_file_fulltext IF NOT EXISTS FOR (n:Document|Section) ON EACH [n.title, n.description];")
    lines.append("")
    lines.append("// Vector index for semantic search with pre-filtering (Neo4j 2026.01+)")
    lines.append("// Create after embeddings are generated; dimensions must match your embed model.")
    lines.append("// CREATE VECTOR INDEX local_file_embedding IF NOT EXISTS")
    lines.append("// FOR (n:Document|Section) ON n.embedding")
    lines.append("// WITH [n.domain, n.fileExtension, n.loadedAt, n.createdAt, n.modifiedAt,")
    lines.append("//       n.fileSize, n.language, n.headingLevel, n.pageCount, n.author]")
    lines.append("// OPTIONS { indexConfig: {")
    lines.append("//   `vector.dimensions`: 1536, `vector.similarity_function`: 'cosine',")
    lines.append("//   `vector.quantization.enabled`: true } };")
    lines.append("")

    return "\n".join(lines)


def _sanitize_enum_name(val: str) -> str:
    """Convert an enum value string into a valid Python identifier.

    Handles special characters (A+, A-, O+), leading digits (3d_model),
    and other non-alphanumeric characters while preserving readability.
    """
    import re

    name = val
    # Replace + and - that are NOT word separators (e.g., A+, A-, O+)
    # A trailing +/- or +/- not between two word chars is a sign, not a separator
    name = re.sub(r"\+", "_PLUS", name)
    # Hyphens between word chars are separators (kebab-case); otherwise they mean "minus"
    name = re.sub(r"(?<=\w)-(?=\w)", "_", name)
    name = name.replace("-", "_MINUS")
    name = name.upper().replace(" ", "_")
    # Remove any remaining invalid characters
    name = re.sub(r"[^A-Z0-9_]", "", name)
    # Collapse multiple underscores
    name = re.sub(r"_+", "_", name).strip("_")
    # Prepend underscore if it starts with a digit
    if name and name[0].isdigit():
        name = f"_{name}"
    # Fallback for empty result
    if not name:
        name = "UNKNOWN"
    return name


def generate_pydantic_models(ontology: DomainOntology) -> str:
    """Generate Python Pydantic model source code from the ontology."""
    imports = [
        "from __future__ import annotations",
        "",
        "from datetime import date, datetime",
        "from enum import Enum",
        "from typing import Literal",
        "",
        "from pydantic import BaseModel, Field",
        "",
        "",
    ]

    models = []
    for et in ontology.entity_types:
        # Generate enum classes for enum properties
        enum_classes = []
        for prop in et.properties:
            if prop.enum:
                enum_name = f"{et.label}{prop.name.title().replace('_', '')}Enum"
                enum_lines = [f"class {enum_name}(str, Enum):"]
                for val in prop.enum:
                    safe_name = _sanitize_enum_name(val)
                    enum_lines.append(f'    {safe_name} = "{val}"')
                enum_lines.append("")
                enum_classes.append("\n".join(enum_lines))

        # Generate model class
        class_lines = [f"class {et.label}(BaseModel):"]
        class_lines.append(f'    """Entity model for {et.label}."""')
        class_lines.append("")

        if not et.properties:
            class_lines.append("    pass")
        else:
            for prop in et.properties:
                py_type = _PYTHON_TYPE_MAP.get(prop.type, "str")
                if prop.enum:
                    enum_name = f"{et.label}{prop.name.title().replace('_', '')}Enum"
                    py_type = enum_name

                if not prop.required:
                    py_type = f"{py_type} | None"
                    default = "None"
                else:
                    default = "Field(...)"

                if prop.default is not None:
                    default = f'"{prop.default}"' if prop.type in ("string", "str") else prop.default

                class_lines.append(f"    {prop.name}: {py_type} = {default}")

        class_lines.append("")
        models.extend(enum_classes)
        models.append("\n".join(class_lines))

    return "\n".join(imports) + "\n".join(models)


def generate_visualization_config(ontology: DomainOntology) -> dict:
    """Generate NVL visualization config from the ontology."""
    colors = dict(ontology.visualization.node_colors)
    sizes = dict(ontology.visualization.node_sizes)

    # Fill in from entity types if not explicitly set
    for et in ontology.entity_types:
        if et.label not in colors:
            colors[et.label] = et.color
        if et.label not in sizes:
            sizes[et.label] = 20  # default

    return {
        "nodeColors": colors,
        "nodeSizes": sizes,
        "defaultCypher": ontology.visualization.default_cypher,
    }
