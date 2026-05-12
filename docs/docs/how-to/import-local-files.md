---
sidebar_position: 2
title: Import Local Documents
---

# Import Local Documents

The `local-file` connector ingests documents from your local filesystem directly into your context graph — no API keys, no network, no authentication. It turns a folder of Markdown notes, PDFs, HTML pages, AsciiDoc files, or Word documents into a graph of `:Document` and `:Section` nodes with `:HAS_SECTION` and `:LINKS_TO` edges.

## Supported formats

| Format | Extensions | Notes |
|--------|-----------|-------|
| Markdown | `.md`, `.markdown` | CommonMark + GFM tables, task lists, frontmatter (YAML/TOML `---` blocks are stripped) |
| PDF | `.pdf` | 4-tier strategy — see [PDF performance](#pdf-performance) below |
| HTML | `.html`, `.htm` | Heading tags `<h1>`–`<h6>`, `<a href>` links |
| AsciiDoc | `.adoc`, `.asciidoc`, `.asc` | `=` prefix headings, literal block fencing, autolinks |
| Word | `.docx` | `Heading 1`–`Heading 6` styles, hyperlink relationships |

## Quickstart

```bash
# Scaffold with the connector enabled and ingest immediately
create-context-graph my-app \
  --domain financial-services \
  --framework pydanticai \
  --connector local-file \
  --local-file-path ./my-docs \
  --ingest \
  --neo4j-local
```

Or add it to an existing project by running `make import` after editing `.env`:

```bash
# In your generated project directory
LOCAL_FILE_PATHS=./my-docs make import
```

## CLI options

| Option | Default | Description |
|--------|---------|-------------|
| `--local-file-path PATH` | *(required)* | File or directory to ingest. Repeatable — pass multiple times for multiple roots. |
| `--local-file-pattern GLOB` | `**/*` | Glob pattern to filter files within each root. |
| `--local-file-recursive` / `--local-file-no-recursive` | recursive on | Recurse into subdirectories. Patterns containing `**` require recursion to be enabled. |
| `--local-file-follow-links` | off | Follow symbolic links. |
| `--local-file-exclude GLOB` | *(none)* | Exclude files matching this glob. Repeatable. |

### Examples

```bash
# Ingest only Markdown files, skip drafts/
--local-file-path ./vault \
--local-file-pattern "**/*.md" \
--local-file-exclude "**/drafts/**"

# Multiple roots
--local-file-path ./notes --local-file-path ./reports

# Single file
--local-file-path ./Q1-report.pdf

# Top-level only (no recursion)
--local-file-path ./inbox \
--local-file-pattern "*.md" \
--local-file-no-recursive
```

## Graph shape

Each document becomes a `:Document` node and each heading-delimited section becomes a `:Section` node:

```
(:Document {name: "file:///abs/path/report.md", title: "Q1 Report", …})
  -[:HAS_SECTION]→
    (:Section {name: "…#executive-summary", title: "Executive Summary", …})
      -[:HAS_SECTION]→
        (:Section {name: "…#executive-summary/key-findings", title: "Key Findings", …})
(:Section …) -[:LINKS_TO]→ (:Document {name: "https://example.com/…"})
```

- **`name`** (the MERGE key) is a POSIX-normalised absolute path URI — the same file always produces the same URI on macOS, Linux, and Windows.
- **`description`** on each node holds the section's immediate body text plus URI pointers to its direct children, making it searchable via the graph's vector index.
- **`LINKS_TO`** edges are created for hyperlinks. Targets not parsed in the same run become lightweight stub nodes that are upgraded in place on the next ingest.
- Re-ingesting the same files is safe and idempotent (`ON CREATE / ON MATCH SET`).

## PDF performance

PDF ingestion uses a four-tier strategy, tried in order until one succeeds:

| Tier | Library | Strategy | Speed (text extraction) | License |
|------|---------|----------|------------------------|---------|
| **0** | `pdf-oxide` | `to_markdown_all(detect_headings=True)` | ~0.8ms mean | MIT/Apache-2 |
| **1** | `pypdf` | PDF outline bookmarks | ~1.8s | BSD-3 |
| **2** | `pypdf` | Tagged PDF structure tree | ~1.8s | BSD-3 |
| **3** | `pdfplumber` | Font-size heuristic | ~6.6s | MIT |

**Tier 0** (`pdf-oxide`) is bundled with the `connectors` extra and runs automatically. It converts each PDF to Markdown in a single pass — picking up the PDF outline when present and falling back to font-based heading detection for unstructured documents. Tiers 1–3 are kept as fallbacks for any edge cases where pdf-oxide raises an unexpected exception.

## Re-importing data

Within a generated project, run:

```bash
make import          # import and merge into existing graph
make import-and-seed # reset graph first, then import
```

To change the paths or pattern after scaffolding, edit the `LOCAL_FILE_*` variables in your `.env` file.

## Notes on specific formats

### Markdown frontmatter

YAML/TOML frontmatter (`--- … ---` at the top of a file) is automatically stripped before parsing, so it does not appear as a section heading or body text in the graph.

### Obsidian / wiki-style links

`[[WikiLinks]]` and `[[Page|Alias]]` are treated as **plain text**, not hyperlinks. They are visible in section body text and discoverable via full-text search but do not generate `:LINKS_TO` edges. Standard Markdown `[text](url)` links are resolved normally.

### Large document collections

For vaults with hundreds or thousands of files, use `--local-file-exclude` to skip generated or binary files:

```bash
--local-file-exclude "**/.obsidian/**" \
--local-file-exclude "**/node_modules/**" \
--local-file-exclude "**/*.zip"
```
