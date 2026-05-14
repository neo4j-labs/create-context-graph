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

"""Markdown parser for the Local File document connector.

Uses ``markdown-it-py`` (CommonMark + GFM extensions via
``mdit-py-plugins``) — real-world Markdown is overwhelmingly GFM, not
pure CommonMark, so tables/strikethrough/tasklists are enabled.

Headings (any of H1–H6) delimit ``ParsedSection`` nodes. The first H1 (or
file metadata title, falling back to the filename stem) is the document
title. Inline link tokens populate the ``links`` list on the section
where they appear (or the document's preamble links list when before the
first heading).
"""

from __future__ import annotations

from pathlib import Path

from create_context_graph.connectors._local_file.parser import (
    ParsedDocument,
    ParsedSection,
    posix_uri,
    read_text_file,
)


def parse(path: str | Path) -> ParsedDocument:
    """Parse a Markdown file into a :class:`ParsedDocument`.

    Raises:
        ImportError: if ``markdown-it-py`` is not installed.
    """
    try:
        from markdown_it import MarkdownIt
        from mdit_py_plugins.front_matter import front_matter_plugin
        from mdit_py_plugins.tasklists import tasklists_plugin
    except ImportError as exc:  # pragma: no cover - exercised at runtime only.
        raise ImportError(
            "Markdown parsing requires 'markdown-it-py' and 'mdit-py-plugins'. "
            "Install with: pip install 'markdown-it-py>=4.0' 'mdit-py-plugins>=0.4'"
        ) from exc

    p = Path(path)
    text = read_text_file(p)

    # GFM-like enables tables + strikethrough + linkify; we keep tables and
    # strikethrough but disable linkify (which needs ``linkify-it-py`` and is
    # not in our dependency surface). Tasklists come from ``mdit-py-plugins``.
    # front_matter_plugin strips YAML/TOML frontmatter (--- ... ---) so it is
    # not mistaken for a Setext H2 heading by the CommonMark tokeniser.
    md = (
        MarkdownIt("gfm-like", {"linkify": False})
        .use(front_matter_plugin)
        .use(tasklists_plugin)
    )
    tokens = md.parse(text)
    lines = text.splitlines()

    author, language = _frontmatter_author_language(tokens)
    return _build_document(tokens, lines, p, text, author=author, language=language)


# ---------------------------------------------------------------------------
# Internals
# ---------------------------------------------------------------------------


def _frontmatter_author_language(tokens) -> tuple[str | None, str | None]:
    """Extract author and language from a YAML frontmatter token if present."""
    for tok in tokens:
        if tok.type == "front_matter":
            try:
                import yaml
                data = yaml.safe_load(tok.content)
                if not isinstance(data, dict):
                    break
                raw_author = data.get("author") or data.get("authors")
                if isinstance(raw_author, list):
                    raw_author = ", ".join(str(a) for a in raw_author if a)
                author = str(raw_author).strip() or None if raw_author else None
                raw_lang = data.get("lang") or data.get("language")
                language = str(raw_lang).strip() or None if raw_lang else None
                return author, language
            except Exception:
                break
    return None, None


def _build_document(
    tokens, lines: list[str], path: Path, text: str,
    *, author: str | None = None, language: str | None = None,
) -> ParsedDocument:
    """Build a ``ParsedDocument`` tree from a token stream.

    The token stream from ``markdown-it-py`` is flat; we walk forward,
    using each ``heading_open`` token as a section boundary and the
    intervening tokens as the section body.
    """
    headings = _collect_headings(tokens, lines)
    title = _document_title(headings, path)

    # Slice the source into top-level "spans" — one per heading plus the
    # leading preamble — so each section/preamble owns a deterministic
    # range of raw source lines.
    spans = _build_spans(headings, total_lines=len(lines))

    preamble_text = _slice_text(lines, spans[0]) if spans else text
    preamble_links = _collect_links_in_range(tokens, spans[0]) if spans else []

    sections = _build_section_tree(
        headings, spans[1:], tokens, lines
    )

    return ParsedDocument(
        uri=posix_uri(path),
        title=title,
        preamble=preamble_text.strip(),
        sections=sections,
        links=preamble_links,
        source_type="LOCAL_FILE",
        author=author,
        language=language,
    )


def _collect_headings(tokens, lines: list[str]) -> list[dict]:
    """Walk the flat token stream and produce a list of heading metadata.

    Each entry contains the heading level, the rendered text, the line
    number of the ``heading_open`` token, and the line number where the
    next heading or EOF starts (computed in ``_build_spans``).
    """
    headings = []
    i = 0
    while i < len(tokens):
        tok = tokens[i]
        if tok.type == "heading_open":
            # The inline token immediately after holds the heading text.
            level = int(tok.tag[1:])  # 'h3' -> 3
            inline = tokens[i + 1] if i + 1 < len(tokens) else None
            title = (inline.content if inline else "").strip()
            start_line = (tok.map or [0, 0])[0]
            headings.append({"level": level, "title": title, "start_line": start_line})
            # Advance past the heading_close.
            j = i + 1
            while j < len(tokens) and tokens[j].type != "heading_close":
                j += 1
            i = j + 1
        else:
            i += 1
    return headings


