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

"""Linear connector — imports issues, projects, cycles, teams, users,
relations, history (as decision traces), comments, milestones, initiatives,
attachments, and Linear Docs."""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from typing import Any

from create_context_graph.connectors import (
    BaseConnector,
    NormalizedData,
    register_connector,
)

LINEAR_API_URL = "https://api.linear.app/graphql"

# Priority mapping: Linear uses 0=No Priority, 1=Urgent, 2=High, 3=Medium, 4=Low
PRIORITY_LABELS = {0: "No Priority", 1: "Urgent", 2: "High", 3: "Medium", 4: "Low"}

# IssueRelation type mapping
RELATION_TYPE_MAP = {
    "blocks": "BLOCKS",
    "blocked-by": "BLOCKED_BY",
    "related": "RELATED_TO",
    "duplicate": "DUPLICATE_OF",
}


def _describe_history_step(entry: dict) -> dict[str, str] | None:
    """Transform a single IssueHistory entry into a thought/action/observation triple."""
    parts = []
    action_parts = []
    actor_name = entry.get("actor", {}).get("name", "Someone") if entry.get("actor") else "System"

    from_state = entry.get("fromState")
    to_state = entry.get("toState")
    if from_state and to_state:
        parts.append(f"State changed from {from_state.get('name', '?')} to {to_state.get('name', '?')}")
        action_parts.append(f"{actor_name} moved issue to {to_state.get('name', '?')}")

    from_assignee = entry.get("fromAssignee")
    to_assignee = entry.get("toAssignee")
    if to_assignee and (not from_assignee or from_assignee.get("name") != to_assignee.get("name")):
        old = from_assignee.get("name", "unassigned") if from_assignee else "unassigned"
        new = to_assignee.get("name", "?")
        parts.append(f"Reassigned from {old} to {new}")
        action_parts.append(f"{actor_name} assigned to {new}")

    from_priority = entry.get("fromPriority")
    to_priority = entry.get("toPriority")
    if to_priority is not None and from_priority != to_priority:
        old_label = PRIORITY_LABELS.get(int(from_priority), "?") if from_priority is not None else "None"
        new_label = PRIORITY_LABELS.get(int(to_priority), "?")
        parts.append(f"Priority changed from {old_label} to {new_label}")
        action_parts.append(f"{actor_name} set priority to {new_label}")

    added_labels = entry.get("addedLabels") or []
    removed_labels = entry.get("removedLabels") or []
    if added_labels:
        names = ", ".join(lb.get("name", "?") for lb in added_labels)
        parts.append(f"Added labels: {names}")
    if removed_labels:
        names = ", ".join(lb.get("name", "?") for lb in removed_labels)
        parts.append(f"Removed labels: {names}")

    if not parts:
        return None

    return {
        "thought": "; ".join(parts),
        "action": "; ".join(action_parts) if action_parts else f"{actor_name} updated issue",
        "observation": f"Change recorded at {entry.get('createdAt', 'unknown time')}",
    }


