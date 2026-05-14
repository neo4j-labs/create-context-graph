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

"""``ParsedDocument`` → :class:`NormalizedData` mapper.

This is the single place where the graph shape is built. Per-format
parsers are intentionally simple: they produce a tree-shaped
``ParsedDocument`` plus raw ``links`` lists. The mapper applies the
spec's content-construction rules (§4) and link-handling semantics (§6)
to that tree.

Key rules implemented here:

* **Shallow descriptions with child pointers** (§4 Rule 1): each node's
  ``description`` holds only its own body text plus ``uri:`` references
  to its direct children.
* **Skipped heading levels** (§4 Rule 2): the parsers already place a
  skipped-level heading as a direct child of its nearest ancestor; the
  mapper just emits ``HAS_SECTION`` along the tree it receives.
* **Per-parent duplicate disambiguation** (§4 Rule 3, GitHub/Pandoc): the
  second occurrence of a heading at the same level under the same parent
  gets ``-1`` appended, the third ``-2``, etc.
* **Link classification & target resolution** (§6.2): http(s) → external
  URL stub Document; relative path → resolved local path stub; ``#anchor``
  → same-document Section; ``path#anchor`` → cross-document Section;
  ``mailto:``/``tel:``/``javascript:``/``data:``/``ftp:`` → skipped.
* **Stub upsert** (§6.3): a ``LINKS_TO`` target Document/Section that is
  not parsed in this run gets a stub entity in ``entities`` — the
  existing MERGE-on-``name+domain`` pipeline upgrades it later when the
  target is parsed for real. Stubs carry no ``title`` / ``description`` so
  ON MATCH SET from a later real ingest enriches the node correctly.
"""

from __future__ import annotations

import posixpath
from datetime import datetime, timezone
from typing import Iterable
from urllib.parse import urlsplit, unquote

from create_context_graph.connectors import NormalizedData
from create_context_graph.connectors._local_file.parser import (
    ParsedDocument,
    ParsedSection,
    slugify,
)

# Schemes we recognise but deliberately do not turn into graph nodes.
_NON_DOCUMENT_SCHEMES: frozenset[str] = frozenset({
    "mailto", "tel", "javascript", "data", "ftp", "ftps", "sms",
})

_HTTP_SCHEMES: frozenset[str] = frozenset({"http", "https"})


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


