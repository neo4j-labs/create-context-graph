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

"""PDF parser for the Local File document connector.

Four-tier deterministic strategy, tried in order:

0. **pdf-oxide** (``pdf_oxide``) — bundled with the ``connectors`` extra
   (MIT/Apache-2.0). Uses ``PdfDocument.to_markdown_all(detect_headings=True)``
   which handles both outline-bearing and unstructured PDFs. Falls through to
   tiers 1–3 only on an unexpected parsing error.
1. **PDF outline** (``PdfReader.outline``) — most common heading source for
   real-world long-form documents (LaTeX/Word/Acrobat emit them by
   default). Bookmark depth = heading level; body text is the page range
   between adjacent bookmarks.
2. **Structure tree** (``trailer['/Root']['/StructTreeRoot']``) — tagged
   PDFs (~3-10%). Walk ``/StructElem`` nodes, mapping ``/H1``..``/H6`` to
   heading levels.
3. **Font-size heuristics** (``pdfplumber.page.chars``) — fallback for
   untagged PDFs with no bookmarks. Distinct font sizes sorted descending
   and assigned H1..H6.

The chosen strategy is logged at INFO; pure-Python and fully
deterministic given the same input file.
"""

from __future__ import annotations

import logging
from pathlib import Path

from create_context_graph.connectors._local_file.parser import (
    ParsedDocument,
    ParsedSection,
    posix_uri,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def parse(path: str | Path) -> ParsedDocument:
    """Parse a PDF file into a :class:`ParsedDocument`.

    Tries tier 0 (pdf-oxide) first, then falls through to pypdf/pdfplumber.

    Raises:
        ImportError: if ``pypdf`` is not installed (required for tiers 1–3).
    """
    p = Path(path)
    uri = posix_uri(p)

    # Tier 0: pdf-oxide — bundled with connectors extra, MIT/Apache-2.
    doc = _try_pdf_oxide(p, uri)
    if doc is not None:
        return doc

    # Tiers 1–3: pypdf + pdfplumber (bundled, BSD/MIT).
    try:
        from pypdf import PdfReader
    except ImportError as exc:  # pragma: no cover - exercised at runtime only.
        raise ImportError(
            "PDF parsing requires 'pypdf'. Install with: pip install 'pypdf>=6.11'"
        ) from exc

    reader = PdfReader(str(p))
    title = _document_title(reader, p)
    author, language = _pdf_author_language(reader)
    page_count = len(reader.pages)
    doc_links = _collect_uri_links(reader)

    # Tier 1: outline.
    sections = _try_outline(reader)
    if sections is not None:
        logger.info("PDF parser: tier 1 (pypdf/outline) for %s", p)
        return ParsedDocument(
            uri=uri, title=title, sections=sections, links=doc_links,
            source_type="LOCAL_FILE",
            author=author, language=language, page_count=page_count,
        )

    # Tier 2: structure tree.
    sections = _try_structure_tree(reader)
    if sections is not None:
        logger.info("PDF parser: tier 2 (pypdf/StructTree) for %s", p)
        return ParsedDocument(
            uri=uri, title=title, sections=sections, links=doc_links,
            source_type="LOCAL_FILE",
            author=author, language=language, page_count=page_count,
        )

    # Tier 3: font-size heuristics.
    logger.info("PDF parser: tier 3 (pdfplumber/font) for %s", p)
    sections, preamble = _try_font_heuristic(p)
    if not sections:
        logger.warning(
            "PDF parser: no heading structure detected in '%s' (outline absent, "
            "no structure tree, font heuristic found no larger-font spans). "
            "Document will be ingested as flat text with no sections.",
            p,
        )
    return ParsedDocument(
        uri=uri, title=title, preamble=preamble, sections=sections,
        links=doc_links, source_type="LOCAL_FILE",
        author=author, language=language, page_count=page_count,
    )


# ---------------------------------------------------------------------------
# Title extraction
# ---------------------------------------------------------------------------


def _document_title(reader, path: Path) -> str:
    """Return the PDF metadata ``/Title`` if set, else the filename stem."""
    try:
        meta = reader.metadata
        if meta is not None:
            title = getattr(meta, "title", None) or meta.get("/Title") if hasattr(meta, "get") else None
            if title:
                title = str(title).strip()
                if title:
                    return title
    except Exception:  # pragma: no cover - metadata is best-effort.
        pass
    return path.stem


def _pdf_author_language(reader) -> tuple[str | None, str | None]:
    """Extract author and language from a pypdf PdfReader's metadata dict."""
    try:
        meta = reader.metadata
        if meta is None:
            return None, None
        raw_author = getattr(meta, "author", None)
        if raw_author is None and hasattr(meta, "get"):
            raw_author = meta.get("/Author")
        author = str(raw_author).strip() or None if raw_author else None

        raw_lang = None
        if hasattr(meta, "get"):
            raw_lang = meta.get("/Lang") or meta.get("/Language")
        language = str(raw_lang).strip() or None if raw_lang else None
        return author, language
    except Exception:  # pragma: no cover - metadata is best-effort.
        return None, None


# ---------------------------------------------------------------------------
# Tier 0: pdf-oxide (bundled with connectors extra)
# ---------------------------------------------------------------------------


def _try_pdf_oxide(p: Path, uri: str) -> ParsedDocument | None:
    """Return a ParsedDocument using pdf-oxide, or None if not installed.

    pdf-oxide (MIT/Apache-2.0) is bundled with the ``connectors`` extra.
    It converts the PDF to Markdown (with ``detect_headings=True``) which
    handles both outline-bearing and unstructured PDFs in a single pass.
    Falls through to tiers 1–3 only on an unexpected exception.
    """
    try:
        from pdf_oxide import PdfDocument
    except ImportError:
        return None

    try:
        doc = PdfDocument(str(p))
        md = doc.to_markdown_all(detect_headings=True)
    except Exception as exc:  # pragma: no cover - guard against malformed PDFs
        logger.warning("PDF parser: pdf-oxide failed for '%s' (%s), falling through.", p, exc)
        return None

    title = _title_from_markdown(md, p.stem)
    sections, preamble = _parse_markdown_sections(md)
    links = _pdf_oxide_uri_links(md)

    if not sections:
        logger.warning(
            "PDF parser: pdf-oxide found no heading structure in '%s'. "
            "Document will be ingested as flat text with no sections.", p,
        )
    else:
        logger.info("PDF parser: tier 0 (pdf-oxide) for %s", p)

    page_count = doc.page_count()
    # Enrich with author/language from pypdf metadata — best effort.
    author = language = None
    try:
        from pypdf import PdfReader
        reader = PdfReader(str(p))
        author, language = _pdf_author_language(reader)
    except Exception:  # pragma: no cover - metadata is best-effort.
        pass
    return ParsedDocument(
        uri=uri, title=title, preamble=preamble, sections=sections,
        links=links, source_type="LOCAL_FILE",
        author=author, language=language, page_count=page_count,
    )


def _title_from_markdown(md: str, fallback: str) -> str:
    """Return the first H1 heading as document title, or the fallback stem."""
    for line in md.splitlines():
        line = line.strip()
        if not line:
            continue
        if line.startswith("# "):
            return line[2:].strip()
        break
    return fallback


def _parse_markdown_sections(md: str) -> tuple[list[ParsedSection], str]:
    """Parse a Markdown string into a ParsedSection hierarchy.

    Lines beginning with ``#``–``######`` become section headings.
    Everything else is body text accumulated into the current section (or
    the preamble if no heading has been seen yet).
    """
    import re
    heading_re = re.compile(r"^(#{1,6})\s+(.*)")

    root: list[ParsedSection] = []
    stack: list[ParsedSection] = []
    preamble_lines: list[str] = []
    current: ParsedSection | None = None
    current_body: list[str] = []

    def flush() -> None:
        if current is not None:
            current.body = "\n".join(current_body).strip()

    for line in md.splitlines():
        m = heading_re.match(line)
        if m:
            flush()
            current_body = []
            level = len(m.group(1))
            title = m.group(2).strip()
            section = ParsedSection(title=title, level=level, body="", subsections=[], links=[])
            while stack and stack[-1].level >= level:
                stack.pop()
            if stack:
                stack[-1].subsections.append(section)
            else:
                root.append(section)
            stack.append(section)
            current = section
        else:
            (preamble_lines if current is None else current_body).append(line)
    flush()
    return root, "\n".join(preamble_lines).strip()


def _pdf_oxide_uri_links(md: str) -> list[str]:
    """Extract HTTP/S links from a Markdown string (inline and bare)."""
    import re
    seen: set[str] = set()
    links: list[str] = []
    for url in re.findall(r"\[(?:[^\]]*)\]\((https?://[^\)]+)\)", md):
        if url not in seen:
            seen.add(url)
            links.append(url)
    for url in re.findall(r"(?<!\()(https?://\S+)", md):
        url = url.rstrip(".,;:!?)\"'")
        if url and url not in seen:
            seen.add(url)
            links.append(url)
    return links


# ---------------------------------------------------------------------------
# Tier 1: outline
# ---------------------------------------------------------------------------


def _try_outline(reader) -> list[ParsedSection] | None:
    """Return a section tree built from the PDF outline, or ``None``."""
    try:
        outline = reader.outline
    except Exception:  # pragma: no cover - some readers raise on missing.
        return None
    if not outline:
        return None

    # Flatten the nested outline into (level, destination, title) tuples.
    flat: list[tuple[int, object, str]] = []
    _flatten_outline(outline, depth=1, out=flat)
    if not flat:
        return None

    # Resolve page index for each destination.
    page_count = len(reader.pages)
    starts: list[int] = []
    for _level, dest, _title in flat:
        try:
            page_idx = reader.get_destination_page_number(dest)
        except Exception:  # pragma: no cover - malformed destinations.
            page_idx = 0
        if page_idx is None or page_idx < 0:
            page_idx = 0
        if page_idx >= page_count:
            page_idx = page_count - 1
        starts.append(page_idx)

    # Extract body text for each bookmark by slicing page ranges.
    bodies: list[str] = []
    for idx, (_level, _dest, _title) in enumerate(flat):
        start = starts[idx]
        end = starts[idx + 1] + 1 if idx + 1 < len(flat) else page_count
        if end <= start:
            end = start + 1
        bodies.append(_extract_page_range_text(reader, start, end))

    # Build the tree by walking flat with a level stack.
    root: list[ParsedSection] = []
    stack: list[ParsedSection] = []
    for (level, _dest, title), body in zip(flat, bodies):
        section = ParsedSection(
            title=title.strip(),
            level=level,
            body=body.strip(),
            subsections=[],
            links=[],
        )
        while stack and stack[-1].level >= level:
            stack.pop()
        if stack:
            stack[-1].subsections.append(section)
        else:
            root.append(section)
        stack.append(section)
    return root


def _flatten_outline(outline, *, depth: int, out: list) -> None:
    """Walk pypdf's nested-list outline structure into a flat list."""
    for item in outline:
        if isinstance(item, list):
            _flatten_outline(item, depth=depth + 1, out=out)
        else:
            title = getattr(item, "title", "") or ""
            out.append((depth, item, str(title)))


def _extract_page_range_text(reader, start: int, end: int) -> str:
    """Return concatenated text from pages ``[start, end)``."""
    parts: list[str] = []
    for i in range(start, end):
        try:
            text = reader.pages[i].extract_text() or ""
        except Exception:  # pragma: no cover - extraction can fail per page.
            text = ""
        if text:
            parts.append(text)
    return "\n".join(parts)


# ---------------------------------------------------------------------------
# Tier 2: structure tree
# ---------------------------------------------------------------------------


def _try_structure_tree(reader) -> list[ParsedSection] | None:
    """Return a section tree built from a tagged PDF structure tree, or
    ``None`` if no ``/StructTreeRoot`` is present.

    This is a best-effort walker: it picks up ``/H1``–``/H6`` elements as
    headings and collects sibling ``/P`` text as body. Real-world tagged
    PDFs are rare enough that we keep this conservative.
    """
    try:
        trailer = reader.trailer
        root = trailer.get("/Root")
        if root is None:
            return None
        struct_root = root.get("/StructTreeRoot")
        if struct_root is None:
            return None
    except Exception:  # pragma: no cover - missing trailer/root.
        return None

    headings: list[tuple[int, str, str]] = []  # (level, title, body)
    try:
        _walk_struct(struct_root, headings)
    except Exception:  # pragma: no cover - malformed tree.
        return None
    if not headings:
        return None

    root_sections: list[ParsedSection] = []
    stack: list[ParsedSection] = []
    for level, title, body in headings:
        section = ParsedSection(
            title=title.strip(),
            level=level,
            body=body.strip(),
            subsections=[],
            links=[],
        )
        while stack and stack[-1].level >= level:
            stack.pop()
        if stack:
            stack[-1].subsections.append(section)
        else:
            root_sections.append(section)
        stack.append(section)
    return root_sections


def _walk_struct(node, headings: list) -> None:
    """Recursively walk a structure tree, emitting heading entries."""
    kids = _get(node, "/K")
    if kids is None:
        return
    if not isinstance(kids, list):
        kids = [kids]

    current_heading: list | None = None
    body_buf: list[str] = []
    for kid in kids:
        if not _is_dict_like(kid):
            continue
        kid_type = _get(kid, "/S")
        kid_type = str(kid_type) if kid_type is not None else ""
        if kid_type.startswith("/H") and len(kid_type) >= 3 and kid_type[2].isdigit():
            if current_heading is not None:
                headings.append((current_heading[0], current_heading[1], "\n".join(body_buf)))
            level = int(kid_type[2])
            text = _struct_node_text(kid)
            current_heading = [level, text]
            body_buf = []
        elif kid_type == "/P":
            body_buf.append(_struct_node_text(kid))
        else:
            _walk_struct(kid, headings)
    if current_heading is not None:
        headings.append((current_heading[0], current_heading[1], "\n".join(body_buf)))


def _struct_node_text(node) -> str:
    """Best-effort text extraction from a /StructElem subtree."""
    actual = _get(node, "/ActualText")
    if actual:
        return str(actual)
    kids = _get(node, "/K")
    if kids is None:
        return ""
    if not isinstance(kids, list):
        kids = [kids]
    parts: list[str] = []
    for kid in kids:
        if isinstance(kid, str):
            parts.append(kid)
        elif _is_dict_like(kid):
            parts.append(_struct_node_text(kid))
    return " ".join(p for p in parts if p)


def _get(obj, key):
    """Resolve a key on a pypdf indirect/direct object."""
    try:
        value = obj.get(key)
    except AttributeError:
        return None
    if value is None:
        return None
    get_object = getattr(value, "get_object", None)
    if callable(get_object):
        try:
            value = get_object()
        except Exception:  # pragma: no cover - malformed indirect refs.
            return value
    return value


def _is_dict_like(obj) -> bool:
    return hasattr(obj, "get") and not isinstance(obj, str)


# ---------------------------------------------------------------------------
# Tier 3: font-size heuristics
# ---------------------------------------------------------------------------


def _try_font_heuristic(path: Path) -> tuple[list[ParsedSection], str]:
    """Return (sections, preamble) from a font-size based heading guess.

    Algorithm:
      1. Read every page's character stream via ``pdfplumber.page.chars``.
      2. Group chars into single-line "spans" of identical ``size``.
      3. The dominant body size is whichever size accumulates the most
         total characters across all spans. Any span with a strictly
         larger size is a heading candidate (no minimum char-count filter
         is applied — any single-character span at a larger size qualifies).
      4. Assign distinct heading sizes to H1..H6 in descending order.

    Sections are built in document order. If pdfplumber isn't available
    or the PDF yields no character data, returns ([], "").
    """
    try:
        import pdfplumber
    except ImportError:  # pragma: no cover - exercised at runtime only.
        return [], ""

    spans: list[dict] = []  # each: {text, size, page}
    with pdfplumber.open(str(path)) as pdf:
        for page_idx, page in enumerate(pdf.pages):
            chars = page.chars or []
            if not chars:
                continue
            line: list[dict] = []
            current_top: float | None = None
            current_size: float | None = None
            for ch in chars:
                size = round(float(ch.get("size", 0)), 2)
                top = round(float(ch.get("top", 0)), 1)
                if current_top is None:
                    current_top = top
                    current_size = size
                # New line when the top moves significantly or size changes.
                if (
                    abs(top - (current_top or 0)) > 2
                    or (current_size is not None and abs(size - current_size) > 0.5)
                ):
                    if line:
                        spans.append(_flush_span(line, page_idx))
                    line = []
                    current_top = top
                    current_size = size
                line.append(ch)
            if line:
                spans.append(_flush_span(line, page_idx))

    if not spans:
        return [], ""

    # Determine the dominant body size.
    size_counts: dict[float, int] = {}
    for span in spans:
        size_counts[span["size"]] = size_counts.get(span["size"], 0) + len(span["text"])

    body_size = max(size_counts.items(), key=lambda kv: kv[1])[0]
    heading_sizes = sorted(
        {sz for sz, n in size_counts.items() if sz > body_size and n >= 1},
        reverse=True,
    )
    if not heading_sizes:
        # No headings detected — return full text as preamble.
        return [], "\n".join(s["text"] for s in spans).strip()
    size_to_level = {sz: min(i + 1, 6) for i, sz in enumerate(heading_sizes)}

    # Walk spans, splitting at heading-sized lines.
    sections: list[ParsedSection] = []
    stack: list[ParsedSection] = []
    preamble_lines: list[str] = []
    current: ParsedSection | None = None
    current_body: list[str] = []

    def flush_body():
        if current is not None:
            current.body = "\n".join(current_body).strip()

    for span in spans:
        if span["size"] in size_to_level:
            # Heading span — open a new section.
            flush_body()
            level = size_to_level[span["size"]]
            section = ParsedSection(
                title=span["text"].strip(),
                level=level,
                body="",
                subsections=[],
                links=[],
            )
            while stack and stack[-1].level >= level:
                stack.pop()
            if stack:
                stack[-1].subsections.append(section)
            else:
                sections.append(section)
            stack.append(section)
            current = section
            current_body = []
        else:
            if current is None:
                preamble_lines.append(span["text"])
            else:
                current_body.append(span["text"])
    flush_body()
    return sections, "\n".join(preamble_lines).strip()


def _flush_span(line: list[dict], page_idx: int) -> dict:
    text = "".join(ch.get("text", "") for ch in line)
    size = round(float(line[0].get("size", 0)), 2)
    return {"text": text, "size": size, "page": page_idx}


# ---------------------------------------------------------------------------
# Hyperlink annotation extraction
# ---------------------------------------------------------------------------


def _collect_uri_links(reader) -> list[str]:
    """Return every external URI link annotation found in the PDF.

    Internal page-destination links are ignored for MVP (spec §6.1).
    """
    seen: set[str] = set()
    links: list[str] = []
    for page in reader.pages:
        try:
            annots = page.get("/Annots")
        except Exception:  # pragma: no cover - some pages have no annots.
            annots = None
        if not annots:
            continue
        for annot_ref in annots:
            annot = _resolve(annot_ref)
            if not _is_dict_like(annot):
                continue
            action = _get(annot, "/A")
            if not _is_dict_like(action):
                continue
            uri = _get(action, "/URI")
            if uri is None:
                continue
            uri_str = str(uri)
            if uri_str and uri_str not in seen:
                seen.add(uri_str)
                links.append(uri_str)
    return links


def _resolve(obj):
    get_object = getattr(obj, "get_object", None)
    if callable(get_object):
        try:
            return get_object()
        except Exception:  # pragma: no cover
            return obj
    return obj
