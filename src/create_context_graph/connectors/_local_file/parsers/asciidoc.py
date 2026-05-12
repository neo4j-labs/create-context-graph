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

"""AsciiDoc parser for the Local File document connector.

Focused regex parser (MVP, zero deps) — no maintained, permissively-licensed
pure-Python AsciiDoc parser exists as of 2026 (``asciidoc-py`` is GPL +
abandoned; ``asciidoc3`` is AGPL). Our scope is narrow: heading structure,
body text, and links. AsciiDoc's heading syntax is regular (``=+`` prefix)
so a focused parser is sufficient and fully deterministic.

Block-state tracking handles ``----`` / ``....`` / ``++++`` / ``|===``
literal blocks so a stray ``=`` inside a code/listing block is not
mistaken for a heading. Links come from ``link:URL[text]``, bare
``http(s)://...`` autolinks, and ``<<xref>>`` references.
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

# Match a heading: a run of '=' characters, then whitespace, then text.
# The level is the number of '=' characters.
_HEADING_RE = re.compile(r"^(=+)\s+(\S.*)$")

# AsciiDoc literal/code/passthrough/table block delimiters. Each is a line
# of four-plus matching characters (or three-plus pipes for tables) on its
# own. Encountering the *same* delimiter again closes the block.
_BLOCK_DELIMITERS: tuple[tuple[re.Pattern, str], ...] = (
    (re.compile(r"^-{4,}\s*$"), "listing"),       # ----
    (re.compile(r"^\.{4,}\s*$"), "literal"),      # ....
    (re.compile(r"^\+{4,}\s*$"), "passthrough"),  # ++++
    (re.compile(r"^\|={3,}\s*$"), "table"),       # |===
)

# Link patterns.
_LINK_MACRO_RE = re.compile(r"link:([^\[\s]+)\[[^\]]*\]")
_AUTOLINK_RE = re.compile(r"(?<![\w:/])(https?://\S+)")
_TRAILING_PUNCT = '.,;:!?)\\]>"\''
_XREF_RE = re.compile(r"<<([^,>]+)(?:,[^>]*)?>>")


def parse(path: str | Path) -> ParsedDocument:
    """Parse an AsciiDoc file into a :class:`ParsedDocument`."""
    p = Path(path)
    text = read_text_file(p)
    lines = text.splitlines()

    headings, line_in_block = _scan_headings(lines)
    title = _document_title(lines, headings, p)
    author, language = _asciidoc_author_language(lines)
    preamble_text, preamble_links = _collect_preamble(lines, headings, line_in_block)
    sections = _build_section_tree(lines, headings, line_in_block)

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
# Block-aware heading scan
# ---------------------------------------------------------------------------


def _scan_headings(lines: list[str]) -> tuple[list[dict], list[bool]]:
    """Return ``(headings, line_in_block)``.

    ``headings`` is a list of ``{level, title, line}`` dicts in document
    order. ``line_in_block[i]`` is ``True`` when ``lines[i]`` lies inside a
    literal/code/passthrough/table block — used by callers when scanning
    text for links so that block content is treated as opaque.
    """
    headings: list[dict] = []
    line_in_block: list[bool] = [False] * len(lines)
    inside: str | None = None

    for i, line in enumerate(lines):
        if inside is not None:
            line_in_block[i] = True
            # Check for matching close delimiter.
            for pattern, kind in _BLOCK_DELIMITERS:
                if kind == inside and pattern.match(line):
                    inside = None
                    break
            continue

        # Not in a block — see if this line opens one.
        opened = False
        for pattern, kind in _BLOCK_DELIMITERS:
            if pattern.match(line):
                inside = kind
                line_in_block[i] = True
                opened = True
                break
        if opened:
            continue

        m = _HEADING_RE.match(line)
        if m:
            level = len(m.group(1))
            if level > 6:
                level = 6
            title = m.group(2).strip()
            headings.append({"level": level, "title": title, "line": i})

    return headings, line_in_block


# ---------------------------------------------------------------------------
# Title + preamble extraction
# ---------------------------------------------------------------------------


# AsciiDoc document attribute: `:name: value`
_ATTR_RE = re.compile(r"^:([^:]+):\s*(.*?)\s*$")


def _asciidoc_author_language(lines: list[str]) -> tuple[str | None, str | None]:
    """Scan the document header (first 50 lines) for :author: and :lang: attributes."""
    author = language = None
    for line in lines[:50]:
        m = _ATTR_RE.match(line)
        if not m:
            continue
        key, value = m.group(1).lower().strip(), m.group(2).strip()
        if key == "author" and not author:
            author = value or None
        elif key in ("lang", "language") and not language:
            language = value or None
    return author, language


def _document_title(lines: list[str], headings: list[dict], path: Path) -> str:
    """Pick the document title: first level-1 heading, else filename stem."""
    for h in headings:
        if h["level"] == 1:
            return h["title"]
    return path.stem


def _collect_preamble(
    lines: list[str], headings: list[dict], line_in_block: list[bool]
) -> tuple[str, list[str]]:
    """Text + links appearing before the first heading."""
    if not headings:
        body_lines = lines
    else:
        body_lines = lines[: headings[0]["line"]]
    body = "\n".join(body_lines).strip()
    links = _collect_links_in_lines(body_lines, line_in_block, offset=0)
    return body, links


# ---------------------------------------------------------------------------
# Section tree
# ---------------------------------------------------------------------------


def _build_section_tree(
    lines: list[str], headings: list[dict], line_in_block: list[bool]
) -> list[ParsedSection]:
    """Construct the nested ParsedSection tree."""
    root: list[ParsedSection] = []
    stack: list[ParsedSection] = []

    for idx, h in enumerate(headings):
        # The "span" for this heading is from its line+1 to the next heading's
        # line (or EOF). The "body" is the prefix of that span up to the
        # first deeper-or-equal heading inside it — for direct body, we want
        # to stop at the first descendant heading of ANY deeper level.
        own_line = h["line"]
        next_any_line = (
            headings[idx + 1]["line"] if idx + 1 < len(headings) else len(lines)
        )
        # Find the next descendant heading (anything with a strictly higher
        # level) within this span — bounds the body.
        body_end = next_any_line
        for j in range(idx + 1, len(headings)):
            if headings[j]["line"] >= next_any_line:
                break
            if headings[j]["level"] > h["level"]:
                body_end = headings[j]["line"]
                break

        body_lines = lines[own_line + 1: body_end]
        body_text = "\n".join(body_lines).strip()
        body_links = _collect_links_in_lines(
            body_lines, line_in_block, offset=own_line + 1
        )

        section = ParsedSection(
            title=h["title"],
            level=h["level"],
            body=body_text,
            subsections=[],
            links=body_links,
        )
        while stack and stack[-1].level >= h["level"]:
            stack.pop()
        if stack:
            stack[-1].subsections.append(section)
        else:
            root.append(section)
        stack.append(section)
    return root


# ---------------------------------------------------------------------------
# Link extraction
# ---------------------------------------------------------------------------


def _collect_links_in_lines(
    body_lines: list[str], line_in_block: list[bool], *, offset: int
) -> list[str]:
    """Return raw hrefs/xrefs found in ``body_lines``.

    Lines that are inside a literal/code/passthrough/table block (per
    ``line_in_block`` at the corresponding absolute index) are skipped so
    URLs embedded in code samples don't produce ``LINKS_TO`` edges.
    """
    seen: set[str] = set()
    links: list[str] = []
    for rel_idx, line in enumerate(body_lines):
        abs_idx = offset + rel_idx
        if 0 <= abs_idx < len(line_in_block) and line_in_block[abs_idx]:
            continue
        for m in _LINK_MACRO_RE.finditer(line):
            href = m.group(1)
            if href and href not in seen:
                seen.add(href)
                links.append(href)
        for m in _AUTOLINK_RE.finditer(line):
            href = m.group(1).rstrip(_TRAILING_PUNCT)
            if href and href not in seen:
                seen.add(href)
                links.append(href)
        for m in _XREF_RE.finditer(line):
            xref = "#" + m.group(1).strip()
            if xref not in seen:
                seen.add(xref)
                links.append(xref)
    return links