class DocumentMapper:
    """Accumulate ``ParsedDocument``s and emit a single :class:`NormalizedData`.

    Designed to be called from a loop in :class:`LocalFileConnector.fetch`,
    one parsed document at a time. Internally tracks the URIs of documents
    we *fully* parsed during this run so links to them resolve to the
    real nodes; everything else becomes a stub (§6.3).
    """

    def __init__(self) -> None:
        # Per-entity dedup: URI → entity dict. Insertion order preserved.
        self._documents: dict[str, dict] = {}
        self._sections: dict[str, dict] = {}
        # All relationships emitted so far (insertion order preserved).
        self._relationships: list[dict] = []
        # Dedup key set: (type, source_name, target_name).
        self._rel_seen: set[tuple[str, str, str]] = set()
        # URIs of documents that WILL be fully parsed in this run.  Pre-registered
        # by LocalFileConnector.fetch() before the first add() call so that
        # _emit_links_to can suppress stub creation for targets we know will
        # receive a full _upsert_document / _upsert_section call later.
        self._parsed_doc_uris: set[str] = set()
        # Stamp once per run — the existing ingest pipeline overwrites
        # ``loadedAt`` on re-merge, which is acceptable per spec §7.
        # Stored as a native datetime so the Neo4j driver writes a ZonedDateTime
        # property, enabling temporal range filtering in the vector index.
        self._loaded_at: datetime = datetime.now(tz=timezone.utc)

    def register_known_uris(self, uris: Iterable[str]) -> None:
        """Pre-register document URIs that will be fully parsed in this run.

        Call this before the first :meth:`add` call so that link targets
        pointing to documents in the same batch are not emitted as stubs.
        """
        self._parsed_doc_uris.update(uris)

    # ---- accumulation ---------------------------------------------------

    def add(self, doc: ParsedDocument) -> None:
        """Add one parsed document to the in-progress NormalizedData."""
        self._parsed_doc_uris.add(doc.uri)

        # ---- Build Section entities (recursive, with per-parent dedup). ---
        # ``used_slugs`` is shared across siblings under the same parent so
        # GitHub/Pandoc disambiguation (``-1``, ``-2``, …) applies across
        # duplicate-titled siblings.
        top_used_slugs: dict[str, int] = {}
        children_uris = [
            self._add_section_recursive(
                section,
                parent_uri=doc.uri,
                parent_label="Document",
                used_slugs=top_used_slugs,
            )
            for section in doc.sections
        ]

        # ---- Build the Document entity. -----------------------------------
        desc = _format_description(doc.preamble, children_uris)
        self._upsert_document(
            uri=doc.uri,
            title=doc.title,
            description=desc,
            source_type=doc.source_type,
            file_extension=doc.file_extension,
            file_size=doc.file_size,
            created_at=doc.created_at,
            modified_at=doc.modified_at,
            author=doc.author,
            language=doc.language,
            page_count=doc.page_count,
        )

        # ---- LINKS_TO edges from document preamble links. ----------------
        # Preamble-level links live on the Document node itself. The spec
        # mandates `LINKS_TO` is a Section → ... edge; for preamble-level
        # links we treat the Document as the implicit source.
        for raw in doc.links:
            target = self._resolve_link(raw, source_doc_uri=doc.uri)
            if target is None:
                continue
            self._emit_links_to(
                source_uri=doc.uri,
                source_label="Document",
                target=target,
            )

    def build(self) -> NormalizedData:
        """Return the accumulated :class:`NormalizedData`."""
        entities: dict[str, list[dict]] = {}
        if self._documents:
            entities["Document"] = list(self._documents.values())
        if self._sections:
            entities["Section"] = list(self._sections.values())
        # Spec §5: do NOT populate the `documents=[]` list — the existing
        # pipeline's ``documents`` field MERGEs ``:Document`` on ``title``,
        # which would collide with our ``name``-keyed Document entities.
        return NormalizedData(
            entities=entities,
            relationships=list(self._relationships),
            documents=[],
            traces=[],
        )

    def _add_relationship(self, rel: dict) -> None:
        """Append *rel* to the relationships list, silently dropping duplicates."""
        key = (rel["type"], rel["source_name"], rel["target_name"])
        if key not in self._rel_seen:
            self._rel_seen.add(key)
            self._relationships.append(rel)


    # ---- internals ------------------------------------------------------

    def _add_section_recursive(
        self,
        section: ParsedSection,
        *,
        parent_uri: str,
        parent_label: str,
        used_slugs: dict[str, int],
    ) -> str:
        """Add a section (and its descendants) to the working data.

        Returns the URI of ``section`` so the caller can append it to the
        parent's child-pointer list.

        Emits exactly one ``HAS_SECTION`` edge per node — from ``parent_uri``
        to this section. Child edges are produced by the children's own
        recursive calls.
        """
        slug = _disambiguated_slug(section.title, used_slugs)
        if parent_label == "Section":
            # Parent is itself a section; descend the path component after
            # the document URI's '#'.
            section_uri = f"{parent_uri}/{slug}"
        else:
            section_uri = f"{parent_uri}#{slug}"

        # Recurse — children share one ``used_slugs`` dict so per-parent
        # disambiguation works.
        child_used_slugs: dict[str, int] = {}
        child_uris = [
            self._add_section_recursive(
                child,
                parent_uri=section_uri,
                parent_label="Section",
                used_slugs=child_used_slugs,
            )
            for child in section.subsections
        ]

        description = _format_description(section.body, child_uris)
        self._upsert_section(
            uri=section_uri,
            title=section.title,
            heading_level=section.level,
            description=description,
        )

        # HAS_SECTION: parent → this section.
        self._add_relationship({
            "type": "HAS_SECTION",
            "source_name": parent_uri,
            "source_label": parent_label,
            "target_name": section_uri,
            "target_label": "Section",
        })

        # LINKS_TO from this section's body.
        section_doc_uri = section_uri.split("#", 1)[0]
        for raw in section.links:
            target = self._resolve_link(raw, source_doc_uri=section_doc_uri)
            if target is None:
                continue
            self._emit_links_to(
                source_uri=section_uri,
                source_label="Section",
                target=target,
            )

        return section_uri

    def _emit_links_to(
        self,
        *,
        source_uri: str,
        source_label: str,
        target: tuple[str, str],
    ) -> None:
        target_label, target_uri = target
        # Only create a stub for targets NOT parsed in this run. Documents
        # and sections in _parsed_doc_uris will receive a full upsert from
        # their own add() call, so creating a stub would be redundant and
        # would suppress the real data if ordering causes the link to be
        # processed before the target document is added.
        if target_label == "Document":
            if target_uri not in self._documents and target_uri not in self._parsed_doc_uris:
                self._upsert_document_stub(target_uri)
        elif target_label == "Section":
            doc_uri = target_uri.split("#", 1)[0]
            if target_uri not in self._sections and doc_uri not in self._parsed_doc_uris:
                self._upsert_section_stub(target_uri)
        self._add_relationship({
            "type": "LINKS_TO",
            "source_name": source_uri,
            "source_label": source_label,
            "target_name": target_uri,
            "target_label": target_label,
        })

    # ---- entity upsert helpers -----------------------------------------

    def _upsert_document(
        self,
        *,
        uri: str,
        title: str,
        description: str,
        source_type: str,
        file_extension: str | None = None,
        file_size: int | None = None,
        created_at: datetime | None = None,
        modified_at: datetime | None = None,
        author: str | None = None,
        language: str | None = None,
        page_count: int | None = None,
    ) -> None:
        existing = self._documents.get(uri)
        if existing is None:
            self._documents[uri] = {
                "name": uri,
                "title": title,
                "description": description,
                "loadedAt": self._loaded_at,
                "sourceType": source_type,
                "fileExtension": file_extension,
                "fileSize": file_size,
                "createdAt": created_at,
                "modifiedAt": modified_at,
                "author": author,
                "language": language,
                "pageCount": page_count,
            }
            return
        # Upgrade a stub (or refresh data) — preserve loadedAt if already
        # set (stubs do not set it).
        existing["title"] = title
        existing["description"] = description
        existing["sourceType"] = source_type
        existing["fileExtension"] = file_extension
        existing["fileSize"] = file_size
        existing["createdAt"] = created_at
        existing["modifiedAt"] = modified_at
        existing["author"] = author
        existing["language"] = language
        existing["pageCount"] = page_count
        existing.setdefault("loadedAt", self._loaded_at)

    def _upsert_document_stub(self, uri: str) -> None:
        if uri in self._documents:
            return
        source_type = "URL_LINK" if _is_url(uri) else "LOCAL_FILE"
        self._documents[uri] = {
            "name": uri,
            "sourceType": source_type,
        }

    def _upsert_section(
        self,
        *,
        uri: str,
        title: str,
        heading_level: int,
        description: str,
    ) -> None:
        # Derive fileExtension from the parent document URI (everything before '#').
        doc_uri = uri.split("#", 1)[0]
        file_extension = posixpath.splitext(doc_uri)[1].lstrip(".").lower() or None

        existing = self._sections.get(uri)
        if existing is None:
            self._sections[uri] = {
                "name": uri,
                "title": title,
                "headingLevel": heading_level,
                "description": description,
                "loadedAt": self._loaded_at,
                "fileExtension": file_extension,
            }
            return
        # Upgrade stub: stubs only carry `name`. Fill in the real fields.
        existing["title"] = title
        existing["headingLevel"] = heading_level
        existing["description"] = description
        existing["fileExtension"] = file_extension
        existing.setdefault("loadedAt", self._loaded_at)

    def _upsert_section_stub(self, uri: str) -> None:
        if uri in self._sections:
            return
        self._sections[uri] = {"name": uri}
        # Ensure the parent Document stub exists and has a HAS_SECTION edge to
        # this section.  When the document is later ingested, _upsert_document()
        # upgrades the stub in-place and _add_section_recursive() emits the
        # same HAS_SECTION edge — the ingest MERGE matches it without creating
        # a duplicate.
        doc_uri = uri.split("#", 1)[0]
        self._upsert_document_stub(doc_uri)
        self._add_relationship({
            "type": "HAS_SECTION",
            "source_name": doc_uri,
            "source_label": "Document",
            "target_name": uri,
            "target_label": "Section",
        })

    # ---- link classification -------------------------------------------

    def _resolve_link(
        self, raw: str, *, source_doc_uri: str
    ) -> tuple[str, str] | None:
        """Classify a raw href and resolve it to ``(label, uri)`` or ``None``.

        Returns ``None`` when the link should be skipped (non-document
        scheme, empty, etc.).
        """
        if not raw:
            return None
        href = raw.strip()
        if not href:
            return None

        parts = urlsplit(href)
        scheme = parts.scheme.lower()

        # Anchor-only / same-document link.
        if not parts.scheme and not parts.netloc and not parts.path:
            if parts.fragment:
                return ("Section", f"{source_doc_uri}#{parts.fragment}")
            return None

        if scheme in _NON_DOCUMENT_SCHEMES:
            return None

        if scheme in _HTTP_SCHEMES:
            return _classify_http(href, parts)

        if scheme:
            # Unknown scheme — skip (avoid creating orphan nodes for
            # schemes we don't know how to navigate).
            return None

        # No scheme → local path (possibly with anchor).
        return _classify_local_path(parts, source_doc_uri)


