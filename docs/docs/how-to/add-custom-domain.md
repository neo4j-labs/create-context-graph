---
sidebar_position: 2
title: Add a Custom Domain
---

# Add a Custom Domain

Beyond the 27 built-in domains, you can define your own domain ontology. There are three ways to do this: let the LLM generate one from a description, pass a description via CLI flags, or write the YAML by hand.

## Option 1: Interactive Wizard

Run the CLI and select the custom domain option:

```bash
create-context-graph my-app
```

1. At the domain selection step, choose **"Custom (describe your domain)"**.
2. Enter a natural-language description of your domain (e.g., `"veterinary clinic management with patients, owners, appointments, and treatments"`).
3. The LLM generates a full ontology YAML -- entity types, relationships, agent tools, system prompt, visualization config, and demo scenarios.
4. Review the generated ontology summary. Accept it, or refine your description and regenerate.

This requires an Anthropic API key. The wizard prompts for one if `ANTHROPIC_API_KEY` is not set in your environment.

## Option 2: CLI Flags

Skip the wizard entirely:

```bash
create-context-graph my-app \
  --custom-domain "veterinary clinic management with patients, owners, appointments, and treatments" \
  --anthropic-api-key $ANTHROPIC_API_KEY \
  --framework pydanticai \
  --demo-data
```

The `--custom-domain` flag triggers LLM ontology generation and bypasses the domain selection step. All other flags (`--framework`, `--demo-data`, `--connector`, etc.) work as usual.

## Option 3: Manual YAML

Write a domain YAML file from scratch and point the CLI at it:

```bash
create-context-graph my-app --ontology-file ./my-domain.yaml --framework langgraph
```

Your YAML must follow the domain ontology schema. At minimum, include:

```yaml
inherits: _base

domain:
  id: veterinary
  name: Veterinary Clinic
  description: Veterinary clinic management system
  tagline: "AI-powered veterinary care coordination"
  emoji: "🐾"

entity_types:
  - label: Patient
    pole_type: PERSON
    subtype: Animal
    color: "#4CAF50"
    icon: pet
    properties:
      - name: name
        type: string
        required: true
      - name: species
        type: string
        required: true
        enum: ["dog", "cat", "bird", "reptile", "other"]

relationships:
  - type: OWNS
    source: Person
    target: Patient

agent_tools:
  - name: find_patient
    description: Find a patient by name
    cypher: "MATCH (p:Patient) WHERE p.name CONTAINS $name RETURN p"
    parameters:
      - name: name
        type: string

system_prompt: |
  You are a veterinary clinic assistant with access to patient and appointment records.

visualization:
  node_colors:
    Patient: "#4CAF50"
  default_cypher: "MATCH (n) RETURN n LIMIT 50"
```

See the [Ontology YAML Schema](/docs/reference/ontology-yaml-schema) for the complete specification with examples. The `_base.yaml` file defines the inherited POLE+O entity types (Person, Organization, Location, Event, Object) that your domain will automatically include. In the generated project, your ontology lives at `data/ontology.yaml`.

## Saving Custom Domains for Reuse

LLM-generated ontologies are saved to `~/.create-context-graph/custom-domains/` by default. You can reuse a previously generated domain:

```bash
# List saved custom domains
ls ~/.create-context-graph/custom-domains/

# Reuse a saved domain
create-context-graph my-app \
  --ontology-file ~/.create-context-graph/custom-domains/veterinary.yaml
```

Generated domains are also copied into the scaffolded project at `data/ontology.yaml`, so each project is self-contained.

## Tips for Writing Good Domain Descriptions

- **Be specific about entities.** "Healthcare with patients, doctors, diagnoses, medications, and appointments" produces better results than "healthcare."
- **Mention key relationships.** "Students enroll in courses taught by professors" helps the LLM define the correct graph edges.
- **Include domain actions.** "Track shipments, manage inventory, handle returns" gives the LLM material for generating agent tools.
- **Keep it to 1-3 sentences.** The LLM works best with focused descriptions rather than long paragraphs.

## How LLM generation works

When you pass `--custom-domain "..."` (or pick the custom option in the wizard), `custom_domain.py` runs a 3-step pipeline:

