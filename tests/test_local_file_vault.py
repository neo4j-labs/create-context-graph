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

"""Functional test for the local-file connector over a realistic vault.

This is the **functional** counterpart to ``tests/test_local_file_connector.py``
(the unit suite). It ingests a small but realistic Obsidian-style notebook
that lives at ``tests/fixtures/local_file_vault/`` and asserts the structural
invariants documented in :file:`tests/fixtures/local_file_vault/TESTING.md`.

The whole module is gated behind the ``--functional`` pytest flag and the
``@pytest.mark.functional`` marker (see ``tests/conftest.py``), so it does
not run during ``make test``. Invoke with::

    pytest tests/test_local_file_vault.py --functional -v
    make test-functional

Edge cases asserted here mirror §6 of the in-fixture ``TESTING.md`` guide.
"""

from __future__ import annotations

from pathlib import Path

import pytest

# All assertions assume the parser deps are installed.
pytest.importorskip("markdown_it")
pytest.importorskip("mdit_py_plugins")
pytest.importorskip("bs4")
pytest.importorskip("pypdf")
pytest.importorskip("docx")

from create_context_graph.connectors import NormalizedData  # noqa: E402
from create_context_graph.connectors.local_file_connector import LocalFileConnector  # noqa: E402


VAULT_ROOT = Path(__file__).parent / "fixtures" / "local_file_vault"
# Note: the developer-facing TESTING guide intentionally lives one level up at
# ``tests/fixtures/local_file_vault_TESTING.md`` so it cannot be ingested as
# part of the corpus. Everything inside VAULT_ROOT is fair game for the
# connector.


# Mark every test in this module as functional so --functional gates them all.
pytestmark = pytest.mark.functional


# ---------------------------------------------------------------------------
# Shared session-scoped fixture: ingest the vault exactly once.
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def vault_data() -> NormalizedData:
    """Run ``LocalFileConnector.fetch()`` against the vault once per module run."""
    assert VAULT_ROOT.is_dir(), (
        f"Fixture vault missing at {VAULT_ROOT}. The vault is committed at "
        "tests/fixtures/local_file_vault/; restore it from git if you deleted it."
    )
    conn = LocalFileConnector()
    conn.authenticate({"paths": [str(VAULT_ROOT)]})
    return conn.fetch()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _doc_uri(file_path: Path) -> str:
    """Return the canonical Document URI for a vault file."""
    return file_path.resolve().as_posix()


def _docs_by_uri(data: NormalizedData) -> dict[str, dict]:
    return {d["name"]: d for d in data.entities.get("Document", [])}


def _sections_by_uri(data: NormalizedData) -> dict[str, dict]:
    return {s["name"]: s for s in data.entities.get("Section", [])}


def _links_from(data: NormalizedData, source_uri: str) -> list[dict]:
    return [
        r for r in data.relationships
        if r["type"] == "LINKS_TO" and r["source_name"] == source_uri
    ]


# ---------------------------------------------------------------------------
# 1. Baseline structure
# ---------------------------------------------------------------------------


class TestVaultBaseline:
    """Sanity checks: the connector ingests the vault without crashing."""

    def test_returns_normalized_data(self, vault_data):
        assert isinstance(vault_data, NormalizedData)

    def test_documents_and_sections_emitted(self, vault_data):
        docs = vault_data.entities.get("Document", [])
        secs = vault_data.entities.get("Section", [])
        # Vault has 17 source files (README + 11 md + 1 html + 1 pdf + 1 docx + 1 adoc).
        # Some of them produce stub Documents for external URLs/local files, so the
        # count is >= the file count.
        assert len(docs) >= 17, f"Expected ≥17 Documents, got {len(docs)}"
        # Every file has at least one heading, so >= 17 Sections too.
        assert len(secs) >= 17, f"Expected ≥17 Sections, got {len(secs)}"

    def test_documents_list_field_empty(self, vault_data):
        # Spec §5: the connector must NOT populate `documents=[]` (that
        # collides with ingest.py's MERGE-on-title :Document nodes).
        assert vault_data.documents == []

    def test_relationships_non_empty(self, vault_data):
        assert len(vault_data.relationships) > 0
        # Every HAS_SECTION edge target should be a real Section URI.
        section_uris = {s["name"] for s in vault_data.entities["Section"]}
        has_section_targets = [
            r["target_name"] for r in vault_data.relationships if r["type"] == "HAS_SECTION"
        ]
        assert set(has_section_targets) <= section_uris, (
            "HAS_SECTION points at a name that is not in entities['Section']"
        )

    def test_posix_uris_only(self, vault_data):
        for doc in vault_data.entities["Document"]:
            assert "\\" not in doc["name"], doc["name"]


