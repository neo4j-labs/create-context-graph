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

"""LLM-powered custom domain ontology generation.

Generates a complete domain YAML from a natural language description,
validates it against the DomainOntology Pydantic model, and optionally
saves it for future reuse.
"""

from __future__ import annotations

from importlib.resources import files
from pathlib import Path

import yaml
from pydantic import ValidationError
from rich.console import Console
from rich.table import Table

from create_context_graph.generator import _get_llm_client, _llm_generate
from create_context_graph.ontology import (
    DomainOntology,
    _get_custom_domains_path,
    load_domain_from_yaml_string,
)

console = Console()


# ---------------------------------------------------------------------------
# Prompt construction
# ---------------------------------------------------------------------------

_SCHEMA_SPEC = """\
The YAML must follow this exact structure:

inherits: _base

domain:
  id: <kebab-case-id>
  name: <Human Readable Name>
  description: <one-line description>
  tagline: <short marketing tagline in quotes>
  emoji: <single emoji character>

entity_types:
  - label: <PascalCase>
    pole_type: <PERSON|ORGANIZATION|LOCATION|EVENT|OBJECT>
    subtype: <UPPER_SNAKE optional>
    color: <hex color like "#16a34a">
    icon: <icon name>
    properties:
      - name: <snake_case>
        type: <string|integer|float|boolean|date|datetime|point>
        required: <true|false>
        unique: <true|false>
        enum: [<quoted values if applicable>]

relationships:
  - type: <UPPER_SNAKE_CASE>
    source: <EntityLabel>
    target: <EntityLabel>

document_templates:
  - id: <kebab-case>
    name: <Template Name>
    description: <what this document type represents>
    count: <integer, typically 3-5>
    prompt_template: <prompt for LLM to generate a sample document>
    required_entities: [<EntityLabel>, ...]

decision_traces:
  - id: <kebab-case>
    task: <description of the decision task>
    steps:
      - thought: <reasoning step>
        action: <action taken>
        observation: <result observed>
    outcome_template: <template for the decision outcome>

demo_scenarios:
  - name: <scenario name>
    prompts:
      - <sample user prompt 1>
      - <sample user prompt 2>

agent_tools:
  - name: <snake_case_tool_name>
    description: <what the tool does>
    cypher: <Cypher query with $parameter placeholders>
    parameters:
      - name: <param_name>
        type: string
        description: <param description>

system_prompt: |
  <Multi-line system prompt for the AI agent in this domain>

visualization:
  node_colors:
    <EntityLabel>: "<hex>"
  node_sizes:
    <EntityLabel>: <int>
  default_cypher: "MATCH (n)-[r]->(m) RETURN n, r, m LIMIT 100"

Rules:
- Include "inherits: _base" at the top (this merges Person, Organization, Location, Event, Object base types)
- Define at least 3 domain-specific entity types (beyond the base types)
- Define at least 3 relationships connecting your entities
- Each entity type must have at least one property with required: true and unique: true
- Include at least 2 document_templates, 1 decision_trace, 2 demo_scenarios, and 3 agent_tools
- Property types must be one of: string, integer, float, boolean, date, datetime, point
- YAML booleans in enum values must be quoted: enum: ["true", "false"] not enum: [true, false]
- Use realistic hex colors that visually distinguish entity types
- The system_prompt should describe the AI agent's role and capabilities for this domain
- Cypher queries in agent_tools should use $parameter syntax for variables
"""


def _build_domain_generation_prompt(
    description: str, base_yaml: str, examples: list[str]
) -> str:
    """Build the prompt for LLM domain generation."""
    prompt = f"""Generate a complete domain ontology YAML for the following domain:

DOMAIN DESCRIPTION: {description}

{_SCHEMA_SPEC}

Here is the base ontology that will be inherited (do NOT redefine these entity types):

```yaml
{base_yaml}
```

Here are two example domain ontologies for reference:

"""
    for i, example in enumerate(examples, 1):
        prompt += f"--- Example {i} ---\n```yaml\n{example}\n```\n\n"

    prompt += """Now generate a complete domain ontology YAML for the described domain. Output ONLY the YAML content, no markdown fences or explanation."""

    return prompt


def _build_retry_prompt(
    description: str, previous_yaml: str, errors: str
) -> str:
    """Build a retry prompt with validation error feedback."""
    return f"""The domain YAML you generated for "{description}" had validation errors:

{errors}

Here was your previous attempt:
```yaml
{previous_yaml}
```

Please fix the errors and generate a corrected YAML. Output ONLY the valid YAML content, no markdown fences or explanation.

{_SCHEMA_SPEC}"""


