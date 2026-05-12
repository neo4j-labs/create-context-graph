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

"""Shared types and helpers for the Local File document connector.

This module defines the format-agnostic intermediate representation
(``ParsedDocument`` / ``ParsedSection``) that every per-format parser
produces, plus deterministic helpers used across parsers:

* :func:`slugify` — GitHub/Pandoc HTML-anchor slug algorithm.
* :func:`posix_uri` — POSIX-normalised absolute URI for a filesystem path
  so the same file produces the same URI on macOS, Linux, and Windows.
* :func:`read_text_file` — UTF-8 read with ``errors="replace"`` fallback.
* :func:`parse_file` — file-extension based dispatch to a format parser.

All parsers are pure-Python and deterministic: given the same input file
they always emit the same ``ParsedDocument``.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

# ---------------------------------------------------------------------------
# Intermediate representation
# ---------------------------------------------------------------------------


@dataclass
class ParsedSection:
    """A heading-delimited section within a ``ParsedDocument``.

    Attributes:
        title: Heading text (display name).
        level: 1–6; reflects the *actual* heading level even when the parent
            skipped a level (e.g. H1 → H3 leaves level=3 on the H3).
        body: Immediate body text only — text between this heading and the
            first child heading. Descendant bodies live on the child nodes.
        subsections: Direct children only; the full tree is nested.
        links: Raw hrefs/URLs found in ``body`` (not in child sections).
    """

    title: str
    level: int
    body: str = ""
    subsections: list["ParsedSection"] = field(default_factory=list)
    links: list[str] = field(default_factory=list)


@dataclass
class ParsedDocument:
    """A document parsed into a heading hierarchy.

    Attributes:
        uri: Absolute POSIX-normalised path (for local files) or URL.
        title: First H1 heading text, document metadata title, or filename
            stem if neither is available.
        preamble: Text before the first heading.
        sections: Direct top-level sections only; tree is nested.
        links: Document-level links found before the first heading.
        source_type: ``"LOCAL_FILE"`` for files parsed from disk;
            ``"URL_LINK"`` for stub references discovered via hyperlinks.
    """

    uri: str
    title: str
    preamble: str = ""
    sections: list[ParsedSection] = field(default_factory=list)
    links: list[str] = field(default_factory=list)
    source_type: str = "LOCAL_FILE"
    # Filesystem metadata — populated by parse_file(); None for in-memory docs.
    file_extension: str | None = None
    file_size: int | None = None
    created_at: datetime | None = None
    modified_at: datetime | None = None
    # Document-level metadata — populated by per-format parsers where available.
    author: str | None = None
    language: str | None = None
    page_count: int | None = None


# ---------------------------------------------------------------------------
# Deterministic helpers
# ---------------------------------------------------------------------------

_SLUG_NON_ALNUM_UNDERSCORE = re.compile(r"[^a-z0-9_]+")


def slugify(text: str) -> str:
    """Return a GitHub/Pandoc-style HTML-anchor slug.

    Algorithm (deterministic, ASCII-only):

    1. Unicode-normalise to NFKD (decomposes accented chars into base +
       combining marks).
    2. Encode to ASCII with ``errors="ignore"`` (drops non-ASCII codepoints
       including emoji, CJK, and combining marks).
    3. Lowercase.
    4. Replace every run of characters outside ``[a-z0-9_]`` with a single
       hyphen — this collapses whitespace, punctuation (``.``, ``!``, em-
       dashes that survive normalisation, ``—`` etc.), and consecutive
       separators in one pass.
    5. Strip leading/trailing hyphens.

    Underscores are preserved (matches the GitHub HTML-anchor convention).
    Empty input or input that consists entirely of stripped characters
    produces an empty string.

    >>> slugify("OAuth 2.0 — Token Exchange!")
    'oauth-2-0-token-exchange'
    >>> slugify("Café Résumé")
    'cafe-resume'
    """
    if not text:
        return ""
    ascii_only = (
        unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    )
    lowered = ascii_only.lower()
    hyphenated = _SLUG_NON_ALNUM_UNDERSCORE.sub("-", lowered)
    return hyphenated.strip("-")


def posix_uri(path: str | Path) -> str:
    """Return a POSIX-normalised absolute URI for ``path``.

    On Windows, ``C:\\docs\\guide.md`` becomes ``C:/docs/guide.md`` so the
    same file produces the same URI on every operating system.
    """
    return Path(path).resolve().as_posix()


def read_text_file(path: str | Path) -> str:
    """Read a text file as UTF-8 with a ``replace`` error handler.

    Real-world files routinely contain mixed encodings (Latin-1 mistaken for
    UTF-8, stray BOMs, mojibake). The connector treats this as recoverable —
    replacement characters in body text are acceptable; the parse must not
    fail.
    """
    with open(path, encoding="utf-8", errors="replace") as fh:
        return fh.read()


# ---------------------------------------------------------------------------
# Format dispatch
# ---------------------------------------------------------------------------

# Mapping of lowercase file extensions (with leading dot) to a callable that
# parses a path into a ``ParsedDocument``. Populated lazily inside
# ``parse_file`` to avoid eager imports of optional dependencies (pypdf,
# python-docx, etc.) when only a subset of formats is needed.
SUPPORTED_EXTENSIONS: tuple[str, ...] = (
    ".md",
    ".mdx",
    ".markdown",
    ".pdf",
    ".html",
    ".htm",
    ".adoc",
    ".asciidoc",
    ".asc",
    ".docx",
)


# Map each supported extension to the name of the per-format parser module.
# The module is imported lazily inside :func:`parse_file` so a missing
# optional dependency only blocks the formats that need it.
_EXTENSION_TO_PARSER: dict[str, str] = {
    ".md": "markdown",
    ".mdx": "markdown",
    ".markdown": "markdown",
    ".pdf": "pdf",
    ".html": "html",
    ".htm": "html",
    ".adoc": "asciidoc",
    ".asciidoc": "asciidoc",
    ".asc": "asciidoc",
    ".docx": "docx",
}


def parse_file(path: str | Path) -> ParsedDocument:
    """Dispatch ``path`` to the parser matching its extension.

    Each parser module is imported lazily so a missing optional dependency
    only blocks the formats that need it.

    Raises:
        ValueError: if the extension is not in :data:`SUPPORTED_EXTENSIONS`.
        FileNotFoundError: if ``path`` does not exist.
    """
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"File not found: {p}")
    ext = p.suffix.lower()
    module_name = _EXTENSION_TO_PARSER.get(ext)
    if module_name is None:
        raise ValueError(
            f"Unsupported file extension {ext!r}. "
            f"Supported extensions: {', '.join(sorted(SUPPORTED_EXTENSIONS))}"
        )
    import importlib

    module = importlib.import_module(
        f"create_context_graph.connectors._local_file.parsers.{module_name}"
    )
    parse_fn: Callable[[Path], ParsedDocument] = module.parse
    doc = parse_fn(p)

    # Attach filesystem metadata so the mapper can store it on the graph node.
    st = p.stat()
    doc.file_extension = p.suffix.lstrip(".").lower() or None
    doc.file_size = st.st_size
    doc.modified_at = datetime.fromtimestamp(st.st_mtime, tz=timezone.utc)
    # st_birthtime is macOS/Windows only; fall back to mtime on Linux.
    birthtime = getattr(st, "st_birthtime", None)
    doc.created_at = datetime.fromtimestamp(
        birthtime if birthtime is not None else st.st_mtime, tz=timezone.utc
    )
    return doc