# ---------------------------------------------------------------------------
# 2. Per-file presence + parser-strategy assertions
# ---------------------------------------------------------------------------


class TestVaultFilePresence:
    """Every file in the vault should produce a Document node."""

    @pytest.mark.parametrize("relative_path", [
        "README.md",
        "companies/acme-corp.md",
        "companies/betawidgets-inc.md",
        "daily-notes/2026-05-08.md",
        "daily-notes/2026-05-09.md",
        "decisions/2026-q2-thesis-call.md",
        "meetings/2026-05-07-portfolio-review.md",
        "methodology/dcf-framework.md",
        "methodology/dcf-spec.adoc",
        "people/sarah-chen.md",
        "people/dana-liu.md",
        "people/marcus-reyes.md",
        "people/tariq-osei.md",
        "people/yuki-tanaka.md",
        "external/sector-report-q1-2026.html",
        "external/acme-10q-2026q1.pdf",
        "memos/acme-investment-memo.docx",
    ])
    def test_file_produces_document(self, vault_data, relative_path):
        uri = _doc_uri(VAULT_ROOT / relative_path)
        docs = _docs_by_uri(vault_data)
        assert uri in docs, f"{relative_path} did not produce a Document entity"
        doc = docs[uri]
        # Fully-parsed docs have title + description; stubs have neither.
        assert "title" in doc, f"{relative_path} Document missing title (parsed as stub?)"

    def test_meta_doc_not_in_corpus(self, vault_data):
        # The developer-facing TESTING guide lives outside the vault directory
        # (at tests/fixtures/local_file_vault_TESTING.md) precisely so that
        # LocalFileConnector cannot accidentally ingest it. Verify it never
        # shows up under any spelling.
        for d in vault_data.entities.get("Document", []):
            assert "local_file_vault_TESTING" not in d["name"]
            assert not d["name"].endswith("/TESTING.md")


# ---------------------------------------------------------------------------
# 3. Markdown edge cases
# ---------------------------------------------------------------------------


