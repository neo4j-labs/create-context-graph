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

"""Claude Code session history connector.

Imports session data from local Claude Code JSONL files
(``~/.claude/projects/``) into a context graph.  Unlike other connectors
this requires no authentication — all data is read from the local
filesystem.

The connector extracts:
* Session structure (projects, sessions, messages, tool calls)
* File and package entities referenced in tool calls
* Decision traces from user corrections, error-resolution cycles,
  and deliberation patterns
* Developer preferences from explicit statements and behavioral patterns
"""

from __future__ import annotations

import hashlib
import logging
import os
from pathlib import Path
from typing import Any

from create_context_graph.connectors import (
    BaseConnector,
    NormalizedData,
    register_connector,
)
from create_context_graph.connectors._claude_code.parser import (
    discover_projects,
    discover_sessions,
    parse_session,
)
from create_context_graph.connectors._claude_code.redactor import redact_secrets

logger = logging.getLogger(__name__)

# Safety limits.
MAX_SESSIONS_DEFAULT = 500
MAX_CONTENT_LEN_DEFAULT = 2000


@register_connector("claude-code")
class ClaudeCodeConnector(BaseConnector):
    """Import session history from local Claude Code JSONL files."""

    service_name = "Claude Code"
    service_description = (
        "Import AI coding session history from local Claude Code JSONL files "
        "(~/.claude/projects/). No API key required."
    )
    requires_oauth = False

    BODY_FIELDS = {"Message": "content"}

    def __init__(self) -> None:
        self._base_path: Path | None = None
        self._scope: str = "current"
        self._project_filter: str = ""
        self._content_mode: str = "truncated"
        self._max_content_len: int = MAX_CONTENT_LEN_DEFAULT
        self._since: str = ""
        self._max_sessions: int = 0
        self._extract_decisions: bool = True
        self._extract_preferences: bool = True
        self._redact: bool = True
        self._cwd: str = ""

    # ------------------------------------------------------------------
    # BaseConnector interface
    # ------------------------------------------------------------------

    def get_credential_prompts(self) -> list[dict[str, Any]]:
        """No credentials needed — data is on the local filesystem."""
        return []

    def authenticate(self, credentials: dict[str, str]) -> None:
        """Parse configuration from credentials dict.

        The CLI wires ``--claude-code-*`` flags into the credentials dict
        so that configuration flows through the standard connector pipeline.
        """
        base = credentials.get("base_path", "")
        self._base_path = Path(base).expanduser() if base else None
        self._scope = credentials.get("scope", "current")
        self._project_filter = credentials.get("project_filter", "")
        self._content_mode = credentials.get("content_mode", "truncated")
        self._max_content_len = int(
            credentials.get("max_content_len", str(MAX_CONTENT_LEN_DEFAULT))
        )
        self._since = credentials.get("since", "")
        self._max_sessions = int(credentials.get("max_sessions", "0"))
        self._extract_decisions = credentials.get("extract_decisions", "true") == "true"
        self._extract_preferences = credentials.get("extract_preferences", "true") == "true"
        self._redact = credentials.get("redact", "true") == "true"
        self._cwd = credentials.get("cwd", os.getcwd())

        # Validate base path exists.
        resolved = self._base_path or Path.home() / ".claude" / "projects"
        if not resolved.is_dir():
            logger.warning(
                "Claude Code projects directory not found: %s. "
                "No sessions will be imported.",
                resolved,
            )

    def fetch(self, **kwargs: Any) -> NormalizedData:
        """Parse Claude Code sessions and return normalised graph data."""
        entities: dict[str, list[dict[str, Any]]] = {}
        relationships: list[dict[str, Any]] = []
        documents: list[dict[str, Any]] = []
        traces: list[dict[str, Any]] = []

        # 1. Discover projects.
        projects = discover_projects(self._base_path)

        if self._project_filter:
            projects = [
                p for p in projects
                if self._project_filter in p["decoded_path"]
                or self._project_filter in p["encoded_path"]
            ]
        elif self._scope == "current":
            projects = self._filter_current_project(projects)

        if not projects:
            logger.info("No Claude Code projects found to import.")
            return NormalizedData()

        logger.info("Found %d project(s) to import.", len(projects))

        # Track global dedup sets.
        seen_files: dict[str, dict[str, Any]] = {}
        seen_branches: set[str] = set()
        all_parsed_sessions: list[dict[str, Any]] = []

        total_sessions_imported = 0

        for project in projects:
            project_path = project["full_path"]

            # 2. Discover sessions.
            sessions = discover_sessions(
                project_path,
                since=self._since,
                max_sessions=self._max_sessions,
            )

            if not sessions:
                continue

            logger.info(
                "  Project %s: %d session(s)",
                project["decoded_path"],
                len(sessions),
            )

            # Create Project entity.
            project_entity = {
                "name": project["decoded_path"],
                "encodedPath": project["encoded_path"],
                "sessionCount": len(sessions),
            }
            entities.setdefault("Project", []).append(project_entity)

            for sess_info in sessions:
                # 3. Parse session.
                parsed = parse_session(
                    sess_info["jsonl_path"],
                    content_mode=self._content_mode,
                    max_content_len=self._max_content_len,
                )
                all_parsed_sessions.append(parsed)
                total_sessions_imported += 1

                meta = parsed["metadata"]

                # Build a unique session name using the session ID so that
                # entity merge keys ({name, domain}) remain distinct across
                # sessions even when two sessions start with the same prompt.
                # The human-readable first prompt is stored as a separate
                # display property.
                session_id = parsed["session_id"]
                first_prompt = sess_info.get("first_prompt", "")
                session_name = f"Session:{session_id}"

                # Store the canonical name back into parsed so that
                # decision_extractor.extract_decisions() uses the same key.
                parsed["session_name"] = session_name

                # Create Session entity.
                session_entity = {
                    "name": session_name,
                    "sessionId": session_id,
                    "firstPrompt": first_prompt[:200] if first_prompt else "",
                    "startedAt": meta["first_timestamp"],
                    "endedAt": meta["last_timestamp"],
                    "branch": meta["git_branch"],
                    "messageCount": meta["message_count"],
                    "totalInputTokens": meta["total_input_tokens"],
                    "totalOutputTokens": meta["total_output_tokens"],
                    "progressCount": parsed["progress_count"],
                }
                entities.setdefault("Session", []).append(session_entity)

                # HAS_SESSION relationship.
                relationships.append({
                    "type": "HAS_SESSION",
                    "source_name": project["decoded_path"],
                    "source_label": "Project",
                    "target_name": session_name,
                    "target_label": "Session",
                })

                # ON_BRANCH relationship.
                branch = meta["git_branch"]
                if branch:
                    if branch not in seen_branches:
                        seen_branches.add(branch)
                        entities.setdefault("GitBranch", []).append({
                            "name": branch,
                            "project": project["decoded_path"],
                        })
                    relationships.append({
                        "type": "ON_BRANCH",
                        "source_name": session_name,
                        "source_label": "Session",
                        "target_name": branch,
                        "target_label": "GitBranch",
                    })

                # Process messages.
                prev_message_name: str | None = None
                for msg in parsed["messages"]:
                    msg_name = f"msg-{msg['uuid'][:12]}"
                    content = msg["content"]
                    if self._redact and content:
                        content = redact_secrets(content)

                    msg_entity = {
                        "name": msg_name,
                        "uuid": msg["uuid"],
                        "role": msg["role"],
                        "content": content,
                        "timestamp": msg["timestamp"],
                    }
                    entities.setdefault("Message", []).append(msg_entity)

                    # HAS_MESSAGE relationship.
                    relationships.append({
                        "type": "HAS_MESSAGE",
                        "source_name": session_name,
                        "source_label": "Session",
                        "target_name": msg_name,
                        "target_label": "Message",
                    })

                    # NEXT relationship (sequential message chain).
                    if prev_message_name:
                        relationships.append({
                            "type": "NEXT",
                            "source_name": prev_message_name,
                            "source_label": "Message",
                            "target_name": msg_name,
                            "target_label": "Message",
                        })
                    prev_message_name = msg_name

                    # USED_TOOL relationships.
                    for tc_id in msg.get("tool_use_ids", []):
                        # Find matching tool call.
                        tc = next(
                            (t for t in parsed["tool_calls"] if t["tool_use_id"] == tc_id),
                            None,
                        )
                        if tc:
                            tc_name = _tool_call_name(tc)
                            relationships.append({
                                "type": "USED_TOOL",
                                "source_name": msg_name,
                                "source_label": "Message",
                                "target_name": tc_name,
                                "target_label": "ToolCall",
                            })

                # Process tool calls.
                prev_tc_name: str | None = None
                for tc in parsed["tool_calls"]:
                    tc_name = _tool_call_name(tc)
                    output = tc.get("output", "")
                    if self._redact and output:
                        output = redact_secrets(output)

                    tc_entity = {
                        "name": tc_name,
                        "toolUseId": tc["tool_use_id"],
                        "toolName": tc["tool_name"],
                        "input": tc.get("input_summary", ""),
                        "output": output[:self._max_content_len] if output else "",
                        "isError": tc.get("is_error", False),
                        "timestamp": tc["timestamp"],
                    }
                    entities.setdefault("ToolCall", []).append(tc_entity)

                    # PRECEDED_BY chain (sequential tool calls).
                    if prev_tc_name:
                        relationships.append({
                            "type": "PRECEDED_BY",
                            "source_name": tc_name,
                            "source_label": "ToolCall",
                            "target_name": prev_tc_name,
                            "target_label": "ToolCall",
                        })
                    prev_tc_name = tc_name

                # Process files.
                for path, file_info in parsed["files_touched"].items():
                    if path not in seen_files:
                        seen_files[path] = {
                            "name": path,
                            "path": path,
                            "language": file_info["language"],
                            "modificationCount": file_info["modification_count"],
                            "readCount": file_info["read_count"],
                        }
                    else:
                        seen_files[path]["modificationCount"] += file_info["modification_count"]
                        seen_files[path]["readCount"] += file_info["read_count"]

                    # File relationships from tool calls.
                    for tc in parsed["tool_calls"]:
                        tc_name = _tool_call_name(tc)
                        tc_input = tc.get("input", {})
                        tc_path = tc_input.get("file_path", "") or tc_input.get("path", "")
                        if not tc_path:
                            continue
                        # Normalise for comparison.
                        norm_path = tc_path
                        if not os.path.isabs(tc_path) and meta["cwd"]:
                            norm_path = os.path.normpath(
                                os.path.join(meta["cwd"], tc_path)
                            )
                        if norm_path != path:
                            continue

                        if tc["tool_name"] in ("Write", "Edit", "NotebookEdit"):
                            relationships.append({
                                "type": "MODIFIED_FILE",
                                "source_name": tc_name,
                                "source_label": "ToolCall",
                                "target_name": path,
                                "target_label": "File",
                            })
                        elif tc["tool_name"] in ("Read", "Grep", "Glob"):
                            relationships.append({
                                "type": "READ_FILE",
                                "source_name": tc_name,
                                "source_label": "ToolCall",
                                "target_name": path,
                                "target_label": "File",
                            })

                # Process errors.
                for err in parsed["errors"]:
                    err_name = f"error-{_short_hash(err['message'])}"
                    err_entity = {
                        "name": err_name,
                        "message": redact_secrets(err["message"]) if self._redact else err["message"],
                        "timestamp": err["timestamp"],
                        "toolUseId": err["tool_use_id"],
                    }
                    entities.setdefault("Error", []).append(err_entity)

                    # ENCOUNTERED_ERROR relationship.
                    tc = next(
                        (t for t in parsed["tool_calls"] if t["tool_use_id"] == err["tool_use_id"]),
                        None,
                    )
                    if tc:
                        relationships.append({
                            "type": "ENCOUNTERED_ERROR",
                            "source_name": _tool_call_name(tc),
                            "source_label": "ToolCall",
                            "target_name": err_name,
                            "target_label": "Error",
                        })

                # Create session document for full-text search.
                doc_parts = []
                for msg in parsed["messages"]:
                    role = msg["role"]
                    text = msg.get("full_content", msg.get("content", ""))
                    if text:
                        doc_parts.append(f"[{role}] {text[:500]}")
                doc_content = "\n\n".join(doc_parts)
                if self._redact:
                    doc_content = redact_secrets(doc_content)

                documents.append({
                    "title": f"Claude Code Session: {session_name}",
                    "content": doc_content[:10000],
                    "template_id": "claude-code-session",
                    "template_name": "Claude Code Session",
                })

        # Add deduplicated File entities.
        entities["File"] = list(seen_files.values())

        # 4. Decision extraction.
        if self._extract_decisions:
            try:
                from create_context_graph.connectors._claude_code.decision_extractor import (
                    extract_decisions,
                )

                for parsed in all_parsed_sessions:
                    decision_data = extract_decisions(parsed)
                    for label, items in decision_data.get("entities", {}).items():
                        entities.setdefault(label, []).extend(items)
                    relationships.extend(decision_data.get("relationships", []))
                    traces.extend(decision_data.get("traces", []))
            except Exception:
                logger.warning("Decision extraction failed", exc_info=True)

        # 5. Preference extraction.
        if self._extract_preferences and all_parsed_sessions:
            try:
                from create_context_graph.connectors._claude_code.preference_extractor import (
                    extract_preferences,
                )

                pref_data = extract_preferences(all_parsed_sessions)
                for label, items in pref_data.get("entities", {}).items():
                    entities.setdefault(label, []).extend(items)
                relationships.extend(pref_data.get("relationships", []))
            except Exception:
                logger.warning("Preference extraction failed", exc_info=True)

        logger.info(
            "Claude Code import complete: %d projects, %d sessions, "
            "%d entities, %d relationships",
            len(projects),
            total_sessions_imported,
            sum(len(v) for v in entities.values()),
            len(relationships),
        )

        return NormalizedData(
            entities=entities,
            relationships=relationships,
            documents=documents,
            traces=traces,
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _filter_current_project(
        self, projects: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        """Filter projects to the one matching the current working directory."""
        cwd = self._cwd
        if not cwd:
            return projects

        matched = []
        for p in projects:
            # Check if the decoded path matches or is a parent of cwd.
            decoded = p["decoded_path"]
            if cwd.startswith(decoded) or decoded.startswith(cwd):
                matched.append(p)
            # Also check the encoded form against cwd.
            cwd_encoded = cwd.replace("/", "-")
            if cwd_encoded in p["encoded_path"] or p["encoded_path"] in f"-{cwd_encoded}":
                matched.append(p)

        # Deduplicate.
        seen = set()
        result = []
        for p in matched:
            if p["encoded_path"] not in seen:
                seen.add(p["encoded_path"])
                result.append(p)

        return result


def _tool_call_name(tc: dict[str, Any]) -> str:
    """Generate a unique name for a tool call entity."""
    summary = tc.get("input_summary", "")[:60]
    tool_name = tc["tool_name"]

    unique_id = tc.get("tool_use_id")
    if not unique_id:
        unique_id = (
            tc.get("timestamp")
            or tc.get("created_at")
            or tc.get("time")
        )
    if not unique_id:
        unique_id = _short_hash(repr(sorted(tc.items())))

    return (
        f"{tool_name}[{unique_id}]: {summary}"
        if summary
        else f"{tool_name}[{unique_id}]"
    )
def _short_hash(text: str) -> str:
    """Generate a short hash for deduplication."""
    return hashlib.sha256(text.encode()).hexdigest()[:10]
