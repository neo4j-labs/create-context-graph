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
- **`LINKS_TO`** edges point at the most specific target: a URL with a fragment (`doc.md#heading`) resolves to a `:Section`; a bare URL resolves to a `:Document`. The parent `:Document` is always reachable from any `:Section` via `[:HAS_SECTION*]`. Targets not parsed in the same run become lightweight stub nodes — when a linked document with an anchor (`#`) is encountered, its parent `:Document` stub and a `HAS_SECTION` edge are created immediately so the graph stays traversable before that document is ingested. Stubs are upgraded in place on the next ingest.
- Re-ingesting the same files is safe and idempotent (`ON CREATE / ON MATCH SET`).

### `:Document` node properties

| Property | Type | Description |
|----------|------|-------------|
| `name` | String | MERGE key — POSIX-normalised absolute path URI |
| `title` | String | First H1 heading, document metadata title, or filename stem |
| `description` | String | Preamble text + `uri:` child pointers |
| `sourceType` | String | `LOCAL_FILE` for parsed files; `URL_LINK` for link-target stubs |
| `fileExtension` | String | Lowercase extension without dot: `md`, `pdf`, `html`, `docx`, `adoc` |
| `fileSize` | Integer | File size in bytes |
| `createdAt` | ZonedDateTime | File creation time (macOS/Windows `st_birthtime`; Linux falls back to `st_mtime`) |
| `modifiedAt` | ZonedDateTime | File last-modified time (`st_mtime`) |
| `loadedAt` | ZonedDateTime | Timestamp when this ingest run started |
| `author` | String | From document metadata where available (see format table below) |
| `language` | String | Language tag (e.g. `en`, `de`, `fr`) where available |
| `pageCount` | Integer | Number of pages (PDF only) |
| `domain` | String | Set by the ingest pipeline for cross-domain isolation |

### `:Section` node properties

| Property | Type | Description |
|----------|------|-------------|
| `name` | String | MERGE key — `{docUri}#{slug}` or `{parentUri}/{slug}` for nested sections |
| `title` | String | Heading text |
| `description` | String | Immediate body text + `uri:` child pointers |
| `headingLevel` | Integer | 1–6; the actual heading level in the source |
| `fileExtension` | String | Inherited from parent document URI |
| `loadedAt` | ZonedDateTime | Timestamp when this ingest run started |
| `domain` | String | Set by the ingest pipeline |

### Author and language availability by format

| Format | `author` | `language` |
|--------|----------|-----------|
| Markdown | YAML/TOML frontmatter `author:` / `authors:` | frontmatter `lang:` / `language:` |
| PDF | `/Author` in PDF metadata dictionary | `/Lang` in metadata (rare) |
| DOCX | Core properties `author` field | Core properties `language` field |
| HTML | `<meta name="author">` | `<html lang="">` or `<meta http-equiv="content-language">` |
| AsciiDoc | `:author:` document attribute | `:lang:` / `:language:` document attribute |

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
