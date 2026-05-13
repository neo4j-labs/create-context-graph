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

"""HTML parser for the Local File document connector.

Uses ``beautifulsoup4`` with the ``lxml`` backend. We find every
``<h1>``..``<h6>`` element in document order, walk forward through its
siblings collecting text until we hit the next same-or-shallower heading,
and assemble a ``ParsedDocument`` tree that mirrors the heading
hierarchy. Hyperlinks come from ``<a href>`` attributes within each
section's text range; ``<img>`` tags are NOT treated as links.
"""

from __future__ import annotations

import re
from pathlib import Path

from create_context_graph.connectors._local_file.parser import (
    ParsedDocument,
    ParsedSection,
    posix_uri,
    read_text_file,
)

_HEADING_TAGS = ("h1", "h2", "h3", "h4", "h5", "h6")


def parse(path: str | Path) -> ParsedDocument:
    """Parse an HTML file into a :class:`ParsedDocument`.

    Raises:
        ImportError: if ``beautifulsoup4`` is not installed.
    """
    try:
        from bs4 import BeautifulSoup
    except ImportError as exc:  # pragma: no cover - exercised at runtime only.
        raise ImportError(
            "HTML parsing requires 'beautifulsoup4' (with the lxml backend). "
            "Install with: pip install 'beautifulsoup4>=4.14' 'lxml>=5.0'"
        ) from exc

    p = Path(path)
    html = read_text_file(p)
    soup = _make_soup(BeautifulSoup, html)

    title = _document_title(soup, p)
    headings = soup.find_all(_HEADING_TAGS)

    author, language = _html_author_language(soup)

    if not headings:
        # No headings: whole body becomes the preamble.
        preamble = soup.get_text("\n", strip=True)
        links = _collect_links(soup)
        return ParsedDocument(
            uri=posix_uri(p),
            title=title,
            preamble=preamble,
            sections=[],
            links=links,
            source_type="LOCAL_FILE",
            author=author,
            language=language,
        )

    preamble_text, preamble_links = _collect_preamble(soup, headings[0])
    sections = _build_section_tree(soup, headings)
    return ParsedDocument(
        uri=posix_uri(p),
        title=title,
        preamble=preamble_text,
        sections=sections,
        links=preamble_links,
        source_type="LOCAL_FILE",
        author=author,
        language=language,
    )


# ---------------------------------------------------------------------------
# Internals
# ---------------------------------------------------------------------------


def _make_soup(BeautifulSoup, html: str):
    """Return a BeautifulSoup tree, preferring lxml and falling back to html.parser."""
    try:
        return BeautifulSoup(html, "lxml")
    except Exception:  # pragma: no cover - fallback for environments lacking lxml.
        return BeautifulSoup(html, "html.parser")


def _html_author_language(soup) -> tuple[str | None, str | None]:
    """Extract author and language from HTML meta tags and the html[lang] attribute."""
    author = language = None
    # Language: <html lang="..."> takes priority over <meta> tags.
    html_tag = soup.find("html")
    if html_tag and html_tag.get("lang"):
        language = str(html_tag["lang"]).strip() or None
    # Author: <meta name="author" content="...">
    meta = soup.find("meta", attrs={"name": re.compile(r"^author$", re.I)})
    if meta:
        author = str(meta.get("content", "")).strip() or None
    # Fallback language from <meta name="language"> or http-equiv="content-language".
    if not language:
        meta = soup.find("meta", attrs={"name": re.compile(r"^(language|content-language)$", re.I)})
        if meta:
            language = str(meta.get("content", "")).strip() or None
    if not language:
        meta = soup.find("meta", attrs={"http-equiv": re.compile(r"^content-language$", re.I)})
        if meta:
            language = str(meta.get("content", "")).strip() or None
    return author, language


def _document_title(soup, path: Path) -> str:
    """Pick the document title: first H1, then ``<title>`` tag, then filename stem."""
    h1 = soup.find("h1")
    if h1 is not None:
        text = h1.get_text(strip=True)
        if text:
            return text
    title_tag = soup.find("title")
    if title_tag is not None:
        text = title_tag.get_text(strip=True)
        if text:
            return text
    return path.stem


def _heading_level(tag) -> int:
    return int(tag.name[1])


def _build_section_tree(soup, headings) -> list[ParsedSection]:
    """Build the nested ParsedSection tree from a flat list of <hN> tags."""
    root: list[ParsedSection] = []
    stack: list[ParsedSection] = []

    for idx, h in enumerate(headings):
        own_level = _heading_level(h)
        title = h.get_text(strip=True)
        # Find the first deeper heading (if any) — that bounds the body.
        first_deeper = None
        end_same_or_shallower = None
        for h2 in headings[idx + 1:]:
            l2 = _heading_level(h2)
            if l2 <= own_level:
                end_same_or_shallower = h2
                break
            if first_deeper is None:
                first_deeper = h2

        stop_node = first_deeper or end_same_or_shallower
        body_text, body_links = _collect_body_and_links(h, stop_node)

        section = ParsedSection(
            title=title,
            level=own_level,
            body=body_text,
            subsections=[],
            links=body_links,
        )
        while stack and stack[-1].level >= own_level:
            stack.pop()
        if stack:
            stack[-1].subsections.append(section)
        else:
            root.append(section)
        stack.append(section)
    return root


def _collect_body_and_links(start_tag, stop_node) -> tuple[str, list[str]]:
    """Collect text and ``<a href>`` links between ``start_tag`` (exclusive)
    and ``stop_node`` (exclusive).

    Skips descendants of ``start_tag`` itself so that the heading's own
    text doesn't leak into the body of its section.
    """
    from bs4 import NavigableString, Tag

    text_parts: list[str] = []
    seen_links: set[str] = set()
    links: list[str] = []

    for node in start_tag.next_elements:
        if node is start_tag:
            continue
        if node is stop_node:
            break
        # Skip anything that lives inside the heading tag itself.
        if _is_descendant_of(node, start_tag):
            continue
        if isinstance(node, NavigableString):
            text_parts.append(str(node))
        elif isinstance(node, Tag):
            if node.name == "a" and node.has_attr("href"):
                href = node["href"]
                if href and href not in seen_links:
                    seen_links.add(href)
                    links.append(href)
            elif node.name == "img":
                # Spec §6.2: images are NOT hyperlinks. Skip silently.
                continue
    body = "".join(text_parts).strip()
    return body, links


def _is_descendant_of(node, ancestor) -> bool:
    """Return ``True`` if ``node`` lies somewhere inside ``ancestor``."""
    for parent in getattr(node, "parents", ()):  # NavigableString also has .parents.
        if parent is ancestor:
            return True
    return False


def _collect_preamble(soup, first_heading) -> tuple[str, list[str]]:
    """Collect text and links that appear before the first heading."""
    from bs4 import NavigableString, Tag

    body_tag = soup.body or soup
    text_parts: list[str] = []
    seen_links: set[str] = set()
    links: list[str] = []
    for node in body_tag.descendants:
        if node is first_heading:
            break
        if isinstance(node, NavigableString):
            text_parts.append(str(node))
        elif isinstance(node, Tag):
            if node.name in _HEADING_TAGS:
                break
            if node.name == "a" and node.has_attr("href"):
                href = node["href"]
                if href and href not in seen_links:
                    seen_links.add(href)
                    links.append(href)
    return "".join(text_parts).strip(), links


def _collect_links(soup) -> list[str]:
    """Return every ``<a href>`` value found in the document."""
    seen: set[str] = set()
    out: list[str] = []
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if href and href not in seen:
            seen.add(href)
            out.append(href)
    return out
