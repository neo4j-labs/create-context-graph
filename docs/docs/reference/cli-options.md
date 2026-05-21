---
sidebar_position: 1
title: CLI Options & Flags
---

# CLI Options & Flags

Complete reference for the `create-context-graph` command-line interface.

## Command Signature

```
create-context-graph [PROJECT_NAME] [OPTIONS]
```

`PROJECT_NAME` is optional. If omitted but `--domain` and `--framework` are provided, a slug is auto-generated (e.g., `healthcare-pydanticai-app`). If neither project name nor required flags are provided, the interactive wizard launches.

## Options

### Project Setup

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `--domain` | `string` | *(wizard)* | Domain ID (e.g., `healthcare`, `financial-services`). Use `--list-domains` to see all. |
| `--framework` | `choice` | *(wizard)* | Agent framework: `pydanticai`, `claude-agent-sdk`, `strands`, `google-adk`, `openai-agents`, `langgraph`, `crewai`, `anthropic-tools`. |
| `--custom-domain` | `string` | -- | Natural language domain description. Requires `--anthropic-api-key`. |
| `--output-dir` | `path` | `./<project-slug>` | Directory for generated project. |
| `--with-mcp` | `flag` | `false` | Generate MCP server config for Claude Desktop. |
| `--mcp-profile` | `choice` | `extended` | MCP tool profile: `core` (6 tools) or `extended` (16 tools). |

### Data Generation

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `--demo-data` | `flag` | `false` | Generate synthetic demo data. Uses static data by default; pass `--anthropic-api-key` for LLM-generated data. |
| `--demo` | `flag` | `false` | Shortcut for `--reset-database --demo-data --ingest`. |
| `--ingest` | `flag` | `false` | Ingest generated data into Neo4j after scaffolding. |
| `--reset-database` | `flag` | `false` | Clear all Neo4j data before ingesting. |

### Memory Backend

The CLI chooses one of two memory backends per project:

