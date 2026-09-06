#!/usr/bin/env python3
"""Regenerate all 23 fixture files using Claude API for high-quality demo data.

This is a one-time dev tool — NOT part of the installed package.
Run with: ANTHROPIC_API_KEY=$KEY python scripts/regenerate_fixtures.py

Requires: pip install anthropic
"""

from __future__ import annotations

import json
import os
import re
import sys
import time
from pathlib import Path

# Add src to path so we can import project modules
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from create_context_graph.constants import DEFAULT_ANTHROPIC_MODEL
from create_context_graph.ontology import list_available_domains, load_domain

try:
    import anthropic
except ImportError:
    print("Error: anthropic package required. Install with: pip install anthropic")
    sys.exit(1)


FIXTURES_DIR = Path(__file__).parent.parent / "src" / "create_context_graph" / "fixtures"
MODEL = os.environ.get("ANTHROPIC_MODEL", DEFAULT_ANTHROPIC_MODEL)


def _response_text(response) -> str:
    """First text block of an Anthropic response (thinking blocks may come first)."""
    for block in getattr(response, "content", None) or []:
        text = getattr(block, "text", None)
        if isinstance(text, str):
            return text
    return ""
MAX_RETRIES = 3


def _strip_fences(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        text = "\n".join(text.split("\n")[1:])
    if text.endswith("```"):
        text = text[:-3]
    return text.strip()


def generate_entities(client: anthropic.Anthropic, ontology) -> dict[str, list[dict]]:
    """Generate all entities for a domain in a single coherent prompt."""
    entity_specs = []
    for et in ontology.entity_types:
        props = []
        for p in et.properties:
            spec = f"{p.name} ({p.type}"
            if p.enum:
                spec += f", one of: {p.enum}"
            if p.required:
                spec += ", required"
            if p.unique:
                spec += ", unique"
            spec += ")"
            props.append(spec)

        count = 10 if et.pole_type in ("PERSON", "OBJECT") else 8
        # Base types get fewer
        if et.label in ("Person", "Organization", "Location", "Event", "Object"):
            count = 5

        entity_specs.append({
            "label": et.label,
            "pole_type": et.pole_type,
            "count": count,
            "properties": props,
        })

    prompt = f"""Generate realistic sample entities for a {ontology.domain.name} knowledge graph application.
{ontology.domain.description}

Generate entities for EACH of these types. Use realistic, diverse names (mix of genders,
ethnicities, geographic regions appropriate to the domain). Properties should have realistic
values — real-looking IDs, plausible amounts, actual-sounding descriptions.

Entity types to generate:
"""
    for spec in entity_specs:
        prompt += f"\n### {spec['label']} ({spec['pole_type']}) — generate {spec['count']} entities\n"
        prompt += f"Properties: {', '.join(spec['properties'])}\n"

    prompt += """

Return a JSON object where each key is the entity type label and each value is an array of entity objects.
Every entity MUST have a "name" field. Example structure:
{"Person": [{"name": "Sarah Chen", "email": "sarah.chen@example.com", ...}], "Account": [...]}

Respond with ONLY the JSON. No markdown fences, no explanation."""

    response = client.messages.create(
        model=MODEL,
        max_tokens=8192,
        system="You are generating realistic, high-quality sample data for a knowledge graph application. All data should be believable and internally consistent.",
        messages=[{"role": "user", "content": prompt}],
    )
    text = _strip_fences(_response_text(response))
    return json.loads(text)


def generate_documents(client: anthropic.Anthropic, ontology, entities: dict) -> list[dict]:
    """Generate realistic documents using entity data for context."""
    documents = []

    for template in ontology.document_templates:
        count = min(template.count, 5)

        # Gather entity names for context
        context_entities = {}
        for req_label in template.required_entities:
            if req_label in entities:
                context_entities[req_label] = [e["name"] for e in entities[req_label]]

        prompt = f"""Generate {count} realistic {template.name} documents for a {ontology.domain.name} application.

Document type: {template.description}
{f"Template guidance: {template.prompt_template}" if template.prompt_template else ""}

Available entities to reference:
"""
        for label, names in context_entities.items():
            prompt += f"  {label}: {', '.join(names[:5])}\n"

        prompt += f"""
Each document should:
- Be 200-400 words of realistic, professional content
- Reference specific entities by name where appropriate
- Read like an actual {template.name.lower()} from the {ontology.domain.name.lower()} industry
- Have unique content (don't repeat the same document with different names)

Return a JSON array of objects, each with: "title" (string), "content" (string).
Respond with ONLY the JSON array. No markdown fences."""

        try:
            response = client.messages.create(
                model=MODEL,
                max_tokens=8192,
                system=f"You are generating realistic {ontology.domain.name.lower()} documents. Write professional, detailed content.",
                messages=[{"role": "user", "content": prompt}],
            )
            text = _strip_fences(_response_text(response))
            items = json.loads(text)

            for item in items:
                documents.append({
                    "template_id": template.id,
                    "template_name": template.name,
                    "title": item.get("title", f"{template.name}"),
                    "content": item.get("content", ""),
                })
        except Exception as e:
            print(f"    Warning: Document generation failed for {template.name}: {e}")

    return documents


def _interpolate_template_vars(text: str, entities: dict[str, list[dict]]) -> str:
    """Replace all {{entity_type.property}} patterns with actual entity values."""
    import random as _rng

    entity_lookup: dict[str, tuple[str, dict]] = {}
    for label, ents in entities.items():
        if ents:
            entity = _rng.choice(ents)
            entity_lookup[label.lower()] = (label, entity)
            snake = re.sub(r"([a-z])([A-Z])", r"\1_\2", label).lower()
            if snake != label.lower():
                entity_lookup[snake] = (label, entity)

    def _replace_match(match: re.Match) -> str:
        var = match.group(1)
        if "." in var:
            entity_key, prop = var.split(".", 1)
            if entity_key in entity_lookup:
                _label, entity = entity_lookup[entity_key]
                value = entity.get(prop, entity.get("name", entity_key))
                return str(value)
        else:
            if var in entity_lookup:
                _label, entity = entity_lookup[var]
                return str(entity.get("name", var))
        return match.group(0)

    result = re.sub(r"\{\{([^}]+)\}\}", _replace_match, text)
    result = re.sub(r"\{\{[^}]+\}\}", "the relevant criteria", result)
    return result


def generate_traces(client: anthropic.Anthropic, ontology, entities: dict) -> list[dict]:
    """Generate complete decision traces with realistic observations and outcomes."""
    traces = []

    for trace_def in ontology.decision_traces:
        # Interpolate entity references into task
        task = _interpolate_template_vars(trace_def.task, entities)

        steps_prompt = "\n".join(
            f"  Step {i+1}: Thought: {s.thought} | Action: {s.action}"
            for i, s in enumerate(trace_def.steps)
        )

        prompt = f"""Generate realistic observations and an outcome for this decision trace in a {ontology.domain.name} context.

Task: {task}

Steps:
{steps_prompt}

For each step, generate a realistic 1-2 sentence observation that would result from the action.
Then generate a 1-2 sentence outcome/decision for the overall task.

Return JSON with this structure:
{{"observations": ["obs for step 1", "obs for step 2", ...], "outcome": "the final decision/outcome"}}
Respond with ONLY the JSON."""

        try:
            response = client.messages.create(
                model=MODEL,
                max_tokens=2048,
                system="Generate realistic, domain-appropriate observations and outcomes. Be specific and detailed.",
                messages=[{"role": "user", "content": prompt}],
            )
            text = _strip_fences(_response_text(response))
            result = json.loads(text)

            steps = []
            for i, step in enumerate(trace_def.steps):
                obs = result["observations"][i] if i < len(result.get("observations", [])) else f"Analysis completed for: {step.action}"
                steps.append({
                    "thought": step.thought,
                    "action": step.action,
                    "observation": obs,
                })

            traces.append({
                "id": trace_def.id,
                "task": task,
                "steps": steps,
                "outcome": result.get("outcome", f"Decision completed for: {task}"),
            })
        except Exception as e:
            print(f"    Warning: Trace generation failed for {trace_def.id}: {e}")

    return traces


def _ensure_names(entities: dict) -> dict:
    """Ensure all entities have a 'name' field."""
    for label, items in entities.items():
        for i, item in enumerate(items):
            if "name" not in item:
                # Try common alternative name fields
                for alt in ("title", "label", "display_name", "full_name", "common_name"):
                    if alt in item:
                        item["name"] = item[alt]
                        break
                else:
                    item["name"] = f"{label} {i + 1}"
    return entities


def weave_relationships(ontology, entities: dict) -> list[dict]:
    """Create relationships between entities based on ontology definitions."""
    import random
    relationships = []

    for rel_def in ontology.relationships:
        source_entities = entities.get(rel_def.source, [])
        target_entities = entities.get(rel_def.target, [])

        if not source_entities or not target_entities:
            continue

        for source in source_entities:
            source_name = source.get("name", "Unknown")
            targets = random.sample(
                target_entities,
                min(random.randint(1, 3), len(target_entities)),
            )
            for target in targets:
                target_name = target.get("name", "Unknown")
                if source_name == target_name:
                    continue
                relationships.append({
                    "type": rel_def.type,
                    "source_label": rel_def.source,
                    "source_name": source_name,
                    "target_label": rel_def.target,
                    "target_name": target_name,
                })

    return relationships


def validate_fixture(data: dict, ontology) -> list[str]:
    """Validate a generated fixture. Returns list of errors (empty = valid)."""
    errors = []

    if "entities" not in data:
        errors.append("Missing 'entities' key")
        return errors

    # Check all entity types present
    ontology_labels = {et.label for et in ontology.entity_types}
    for label in ontology_labels:
        if label not in data["entities"]:
            errors.append(f"Missing entity type: {label}")
        elif len(data["entities"][label]) < 3:
            errors.append(f"Too few entities for {label}: {len(data['entities'][label])}")

    # Check all entities have name
    for label, items in data["entities"].items():
        for i, item in enumerate(items):
            if "name" not in item or item["name"] is None:
                errors.append(f"{label}[{i}] missing 'name'")
            elif isinstance(item["name"], str) and re.match(r"^(Person|Organization|Location|Event|Object|Account|Patient|Species)\s+\d+$", item["name"]):
                errors.append(f"{label}[{i}] has placeholder name: {item['name']}")

    # Check documents
    for i, doc in enumerate(data.get("documents", [])):
        if len(doc.get("content", "")) < 100:
            errors.append(f"Document {i} content too short: {len(doc.get('content', ''))} chars")

    # Check traces for template variables
    for trace in data.get("traces", []):
        if "{{" in trace.get("task", ""):
            errors.append(f"Trace '{trace.get('id')}' has uninterpolated task: {trace['task'][:50]}")
        if "{{" in trace.get("outcome", ""):
            errors.append(f"Trace '{trace.get('id')}' has uninterpolated outcome: {trace['outcome'][:50]}")
        for step in trace.get("steps", []):
            if step.get("observation", "").startswith("Results retrieved for:"):
                errors.append(f"Trace '{trace.get('id')}' has placeholder observation")

    return errors


def regenerate_domain(client: anthropic.Anthropic, domain_id: str) -> dict | None:
    """Regenerate fixture data for a single domain."""
    ontology = load_domain(domain_id)

    for attempt in range(MAX_RETRIES):
        try:
            print(f"  [Attempt {attempt + 1}] Generating entities...")
            entities = generate_entities(client, ontology)
            entities = _ensure_names(entities)
            entity_count = sum(len(v) for v in entities.values())
            print(f"  Generated {entity_count} entities across {len(entities)} types")

            print("  Weaving relationships...")
            relationships = weave_relationships(ontology, entities)

            print("  Generating documents...")
            documents = generate_documents(client, ontology, entities)

            print("  Generating decision traces...")
            traces = generate_traces(client, ontology, entities)

            data = {
                "domain": domain_id,
                "entities": entities,
                "relationships": relationships,
                "documents": documents,
                "traces": traces,
            }

            # Validate
            errors = validate_fixture(data, ontology)
            if errors:
                print(f"  Validation errors: {errors[:3]}")
                if attempt < MAX_RETRIES - 1:
                    print("  Retrying...")
                    continue
                else:
                    print(f"  WARNING: Proceeding with {len(errors)} validation errors")

            entity_count = sum(len(v) for v in entities.values())
            print(f"  OK: {entity_count} entities, {len(relationships)} rels, {len(documents)} docs, {len(traces)} traces")
            return data

        except Exception as e:
            import traceback
            print(f"  Error: {e}")
            traceback.print_exc()
            if attempt < MAX_RETRIES - 1:
                print("  Retrying in 5s...")
                time.sleep(5)
            else:
                print(f"  FAILED after {MAX_RETRIES} attempts")
                return None

    return None


def main():
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        print("Error: ANTHROPIC_API_KEY environment variable required")
        sys.exit(1)

    client = anthropic.Anthropic(api_key=api_key)
    domains = list_available_domains()

    # Allow filtering to specific domains via command line
    if len(sys.argv) > 1:
        filter_ids = set(sys.argv[1:])
        domains = [d for d in domains if d["id"] in filter_ids]

    print(f"Regenerating fixtures for {len(domains)} domains...\n")

    success = 0
    failed = []

    for domain in domains:
        domain_id = domain["id"]
        print(f"[{domain_id}] {domain['name']}")

        data = regenerate_domain(client, domain_id)
        if data:
            output_path = FIXTURES_DIR / f"{domain_id}.json"
            output_path.write_text(json.dumps(data, indent=2, default=str))
            size_kb = output_path.stat().st_size / 1024
            print(f"  Written: {output_path.name} ({size_kb:.1f} KB)\n")
            success += 1
        else:
            failed.append(domain_id)
            print("  FAILED\n")

    print(f"\nDone: {success}/{len(domains)} succeeded")
    if failed:
        print(f"Failed: {', '.join(failed)}")


if __name__ == "__main__":
    main()