def _load_example_yamls() -> tuple[str, list[str]]:
    """Load the base YAML and two reference domain YAMLs."""
    domains_dir = Path(str(files("create_context_graph") / "domains"))

    base_path = domains_dir / "_base.yaml"
    base_yaml = base_path.read_text() if base_path.exists() else ""

    examples = []
    for domain_id in ("healthcare", "wildlife-management"):
        path = domains_dir / f"{domain_id}.yaml"
        if path.exists():
            examples.append(path.read_text())

    return base_yaml, examples


def _strip_yaml_fences(text: str) -> str:
    """Strip markdown code fences from LLM output."""
    text = text.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        text = "\n".join(lines[1:])
    if text.endswith("```"):
        text = text[:-3]
    return text.strip()


# ---------------------------------------------------------------------------
# Core generation
# ---------------------------------------------------------------------------


def generate_custom_domain(
    description: str,
    api_key: str,
    provider: str = "anthropic",
    max_retries: int = 3,
    base_url: str | None = None,
) -> tuple[DomainOntology, str]:
    """Generate a complete domain ontology from a natural language description.

    Returns (DomainOntology, raw_yaml_string) on success.
    Raises ValueError if generation fails after max_retries.
    """
    client, resolved_provider = _get_llm_client(api_key, provider, base_url)
    if client is None:
        raise ValueError(
            "Could not initialize LLM client. Install 'anthropic' or 'openai' package."
        )

    base_yaml, examples = _load_example_yamls()
    prompt = _build_domain_generation_prompt(description, base_yaml, examples)

    system = (
        "You are an expert knowledge graph architect. Generate precise, valid YAML "
        "domain ontologies for context graph applications. Your output must be "
        "syntactically valid YAML that passes strict Pydantic validation."
    )

    last_error = None
    raw_yaml = ""

    for attempt in range(max_retries):
        if attempt == 0:
            raw_yaml = _llm_generate(client, resolved_provider, prompt, system)
        else:
            retry_prompt = _build_retry_prompt(description, raw_yaml, str(last_error))
            raw_yaml = _llm_generate(client, resolved_provider, retry_prompt, system)

        raw_yaml = _strip_yaml_fences(raw_yaml)

        try:
            ontology = load_domain_from_yaml_string(raw_yaml)
            return ontology, raw_yaml
        except (ValidationError, ValueError, yaml.YAMLError) as e:
            last_error = e
            if attempt < max_retries - 1:
                console.print(
                    f"[yellow]Validation failed (attempt {attempt + 1}/{max_retries}), retrying...[/yellow]"
                )

    raise ValueError(
        f"Failed to generate valid domain after {max_retries} attempts. "
        f"Last error: {last_error}"
    )


# ---------------------------------------------------------------------------
# Display and persistence
# ---------------------------------------------------------------------------


def display_ontology_summary(ontology: DomainOntology, target_console: Console | None = None) -> None:
    """Show a Rich summary table of a generated ontology."""
    c = target_console or console

    c.print()
    c.print(f"[bold cyan]{ontology.domain.emoji} {ontology.domain.name}[/bold cyan]")
    c.print(f"[dim]{ontology.domain.description}[/dim]")
    c.print()

    # Entity types
    table = Table(title="Entity Types", show_header=True)
    table.add_column("Label", style="bold")
    table.add_column("POLE+O Type")
    table.add_column("Properties", justify="right")
    table.add_column("Color")

    for et in ontology.entity_types:
        table.add_row(et.label, et.pole_type, str(len(et.properties)), et.color)

    c.print(table)
    c.print()

    # Relationships
    if ontology.relationships:
        rel_table = Table(title="Relationships", show_header=True)
        rel_table.add_column("Type", style="bold")
        rel_table.add_column("Source")
        rel_table.add_column("Target")
        for r in ontology.relationships:
            rel_table.add_row(r.type, r.source, r.target)
        c.print(rel_table)
        c.print()

    # Agent tools
    if ontology.agent_tools:
        c.print(f"[bold]Agent Tools:[/bold] {', '.join(t.name for t in ontology.agent_tools)}")

    # Document templates
    if ontology.document_templates:
        c.print(f"[bold]Document Templates:[/bold] {', '.join(t.name for t in ontology.document_templates)}")

    c.print()


def save_custom_domain(ontology: DomainOntology, yaml_content: str) -> Path:
    """Save a custom domain YAML to ~/.create-context-graph/custom-domains/.

    Returns the path the file was saved to.
    """
    custom_dir = _get_custom_domains_path()
    custom_dir.mkdir(parents=True, exist_ok=True)

    domain_id = ontology.domain.id
    output_path = custom_dir / f"{domain_id}.yaml"
    output_path.write_text(yaml_content)

    console.print(f"[green]Saved custom domain to {output_path}[/green]")
    return output_path
