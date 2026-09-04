---
sidebar_position: 3
---

# Use Neo4j Aura

Neo4j Aura is a fully managed cloud graph database. It's the easiest way to get started with `create-context-graph` without running Neo4j locally.

## Prerequisites

- A [Neo4j Aura](https://neo4j.com/cloud/aura/) account (free tier available)

## Step 1: Create an Aura Instance

1. Go to [console.neo4j.io](https://console.neo4j.io)
2. Click **New Instance**
3. Choose **AuraDB Free** (or a paid tier for production)
4. Select a region close to you
5. Click **Create**
6. **Save the generated password** — you'll need it in the next step

## Step 2: Download the `.env` File

After creating the instance, Neo4j Aura offers a **Download .env** button. This file contains your connection credentials:

```env
NEO4J_URI=neo4j+s://xxxxxxxx.databases.neo4j.io
NEO4J_USERNAME=neo4j
NEO4J_PASSWORD=your-generated-password
```

Save this file somewhere accessible.

## Step 3: Scaffold Your Project

Use the `--neo4j-aura-env` flag to import your Aura credentials directly:

```bash
uvx create-context-graph my-app \
  --domain healthcare \
  --framework pydanticai \
  --neo4j-aura-env /path/to/Neo4j-xxxxxxxx-Created-2026-03-28.txt \
  --demo-data
```

This will:
- Parse the `.env` file for connection details (including `NEO4J_DATABASE` when present)
- Configure the generated project to use your Aura instance
- Set `neo4j_type` to `aura` automatically

:::caution Database name

Aura instances provisioned through the Aura API or CLI often name their
database after the instance id rather than the literal string `neo4j`. If your
`.env` download includes a `NEO4J_DATABASE` line, it is imported automatically;
otherwise pass `--neo4j-database <name>` explicitly. Without it, the app
connects fine but every memory write targets a database that doesn't exist —
the `/health` endpoint will report `"memory": false` with a classified
`memory_error` when this happens.

:::

## Step 4: Verify the Connection

After scaffolding, verify the connection:

```bash
cd my-app
make test-connection
```

You should see:

```
✅ Connected to Neo4j Aura (neo4j+s://xxxxxxxx.databases.neo4j.io)
```

## Step 5: Seed Data and Start

```bash
make install
make seed
make start
```

## Troubleshooting

### Connection refused

- Ensure your Aura instance is **Running** (not paused)
- Free-tier instances pause after 3 days of inactivity — resume from the Aura console
- Check that `NEO4J_URI` starts with `neo4j+s://` (TLS required for Aura)

### Authentication failed

- Double-check the password in your `.env` file
- If you lost the password, reset it from the Aura console under **Instance settings**

### Slow queries

- Free-tier Aura instances have limited resources — queries may take 2-5 seconds
- For better performance, upgrade to a paid tier

## Further Reading

- [Use Docker](/docs/how-to/use-docker) -- alternative: run Neo4j locally via Docker
- [Use Neo4j Local](/docs/how-to/use-neo4j-local) -- alternative: run Neo4j without Docker
- [Quick Start](/docs/quick-start) -- get a full app running in under 5 minutes