1. **Build a few-shot prompt.** The LLM is shown `_base.yaml` plus two reference domain YAMLs (currently `healthcare` and `software-engineering`) so it can pattern-match the schema rather than infer it from prose alone.
2. **Generate and validate.** The model returns a complete YAML block, which is parsed and validated against the `DomainOntology` Pydantic model. Validation catches missing required fields, invalid `pole_type` values, unquoted boolean enums, color collisions with `_base`, malformed Cypher in `agent_tools`, and other structural issues.
3. **Retry on failure.** Up to **3 attempts** — the validation error message is fed back to the LLM so it can self-correct. After 3 failures the CLI aborts and prints the last error rather than scaffolding from a broken ontology.

You can inspect the generated YAML at the wizard's review step before scaffolding starts. The wizard saves accepted custom domains to `~/.create-context-graph/custom-domains/{id}.yaml` so they can be reused without re-paying for LLM generation.

## Worked examples

The following descriptions were generated end-to-end with `--custom-domain "..." --anthropic-api-key $ANTHROPIC_API_KEY`. Each produced a complete YAML on the first try.

### Insurance claims processing

Description used:

> Insurance claims processing system tracking policies, claimants, adjusters, claims, payments, and fraud investigations. Adjusters investigate claims filed by claimants under their policies; suspicious claims escalate to fraud investigations.

Headline entities the LLM produced: `Policy`, `Claim`, `Claimant`, `Adjuster`, `Payment`, `FraudInvestigation`, `PolicyHolder`. Sample relationships: `FILED_BY (Claim → Claimant)`, `INVESTIGATED_BY (Claim → Adjuster)`, `COVERS (Policy → Person)`, `TRIGGERED (Claim → FraudInvestigation)`. Sample agent tools: `search_claim`, `policy_coverage`, `adjuster_workload`, `fraud_indicators`, `payment_history`.

### Podcast production network

Description used:

> Podcast production network with shows, episodes, hosts, guests, sponsors, and editing workflow. Each episode goes through script → record → edit → publish stages with a producer overseeing the pipeline.

Headline entities: `Show`, `Episode`, `Host`, `Guest`, `Sponsor`, `EditingTask`, `Producer`. Sample relationships: `HOSTS (Host → Show)`, `APPEARED_ON (Guest → Episode)`, `SPONSORS (Sponsor → Show)`, `IN_STAGE (Episode → EditingTask)`. Sample agent tools: `search_show`, `episode_pipeline`, `guest_history`, `sponsor_roster`, `pending_edits`.

Both ontologies validated on the first attempt and scaffolded cleanly across all 9 agent frameworks.

## Promoting a custom domain to a permanent contribution

If your generated domain becomes load-bearing for a project (or you want to share it back upstream), the path from `~/.create-context-graph/custom-domains/foo.yaml` to a permanent built-in domain is straightforward:

1. **Move the YAML** to `src/create_context_graph/domains/{domain-id}.yaml` in a fork of the repo. Re-check it against the [ontology schema](/docs/reference/ontology-yaml-schema) — the LLM is good but not perfect; tighten property enums, add missing `unique: true` constraints, and make sure each `agent_tools[].cypher` query has a sensible `LIMIT`.
2. **Generate a fixture** for tests and demos:
   ```bash
   python scripts/regenerate_fixtures.py --domain {domain-id} --anthropic-api-key sk-...
   # or for a deterministic, no-LLM static fixture:
   python -c "from pathlib import Path; from create_context_graph.ontology import load_domain; from create_context_graph.generator import generate_fixture_data; \
     generate_fixture_data(load_domain('{domain-id}'), Path('src/create_context_graph/fixtures/{domain-id}.json'), api_key=None)"
   ```
3. **Verify** with `pytest tests/test_ontology.py tests/test_fixtures.py -k {domain-id}`. The existing `TestLoadAllDomains` test will auto-pick up your new YAML.
4. **Add to the scaffold matrix.** Append one `(domain-id, framework)` tuple to `TestMultipleDomainScaffolds` in `tests/test_cli.py` so CI proves the domain renders cleanly with at least one framework.
5. **Open a PR.** Domains submitted this way have landed in the project repo via this exact path — see `legal`, `education`, `cybersecurity`, and `government` (v0.13.0).
