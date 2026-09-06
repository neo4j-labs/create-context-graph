# create-context-graph

Interactive CLI scaffolding tool that generates domain-specific context graph applications with Neo4j.

```bash
npx create-context-graph
```

Pick your industry domain (22 available), pick your agent framework (8 options), and get a complete full-stack app — FastAPI backend, Next.js frontend, Neo4j knowledge graph, and AI agent — in under 5 minutes.

> This is an npm wrapper that delegates to the Python CLI. Requires Python 3.11+ with [uv](https://docs.astral.sh/uv/) installed.

## Quick Start

```bash
# Interactive wizard
npx create-context-graph

# Non-interactive
npx create-context-graph my-app --domain healthcare --framework pydanticai --demo-data
```

## Requirements

- **Python 3.11+** with `uv` (recommended) or `pip`
- **Node.js 22+ (24 LTS recommended)** (for the generated frontend)
- **Neo4j 5+** (Docker, Aura, or local)

## Documentation

See the full documentation at [github.com/neo4j-labs/create-context-graph](https://github.com/neo4j-labs/create-context-graph).

## License

Apache-2.0
