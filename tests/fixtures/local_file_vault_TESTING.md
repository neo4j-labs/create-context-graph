# Local-File Connector — Functional Test Vault

The sibling directory `local_file_vault/` is a **realistic document corpus**
used by the optional functional test in `tests/test_local_file_vault.py`. It's
a fictional financial analyst's Obsidian-style notebook for ACME Incorporated's
Corporate Strategy & FP&A team and contains one of each supported format so
every parser path is exercised.

This meta-doc lives **outside** the vault directory on purpose: putting it
inside `local_file_vault/` would mean `LocalFileConnector` ingests it as part
of the corpus on every run, polluting the graph. By sitting at
`tests/fixtures/local_file_vault_TESTING.md` (sibling to the vault, not inside
it) it stays discoverable to developers while never landing in
`LocalFileConnector.fetch()` output.

The vault's own `README.md` is the in-fiction "vault index" — it's part of the
fixture content itself and its body becomes a real `:Document` node in the
graph.

---

## Vault contents

```
tests/fixtures/
├── local_file_vault_TESTING.md              # this file (meta-doc, OUTSIDE the vault)
└── local_file_vault/                        # ← the corpus (everything inside is ingested)
    ├── README.md                            # vault index (part of the corpus)
    ├── daily-notes/                         # 2 daily notes (.md)
    ├── companies/                           # ACME + BetaWidgets analyses (.md)
    ├── people/                              # 5 atomic person notes (.md)
    ├── meetings/                            # 1 meeting capture (.md)
    ├── decisions/                           # 1 multi-step decision trace (.md)
    ├── methodology/
    │   ├── dcf-framework.md                 # methodology in markdown
    │   └── dcf-spec.adoc                    # SAME methodology in AsciiDoc
    ├── external/
    │   ├── sector-report-q1-2026.html       # third-party report with anchors
    │   └── acme-10q-2026q1.pdf              # 4-page PDF *with outline/bookmarks*
    └── memos/
        └── acme-investment-memo.docx        # Word doc with Heading 1/2/3 styles
```

All cross-document references use real Markdown links
(`[text](../path/to/file.md)` and `[text](file.md#anchor)`) so the connector's
`LINKS_TO` edges have something to bite on. Inline `[[wikilinks]]` are present
(real Obsidian notes have them) but they are plain text — `markdown-it-py`
doesn't parse them, which is the expected behaviour.

External URLs (`https://...`) appear throughout to exercise `URL_LINK` stub
`Document` creation.

---

## Running the test

The functional test is **opt-in** — it does not run during `make test`. It is
gated behind a `--functional` pytest flag (registered in `tests/conftest.py`,
mirroring the existing `--integration` and `--slow` flags).

```bash
# Activate the venv (one-time)
source .venv/bin/activate

# Run only the vault-based functional test
pytest tests/test_local_file_vault.py --functional -v

# Or via the Makefile shortcut
make test-functional
```

Without `--functional`, the test is skipped with a clear message — including
when CI runs `make test`, so the fixture's presence does not slow the fast
suite.

### Prerequisites

The functional test exercises every parser, so it requires the full
`connectors` optional-dep group:

```bash
uv pip install -e ".[connectors,dev]"
```

That installs `markdown-it-py`, `mdit-py-plugins`, `pypdf`, `pdfplumber`,
`beautifulsoup4`, `lxml`, and `python-docx`.

---

## What the test asserts

The test ingests the vault end-to-end through `LocalFileConnector.fetch()` and
asserts the structural invariants from the connector spec
(`scratch/doc-connector-requirements-v2.md`):

| # | Edge case | Where it lives in the vault | Assertion |
|---|---|---|---|
| 1 | **Parses without errors** | every file | `fetch()` returns a `NormalizedData` with no exceptions |
| 2 | **Document + Section nodes created** | every file | both lists are non-empty |
| 3 | **POSIX URIs** | every `Document.name` | no backslashes; absolute paths |
| 4 | **Idempotency** | re-ingest the vault | second run produces the same entities/relationships modulo `loadedAt` |
| 5 | **`[[wikilinks]]` are plain text** | `README.md`, daily notes | no `LINKS_TO` edges pointing at wiki-style targets |
| 6 | **Same-doc anchor links** | `acme-corp.md` → `#customer-concentration` | `Section -LINKS_TO-> Section` within the same Document URI |
| 7 | **Cross-doc anchor links** | `daily-notes/2026-05-08.md` → `../external/sector-report-q1-2026.html#…` | `Section -LINKS_TO-> Section` resolved across documents |
| 8 | **External URL stubs** | LinkedIn URL in `dana-liu.md`, example.com URLs in daily notes | `:Document` stub with `sourceType="URL_LINK"` and no `HAS_SECTION` children |
| 9 | **`mailto:` skipped** | `sector-report-q1-2026.html` footer | NO node, NO relationship for the mailto target |
| 10 | **PDF outline-first parsing** | `external/acme-10q-2026q1.pdf` (has bookmarks) | parses; multiple sections produced (i.e., outline strategy hit, not the fallback) |
| 11 | **DOCX `Heading N` style detection** | `memos/acme-investment-memo.docx` | sections with the expected hierarchy emerge |
| 12 | **HTML hierarchical anchors** | `external/sector-report-q1-2026.html` | nested H1/H2/H3 sections; sibling-walk respected |
| 13 | **AsciiDoc literal-block heading suppression** | `methodology/dcf-spec.adoc` (`[source]----…----` blocks) | `=` lines *inside* `----` blocks do NOT produce extra Section nodes |
| 14 | **Deterministic file ordering** | run discovery twice | identical Document order both times (POSIX-sorted) |
| 15 | **Duplicate-heading per-parent scoping** | several files share top-level headings like `## Snapshot` | each is keyed `#snapshot` within its own document (no spurious `-1` suffix across files) |

If a future change to a parser or to the mapper breaks any of these, the test
catches it immediately on `make test-functional`.

---

## Regenerating the binary fixtures

`acme-10q-2026q1.pdf` and `acme-investment-memo.docx` are committed binaries.
If you ever need to recreate them (e.g. to change their content), use the
generator that lives next to the original development scratchpad:

```bash
# Requires reportlab + python-docx in the venv
python scratch/test-vault/_generate_binaries.py
```

…then copy the regenerated binaries back into
`tests/fixtures/local_file_vault/external/` and
`tests/fixtures/local_file_vault/memos/`. The generator is not committed
under `tests/` because it is a developer tool, not a fixture.

---

## Why this is a "functional" test rather than a unit test

`tests/test_local_file_connector.py` is the **unit/structural** suite — 95
tests covering one behaviour each with hand-crafted minimal inputs.

`tests/test_local_file_vault.py` is the **functional** test — one big test
that exercises the whole pipeline on a realistic, diverse corpus. It catches
integration regressions that no individual unit test would (e.g., a parser
change that's locally correct but produces orphan sections under cross-doc
links, or a slug-algorithm tweak that creates duplicate-key Document nodes
when ingesting the full vault).

Both are valuable; they catch different classes of bug. The unit suite runs
on every PR; the functional test is opt-in, slower, and surfaces "does it
actually work on real documents?" answers when you ask for them.
