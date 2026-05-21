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

"""Google Workspace connector — imports Drive files, comment threads (as decision
traces), revisions, Drive Activity, Calendar events, and Gmail thread metadata
into a unified knowledge graph.

The defining feature is extracting resolved comment threads as first-class
decision traces: the question, deliberation, resolution, and participants
are all captured as graph-connected nodes.
"""

from __future__ import annotations

import json
import logging
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from typing import Any

from create_context_graph.connectors import (
    BaseConnector,
    NormalizedData,
    register_connector,
)
from create_context_graph.connectors.oauth import check_gws_cli, run_gws_command

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

DRIVE_FILES_URL = "https://www.googleapis.com/drive/v3/files"
DRIVE_ACTIVITY_URL = "https://driveactivity.googleapis.com/v2/activity:query"
CALENDAR_EVENTS_URL = "https://www.googleapis.com/calendar/v3/calendars/primary/events"
GMAIL_THREADS_URL = "https://gmail.googleapis.com/gmail/v1/users/me/threads"
GMAIL_MESSAGES_URL = "https://gmail.googleapis.com/gmail/v1/users/me/messages"

GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"

MIME_FILTERS: dict[str, str] = {
    "docs": "application/vnd.google-apps.document",
    "sheets": "application/vnd.google-apps.spreadsheet",
    "slides": "application/vnd.google-apps.presentation",
    "pdf": "application/pdf",
}

# MIME types that support comments
COMMENTABLE_MIMES: set[str] = {
    "application/vnd.google-apps.document",
    "application/vnd.google-apps.spreadsheet",
    "application/vnd.google-apps.presentation",
}

# Drive Activity action type mapping
ACTION_TYPE_MAP: dict[str, str] = {
    "create": "Created",
    "edit": "Edited",
    "move": "Moved",
    "rename": "Renamed",
    "delete": "Deleted",
    "restore": "Restored",
    "permissionChange": "Permission changed",
    "comment": "Commented",
    "suggestion": "Suggestion made",
}

# Cross-connector: Linear-style issue references (e.g., ENG-123)
LINEAR_REF_PATTERN = re.compile(r"\b([A-Z]{2,10}-\d+)\b")

# Drive file URL pattern for cross-linking
DRIVE_URL_PATTERN = re.compile(
    r"https://docs\.google\.com/(?:document|spreadsheets|presentation)/d/([a-zA-Z0-9_-]+)"
)

# Rate limiting: Drive API allows 1000 queries per 100 seconds
RATE_LIMIT_WINDOW = 100  # seconds
RATE_LIMIT_MAX = 950  # leave headroom


# ---------------------------------------------------------------------------
# Connector
# ---------------------------------------------------------------------------