def _build_spans(
    headings: list[dict], *, total_lines: int
) -> list[tuple[int, int]]:
    """Produce inclusive/exclusive line ranges for the preamble and each heading.

    spans[0] is the preamble range (before the first heading or whole file
    if no headings); spans[i+1] is the body range for headings[i].
    """
    spans: list[tuple[int, int]] = []
    if not headings:
        return [(0, total_lines)]

    spans.append((0, headings[0]["start_line"]))
    for idx, h in enumerate(headings):
        start = h["start_line"] + 1  # body starts on the line after the heading.
        end = headings[idx + 1]["start_line"] if idx + 1 < len(headings) else total_lines
        spans.append((start, end))
    return spans


def _slice_text(lines: list[str], span: tuple[int, int]) -> str:
    start, end = span
    return "\n".join(lines[start:end])


def _collect_links_in_range(tokens, span: tuple[int, int]) -> list[str]:
    """Return all href attributes on ``link_open`` tokens within ``span``.

    Reference-style links are resolved by ``markdown-it-py`` so each
    ``link_open`` token carries the resolved ``href`` regardless of whether
    the source was inline or reference. Inline links live inside ``inline``
    tokens, whose ``map`` gives the source line range; we walk the inline
    children for ``link_open`` tokens.
    """
    start_line, end_line = span
    links: list[str] = []
    seen: set[str] = set()
    for tok in tokens:
        if tok.map is None or not (start_line <= tok.map[0] < end_line):
            continue
        # Block-level link_open tokens (rare — e.g. autolinks at block level).
        if tok.type == "link_open":
            href = dict(tok.attrs or {}).get("href")
            if href and href not in seen:
                seen.add(href)
                links.append(href)
            continue
        # Inline container: walk its children for embedded link_open tokens.
        if tok.type == "inline" and tok.children:
            for child in tok.children:
                if child.type == "link_open":
                    href = dict(child.attrs or {}).get("href")
                    if href and href not in seen:
                        seen.add(href)
                        links.append(href)
    return links


def _build_section_tree(
    headings: list[dict],
    body_spans: list[tuple[int, int]],
    tokens,
    lines: list[str],
) -> list[ParsedSection]:
    """Construct the nested section tree from flat heading + span data.

    The tree shape obeys spec §4 Rule 2: if heading levels skip (e.g. H1
    → H3), the H3 becomes a direct child of the H1 at level 3. No
    synthetic H2 is created.
    """
    sections: list[tuple[ParsedSection, int]] = []  # (section, depth-in-tree)
    root_sections: list[ParsedSection] = []
    stack: list[ParsedSection] = []

    for h, span in zip(headings, body_spans):
        body_lines = lines[span[0]:span[1]]
        # The body of a section is the text between this heading and the
        # next heading at the same-or-shallower level (the "direct body"
        # only — child sections live as separate ParsedSection nodes).
        body_until_child = _trim_body_to_first_child(
            body_lines, parent_start=span[0], parent_level=h["level"], headings=headings
        )
        body_text = "\n".join(body_until_child).strip()
        body_span = (span[0], span[0] + len(body_until_child))
        links = _collect_links_in_range(tokens, body_span)

        section = ParsedSection(
            title=h["title"],
            level=h["level"],
            body=body_text,
            subsections=[],
            links=links,
        )

        # Pop the stack until we find a parent with a strictly smaller level.
        while stack and stack[-1].level >= h["level"]:
            stack.pop()
        if stack:
            stack[-1].subsections.append(section)
        else:
            root_sections.append(section)
        stack.append(section)
        sections.append((section, len(stack)))

    return root_sections


def _trim_body_to_first_child(
    body_lines: list[str],
    *,
    parent_start: int,
    parent_level: int,
    headings: list[dict],
) -> list[str]:
    """Trim ``body_lines`` so it ends before the first descendant heading.

    Direct body text is everything between a heading and the first heading
    of any deeper level — child or grandchild. (We do not include
    descendants because their text lives on their own ``ParsedSection``.)
    """
    body_start = parent_start + 1
    # Find the first heading whose start_line > parent_start.
    for h in headings:
        if h["start_line"] <= parent_start:
            continue
        offset = h["start_line"] - body_start
        if 0 <= offset < len(body_lines):
            return body_lines[:offset]
        return body_lines
    return body_lines


def _document_title(headings: list[dict], path: Path) -> str:
    """Pick a display title: first H1, or the filename stem if absent."""
    for h in headings:
        if h["level"] == 1:
            return h["title"]
    return path.stem