# ---------------------------------------------------------------------------
# Module-level helpers
# ---------------------------------------------------------------------------


def _format_description(body: str, child_uris: list[str]) -> str:
    """Combine a node's own body text with ``uri:`` child pointers.

    Returns "" when both inputs are empty.
    """
    body = (body or "").strip()
    if not child_uris:
        return body
    pointers = "\n".join(f"uri:{u}" for u in child_uris)
    if not body:
        return pointers
    return f"{body}\n\n{pointers}"


def _disambiguated_slug(title: str, used_slugs: dict[str, int]) -> str:
    """Return the slug for ``title`` with GitHub/Pandoc disambiguation.

    ``used_slugs`` maps a base slug to the number of times it has been
    used under the current parent. First occurrence returns ``slug``,
    second returns ``slug-1``, third ``slug-2``, …
    """
    base = slugify(title) or "section"
    count = used_slugs.get(base, 0)
    used_slugs[base] = count + 1
    if count == 0:
        return base
    return f"{base}-{count}"


def _is_url(uri: str) -> bool:
    """Crude check: scheme is http(s) (used for stub source_type tagging)."""
    parts = urlsplit(uri)
    return parts.scheme.lower() in _HTTP_SCHEMES


def _classify_http(href: str, parts) -> tuple[str, str]:
    """Resolve an http(s) link.

    If the URL has a fragment, it points at a Section; otherwise at a
    Document. The Section URI follows the same ``{doc_uri}#{slug}`` shape
    used for local files — slugified per the GitHub/Pandoc convention.
    """
    base = parts._replace(fragment="").geturl()
    if parts.fragment:
        return ("Section", f"{base}#{slugify(parts.fragment) or parts.fragment}")
    return ("Document", base)


def _classify_local_path(parts, source_doc_uri: str) -> tuple[str, str]:
    """Resolve a scheme-less link as a local path (optionally with anchor).

    ``parts`` is a :class:`urllib.parse.SplitResult`. ``parts.path`` is
    the (URL-encoded) path component and ``parts.fragment`` is the anchor.

    Resolution uses ``posixpath.normpath`` rather than ``Path.resolve()``
    because the source URI is already a POSIX-form absolute path and we
    want deterministic textual resolution that doesn't touch the actual
    filesystem.
    """
    raw_path = unquote(parts.path)
    if raw_path.startswith("/"):
        target_path = posixpath.normpath(raw_path)
    else:
        source_dir = posixpath.dirname(source_doc_uri)
        target_path = posixpath.normpath(posixpath.join(source_dir, raw_path))

    if parts.fragment:
        slug = slugify(parts.fragment) or parts.fragment
        return ("Section", f"{target_path}#{slug}")
    return ("Document", target_path)


def map_documents(documents: Iterable[ParsedDocument]) -> NormalizedData:
    """Convenience wrapper: build a :class:`NormalizedData` from many docs."""
    mapper = DocumentMapper()
    for doc in documents:
        mapper.add(doc)
    return mapper.build()