class TestVaultMarkdown:
    """Markdown-specific edge cases from §6 of TESTING.md."""

    def test_wikilinks_are_plain_text_not_links(self, vault_data):
        # [[Dana Liu]] / [[2026-05-09]] etc. must NOT create LINKS_TO edges.
        # We assert this by checking that no LINKS_TO target name looks like
        # a raw wikilink token.
        for rel in vault_data.relationships:
            if rel["type"] != "LINKS_TO":
                continue
            target = rel["target_name"]
            assert not target.startswith("[["), (
                f"Wikilink {target!r} was incorrectly treated as a link"
            )
            assert "[[" not in target and "]]" not in target

    def test_same_doc_anchor_link_resolves_to_section(self, vault_data):
        # acme-corp.md has [customer-concentration-note](#customer-concentration)
        # under ## Snapshot. The target Section is ## Customer concentration in
        # the same file. The mapper turns this into Section -LINKS_TO-> Section
        # with both URIs inside acme-corp.md.
        acme_uri = _doc_uri(VAULT_ROOT / "companies" / "acme-corp.md")
        snapshot_uri = f"{acme_uri}#acme-incorporated/snapshot"
        target_uri = f"{acme_uri}#customer-concentration"
        edges = _links_from(vault_data, snapshot_uri)
        targets = {(e["target_label"], e["target_name"]) for e in edges}
        assert ("Section", target_uri) in targets, (
            f"Expected Section→Section anchor link {snapshot_uri} → {target_uri}, "
            f"got edges from snapshot: {edges}"
        )

    def test_cross_doc_anchor_link_resolves(self, vault_data):
        # daily-notes/2026-05-08.md links to ../methodology/dcf-framework.md#terminal-value
        source_doc = _doc_uri(VAULT_ROOT / "daily-notes" / "2026-05-08.md")
        target_doc = _doc_uri(VAULT_ROOT / "methodology" / "dcf-framework.md")
        target_section_uri = f"{target_doc}#terminal-value"
        section_uris = {s["name"] for s in vault_data.entities["Section"]}
        # Cross-document anchor edge from any section in source_doc → target section.
        cross_doc_anchor_edges = [
            r for r in vault_data.relationships
            if r["type"] == "LINKS_TO"
            and r["source_name"].startswith(source_doc + "#")
            and r["target_name"].startswith(target_doc + "#")
        ]
        assert cross_doc_anchor_edges, (
            "Expected at least one Section -LINKS_TO-> Section edge across documents"
        )
        # And specifically the dcf-framework.md#terminal-value target appears
        # somewhere in the graph (real or stub).
        assert target_section_uri in section_uris or any(
            e["target_name"] == target_section_uri for e in cross_doc_anchor_edges
        ), (
            "Cross-doc anchor #terminal-value did not resolve into the graph"
        )

    def test_external_url_creates_url_link_stub(self, vault_data):
        # dana-liu.md has a LinkedIn URL.
        linkedin_uri = "https://www.linkedin.com/in/danaliu-example"
        docs = _docs_by_uri(vault_data)
        assert linkedin_uri in docs, "LinkedIn URL did not create a Document stub"
        assert docs[linkedin_uri]["sourceType"] == "URL_LINK"
        # No HAS_SECTION children for an unfetched URL stub.
        url_has_section = [
            r for r in vault_data.relationships
            if r["type"] == "HAS_SECTION" and r["source_name"] == linkedin_uri
        ]
        assert url_has_section == [], (
            "URL_LINK stub should not own any HAS_SECTION edges"
        )


# ---------------------------------------------------------------------------
# 4. HTML edge cases
# ---------------------------------------------------------------------------


class TestVaultHTML:
    def test_html_produces_sections(self, vault_data):
        html_uri = _doc_uri(VAULT_ROOT / "external" / "sector-report-q1-2026.html")
        sections_in_html = [
            s for s in vault_data.entities["Section"]
            if s["name"].startswith(html_uri + "#")
        ]
        # The report has multiple H2/H3 headings.
        assert len(sections_in_html) >= 3, (
            f"Expected ≥3 sections in HTML report, got {len(sections_in_html)}"
        )

    def test_mailto_link_skipped(self, vault_data):
        # sector-report-q1-2026.html has mailto:research@pinnacle-research.example
        for rel in vault_data.relationships:
            if rel["type"] != "LINKS_TO":
                continue
            assert not rel["target_name"].startswith("mailto:"), (
                f"mailto: target should be skipped, found edge to {rel['target_name']}"
            )
        # And no stub Document was created either.
        docs = _docs_by_uri(vault_data)
        for name in docs:
            assert not name.startswith("mailto:"), (
                f"mailto: stub Document was created: {name}"
            )


# ---------------------------------------------------------------------------
# 5. PDF edge cases (outline-first parsing)
# ---------------------------------------------------------------------------