- **NAMS** (default) — hosted [Neo4j Agent Memory Service](https://memory.neo4jlabs.com). Requires `--nams-api-key` (or `MEMORY_API_KEY` env). Auto-selected when `--self-hosted` is not passed.
- **Bolt** — self-hosted Neo4j over the bolt protocol. Selected by `--self-hosted` (or any explicit `--neo4j-*` flag).

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `--self-hosted` | `flag` | `false` | Use self-hosted Neo4j (bolt) instead of NAMS. |
| `--nams-api-key` | `string` | `$MEMORY_API_KEY` | NAMS API key. Obtain at [memory.neo4jlabs.com](https://memory.neo4jlabs.com). |
| `--nams-endpoint` | `string` | `https://memory.neo4jlabs.com/v1` | Override the NAMS endpoint URL (e.g. for self-hosted gateway). |
| `--memory-llm` | `string` | auto | LiteLLM-style provider string for memory entity extraction. Examples: `anthropic/claude-haiku-4-5`, `openai/gpt-4o-mini`, `bedrock/anthropic.claude-3-haiku-20240307-v1:0`. |
| `--memory-embedding` | `string` | `sentence-transformers/all-MiniLM-L6-v2` | LiteLLM-style provider string for memory embeddings. |

### Memory Behavior

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `--session-strategy` | `choice` | `per_conversation` | Session strategy: `per_conversation`, `per_day`, or `persistent`. |
| `--auto-extract` / `--no-auto-extract` | `flag` | on | Auto-extract entities from conversation messages. |
| `--auto-preferences` / `--no-auto-preferences` | `flag` | on (bolt) / forced off (NAMS) | Auto-detect user preferences. NAMS REST does not expose preference endpoints; this is forced off on the NAMS backend. |

### SaaS Connector Configuration

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `--connector` | `string` (repeatable) | -- | SaaS connector: `github`, `slack`, `jira`, `notion`, `gmail`, `gcal`, `salesforce`, `linear`, `google-workspace`, `claude-code`, `claude-ai`, `chatgpt`. |
| `--linear-api-key` | `string` | `$LINEAR_API_KEY` | Linear personal API key. |
| `--linear-team` | `string` | `$LINEAR_TEAM` | Linear team URL key (e.g., `ENG`). |
| `--gws-folder-id` | `string` | `$GWS_FOLDER_ID` | Google Drive folder ID to scope the import. |
| `--gws-include-comments` / `--gws-no-comments` | `flag` | on | Import comment threads (resolved → decision traces). |
| `--gws-include-revisions` / `--gws-no-revisions` | `flag` | on | Import revision history metadata. |
| `--gws-include-activity` / `--gws-no-activity` | `flag` | on | Import Drive Activity events. |
| `--gws-include-calendar` | `flag` | off | Import Calendar events. |
| `--gws-include-gmail` | `flag` | off | Import Gmail thread metadata. |
| `--gws-since` | `string` | 90 days ago | ISO date; only import activity after this date. |
| `--gws-mime-types` | `string` | `docs,sheets,slides` | MIME type filter (`docs`, `sheets`, `slides`, `pdf`, `all`). |
| `--gws-max-files` | `int` | `500` | Maximum files to import. |
| `--claude-code-scope` | `choice` | `current` | Import from `current` project or `all` projects. |
| `--claude-code-project` | `string` | -- | Explicit project path (overrides `--claude-code-scope`). |
| `--claude-code-since` | `string` | all time | ISO date; only import sessions after this date. |
| `--claude-code-max-sessions` | `int` | `0` (all) | Max sessions to import (most recent first). |
| `--claude-code-content` | `choice` | `truncated` | Content mode: `full`, `truncated` (2000 chars), `none`. |

### Chat History Import

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `--import-preview` | `flag` | `false` | Parse `--import-file` and print a summary (conversation counts, date range, sample titles) without scaffolding or ingesting. Useful as a sanity check before a long ingest of a multi-GB export. Requires `--import-type` and `--import-file`. |
| `--import-type` | `choice` | -- | `claude-ai` or `chatgpt`. Must pair with `--import-file`. |
| `--import-file` | `path` | -- | Path to chat export (`.zip`, `.json`, `.jsonl`). |
| `--import-depth` | `choice` | `fast` | `fast` (messages) or `deep` (messages + tool call traces). |
| `--import-filter-after` | `string` | -- | Only conversations created after this date (ISO 8601). |
| `--import-filter-before` | `string` | -- | Only conversations created before this date (ISO 8601). |
| `--import-filter-title` | `string` | -- | Title pattern filter (regex). |
| `--import-max-conversations` | `int` | `0` (all) | Max conversations to import. |

### Neo4j Configuration (self-hosted only)

All of the following imply `--self-hosted` if passed without `--nams-api-key`.

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `--neo4j-uri` | `string` | `$NEO4J_URI` or `neo4j://localhost:7687` | Neo4j Bolt connection URI. |
| `--neo4j-username` | `string` | `$NEO4J_USERNAME` or `neo4j` | Neo4j username. |
| `--neo4j-password` | `string` | `$NEO4J_PASSWORD` or `password` | Neo4j password. |
| `--neo4j-aura-env` | `path` | -- | Path to Aura `.env` file. Auto-sets `neo4j_type=aura`. |
| `--neo4j-local` | `flag` | `false` | Use `@johnymontana/neo4j-local` (no Docker). |

### API Keys

| Option | Type | Env Variable | Description |
|--------|------|-------------|-------------|
| `--anthropic-api-key` | `string` | `ANTHROPIC_API_KEY` | For LLM data generation and custom domains. |
| `--openai-api-key` | `string` | `OPENAI_API_KEY` | For OpenAI Agents and LangGraph frameworks. |
| `--google-api-key` | `string` | `GOOGLE_API_KEY` | For the `google-adk` framework (Gemini models). |

### Output & Debug

| Option | Type | Description |
|--------|------|-------------|
| `--dry-run` | `flag` | Preview config without creating files. |
| `--verbose` | `flag` | Enable debug logging. |
| `--list-domains` | `flag` | Print all domain IDs and exit. |
| `--version` | `flag` | Print version and exit. |
| `--help` | `flag` | Show help and exit. |

## Interactive vs. Non-Interactive Mode

The CLI operates in two modes:

- **Interactive mode:** If `--domain` or `--framework` is missing, the 6-prompt interactive wizard launches: project name → domain (autocomplete) → framework → NAMS API key (or self-hosted Neo4j) → session strategy → data source. Advanced settings (MCP, extraction toggles, extra API keys) are gated behind a single Y/N prompt.
- **Non-interactive mode:** If `--domain` (or `--custom-domain`) and `--framework` are both provided, the wizard is skipped entirely. `PROJECT_NAME` is optional — if omitted, a slug is auto-generated from the domain and framework (e.g., `healthcare-strands-app`). For NAMS backend, `--nams-api-key` (or `MEMORY_API_KEY`) is required. This mode is suitable for CI/CD pipelines and scripting.

## Examples

### Interactive wizard

Launch the wizard, which prompts for project name, domain, framework, data source, and Neo4j configuration:

```bash
create-context-graph
```

### Fully non-interactive

Generate a financial services app with PydanticAI and demo data, no prompts:

```bash
create-context-graph my-fintech-app \
  --domain financial-services \
  --framework pydanticai \
  --demo-data
```

### LLM-powered data generation

Generate realistic synthetic data using the Anthropic API:

```bash
create-context-graph healthcare-app \
  --domain healthcare \
  --framework claude-agent-sdk \
  --demo-data \
  --anthropic-api-key sk-ant-...
```

Or using the environment variable:

```bash
export ANTHROPIC_API_KEY=sk-ant-...
create-context-graph healthcare-app \
  --domain healthcare \
  --framework claude-agent-sdk \
  --demo-data
```

### Custom domain from natural language

Describe your domain in plain English and let the LLM generate the ontology:

```bash
create-context-graph vet-clinic \
  --custom-domain "veterinary clinic managing patients, owners, appointments, and treatments" \
  --framework pydanticai \
  --demo-data \
  --anthropic-api-key sk-ant-...
```

### With SaaS connectors

Enable GitHub and Slack data import:

```bash
create-context-graph dev-team-graph \
  --domain software-engineering \
  --framework langgraph \
  --connector github \
  --connector slack
```

### Import chat history from Claude AI or ChatGPT

```bash
create-context-graph my-chat-graph \
  --domain personal-knowledge \
  --framework pydanticai \
  --import-type claude-ai \
  --import-file ~/Downloads/claude-export.zip \
  --import-depth deep \
  --import-filter-after 2025-06-01
```

### Import Linear workspace data

```bash
create-context-graph my-project \
  --domain software-engineering \
  --framework pydanticai \
  --connector linear \
  --linear-api-key lin_api_xxxxx \
  --linear-team ENG
```

### With MCP server for Claude Desktop

Generate a project with MCP server support:

```bash
create-context-graph my-app \
  --domain healthcare \
  --framework pydanticai \
  --demo-data \
  --with-mcp \
  --mcp-profile extended
```

After scaffolding, copy `mcp/claude_desktop_config.json` to your Claude Desktop config directory and restart Claude Desktop to connect.

### Scaffold and ingest into Neo4j

Generate the project, create demo data, and load it into a running Neo4j instance:

```bash
create-context-graph my-app \
  --domain supply-chain \
  --framework openai-agents \
  --demo-data \
  --ingest \
  --neo4j-uri neo4j://localhost:7687 \
  --neo4j-password my-secret
```

### Quick demo (scaffold + seed + ingest in one step)

```bash
create-context-graph my-app \
  --domain healthcare \
  --framework pydanticai \
  --demo \
  --neo4j-uri neo4j://localhost:7687
```

### Reset Neo4j before ingesting

Clear all existing data from a shared Neo4j instance before loading new domain data:

```bash
create-context-graph my-app \
  --domain healthcare \
  --framework pydanticai \
  --demo-data \
  --ingest \
  --reset-database \
  --neo4j-uri neo4j://localhost:7687
```

### Custom output directory

Write the generated project to a specific path:

```bash
create-context-graph my-app \
  --domain healthcare \
  --framework crewai \
  --output-dir /tmp/projects/healthcare-demo
```

### Preview without creating files

```bash
create-context-graph my-app \
  --domain healthcare \
  --framework pydanticai \
  --dry-run
```

### List all available domains

```bash
create-context-graph --list-domains
```

### Using uvx (no install required)

```bash
uvx create-context-graph my-app --domain healthcare --framework pydanticai --demo-data
```

## Environment Variables

The following environment variables are read as defaults for their corresponding CLI options:

| Variable | CLI Option |
|----------|-----------|
| `NEO4J_URI` | `--neo4j-uri` |
| `NEO4J_USERNAME` | `--neo4j-username` |
| `NEO4J_PASSWORD` | `--neo4j-password` |
| `ANTHROPIC_API_KEY` | `--anthropic-api-key` |
| `OPENAI_API_KEY` | `--openai-api-key` |
| `GOOGLE_API_KEY` | `--google-api-key` |
| `LINEAR_API_KEY` | `--linear-api-key` |
| `LINEAR_TEAM` | `--linear-team` |

CLI flags always take precedence over environment variables.
