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

"""Local-file document connector.

Ingests structured documents from the local filesystem (Markdown, PDF,
HTML, AsciiDoc, Word) into a context graph. No authentication, no API
keys, no network. Mirrors the ``claude-code`` connector's local-source
shape; the actual parsing lives in
:mod:`create_context_graph.connectors._local_file`.

The connector emits ``:Document`` and ``:Section`` entities keyed on URI
(``name`` field) so the existing MERGE-on-``name+domain`` ingest pipeline
works without modification. See ``scratch/doc-connector-requirements-v2.md``
for the full design.
"""

from __future__ import annotations

import fnmatch
import logging
import os
from pathlib import Path
from typing import Any, Iterable

from create_context_graph.connectors import (
    BaseConnector,
    NormalizedData,
    register_connector,
)
from create_context_graph.connectors._local_file.mapper import DocumentMapper
from create_context_graph.connectors._local_file.parser import (
    SUPPORTED_EXTENSIONS,
    parse_file,
    posix_uri,
)

logger = logging.getLogger(__name__)


@register_connector("local-file")
class LocalFileConnector(BaseConnector):
    """Import documents from the local filesystem."""

    service_name = "Local File"
    service_description = (
        "Ingest documents from the local filesystem (Markdown, HTML, PDF, "
        "Word, AsciiDoc). No authentication required."
    )
    requires_oauth = False

    def __init__(self) -> None:
        self._paths: list[Path] = []
        self._pattern: str = "**/*"
        self._recursive: bool = True
        self._follow_links: bool = False
        self._exclude: list[str] = []

    # ------------------------------------------------------------------
    # BaseConnector interface
    # ------------------------------------------------------------------

    def get_credential_prompts(self) -> list[dict[str, Any]]:
        """Wizard prompt for the path(s) to ingest.

        Returns one required prompt for ``paths`` (comma-separated). The
        CLI flow uses ``--local-file-path`` (repeatable) instead, but the
        wizard needs at least one prompt so users don't silently end up
        with an empty ingest scope. Returning ``[]`` was rejected because
        it risked accidentally importing personal files when a wizard
        user picked the connector without realising it needed a path.
        """
        return [
            {
                "name": "paths",
                "prompt": (
                    "Path(s) to ingest (file or directory; comma-separate "
                    "multiple paths)"
                ),
                "secret": False,
                "description": (
                    "Absolute or relative path to a file or directory of "
                    "documents. Supported extensions: "
                    + ", ".join(sorted(SUPPORTED_EXTENSIONS))
                ),
            }
        ]

    def authenticate(self, credentials: dict[str, Any]) -> None:
        """Parse configuration from a credentials dict.

        Accepts ``paths`` either as a list[str] (CLI flow) or as a
        comma-separated str (wizard flow). All other settings are optional.

        Raises:
            ValueError: if no paths are configured. Erroring loudly here
                is deliberate — the alternative (defaulting to ``cwd``)
                risks accidentally ingesting personal files into a shared
                graph when wizard users pick the connector without a path.
        """
        raw_paths = credentials.get("paths") or []
        if isinstance(raw_paths, str):
            # CLI flow joins paths with os.pathsep; wizard flow uses comma-separated
            # text entered by the user. Try os.pathsep first; fall back to comma so
            # wizard input still works.
            sep = os.pathsep if os.pathsep in raw_paths else ","
            raw_paths = [p.strip() for p in raw_paths.split(sep) if p.strip()]
        self._paths = [Path(p).expanduser() for p in raw_paths if p]
        if not self._paths:
            raise ValueError(
                "At least one --local-file-path is required for the "
                "local-file connector. Pass --local-file-path PATH "
                "(repeatable) or enter a path when prompted by the wizard."
            )
        self._pattern = credentials.get("pattern") or "**/*"
        recursive_raw = credentials.get("recursive", True)
        self._recursive = (
            str(recursive_raw).lower() != "false" if recursive_raw is not None else True
        )
        if not self._recursive and "**" in self._pattern:
            raise ValueError(
                f"Pattern {self._pattern!r} contains '**' but --local-file-no-recursive "
                "was set. Either enable recursion or use a non-recursive pattern (e.g. '*' "
                "to match only direct children)."
            )
        follow_links_raw = credentials.get("follow_links", False)
        self._follow_links = str(follow_links_raw).lower() == "true"
        excludes_raw = credentials.get("exclude") or []
        if isinstance(excludes_raw, str):
            sep = os.pathsep if os.pathsep in excludes_raw else ","
            excludes_raw = [p.strip() for p in excludes_raw.split(sep) if p.strip()]
        self._exclude = list(excludes_raw)

    def fetch(self, **kwargs: Any) -> NormalizedData:
        """Discover supported files under each configured path and parse them."""
        files = list(self._discover_files())
        mapper = DocumentMapper()
        mapper.register_known_uris(posix_uri(f) for f in files)
        if not files:
            logger.info("Local-file connector: no files matched the configured paths.")
            return mapper.build()

        logger.info("Local-file connector: parsing %d file(s).", len(files))
        for file_path in files:
            try:
                parsed = parse_file(file_path)
            except ImportError as exc:
                logger.warning(
                    "Skipping %s: required parser dependency not installed: %s",
                    file_path,
                    exc,
                )
                continue
            except Exception:  # noqa: BLE001 - want to keep going on bad files.
                logger.warning(
                    "Skipping %s: parse error.", file_path, exc_info=True
                )
                continue
            mapper.add(parsed)
        return mapper.build()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _discover_files(self) -> Iterable[Path]:
        """Yield supported files under every configured path in sorted order.

        File discovery is fully deterministic: each root is walked with
        :meth:`pathlib.Path.rglob` (or :meth:`glob` when recursion is
        off), sorted lexicographically by POSIX URI, then filtered by
        extension, ``pattern``, and ``exclude`` globs.
        """
        seen: set[str] = set()
        for root in self._paths:
            if not root.exists():
                logger.warning("Path does not exist, skipping: %s", root)
                continue

            if root.is_file():
                candidates: list[Path] = [root]
            elif self._recursive:
                candidates = list(root.rglob(self._pattern))
            else:
                candidates = list(root.glob(self._pattern))

            # Sort by absolute POSIX URI for deterministic ordering.
            candidates.sort(key=lambda p: posix_uri(p))

            for cand in candidates:
                if not cand.is_file():
                    continue
                if not self._follow_links and cand.is_symlink():
                    continue
                if cand.suffix.lower() not in SUPPORTED_EXTENSIONS:
                    continue
                if self._is_excluded(cand):
                    continue
                key = posix_uri(cand)
                if key in seen:
                    continue
                seen.add(key)
                yield cand

    def _is_excluded(self, path: Path) -> bool:
        """Return ``True`` if ``path`` matches any of the exclude globs."""
        if not self._exclude:
            return False
        candidate = posix_uri(path)
        for pattern in self._exclude:
            if fnmatch.fnmatch(candidate, pattern):
                return True
        return False