class TestVaultPDF:
    def test_pdf_outline_produces_multiple_sections(self, vault_data):
        # acme-10q-2026q1.pdf has a 3-level outline. The outline strategy must
        # hit (not the font-size fallback), producing multiple Section nodes.
        pdf_uri = _doc_uri(VAULT_ROOT / "external" / "acme-10q-2026q1.pdf")
        sections_in_pdf = [
            s for s in vault_data.entities["Section"]
            if s["name"].startswith(pdf_uri + "#")
        ]
        assert len(sections_in_pdf) >= 3, (
            f"Expected ≥3 sections from the PDF outline, got {len(sections_in_pdf)}. "
            "If this fails, the outline strategy may have fallen through to the "
            "font-heuristic tier."
        )
        # At least one Section should have level 2 or deeper — proves the
        # outline's nested structure was preserved.
        assert any(s["headingLevel"] >= 2 for s in sections_in_pdf), (
            "PDF outline parsing collapsed every section to level 1"
        )


# ---------------------------------------------------------------------------
# 6. DOCX edge cases (style-based heading detection)
# ---------------------------------------------------------------------------


class TestVaultDOCX:
    def test_docx_produces_multiple_sections(self, vault_data):
        docx_uri = _doc_uri(VAULT_ROOT / "memos" / "acme-investment-memo.docx")
        sections_in_docx = [
            s for s in vault_data.entities["Section"]
            if s["name"].startswith(docx_uri + "#")
        ]
        assert len(sections_in_docx) >= 2, (
            f"Expected ≥2 sections in the DOCX memo, got {len(sections_in_docx)}. "
            "If this fails, the python-docx style-name detection may be broken."
        )


# ---------------------------------------------------------------------------
# 7. AsciiDoc edge cases (literal-block heading suppression)
# ---------------------------------------------------------------------------


class TestVaultAsciiDoc:
    def test_adoc_produces_sections(self, vault_data):
        adoc_uri = _doc_uri(VAULT_ROOT / "methodology" / "dcf-spec.adoc")
        sections_in_adoc = [
            s for s in vault_data.entities["Section"]
            if s["name"].startswith(adoc_uri + "#")
        ]
        assert len(sections_in_adoc) >= 3

    def test_adoc_literal_blocks_do_not_emit_phantom_headings(self, vault_data):
        # dcf-spec.adoc has `[source]----` blocks containing lines like
        # `= Gross Profit`, `= EBIT`, `= Free Cash Flow to Firm (FCFF)`.
        # Those must NOT become Sections.
        adoc_uri = _doc_uri(VAULT_ROOT / "methodology" / "dcf-spec.adoc")
        section_titles = [
            s.get("title", "")
            for s in vault_data.entities["Section"]
            if s["name"].startswith(adoc_uri + "#")
        ]
        forbidden = {"Gross Profit", "EBIT", "Free Cash Flow to Firm (FCFF)"}
        leaked = forbidden.intersection(section_titles)
        assert not leaked, (
            f"AsciiDoc literal-block content leaked as Section titles: {leaked}"
        )


# ---------------------------------------------------------------------------
# 8. Cross-cutting invariants
# ---------------------------------------------------------------------------


class TestVaultInvariants:
    def test_idempotent(self):
        """Re-ingesting the vault yields the same entities + relationships
        modulo the ``loadedAt`` timestamp.
        """
        def run_once() -> NormalizedData:
            conn = LocalFileConnector()
            conn.authenticate({"paths": [str(VAULT_ROOT)]})
            return conn.fetch()

        a = run_once()
        b = run_once()

        for data in (a, b):
            for entity_list in data.entities.values():
                for entity in entity_list:
                    entity.pop("loadedAt", None)
        assert a.entities == b.entities

        # Relationship lists may differ in order across runs (we don't make
        # ordering guarantees in the spec); compare membership.
        assert sorted(map(repr, a.relationships)) == sorted(map(repr, b.relationships))

    def test_deterministic_file_order(self):
        """File discovery is sorted lexicographically by absolute POSIX URI."""
        conn = LocalFileConnector()
        conn.authenticate({"paths": [str(VAULT_ROOT)]})
        files_a = [p.resolve().as_posix() for p in conn._discover_files()]
        files_b = [p.resolve().as_posix() for p in conn._discover_files()]
        assert files_a == files_b
        assert files_a == sorted(files_a)