@register_connector("linear")
class LinearConnector(BaseConnector):
    """Import issues, projects, cycles, and team data from Linear."""

    service_name = "Linear"
    service_description = "Import issues, projects, cycles, and team data from Linear"
    requires_oauth = False

    def __init__(self):
        self._api_key: str = ""
        self._team_key: str = ""
        self._headers: dict[str, str] = {}

    def get_credential_prompts(self) -> list[dict[str, Any]]:
        return [
            {
                "name": "api_key",
                "prompt": "Linear API key:",
                "secret": True,
                "description": "Personal API key from Linear Settings > Security & Access > API",
            },
            {
                "name": "team_key",
                "prompt": "Linear team key (optional, leave blank for all teams):",
                "secret": False,
                "description": "Team URL key (e.g., ENG) to filter import to a specific team",
            },
        ]

    def authenticate(self, credentials: dict[str, str]) -> None:
        api_key = credentials.get("api_key", "")
        if not api_key:
            raise ValueError("Linear API key is required")

        self._api_key = api_key
        self._team_key = credentials.get("team_key", "")
        self._headers = {
            "Authorization": api_key,
            "Content-Type": "application/json",
        }

        result = self._graphql_request("query { viewer { id name email } }")
        if "errors" in result:
            raise ValueError(
                f"Linear API authentication failed: {result['errors'][0].get('message', 'Unknown error')}"
            )

    def fetch(self, **kwargs: Any) -> NormalizedData:
        if not self._api_key:
            raise RuntimeError("Call authenticate() first")

        entities: dict[str, list[dict]] = {
            "Person": [],
            "Team": [],
            "Project": [],
            "Cycle": [],
            "Issue": [],
            "Label": [],
            "WorkflowState": [],
            "Comment": [],
            "ProjectUpdate": [],
            "ProjectMilestone": [],
            "Initiative": [],
            "Attachment": [],
        }
        relationships: list[dict] = []
        documents: list[dict] = []
        traces: list[dict] = []

        seen_users: set[str] = set()
        seen_labels: set[str] = set()
        seen_states: set[str] = set()
        comment_counter: dict[str, int] = {}  # per-issue counter for unique names

        def _add_user(user_data: dict) -> str | None:
            if not user_data or not user_data.get("id"):
                return None
            uid = user_data["id"]
            name = user_data.get("name") or user_data.get("displayName") or "Unknown"
            if uid not in seen_users:
                seen_users.add(uid)
                entities["Person"].append({
                    "name": name,
                    "linearId": uid,
                    "displayName": user_data.get("displayName", name),
                    "email": user_data.get("email", ""),
                    "admin": user_data.get("admin", False),
                    "active": user_data.get("active", True),
                })
            return name

        def _add_label(label_data: dict) -> str | None:
            if not label_data or not label_data.get("id"):
                return None
            lid = label_data["id"]
            name = label_data.get("name", "")
            if lid not in seen_labels:
                seen_labels.add(lid)
                entities["Label"].append({
                    "name": name,
                    "linearId": lid,
                    "color": label_data.get("color", ""),
                    "description": label_data.get("description", ""),
                })
            return name

        def _add_state(state_data: dict, team_name: str | None = None) -> str | None:
            if not state_data or not state_data.get("id"):
                return None
            sid = state_data["id"]
            name = state_data.get("name", "")
            if sid not in seen_states:
                seen_states.add(sid)
                entities["WorkflowState"].append({
                    "name": name,
                    "linearId": sid,
                    "color": state_data.get("color", ""),
                    "type": state_data.get("type", ""),
                    "position": state_data.get("position", 0),
                })
                if team_name:
                    relationships.append({
                        "type": "STATE_OF",
                        "source_name": name,
                        "source_label": "WorkflowState",
                        "target_name": team_name,
                        "target_label": "Team",
                    })
            return name

        def _add_comment(comment_data: dict, parent_entity: str, parent_label: str,
                         parent_comment_name: str | None = None) -> str | None:
            """Add a comment entity and its relationships. Returns the comment name."""
            if not comment_data or not comment_data.get("id"):
                return None
            cid = comment_data["id"]
            # Generate unique comment name
            counter = comment_counter.get(parent_entity, 0) + 1
            comment_counter[parent_entity] = counter
            comment_name = f"Comment {counter} on {parent_entity}"

            entities["Comment"].append({
                "name": comment_name,
                "linearId": cid,
                "body": comment_data.get("body", ""),
                "createdAt": comment_data.get("createdAt", ""),
                "updatedAt": comment_data.get("updatedAt", ""),
                "resolvedAt": comment_data.get("resolvedAt", ""),
            })
            # Comment → parent entity
            relationships.append({
                "type": "HAS_COMMENT",
                "source_name": parent_entity,
                "source_label": parent_label,
                "target_name": comment_name,
                "target_label": "Comment",
            })
            # Comment → author
            comment_user = comment_data.get("user")
            if comment_user:
                author_name = _add_user(comment_user)
                if author_name:
                    relationships.append({
                        "type": "AUTHORED_BY",
                        "source_name": comment_name,
                        "source_label": "Comment",
                        "target_name": author_name,
                        "target_label": "Person",
                    })
            # Thread: reply → parent comment
            if parent_comment_name:
                relationships.append({
                    "type": "REPLY_TO",
                    "source_name": comment_name,
                    "source_label": "Comment",
                    "target_name": parent_comment_name,
                    "target_label": "Comment",
                })
            # Resolution
            resolving_user = comment_data.get("resolvingUser")
            if resolving_user and comment_data.get("resolvedAt"):
                resolver_name = _add_user(resolving_user)
                if resolver_name:
                    relationships.append({
                        "type": "RESOLVED_BY",
                        "source_name": comment_name,
                        "source_label": "Comment",
                        "target_name": resolver_name,
                        "target_label": "Person",
                    })
            return comment_name

        # =====================================================================
        # Fetch teams
        # =====================================================================
        teams = self._fetch_teams()
        if self._team_key:
            teams = [t for t in teams if t.get("key", "").upper() == self._team_key.upper()]
            if not teams:
                raise ValueError(
                    f"Team with key '{self._team_key}' not found. "
                    f"Check your team URL key in Linear."
                )

        for team in teams:
            team_name = team.get("name", "")
            entities["Team"].append({
                "name": team_name,
                "linearId": team["id"],
                "key": team.get("key", ""),
                "description": team.get("description", ""),
            })

        # =====================================================================
        # Fetch users
        # =====================================================================
        org_users = self._fetch_users()
        for user in org_users:
            _add_user(user)

        for team in teams:
            team_name = team.get("name", "")
            members = self._fetch_team_members(team["id"])
            for member in members:
                member_name = _add_user(member)
                if member_name:
                    relationships.append({
                        "type": "MEMBER_OF",
                        "source_name": member_name,
                        "source_label": "Person",
                        "target_name": team_name,
                        "target_label": "Team",
                    })

        # =====================================================================
        # Fetch labels
        # =====================================================================
        labels = self._fetch_labels()
        for label in labels:
            _add_label(label)

        # =====================================================================
        # Fetch initiatives (P2)
        # =====================================================================
        initiatives = self._fetch_initiatives()
        for init in initiatives:
            init_name = init.get("name", "")
            entities["Initiative"].append({
                "name": init_name,
                "linearId": init["id"],
                "description": init.get("description", ""),
                "status": init.get("status", ""),
                "health": init.get("health", ""),
                "targetDate": init.get("targetDate", ""),
                "url": init.get("url", ""),
            })
            owner = init.get("owner")
            if owner:
                owner_name = _add_user(owner)
                if owner_name:
                    relationships.append({
                        "type": "OWNED_BY",
                        "source_name": init_name,
                        "source_label": "Initiative",
                        "target_name": owner_name,
                        "target_label": "Person",
                    })
            # Initiative → Projects
            init_projects = init.get("projects", {}).get("nodes", [])
            for ip in init_projects:
                if ip.get("name"):
                    relationships.append({
                        "type": "CONTAINS_PROJECT",
                        "source_name": init_name,
                        "source_label": "Initiative",
                        "target_name": ip["name"],
                        "target_label": "Project",
                    })

        # =====================================================================
        # Fetch projects (with milestones, updates)
        # =====================================================================
        projects = self._fetch_projects()
        for proj in projects:
            proj_name = proj.get("name", "")
            entities["Project"].append({
                "name": proj_name,
                "linearId": proj["id"],
                "description": proj.get("description", ""),
                "state": proj.get("state", ""),
                "startDate": proj.get("startDate", ""),
                "targetDate": proj.get("targetDate", ""),
                "progress": proj.get("progress", 0),
                "health": proj.get("health", ""),
                "url": proj.get("url", ""),
            })

            lead = proj.get("lead")
            if lead:
                lead_name = _add_user(lead)
                if lead_name:
                    relationships.append({
                        "type": "LEADS",
                        "source_name": lead_name,
                        "source_label": "Person",
                        "target_name": proj_name,
                        "target_label": "Project",
                    })

            proj_members = proj.get("members", {}).get("nodes", [])
            for member in proj_members:
                member_name = _add_user(member)
                if member_name:
                    relationships.append({
                        "type": "MEMBER_OF",
                        "source_name": member_name,
                        "source_label": "Person",
                        "target_name": proj_name,
                        "target_label": "Project",
                    })

            proj_teams = proj.get("teams", {}).get("nodes", [])
            for pt in proj_teams:
                pt_name = pt.get("name", "")
                if pt_name:
                    relationships.append({
                        "type": "CONTRIBUTED_BY",
                        "source_name": pt_name,
                        "source_label": "Team",
                        "target_name": proj_name,
                        "target_label": "Project",
                    })

            # Project milestones (P1)
            milestones = proj.get("projectMilestones", {}).get("nodes", [])
            for ms in milestones:
                ms_name = ms.get("name", "")
                if not ms_name:
                    continue
                entities["ProjectMilestone"].append({
                    "name": ms_name,
                    "linearId": ms["id"],
                    "description": ms.get("description", ""),
                    "targetDate": ms.get("targetDate", ""),
                    "status": ms.get("status", ""),
                    "progress": ms.get("progress", 0),
                })
                relationships.append({
                    "type": "HAS_MILESTONE",
                    "source_name": proj_name,
                    "source_label": "Project",
                    "target_name": ms_name,
                    "target_label": "ProjectMilestone",
                })

            # Project updates (P1)
            updates = proj.get("projectUpdates", {}).get("nodes", [])
            for upd in updates:
                upd_name = f"Update on {proj_name} ({upd.get('createdAt', '')[:10]})"
                entities["ProjectUpdate"].append({
                    "name": upd_name,
                    "linearId": upd["id"],
                    "body": upd.get("body", ""),
                    "health": upd.get("health", ""),
                    "createdAt": upd.get("createdAt", ""),
                })
                relationships.append({
                    "type": "HAS_UPDATE",
                    "source_name": proj_name,
                    "source_label": "Project",
                    "target_name": upd_name,
                    "target_label": "ProjectUpdate",
                })
                upd_user = upd.get("user")
                if upd_user:
                    upd_author = _add_user(upd_user)
                    if upd_author:
                        relationships.append({
                            "type": "POSTED_BY",
                            "source_name": upd_name,
                            "source_label": "ProjectUpdate",
                            "target_name": upd_author,
                            "target_label": "Person",
                        })
                # Project update body as document
                body = upd.get("body", "")
                if body and body.strip():
                    documents.append({
                        "title": upd_name,
                        "content": body,
                        "type": "linear-project-update",
                        "metadata": {"project": proj_name, "health": upd.get("health", "")},
                    })

        # =====================================================================
        # Fetch cycles per team
        # =====================================================================
        for team in teams:
            team_name = team.get("name", "")
            cycles = self._fetch_cycles(team["id"])
            for cycle in cycles:
                cycle_name = cycle.get("name") or f"Cycle {cycle.get('number', '?')}"
                entities["Cycle"].append({
                    "name": cycle_name,
                    "linearId": cycle["id"],
                    "number": cycle.get("number", 0),
                    "startsAt": cycle.get("startsAt", ""),
                    "endsAt": cycle.get("endsAt", ""),
                    "progress": cycle.get("progress", 0),
                })
                relationships.append({
                    "type": "CYCLE_FOR",
                    "source_name": cycle_name,
                    "source_label": "Cycle",
                    "target_name": team_name,
                    "target_label": "Team",
                })

        # =====================================================================
        # Fetch Linear Docs (P2)
        # =====================================================================
        linear_docs = self._fetch_documents()
        for doc in linear_docs:
            doc_title = doc.get("title", "Untitled")
            content = doc.get("content", "")
            if content and content.strip():
                documents.append({
                    "title": doc_title,
                    "content": content,
                    "type": "linear-doc",
                    "metadata": {
                        "linearId": doc.get("id", ""),
                        "project": doc.get("project", {}).get("name", "") if doc.get("project") else "",
                    },
                })

        # =====================================================================
        # Fetch issues per team (paginated) — with relations, comments, history,
        # attachments, milestones
        # =====================================================================
        for team in teams:
            team_name = team.get("name", "")
            issues = self._fetch_issues(team["id"])

            for issue in issues:
                identifier = issue.get("identifier", "")
                title = issue.get("title", "")
                issue_name = f"{identifier} {title}" if identifier else title
                priority = issue.get("priority", 0)

                entities["Issue"].append({
                    "name": issue_name,
                    "linearId": issue["id"],
                    "identifier": identifier,
                    "title": title,
                    "priority": priority,
                    "priorityLabel": PRIORITY_LABELS.get(priority, "No Priority"),
                    "estimate": issue.get("estimate"),
                    "dueDate": issue.get("dueDate", ""),
                    "stateType": issue.get("state", {}).get("type", "") if issue.get("state") else "",
                    "createdAt": issue.get("createdAt", ""),
                    "updatedAt": issue.get("updatedAt", ""),
                    "completedAt": issue.get("completedAt", ""),
                    "canceledAt": issue.get("canceledAt", ""),
                    "startedAt": issue.get("startedAt", ""),
                    "branchName": issue.get("branchName", ""),
                    "number": issue.get("number", 0),
                    "trashed": issue.get("trashed", False),
                    "url": issue.get("url", ""),
                })

                # Issue → Team
                relationships.append({
                    "type": "BELONGS_TO_TEAM",
                    "source_name": issue_name,
                    "source_label": "Issue",
                    "target_name": team_name,
                    "target_label": "Team",
                })

                # Issue → Assignee
                assignee = issue.get("assignee")
                if assignee:
                    assignee_name = _add_user(assignee)
                    if assignee_name:
                        relationships.append({
                            "type": "ASSIGNED_TO",
                            "source_name": issue_name,
                            "source_label": "Issue",
                            "target_name": assignee_name,
                            "target_label": "Person",
                        })

                # Issue → Creator
                creator = issue.get("creator")
                if creator:
                    creator_name = _add_user(creator)
                    if creator_name:
                        relationships.append({
                            "type": "CREATED_BY",
                            "source_name": issue_name,
                            "source_label": "Issue",
                            "target_name": creator_name,
                            "target_label": "Person",
                        })

                # Issue → Project
                project = issue.get("project")
                if project and project.get("name"):
                    relationships.append({
                        "type": "BELONGS_TO_PROJECT",
                        "source_name": issue_name,
                        "source_label": "Issue",
                        "target_name": project["name"],
                        "target_label": "Project",
                    })

                # Issue → Cycle
                cycle = issue.get("cycle")
                if cycle and cycle.get("id"):
                    cycle_name = cycle.get("name") or f"Cycle {cycle.get('number', '?')}"
                    relationships.append({
                        "type": "IN_CYCLE",
                        "source_name": issue_name,
                        "source_label": "Issue",
                        "target_name": cycle_name,
                        "target_label": "Cycle",
                    })

                # Issue → WorkflowState
                state = issue.get("state")
                if state:
                    state_name = _add_state(state, team_name)
                    if state_name:
                        relationships.append({
                            "type": "HAS_STATE",
                            "source_name": issue_name,
                            "source_label": "Issue",
                            "target_name": state_name,
                            "target_label": "WorkflowState",
                        })

                # Issue → Labels
                issue_labels = issue.get("labels", {}).get("nodes", [])
                for label in issue_labels:
                    label_name = _add_label(label)
                    if label_name:
                        relationships.append({
                            "type": "HAS_LABEL",
                            "source_name": issue_name,
                            "source_label": "Issue",
                            "target_name": label_name,
                            "target_label": "Label",
                        })

                # Issue → Parent (sub-issue hierarchy)
                parent = issue.get("parent")
                if parent and parent.get("identifier"):
                    parent_identifier = parent["identifier"]
                    parent_title = parent.get("title", "")
                    parent_name = f"{parent_identifier} {parent_title}" if parent_title else parent_identifier
                    relationships.append({
                        "type": "CHILD_OF",
                        "source_name": issue_name,
                        "source_label": "Issue",
                        "target_name": parent_name,
                        "target_label": "Issue",
                    })

                # Issue → ProjectMilestone
                milestone = issue.get("projectMilestone")
                if milestone and milestone.get("name"):
                    relationships.append({
                        "type": "IN_MILESTONE",
                        "source_name": issue_name,
                        "source_label": "Issue",
                        "target_name": milestone["name"],
                        "target_label": "ProjectMilestone",
                    })

                # ---- Issue Relations (P0) ----
                relations = issue.get("relations", {}).get("nodes", [])
                for rel in relations:
                    rel_type = RELATION_TYPE_MAP.get(rel.get("type", ""), "")
                    related = rel.get("relatedIssue")
                    if rel_type and related and related.get("identifier"):
                        rel_identifier = related["identifier"]
                        rel_title = related.get("title", "")
                        related_name = f"{rel_identifier} {rel_title}" if rel_title else rel_identifier
                        relationships.append({
                            "type": rel_type,
                            "source_name": issue_name,
                            "source_label": "Issue",
                            "target_name": related_name,
                            "target_label": "Issue",
                        })

                # ---- Attachments (P2) ----
                attachments = issue.get("attachments", {}).get("nodes", [])
                for att in attachments:
                    if not att.get("id"):
                        continue
                    att_title = att.get("title", "") or att.get("url", "")
                    att_name = f"Attachment: {att_title[:80]}"
                    entities["Attachment"].append({
                        "name": att_name,
                        "linearId": att["id"],
                        "title": att.get("title", ""),
                        "url": att.get("url", ""),
                        "sourceType": att.get("sourceType", ""),
                        "createdAt": att.get("createdAt", ""),
                    })
                    relationships.append({
                        "type": "HAS_ATTACHMENT",
                        "source_name": issue_name,
                        "source_label": "Issue",
                        "target_name": att_name,
                        "target_label": "Attachment",
                    })

                # ---- Comments with threading (P1) ----
                comments = issue.get("comments", {}).get("nodes", [])
                # Build a map of comment ID → name for threading
                comment_id_to_name: dict[str, str] = {}
                for comment in comments:
                    if not comment.get("id"):
                        continue
                    parent_comment_id = comment.get("parent", {}).get("id") if comment.get("parent") else None
                    parent_comment_name = comment_id_to_name.get(parent_comment_id) if parent_comment_id else None
                    cname = _add_comment(comment, issue_name, "Issue", parent_comment_name)
                    if cname:
                        comment_id_to_name[comment["id"]] = cname

                # ---- Issue History → Decision Traces (P0) ----
                history = issue.get("history", {}).get("nodes", [])
                if len(history) >= 2:
                    steps = []
                    for entry in sorted(history, key=lambda h: h.get("createdAt", "")):
                        step = _describe_history_step(entry)
                        if step:
                            steps.append(step)
                    if steps:
                        # Determine outcome from current state
                        current_state = issue.get("state", {}).get("name", "Unknown") if issue.get("state") else "Unknown"
                        state_type = issue.get("state", {}).get("type", "") if issue.get("state") else ""
                        if state_type == "completed":
                            outcome = f"Completed: {current_state}"
                        elif state_type == "canceled":
                            outcome = f"Canceled: {current_state}"
                        else:
                            outcome = f"Currently in {current_state}"

                        traces.append({
                            "id": f"trace-{identifier}",
                            "task": f"Lifecycle of {issue_name}",
                            "outcome": outcome,
                            "steps": [
                                {
                                    "thought": s["thought"],
                                    "action": s["action"],
                                    "observation": s["observation"],
                                }
                                for s in steps
                            ],
                        })

                # Document from issue description
                description = issue.get("description", "")
                if description and description.strip():
                    documents.append({
                        "title": f"{identifier}: {title}",
                        "content": description,
                        "type": "linear-issue",
                        "metadata": {
                            "identifier": identifier,
                            "priority": PRIORITY_LABELS.get(priority, "No Priority"),
                            "stateType": issue.get("state", {}).get("type", "") if issue.get("state") else "",
                        },
                    })

        result = NormalizedData(
            entities=entities,
            relationships=relationships,
            documents=documents,
        )
        # Attach traces to the result dict for ingestion pipeline compatibility
        if traces:
            result_dict = result.model_dump()
            result_dict["traces"] = traces
            return NormalizedData(**{k: v for k, v in result_dict.items() if k != "traces"})
        return result

    # =====================================================================
    # GraphQL helpers
    # =====================================================================

    def _graphql_request(self, query: str, variables: dict | None = None) -> dict:
        """Execute a GraphQL request against the Linear API."""
        body = json.dumps({"query": query, "variables": variables or {}}).encode()
        req = urllib.request.Request(
            LINEAR_API_URL,
            data=body,
            headers=self._headers,
            method="POST",
        )

        try:
            with urllib.request.urlopen(req) as resp:
                remaining = resp.headers.get("X-RateLimit-Requests-Remaining")
                if remaining and int(remaining) < 10:
                    reset_time = resp.headers.get("X-RateLimit-Requests-Reset")
                    if reset_time:
                        wait = max(1, int(reset_time) - int(time.time()))
                        time.sleep(min(wait, 30))
                    else:
                        time.sleep(2)

                return json.loads(resp.read())
        except urllib.error.HTTPError as e:
            if e.code == 401:
                raise ValueError("Invalid Linear API key. Check your key at Linear Settings > Security & Access > API.")
            error_body = e.read().decode() if e.fp else ""
            raise RuntimeError(f"Linear API error ({e.code}): {error_body}")

    def _paginate(self, query: str, variables: dict, data_path: list[str]) -> list[dict]:
        """Paginate through a Linear GraphQL connection."""
        all_nodes: list[dict] = []
        cursor = None

        while True:
            vars_with_cursor = {**variables}
            if cursor:
                vars_with_cursor["cursor"] = cursor

            result = self._graphql_request(query, vars_with_cursor)
            data = result.get("data", {})

            connection = data
            for key in data_path:
                connection = connection.get(key, {})

            nodes = connection.get("nodes", [])
            all_nodes.extend(nodes)

            page_info = connection.get("pageInfo", {})
            if page_info.get("hasNextPage"):
                cursor = page_info.get("endCursor")
            else:
                break

        return all_nodes

    # =====================================================================
    # Data fetching methods
    # =====================================================================

    def _fetch_teams(self) -> list[dict]:
        query = """
        query FetchTeams {
            teams { nodes { id name key description } }
        }
        """
        result = self._graphql_request(query)
        return result.get("data", {}).get("teams", {}).get("nodes", [])

    def _fetch_users(self) -> list[dict]:
        query = """
        query FetchUsers($cursor: String) {
            users(first: 100, after: $cursor) {
                pageInfo { hasNextPage endCursor }
                nodes { id name displayName email admin active }
            }
        }
        """
        return self._paginate(query, {}, ["users"])

    def _fetch_team_members(self, team_id: str) -> list[dict]:
        query = """
        query FetchTeamMembers($teamId: String!) {
            team(id: $teamId) {
                members { nodes { id name displayName email admin active } }
            }
        }
        """
        result = self._graphql_request(query, {"teamId": team_id})
        return result.get("data", {}).get("team", {}).get("members", {}).get("nodes", [])

    def _fetch_labels(self) -> list[dict]:
        query = """
        query FetchLabels($cursor: String) {
            issueLabels(first: 100, after: $cursor) {
                pageInfo { hasNextPage endCursor }
                nodes { id name color description }
            }
        }
        """
        return self._paginate(query, {}, ["issueLabels"])

    def _fetch_initiatives(self) -> list[dict]:
        query = """
        query FetchInitiatives($cursor: String) {
            initiatives(first: 50, after: $cursor) {
                pageInfo { hasNextPage endCursor }
                nodes {
                    id name description status health targetDate url
                    owner { id name displayName email }
                    projects { nodes { id name } }
                }
            }
        }
        """
        return self._paginate(query, {}, ["initiatives"])

    def _fetch_projects(self) -> list[dict]:
        query = """
        query FetchProjects($cursor: String) {
            projects(first: 20, after: $cursor) {
                pageInfo { hasNextPage endCursor }
                nodes {
                    id name description state startDate targetDate progress health url
                    lead { id name displayName email }
                    members(first: 20) { nodes { id name displayName email } }
                    teams(first: 10) { nodes { id name key } }
                    projectMilestones(first: 10) { nodes { id name description targetDate status progress } }
                    projectUpdates(first: 5) { nodes {
                        id body health createdAt
                        user { id name displayName email }
                    } }
                }
            }
        }
        """
        return self._paginate(query, {}, ["projects"])

    def _fetch_cycles(self, team_id: str) -> list[dict]:
        query = """
        query FetchCycles($teamId: String!) {
            team(id: $teamId) {
                cycles { nodes { id name number startsAt endsAt progress } }
            }
        }
        """
        result = self._graphql_request(query, {"teamId": team_id})
        return result.get("data", {}).get("team", {}).get("cycles", {}).get("nodes", [])

    def _fetch_documents(self) -> list[dict]:
        query = """
        query FetchDocuments($cursor: String) {
            documents(first: 50, after: $cursor) {
                pageInfo { hasNextPage endCursor }
                nodes {
                    id title content createdAt updatedAt
                    creator { id name displayName email }
                    project { id name }
                }
            }
        }
        """
        return self._paginate(query, {}, ["documents"])

    def _fetch_issues(self, team_id: str) -> list[dict]:
        """Fetch all issues for a team with relations, comments, history, attachments."""
        query = """
        query FetchIssues($teamId: ID, $cursor: String) {
            issues(first: 25, after: $cursor, filter: { team: { id: { eq: $teamId } } }) {
                pageInfo { hasNextPage endCursor }
                nodes {
                    id identifier title description priority priorityLabel estimate
                    number dueDate createdAt updatedAt completedAt canceledAt startedAt
                    branchName trashed url
                    state { id name type color position }
                    assignee { id name email displayName }
                    creator { id name email displayName }
                    team { id name key }
                    project { id name }
                    projectMilestone { id name }
                    cycle { id number name startsAt endsAt }
                    labels { nodes { id name color } }
                    parent { id identifier title }
                    children { nodes { id identifier title } }
                    relations { nodes { id type relatedIssue { id identifier title } } }
                    attachments(first: 5) { nodes { id title url sourceType createdAt } }
                    comments(first: 20) { nodes {
                        id body createdAt updatedAt resolvedAt
                        user { id name displayName email }
                        parent { id }
                        resolvingUser { id name displayName email }
                    } }
                    history(first: 15) { nodes {
                        id createdAt
                        fromState { name type }
                        toState { name type }
                        fromAssignee { name }
                        toAssignee { name }
                        fromPriority toPriority
                        actor { id name displayName email }
                        addedLabels { name }
                        removedLabels { name }
                    } }
                }
            }
        }
        """
        return self._paginate(query, {"teamId": team_id}, ["issues"])