@register_connector("google-workspace")
class GoogleWorkspaceConnector(BaseConnector):
    """Import Drive files, comment threads, revisions, activity, calendar,
    and Gmail thread metadata from Google Workspace.

    Resolved comment threads are extracted as first-class decision traces
    with participants, deliberation, and resolution.
    """

    service_name = "Google Workspace"
    service_description = (
        "Import Drive files, comment threads (as decision traces), "
        "revisions, activity, calendar, and Gmail"
    )
    requires_oauth = True

    # DecisionThread and Reply both carry the actual comment/reply body in
    # their ``content`` field. Document descriptions are short metadata
    # captions, not bodies — already covered by Document fixture entries.
    BODY_FIELDS = {"DecisionThread": "content", "Reply": "content"}

    def __init__(self) -> None:
        self._use_gws: bool = False
        self._access_token: str = ""

        # Feature flags (parsed from credentials dict)
        self._folder_id: str = ""
        self._include_comments: bool = True
        self._include_revisions: bool = True
        self._include_activity: bool = True
        self._include_calendar: bool = False
        self._include_gmail: bool = False
        self._since: str = ""
        self._mime_types: list[str] = []
        self._max_files: int = 500

        # Rate limiting state
        self._request_count: int = 0
        self._request_window_start: float = 0.0

    # ------------------------------------------------------------------
    # BaseConnector interface
    # ------------------------------------------------------------------

    def get_credential_prompts(self) -> list[dict[str, Any]]:
        if check_gws_cli():
            return []  # gws handles auth itself
        return [
            {
                "name": "client_id",
                "prompt": "Google OAuth2 Client ID:",
                "secret": False,
                "description": "From Google Cloud Console > APIs & Services > Credentials",
            },
            {
                "name": "client_secret",
                "prompt": "Google OAuth2 Client Secret:",
                "secret": True,
                "description": "From the same OAuth2 credentials page",
            },
        ]

    def authenticate(self, credentials: dict[str, str]) -> None:
        # Parse feature flags from credentials
        self._folder_id = credentials.get("folder_id", "")
        self._include_comments = credentials.get("include_comments", "true") != "false"
        self._include_revisions = credentials.get("include_revisions", "true") != "false"
        self._include_activity = credentials.get("include_activity", "true") != "false"
        self._include_calendar = credentials.get("include_calendar", "false") == "true"
        self._include_gmail = credentials.get("include_gmail", "false") == "true"
        self._since = credentials.get("since", "")
        self._max_files = int(credentials.get("max_files", "500"))

        mime_types_str = credentials.get("mime_types", "")
        if mime_types_str:
            self._mime_types = [m.strip() for m in mime_types_str.split(",") if m.strip()]
        else:
            self._mime_types = ["docs", "sheets", "slides"]

        # Authenticate
        if check_gws_cli():
            self._use_gws = True
            return

        client_id = credentials.get("client_id", "")
        client_secret = credentials.get("client_secret", "")
        if not client_id or not client_secret:
            raise ValueError(
                "Google OAuth2 Client ID and Secret are required. "
                "Set up credentials at Google Cloud Console > APIs & Services > Credentials."
            )

        from create_context_graph.connectors.oauth import oauth2_authorize

        # Build scopes based on enabled features
        scopes = ["https://www.googleapis.com/auth/drive.readonly"]
        if self._include_activity:
            scopes.append("https://www.googleapis.com/auth/drive.activity.readonly")
        if self._include_calendar:
            scopes.append("https://www.googleapis.com/auth/calendar.readonly")
        if self._include_gmail:
            scopes.append("https://www.googleapis.com/auth/gmail.readonly")

        tokens = oauth2_authorize(
            auth_url=GOOGLE_AUTH_URL,
            token_url=GOOGLE_TOKEN_URL,
            client_id=client_id,
            client_secret=client_secret,
            scopes=scopes,
        )
        self._access_token = tokens.get("access_token", "")
        if not self._access_token:
            raise ValueError("OAuth2 authorization did not return an access token")

    def fetch(self, **kwargs: Any) -> NormalizedData:
        if not self._use_gws and not self._access_token:
            raise RuntimeError("Call authenticate() first")

        entities: dict[str, list[dict[str, Any]]] = {
            "Document": [],
            "Folder": [],
            "Person": [],
            "DecisionThread": [],
            "Reply": [],
            "Revision": [],
            "Activity": [],
        }
        relationships: list[dict[str, Any]] = []
        documents: list[dict[str, Any]] = []
        traces: list[dict[str, Any]] = []
        seen_persons: set[str] = set()  # deduplicate by email

        # Helper to add a person entity (deduplicated)
        def _add_person(display_name: str, email: str) -> str | None:
            if not email:
                return None
            if email not in seen_persons:
                seen_persons.add(email)
                entities["Person"].append({
                    "name": display_name or email.split("@")[0],
                    "emailAddress": email,
                    "displayName": display_name or email.split("@")[0],
                    "poleType": "Person",
                })
            return display_name or email.split("@")[0]

        # =================================================================
        # Stage 1: Fetch files and folders
        # =================================================================
        file_manifest = self._fetch_files()

        for file_info in file_manifest:
            file_name = file_info.get("name", "")
            drive_id = file_info.get("id", "")
            mime_type = file_info.get("mimeType", "")

            # Folders
            if mime_type == "application/vnd.google-apps.folder":
                entities["Folder"].append({
                    "name": file_name,
                    "driveId": drive_id,
                    "parentId": (file_info.get("parents") or [""])[0],
                    "poleType": "Object",
                })
                continue

            # Documents (files)
            entities["Document"].append({
                "name": file_name,
                "driveId": drive_id,
                "mimeType": mime_type,
                "webViewLink": file_info.get("webViewLink", ""),
                "createdTime": file_info.get("createdTime", ""),
                "modifiedTime": file_info.get("modifiedTime", ""),
                "description": file_info.get("description", ""),
                "poleType": "Object",
            })

            # Owner
            for owner in file_info.get("owners", []):
                owner_name = _add_person(
                    owner.get("displayName", ""),
                    owner.get("emailAddress", ""),
                )
                if owner_name:
                    relationships.append({
                        "type": "CREATED_BY",
                        "source_name": file_name,
                        "source_label": "Document",
                        "target_name": owner_name,
                        "target_label": "Person",
                    })

            # Folder containment
            parents = file_info.get("parents", [])
            if parents:
                # Find matching folder
                for folder in entities["Folder"]:
                    if folder["driveId"] == parents[0]:
                        relationships.append({
                            "type": "CONTAINED_IN",
                            "source_name": file_name,
                            "source_label": "Document",
                            "target_name": folder["name"],
                            "target_label": "Folder",
                        })
                        break

            # Permissions → SHARED_WITH
            for perm in file_info.get("permissions", []):
                if perm.get("type") == "user" and perm.get("emailAddress"):
                    person_name = _add_person(
                        perm.get("displayName", ""),
                        perm.get("emailAddress", ""),
                    )
                    if person_name:
                        relationships.append({
                            "type": "SHARED_WITH",
                            "source_name": file_name,
                            "source_label": "Document",
                            "target_name": person_name,
                            "target_label": "Person",
                        })

            # Document content for NormalizedData.documents
            documents.append({
                "title": file_name,
                "content": file_info.get("description", "") or f"Google {mime_type.split('.')[-1]} document",
                "type": "google-workspace-file",
                "metadata": {
                    "driveId": drive_id,
                    "mimeType": mime_type,
                    "modifiedTime": file_info.get("modifiedTime", ""),
                },
            })

        # =================================================================
        # Stage 2: Fetch comment threads (per-file)
        # =================================================================
        if self._include_comments:
            for doc in entities["Document"]:
                if doc.get("mimeType", "") in COMMENTABLE_MIMES:
                    self._fetch_comments(
                        doc["driveId"], doc["name"],
                        _add_person, entities, relationships, traces,
                    )

        # =================================================================
        # Stage 3: Fetch revisions (per-file)
        # =================================================================
        if self._include_revisions:
            for doc in entities["Document"]:
                self._fetch_revisions(
                    doc["driveId"], doc["name"],
                    _add_person, entities, relationships,
                )

        # =================================================================
        # Stage 4: Fetch Drive Activity
        # =================================================================
        if self._include_activity:
            self._fetch_activity(
                _add_person, entities, relationships,
            )

        # =================================================================
        # Stage 5: Fetch Calendar events (optional)
        # =================================================================
        if self._include_calendar:
            entities["Meeting"] = []
            self._fetch_calendar_events(
                _add_person, entities, relationships, documents,
            )

        # =================================================================
        # Stage 6: Fetch Gmail threads (optional)
        # =================================================================
        if self._include_gmail:
            entities["EmailThread"] = []
            self._fetch_gmail_threads(
                _add_person, entities, relationships, documents,
            )

        # =================================================================
        # Stage 7: Cross-connector linking
        # =================================================================
        cross_refs = self._build_cross_references(entities, documents)
        relationships.extend(cross_refs)

        return NormalizedData(
            entities=entities,
            relationships=relationships,
            documents=documents,
            traces=traces,
        )

    # ------------------------------------------------------------------
    # HTTP layer
    # ------------------------------------------------------------------

    def _rate_limit_wait(self) -> None:
        """Enforce Drive API rate limit: ~1000 queries / 100 seconds."""
        now = time.time()
        if now - self._request_window_start > RATE_LIMIT_WINDOW:
            self._request_count = 0
            self._request_window_start = now

        self._request_count += 1
        if self._request_count >= RATE_LIMIT_MAX:
            sleep_time = RATE_LIMIT_WINDOW - (now - self._request_window_start) + 1
            if sleep_time > 0:
                logger.debug("Rate limit approaching, sleeping %.1fs", sleep_time)
                time.sleep(sleep_time)
            self._request_count = 0
            self._request_window_start = time.time()

    def _api_request(self, url: str, params: dict[str, str] | None = None) -> dict[str, Any]:
        """Make authenticated GET request with rate limiting and exponential backoff."""
        self._rate_limit_wait()

        if params:
            query = urllib.parse.urlencode(params)
            full_url = f"{url}?{query}"
        else:
            full_url = url

        headers = {"Authorization": f"Bearer {self._access_token}"}

        for attempt in range(5):
            req = urllib.request.Request(full_url, headers=headers)
            try:
                with urllib.request.urlopen(req, timeout=30) as resp:
                    return json.loads(resp.read())
            except urllib.error.HTTPError as e:
                body = ""
                try:
                    body = e.read().decode("utf-8", errors="replace")
                except Exception:
                    pass
                if e.code == 429 or (e.code == 403 and "rate" in body.lower()):
                    wait = min(2 ** attempt * 2, 60)
                    logger.debug("Rate limited (HTTP %d), retrying in %ds", e.code, wait)
                    time.sleep(wait)
                    continue
                if e.code == 403 and "scope" in body.lower():
                    raise ValueError(
                        f"Insufficient OAuth scopes for {url}. "
                        "Re-run with broader scopes or enable the required API."
                    ) from e
                raise
        raise RuntimeError(f"Google API rate limit exceeded after 5 retries: {url}")

    def _api_post(self, url: str, body: dict[str, Any]) -> dict[str, Any]:
        """Make authenticated POST request with rate limiting and exponential backoff."""
        self._rate_limit_wait()

        data = json.dumps(body).encode("utf-8")
        headers = {
            "Authorization": f"Bearer {self._access_token}",
            "Content-Type": "application/json",
        }

        for attempt in range(5):
            req = urllib.request.Request(url, data=data, headers=headers, method="POST")
            try:
                with urllib.request.urlopen(req, timeout=30) as resp:
                    return json.loads(resp.read())
            except urllib.error.HTTPError as e:
                resp_body = ""
                try:
                    resp_body = e.read().decode("utf-8", errors="replace")
                except Exception:
                    pass
                if e.code == 429 or (e.code == 403 and "rate" in resp_body.lower()):
                    wait = min(2 ** attempt * 2, 60)
                    time.sleep(wait)
                    continue
                raise
        raise RuntimeError(f"Google API rate limit exceeded after 5 retries: {url}")

    # ------------------------------------------------------------------
    # Stage 1: Drive Files
    # ------------------------------------------------------------------

    def _get_since_datetime(self) -> str:
        """Get the ISO datetime string for the --gws-since cutoff."""
        if self._since:
            return self._since
        dt = datetime.now(timezone.utc) - timedelta(days=90)
        return dt.strftime("%Y-%m-%dT%H:%M:%SZ")

    def _build_file_query(self) -> str:
        """Build the Drive Files API query string."""
        parts: list[str] = []

        # MIME type filter
        if self._mime_types:
            mime_clauses = []
            # Also include folders for hierarchy
            mime_clauses.append("mimeType = 'application/vnd.google-apps.folder'")
            for mt in self._mime_types:
                if mt == "all":
                    mime_clauses = []  # No filter
                    break
                full_mime = MIME_FILTERS.get(mt, mt)
                mime_clauses.append(f"mimeType = '{full_mime}'")
            if mime_clauses:
                parts.append(f"({' or '.join(mime_clauses)})")

        # Modified time filter
        since = self._get_since_datetime()
        parts.append(f"modifiedTime > '{since}'")

        # Folder scope
        if self._folder_id:
            parts.append(f"'{self._folder_id}' in parents")

        # Exclude trashed
        parts.append("trashed = false")

        return " and ".join(parts)

    def _fetch_files(self) -> list[dict[str, Any]]:
        """Fetch file metadata from Drive Files API v3."""
        if self._use_gws:
            return self._fetch_files_via_gws()

        files: list[dict[str, Any]] = []
        page_token: str | None = None

        fields = (
            "nextPageToken,"
            "files(id,name,mimeType,webViewLink,createdTime,modifiedTime,"
            "description,owners,parents,permissions(type,emailAddress,displayName,role))"
        )

        while len(files) < self._max_files:
            params: dict[str, str] = {
                "q": self._build_file_query(),
                "fields": fields,
                "pageSize": str(min(100, self._max_files - len(files))),
                "orderBy": "modifiedTime desc",
            }
            if page_token:
                params["pageToken"] = page_token

            result = self._api_request(DRIVE_FILES_URL, params)
            batch = result.get("files", [])
            files.extend(batch)

            page_token = result.get("nextPageToken")
            if not page_token or not batch:
                break

        logger.debug("Fetched %d files from Drive", len(files))
        return files[:self._max_files]

    def _fetch_files_via_gws(self) -> list[dict[str, Any]]:
        """Fetch files using the gws CLI (fallback path)."""
        try:
            args = ["drive", "+list", "--max-results", str(self._max_files)]
            if self._folder_id:
                args.extend(["--parent", self._folder_id])
            result = run_gws_command(args)
            files = result if isinstance(result, list) else result.get("files", [])
            return files[:self._max_files]
        except RuntimeError:
            logger.warning("gws drive list failed, returning empty file list")
            return []

    # ------------------------------------------------------------------
    # Stage 2: Comment threads & decision traces
    # ------------------------------------------------------------------

    def _fetch_comments(
        self,
        file_id: str,
        file_name: str,
        add_person: Any,
        entities: dict[str, list[dict[str, Any]]],
        relationships: list[dict[str, Any]],
        traces: list[dict[str, Any]],
    ) -> None:
        """Fetch comment threads from Drive Comments API v3 for a single file."""
        if self._use_gws:
            return  # gws does not support comments API; skip

        page_token: str | None = None
        comment_url = f"{DRIVE_FILES_URL}/{file_id}/comments"

        while True:
            params: dict[str, str] = {
                "fields": "*",
                "includeDeleted": "false",
                "pageSize": "100",
            }
            if page_token:
                params["pageToken"] = page_token

            try:
                result = self._api_request(comment_url, params)
            except Exception as e:
                logger.debug("Failed to fetch comments for %s: %s", file_id, e)
                return

            for comment in result.get("comments", []):
                self._process_comment(
                    comment, file_name, add_person,
                    entities, relationships, traces,
                )

            page_token = result.get("nextPageToken")
            if not page_token:
                break

    def _process_comment(
        self,
        comment: dict[str, Any],
        file_name: str,
        add_person: Any,
        entities: dict[str, list[dict[str, Any]]],
        relationships: list[dict[str, Any]],
        traces: list[dict[str, Any]],
    ) -> None:
        """Process a single comment thread into entities, relationships, and traces."""
        comment_id = comment.get("id", "")
        content = comment.get("content", "")
        resolved = comment.get("resolved", False)
        author = comment.get("author", {})
        quoted = comment.get("quotedFileContent", {}).get("value", "")
        created = comment.get("createdTime", "")
        modified = comment.get("modifiedTime", "")
        replies = comment.get("replies", [])

        # Collect participants
        participants: set[str] = set()
        author_email = author.get("emailAddress", "")
        author_name = add_person(
            author.get("displayName", ""),
            author_email,
        )
        if author_email:
            participants.add(author_email)

        # Determine resolver
        resolver_name: str | None = None
        for reply in replies:
            reply_email = reply.get("author", {}).get("emailAddress", "")
            if reply_email:
                participants.add(reply_email)
            if reply.get("action") == "resolve":
                resolver_name = add_person(
                    reply.get("author", {}).get("displayName", ""),
                    reply_email,
                )

        # Create DecisionThread entity
        thread_name = f"Thread: {content[:80]}" if content else f"Thread {comment_id}"
        resolution_text = ""
        if resolved and replies:
            # Last non-resolve reply content is the resolution
            for r in reversed(replies):
                if r.get("content"):
                    resolution_text = r["content"]
                    break

        entities["DecisionThread"].append({
            "name": thread_name,
            "driveCommentId": comment_id,
            "content": content,
            "quotedContent": quoted,
            "resolved": resolved,
            "resolution": resolution_text,
            "createdTime": created,
            "modifiedTime": modified,
            "participantCount": len(participants),
            "poleType": "Object",
        })

        # DecisionThread → Document
        relationships.append({
            "type": "HAS_COMMENT_THREAD",
            "source_name": file_name,
            "source_label": "Document",
            "target_name": thread_name,
            "target_label": "DecisionThread",
        })

        # DecisionThread → Author
        if author_name:
            relationships.append({
                "type": "AUTHORED_BY",
                "source_name": thread_name,
                "source_label": "DecisionThread",
                "target_name": author_name,
                "target_label": "Person",
            })

        # DecisionThread → Resolver
        if resolved and resolver_name:
            relationships.append({
                "type": "RESOLVED_BY",
                "source_name": thread_name,
                "source_label": "DecisionThread",
                "target_name": resolver_name,
                "target_label": "Person",
            })

        # Process replies as Reply entities
        for i, reply in enumerate(replies):
            if reply.get("action") == "resolve" and not reply.get("content"):
                continue  # Skip bare resolve actions without content

            reply_content = reply.get("content", "")
            reply_name = f"Reply {i + 1} on {thread_name}"
            reply_author = reply.get("author", {})

            entities["Reply"].append({
                "name": reply_name,
                "content": reply_content,
                "createdTime": reply.get("createdTime", ""),
                "poleType": "Object",
            })

            # Reply → DecisionThread
            relationships.append({
                "type": "HAS_REPLY",
                "source_name": thread_name,
                "source_label": "DecisionThread",
                "target_name": reply_name,
                "target_label": "Reply",
            })

            # Reply → Author
            reply_author_name = add_person(
                reply_author.get("displayName", ""),
                reply_author.get("emailAddress", ""),
            )
            if reply_author_name:
                relationships.append({
                    "type": "AUTHORED_BY",
                    "source_name": reply_name,
                    "source_label": "Reply",
                    "target_name": reply_author_name,
                    "target_label": "Person",
                })

        # Extract decision trace (only for resolved threads)
        trace = self._extract_decision_trace(comment, file_name)
        if trace:
            traces.append(trace)

    def _extract_decision_trace(
        self, comment: dict[str, Any], file_name: str,
    ) -> dict[str, Any] | None:
        """Transform a resolved comment thread into a decision trace."""
        if not comment.get("resolved"):
            return None

        comment_id = comment.get("id", "")
        content = comment.get("content", "")
        replies = comment.get("replies", [])
        author = comment.get("author", {})

        steps: list[dict[str, str]] = []

        # Step 1: The question/proposal
        steps.append({
            "thought": f"Question raised on '{file_name}': {content[:200]}",
            "action": f"{author.get('displayName', 'Someone')} started discussion",
            "observation": f"Posted at {comment.get('createdTime', 'unknown time')}",
        })

        # Steps for each reply (deliberation)
        for reply in replies:
            reply_author = reply.get("author", {})
            reply_content = reply.get("content", "")
            action_type = reply.get("action", "")

            if action_type == "resolve":
                steps.append({
                    "thought": "Thread resolved — decision made",
                    "action": f"{reply_author.get('displayName', 'Someone')} resolved the discussion",
                    "observation": f"Resolved at {reply.get('modifiedTime', reply.get('createdTime', 'unknown time'))}",
                })
            elif reply_content:
                steps.append({
                    "thought": reply_content[:200],
                    "action": f"{reply_author.get('displayName', 'Someone')} replied",
                    "observation": f"Replied at {reply.get('createdTime', 'unknown time')}",
                })

        # Determine outcome
        outcome = "Resolved"
        if replies:
            for r in reversed(replies):
                if r.get("content"):
                    outcome = f"Resolved: {r['content'][:200]}"
                    break

        return {
            "id": f"trace-gdrive-{comment_id}",
            "task": f"Decision on '{file_name}': {content[:100]}",
            "outcome": outcome,
            "steps": steps,
        }

    # ------------------------------------------------------------------
    # Stage 3: Revisions
    # ------------------------------------------------------------------

    def _fetch_revisions(
        self,
        file_id: str,
        file_name: str,
        add_person: Any,
        entities: dict[str, list[dict[str, Any]]],
        relationships: list[dict[str, Any]],
    ) -> None:
        """Fetch revision metadata from Drive Revisions API v3."""
        if self._use_gws:
            return  # gws does not support revisions API

        revision_url = f"{DRIVE_FILES_URL}/{file_id}/revisions"
        params: dict[str, str] = {
            "fields": "revisions(id,modifiedTime,lastModifyingUser,mimeType,size)",
            "pageSize": "200",
        }

        try:
            result = self._api_request(revision_url, params)
        except Exception as e:
            logger.debug("Failed to fetch revisions for %s: %s", file_id, e)
            return

        revisions = result.get("revisions", [])
        if len(revisions) == 0:
            logger.debug("No revisions returned for %s (known Google API limitation)", file_id)

        for rev in revisions:
            rev_id = rev.get("id", "")
            rev_name = f"Rev {rev_id} of {file_name}"

            entities["Revision"].append({
                "name": rev_name,
                "revisionId": rev_id,
                "modifiedTime": rev.get("modifiedTime", ""),
                "mimeType": rev.get("mimeType", ""),
                "size": rev.get("size", ""),
                "poleType": "Event",
            })

            # Revision → Document
            relationships.append({
                "type": "HAS_REVISION",
                "source_name": file_name,
                "source_label": "Document",
                "target_name": rev_name,
                "target_label": "Revision",
            })

            # Revision → Person
            user = rev.get("lastModifyingUser", {})
            if user:
                person_name = add_person(
                    user.get("displayName", ""),
                    user.get("emailAddress", ""),
                )
                if person_name:
                    relationships.append({
                        "type": "REVISED_BY",
                        "source_name": rev_name,
                        "source_label": "Revision",
                        "target_name": person_name,
                        "target_label": "Person",
                    })

    # ------------------------------------------------------------------
    # Stage 4: Drive Activity
    # ------------------------------------------------------------------

    def _fetch_activity(
        self,
        add_person: Any,
        entities: dict[str, list[dict[str, Any]]],
        relationships: list[dict[str, Any]],
    ) -> None:
        """Fetch actions from Drive Activity API v2."""
        if self._use_gws:
            return  # gws does not support Activity API

        since = self._get_since_datetime()
        body: dict[str, Any] = {
            "filter": f'time >= "{since}"',
            "pageSize": 200,
        }
        if self._folder_id:
            body["ancestorName"] = f"items/{self._folder_id}"

        page_token: str | None = None

        while True:
            if page_token:
                body["pageToken"] = page_token

            try:
                result = self._api_post(DRIVE_ACTIVITY_URL, body)
            except Exception as e:
                logger.debug("Failed to fetch Drive Activity: %s", e)
                return

            for activity in result.get("activities", []):
                self._process_activity(activity, add_person, entities, relationships)

            page_token = result.get("nextPageToken")
            if not page_token:
                break

    def _process_activity(
        self,
        activity: dict[str, Any],
        add_person: Any,
        entities: dict[str, list[dict[str, Any]]],
        relationships: list[dict[str, Any]],
    ) -> None:
        """Process a single Drive Activity item."""
        timestamp = activity.get("timestamp", "")
        if not timestamp:
            time_range = activity.get("timeRange", {})
            timestamp = time_range.get("endTime", time_range.get("startTime", ""))

        # Determine action type from primaryActionDetail
        primary = activity.get("primaryActionDetail", {})
        action_type = "unknown"
        for key in ACTION_TYPE_MAP:
            if key in primary:
                action_type = key
                break

        action_label = ACTION_TYPE_MAP.get(action_type, "Unknown action")

        # Extract actors
        actors = activity.get("actors", [])
        actor_name: str | None = None
        for actor in actors:
            user = actor.get("user", {}).get("knownUser", {})
            if user:
                # Try to extract email from other fields
                actor_email = user.get("emailAddress", "")
                if actor_email:
                    actor_name = add_person("", actor_email)

        # Extract targets
        targets = activity.get("targets", [])
        for target in targets:
            drive_item = target.get("driveItem", {})
            target_name = drive_item.get("title", drive_item.get("name", ""))
            if not target_name:
                continue

            activity_name = f"{action_label}: {target_name} at {timestamp[:19]}"

            entities["Activity"].append({
                "name": activity_name,
                "actionType": action_type,
                "actionLabel": action_label,
                "timestamp": timestamp,
                "targetName": target_name,
                "poleType": "Event",
            })

            # Activity → Document
            relationships.append({
                "type": "ACTIVITY_ON",
                "source_name": activity_name,
                "source_label": "Activity",
                "target_name": target_name,
                "target_label": "Document",
            })

            # Activity → Person
            if actor_name:
                relationships.append({
                    "type": "PERFORMED_BY",
                    "source_name": activity_name,
                    "source_label": "Activity",
                    "target_name": actor_name,
                    "target_label": "Person",
                })

    # ------------------------------------------------------------------
    # Stage 5: Calendar events (optional)
    # ------------------------------------------------------------------

    def _fetch_calendar_events(
        self,
        add_person: Any,
        entities: dict[str, list[dict[str, Any]]],
        relationships: list[dict[str, Any]],
        documents: list[dict[str, Any]],
    ) -> None:
        """Fetch calendar events and link them to documents."""
        if self._use_gws:
            self._fetch_calendar_via_gws(add_person, entities, relationships, documents)
            return

        since = self._get_since_datetime()
        now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        page_token: str | None = None

        # Build set of imported doc Drive IDs for cross-linking
        doc_drive_ids: dict[str, str] = {}
        for doc in entities.get("Document", []):
            doc_drive_ids[doc.get("driveId", "")] = doc.get("name", "")

        while True:
            params: dict[str, str] = {
                "timeMin": since,
                "timeMax": now,
                "maxResults": "250",
                "singleEvents": "true",
                "orderBy": "startTime",
            }
            if page_token:
                params["pageToken"] = page_token

            try:
                result = self._api_request(CALENDAR_EVENTS_URL, params)
            except Exception as e:
                logger.debug("Failed to fetch calendar events: %s", e)
                return

            for event in result.get("items", []):
                self._process_calendar_event(
                    event, add_person, entities, relationships,
                    documents, doc_drive_ids,
                )

            page_token = result.get("nextPageToken")
            if not page_token:
                break

    def _fetch_calendar_via_gws(
        self,
        add_person: Any,
        entities: dict[str, list[dict[str, Any]]],
        relationships: list[dict[str, Any]],
        documents: list[dict[str, Any]],
    ) -> None:
        """Fetch calendar events via gws CLI."""
        doc_drive_ids: dict[str, str] = {}
        for doc in entities.get("Document", []):
            doc_drive_ids[doc.get("driveId", "")] = doc.get("name", "")

        try:
            result = run_gws_command(["calendar", "+list", "--max-results", "250"])
            events = result if isinstance(result, list) else result.get("items", [])
            for event in events:
                self._process_calendar_event(
                    event, add_person, entities, relationships,
                    documents, doc_drive_ids,
                )
        except RuntimeError:
            logger.warning("gws calendar list failed")

    def _process_calendar_event(
        self,
        event: dict[str, Any],
        add_person: Any,
        entities: dict[str, list[dict[str, Any]]],
        relationships: list[dict[str, Any]],
        documents: list[dict[str, Any]],
        doc_drive_ids: dict[str, str],
    ) -> None:
        """Process a single calendar event."""
        summary = event.get("summary", "Untitled event")
        event_id = event.get("id", "")
        start = event.get("start", {})
        end = event.get("end", {})
        start_time = start.get("dateTime", start.get("date", ""))
        end_time = end.get("dateTime", end.get("date", ""))
        description = event.get("description", "")
        location = event.get("location", "")
        status = event.get("status", "")
        attendees = event.get("attendees", [])

        meeting_name = f"{summary} ({start_time[:10]})" if start_time else summary

        entities["Meeting"].append({
            "name": meeting_name,
            "eventId": event_id,
            "summary": summary,
            "startTime": start_time,
            "endTime": end_time,
            "location": location,
            "status": status,
            "description": description,
            "attendeeCount": len(attendees),
            "poleType": "Event",
        })

        # Organizer
        organizer = event.get("organizer", {})
        if organizer.get("email"):
            org_name = add_person(
                organizer.get("displayName", ""),
                organizer.get("email", ""),
            )
            if org_name:
                relationships.append({
                    "type": "ORGANIZED_BY",
                    "source_name": meeting_name,
                    "source_label": "Meeting",
                    "target_name": org_name,
                    "target_label": "Person",
                })

        # Attendees
        for attendee in attendees:
            if attendee.get("email"):
                att_name = add_person(
                    attendee.get("displayName", ""),
                    attendee.get("email", ""),
                )
                if att_name:
                    relationships.append({
                        "type": "ATTENDEE_OF",
                        "source_name": att_name,
                        "source_label": "Person",
                        "target_name": meeting_name,
                        "target_label": "Meeting",
                    })

        # Document-Meeting linking: scan description for Drive URLs
        if description:
            for match in DRIVE_URL_PATTERN.finditer(description):
                drive_id = match.group(1)
                doc_name = doc_drive_ids.get(drive_id)
                if doc_name:
                    relationships.append({
                        "type": "DISCUSSED_IN",
                        "source_name": doc_name,
                        "source_label": "Document",
                        "target_name": meeting_name,
                        "target_label": "Meeting",
                    })

        # Also check attachments
        for attachment in event.get("attachments", []):
            file_url = attachment.get("fileUrl", "")
            for match in DRIVE_URL_PATTERN.finditer(file_url):
                drive_id = match.group(1)
                doc_name = doc_drive_ids.get(drive_id)
                if doc_name:
                    relationships.append({
                        "type": "DISCUSSED_IN",
                        "source_name": doc_name,
                        "source_label": "Document",
                        "target_name": meeting_name,
                        "target_label": "Meeting",
                    })

        # Document entry for meeting
        if description:
            documents.append({
                "title": meeting_name,
                "content": description[:500],
                "type": "google-workspace-meeting",
                "metadata": {
                    "eventId": event_id,
                    "startTime": start_time,
                    "endTime": end_time,
                },
            })

    # ------------------------------------------------------------------
    # Stage 6: Gmail threads (optional)
    # ------------------------------------------------------------------

    def _fetch_gmail_threads(
        self,
        add_person: Any,
        entities: dict[str, list[dict[str, Any]]],
        relationships: list[dict[str, Any]],
        documents: list[dict[str, Any]],
    ) -> None:
        """Fetch Gmail thread metadata (no body text for privacy)."""
        if self._use_gws:
            self._fetch_gmail_via_gws(add_person, entities, relationships, documents)
            return

        # Build set of imported doc Drive IDs for cross-linking
        doc_drive_ids: dict[str, str] = {}
        for doc in entities.get("Document", []):
            doc_drive_ids[doc.get("driveId", "")] = doc.get("name", "")

        # Search for threads containing Drive file URLs
        params: dict[str, str] = {
            "q": "has:drive newer_than:90d",
            "maxResults": "100",
        }

        try:
            result = self._api_request(GMAIL_THREADS_URL, params)
        except Exception as e:
            logger.debug("Failed to fetch Gmail threads: %s", e)
            return

        for thread_summary in result.get("threads", []):
            thread_id = thread_summary.get("id", "")
            try:
                thread = self._api_request(
                    f"{GMAIL_THREADS_URL}/{thread_id}",
                    {"format": "metadata", "metadataHeaders": "Subject,From,To,Cc,Date"},
                )
            except Exception:
                continue

            self._process_gmail_thread(
                thread, add_person, entities, relationships,
                documents, doc_drive_ids,
            )

    def _fetch_gmail_via_gws(
        self,
        add_person: Any,
        entities: dict[str, list[dict[str, Any]]],
        relationships: list[dict[str, Any]],
        documents: list[dict[str, Any]],
    ) -> None:
        """Fetch Gmail threads via gws CLI."""
        doc_drive_ids: dict[str, str] = {}
        for doc in entities.get("Document", []):
            doc_drive_ids[doc.get("driveId", "")] = doc.get("name", "")

        try:
            result = run_gws_command([
                "gmail", "+list",
                "--max-results", "100",
                "--query", "has:drive newer_than:90d",
            ])
            messages = result if isinstance(result, list) else result.get("messages", [])
            for msg_summary in messages:
                msg_id = msg_summary.get("id", "")
                try:
                    msg = run_gws_command(["gmail", "+get", "--id", msg_id])
                except RuntimeError:
                    continue
                # Convert message format to thread-like structure
                self._process_gmail_thread(
                    {"id": msg_id, "messages": [msg]},
                    add_person, entities, relationships,
                    documents, doc_drive_ids,
                )
        except RuntimeError:
            logger.warning("gws gmail list failed")

    def _process_gmail_thread(
        self,
        thread: dict[str, Any],
        add_person: Any,
        entities: dict[str, list[dict[str, Any]]],
        relationships: list[dict[str, Any]],
        documents: list[dict[str, Any]],
        doc_drive_ids: dict[str, str],
    ) -> None:
        """Process a single Gmail thread (metadata only)."""
        thread_id = thread.get("id", "")
        messages = thread.get("messages", [])
        if not messages:
            return

        # Extract headers from first message
        subject = ""
        participants: set[str] = set()
        last_date = ""

        for msg in messages:
            for header in msg.get("payload", {}).get("headers", []):
                name = header.get("name", "").lower()
                value = header.get("value", "")
                if name == "subject" and not subject:
                    subject = value
                elif name in ("from", "to", "cc"):
                    # Extract email addresses
                    for part in value.split(","):
                        part = part.strip()
                        if "<" in part and ">" in part:
                            email = part[part.index("<") + 1:part.index(">")]
                        elif "@" in part:
                            email = part
                        else:
                            continue
                        participants.add(email.strip())
                elif name == "date":
                    last_date = value

        thread_name = subject or f"Thread {thread_id[:8]}"

        entities["EmailThread"].append({
            "name": thread_name,
            "threadId": thread_id,
            "subject": subject,
            "messageCount": len(messages),
            "lastMessageTime": last_date,
            "participantEmails": list(participants),
            "poleType": "Object",
        })

        # Participants
        for email in participants:
            person_name = add_person("", email)
            if person_name:
                relationships.append({
                    "type": "PARTICIPANT_IN",
                    "source_name": person_name,
                    "source_label": "Person",
                    "target_name": thread_name,
                    "target_label": "EmailThread",
                })

        # Thread → Document linking (scan subject for Drive URLs)
        all_text = subject
        for msg in messages:
            snippet = msg.get("snippet", "")
            all_text += " " + snippet
        for match in DRIVE_URL_PATTERN.finditer(all_text):
            drive_id = match.group(1)
            doc_name = doc_drive_ids.get(drive_id)
            if doc_name:
                relationships.append({
                    "type": "THREAD_ABOUT",
                    "source_name": thread_name,
                    "source_label": "EmailThread",
                    "target_name": doc_name,
                    "target_label": "Document",
                })

        # Document entry (metadata only)
        documents.append({
            "title": thread_name,
            "content": f"Email thread with {len(messages)} messages. Participants: {', '.join(sorted(participants))}",
            "type": "google-workspace-email",
            "metadata": {
                "threadId": thread_id,
                "messageCount": len(messages),
                "lastMessageTime": last_date,
            },
        })

    # ------------------------------------------------------------------
    # Stage 7: Cross-connector linking
    # ------------------------------------------------------------------

    def _build_cross_references(
        self,
        entities: dict[str, list[dict[str, Any]]],
        documents: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """Scan text content for Linear issue references and create cross-links."""
        cross_refs: list[dict[str, Any]] = []
        seen: set[tuple[str, str, str]] = set()  # (source_name, source_label, target_id)

        def _scan_and_link(text: str, source_name: str, source_label: str) -> None:
            for match in LINEAR_REF_PATTERN.finditer(text):
                identifier = match.group(1)
                key = (source_name, source_label, identifier)
                if key not in seen:
                    seen.add(key)
                    cross_refs.append({
                        "type": "RELATES_TO_ISSUE",
                        "source_name": source_name,
                        "source_label": source_label,
                        "target_name": identifier,
                        "target_label": "Issue",
                    })

        # Scan DecisionThread content
        for dt in entities.get("DecisionThread", []):
            content = dt.get("content", "")
            if content:
                _scan_and_link(content, dt["name"], "DecisionThread")

        # Scan Reply content
        for reply in entities.get("Reply", []):
            content = reply.get("content", "")
            if content:
                _scan_and_link(content, reply["name"], "Reply")

        # Scan Document names
        for doc in entities.get("Document", []):
            name = doc.get("name", "")
            if name:
                _scan_and_link(name, name, "Document")

        # Scan EmailThread subjects
        for thread in entities.get("EmailThread", []):
            subject = thread.get("subject", "")
            if subject:
                _scan_and_link(subject, thread["name"], "EmailThread")

        # Scan Meeting descriptions
        for meeting in entities.get("Meeting", []):
            desc = meeting.get("description", "")
            if desc:
                _scan_and_link(desc, meeting["name"], "Meeting")

        return cross_refs
