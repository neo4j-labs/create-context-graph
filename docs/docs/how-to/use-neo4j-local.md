---
sidebar_position: 5
title: Use Neo4j Local
---

# Use Neo4j Local (No Docker)

Run Neo4j on your machine without Docker using `@johnymontana/neo4j-local`.

## Overview

`@johnymontana/neo4j-local` is an npm package that downloads and runs Neo4j Community Edition (5.x) directly on your machine. It requires Node.js but no Docker installation.

:::info
`neo4j-local` is maintained by a Neo4j Developer Relations engineer and installs the latest Neo4j 5.x Community Edition. It is not an official Neo4j product but is actively maintained and used across Neo4j Labs projects.
:::

## Quick Start

```bash
npx @johnymontana/neo4j-local
```

This starts Neo4j on the default ports:
- **Bolt**: `neo4j://localhost:7687`
- **Browser**: `http://localhost:7474`

Default credentials: `neo4j` / `neo4j` (you'll be prompted to change the password on first login).

## Using with create-context-graph

### During Scaffolding

Pass the `--neo4j-local` flag to configure your project for local Neo4j:

```bash
uvx create-context-graph my-app \
  --domain healthcare \
  --framework pydanticai \
  --neo4j-local \
  --demo
```

### Manual Configuration

Set these values in your `.env` file:

```env
NEO4J_URI=neo4j://localhost:7687
NEO4J_USERNAME=neo4j
NEO4J_PASSWORD=your-password
```

## Alternative Local Options

### Neo4j Desktop

1. Download [Neo4j Desktop](https://neo4j.com/download/)
2. Create a new project and database
3. Start the database and note the Bolt URI

### Docker (Single Container)

```bash
docker run -d \
  --name neo4j \
  -p 7474:7474 -p 7687:7687 \
  -e NEO4J_AUTH=neo4j/your-password \
  neo4j:5.26.30
```

### Docker Compose

The generated project includes a `docker-compose.yml` with Neo4j configured:

```bash
cd my-app && docker compose up -d neo4j
```

## Troubleshooting

### Port Already in Use

If port 7687 is busy, another Neo4j instance may be running. Stop it first or change the port.

### Authentication Failed

If you get auth errors after changing the password:
1. Stop Neo4j
2. Delete the data directory (usually `~/.neo4j-local/data/`)
3. Restart — you'll get the default credentials again

### Connection Refused

Ensure Neo4j has fully started. It may take 10-30 seconds on first launch while it initializes the database.

## Further Reading

- [Use Neo4j Aura](/docs/how-to/use-neo4j-aura) -- alternative: free managed cloud database
- [Use Docker](/docs/how-to/use-docker) -- alternative: run Neo4j in a container
- [Quick Start](/docs/quick-start) -- get a full app running in under 5 minutes
