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

"""Linear connector — imports issues, projects, cycles, teams, and users."""

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

        # Validate the API key with a viewer query
        result = self._graphql_request("query { viewer { id name email } }")
        if "errors" in result:
            raise ValueError(
                f"Linear API authentication failed: {result['errors'][0].get('message', 'Unknown error')}"
            )

    def fetch(self, **kwargs: Any) -> NormalizedData:
        if not self._api_key:
            raise RuntimeError("Call authenticate() first")

        include_comments = kwargs.get("include_comments", False)

        entities: dict[str, list[dict]] = {
            "Person": [],
            "Team": [],
            "Project": [],
            "Cycle": [],
            "Issue": [],
            "Label": [],
            "WorkflowState": [],
        }
        if include_comments:
            entities["Comment"] = []

        relationships: list[dict] = []
        documents: list[dict] = []

        seen_users: set[str] = set()
        seen_labels: set[str] = set()
        seen_states: set[str] = set()

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
                        "source": name,
                        "source_label": "WorkflowState",
                        "target": team_name,
                        "target_label": "Team",
                    })
            return name

        # --- Fetch teams ---
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

        # --- Fetch users (organization members) ---
        org_users = self._fetch_users()
        for user in org_users:
            _add_user(user)

        # --- Fetch team members and associate ---
        for team in teams:
            team_name = team.get("name", "")
            members = self._fetch_team_members(team["id"])
            for member in members:
                member_name = _add_user(member)
                if member_name:
                    relationships.append({
                        "type": "MEMBER_OF",
                        "source": member_name,
                        "source_label": "Person",
                        "target": team_name,
                        "target_label": "Team",
                    })

        # --- Fetch labels ---
        labels = self._fetch_labels()
        for label in labels:
            _add_label(label)

        # --- Fetch projects ---
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
                "url": proj.get("url", ""),
            })

            # Project lead
            lead = proj.get("lead")
            if lead:
                lead_name = _add_user(lead)
                if lead_name:
                    relationships.append({
                        "type": "LEADS",
                        "source": lead_name,
                        "source_label": "Person",
                        "target": proj_name,
                        "target_label": "Project",
                    })

            # Project members
            proj_members = proj.get("members", {}).get("nodes", [])
            for member in proj_members:
                member_name = _add_user(member)
                if member_name:
                    relationships.append({
                        "type": "MEMBER_OF",
                        "source": member_name,
                        "source_label": "Person",
                        "target": proj_name,
                        "target_label": "Project",
                    })

            # Project teams
            proj_teams = proj.get("teams", {}).get("nodes", [])
            for pt in proj_teams:
                pt_name = pt.get("name", "")
                if pt_name:
                    relationships.append({
                        "type": "CONTRIBUTED_BY",
                        "source": pt_name,
                        "source_label": "Team",
                        "target": proj_name,
                        "target_label": "Project",
                    })

        # --- Fetch cycles per team ---
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
                    "url": cycle.get("url", ""),
                })
                relationships.append({
                    "type": "CYCLE_FOR",
                    "source": cycle_name,
                    "source_label": "Cycle",
                    "target": team_name,
                    "target_label": "Team",
                })

        # --- Fetch issues per team (paginated) ---
        for team in teams:
            team_name = team.get("name", "")
            issues = self._fetch_issues(team["id"], include_comments=include_comments)

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
                    "url": issue.get("url", ""),
                })

                # Issue → Team
                relationships.append({
                    "type": "BELONGS_TO_TEAM",
                    "source": issue_name,
                    "source_label": "Issue",
                    "target": team_name,
                    "target_label": "Team",
                })

                # Issue → Assignee
                assignee = issue.get("assignee")
                if assignee:
                    assignee_name = _add_user(assignee)
                    if assignee_name:
                        relationships.append({
                            "type": "ASSIGNED_TO",
                            "source": issue_name,
                            "source_label": "Issue",
                            "target": assignee_name,
                            "target_label": "Person",
                        })

                # Issue → Creator
                creator = issue.get("creator")
                if creator:
                    creator_name = _add_user(creator)
                    if creator_name:
                        relationships.append({
                            "type": "CREATED_BY",
                            "source": issue_name,
                            "source_label": "Issue",
                            "target": creator_name,
                            "target_label": "Person",
                        })

                # Issue → Project
                project = issue.get("project")
                if project and project.get("name"):
                    relationships.append({
                        "type": "BELONGS_TO_PROJECT",
                        "source": issue_name,
                        "source_label": "Issue",
                        "target": project["name"],
                        "target_label": "Project",
                    })

                # Issue → Cycle
                cycle = issue.get("cycle")
                if cycle and cycle.get("id"):
                    cycle_name = cycle.get("name") or f"Cycle {cycle.get('number', '?')}"
                    relationships.append({
                        "type": "IN_CYCLE",
                        "source": issue_name,
                        "source_label": "Issue",
                        "target": cycle_name,
                        "target_label": "Cycle",
                    })

                # Issue → WorkflowState
                state = issue.get("state")
                if state:
                    state_name = _add_state(state, team_name)
                    if state_name:
                        relationships.append({
                            "type": "HAS_STATE",
                            "source": issue_name,
                            "source_label": "Issue",
                            "target": state_name,
                            "target_label": "WorkflowState",
                        })

                # Issue → Labels
                issue_labels = issue.get("labels", {}).get("nodes", [])
                for label in issue_labels:
                    label_name = _add_label(label)
                    if label_name:
                        relationships.append({
                            "type": "HAS_LABEL",
                            "source": issue_name,
                            "source_label": "Issue",
                            "target": label_name,
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
                        "source": issue_name,
                        "source_label": "Issue",
                        "target": parent_name,
                        "target_label": "Issue",
                    })

                # Comments (optional)
                if include_comments:
                    comments = issue.get("comments", {}).get("nodes", [])
                    for comment in comments:
                        if not comment.get("id"):
                            continue
                        comment_name = f"Comment on {identifier}"
                        entities["Comment"].append({
                            "name": comment_name,
                            "linearId": comment["id"],
                            "body": comment.get("body", ""),
                            "createdAt": comment.get("createdAt", ""),
                            "updatedAt": comment.get("updatedAt", ""),
                            "url": comment.get("url", ""),
                        })
                        relationships.append({
                            "type": "HAS_COMMENT",
                            "source": issue_name,
                            "source_label": "Issue",
                            "target": comment_name,
                            "target_label": "Comment",
                        })
                        comment_user = comment.get("user")
                        if comment_user:
                            comment_author = _add_user(comment_user)
                            if comment_author:
                                relationships.append({
                                    "type": "AUTHORED_BY",
                                    "source": comment_name,
                                    "source_label": "Comment",
                                    "target": comment_author,
                                    "target_label": "Person",
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

        return NormalizedData(
            entities=entities,
            relationships=relationships,
            documents=documents,
        )

    # --- GraphQL helpers ---

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
                # Check rate limits
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

            # Navigate to the connection object via the data path
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

    # --- Data fetching methods ---

    def _fetch_teams(self) -> list[dict]:
        """Fetch all teams in the organization."""
        query = """
        query FetchTeams {
            teams {
                nodes {
                    id name key description
                }
            }
        }
        """
        result = self._graphql_request(query)
        return result.get("data", {}).get("teams", {}).get("nodes", [])

    def _fetch_users(self) -> list[dict]:
        """Fetch all users in the organization."""
        query = """
        query FetchUsers($cursor: String) {
            users(first: 100, after: $cursor) {
                pageInfo { hasNextPage endCursor }
                nodes {
                    id name displayName email admin active
                }
            }
        }
        """
        return self._paginate(query, {}, ["users"])

    def _fetch_team_members(self, team_id: str) -> list[dict]:
        """Fetch members of a specific team."""
        query = """
        query FetchTeamMembers($teamId: String!) {
            team(id: $teamId) {
                members {
                    nodes {
                        id name displayName email admin active
                    }
                }
            }
        }
        """
        result = self._graphql_request(query, {"teamId": team_id})
        return result.get("data", {}).get("team", {}).get("members", {}).get("nodes", [])

    def _fetch_labels(self) -> list[dict]:
        """Fetch all labels in the workspace."""
        query = """
        query FetchLabels($cursor: String) {
            issueLabels(first: 100, after: $cursor) {
                pageInfo { hasNextPage endCursor }
                nodes {
                    id name color description
                }
            }
        }
        """
        return self._paginate(query, {}, ["issueLabels"])

    def _fetch_projects(self) -> list[dict]:
        """Fetch all projects with members and teams."""
        query = """
        query FetchProjects($cursor: String) {
            projects(first: 50, after: $cursor) {
                pageInfo { hasNextPage endCursor }
                nodes {
                    id name description state startDate targetDate progress url
                    lead { id name displayName email }
                    members { nodes { id name displayName email } }
                    teams { nodes { id name key } }
                }
            }
        }
        """
        return self._paginate(query, {}, ["projects"])

    def _fetch_cycles(self, team_id: str) -> list[dict]:
        """Fetch cycles for a team."""
        query = """
        query FetchCycles($teamId: String!) {
            team(id: $teamId) {
                cycles {
                    nodes {
                        id name number startsAt endsAt progress url
                    }
                }
            }
        }
        """
        result = self._graphql_request(query, {"teamId": team_id})
        return result.get("data", {}).get("team", {}).get("cycles", {}).get("nodes", [])

    def _fetch_issues(self, team_id: str, include_comments: bool = False) -> list[dict]:
        """Fetch all issues for a team with relationships."""
        comments_fragment = ""
        if include_comments:
            comments_fragment = """
                comments {
                    nodes {
                        id body createdAt updatedAt url
                        user { id name displayName email }
                    }
                }
            """

        query = f"""
        query FetchIssues($teamId: String, $cursor: String) {{
            issues(first: 50, after: $cursor, filter: {{ team: {{ id: {{ eq: $teamId }} }} }}) {{
                pageInfo {{ hasNextPage endCursor }}
                nodes {{
                    id identifier title description priority priorityLabel estimate
                    dueDate createdAt updatedAt url
                    state {{ id name type color position }}
                    assignee {{ id name email displayName }}
                    creator {{ id name email displayName }}
                    team {{ id name key }}
                    project {{ id name }}
                    cycle {{ id number name startsAt endsAt }}
                    labels {{ nodes {{ id name color }} }}
                    parent {{ id identifier title }}
                    children {{ nodes {{ id identifier title }} }}
                    {comments_fragment}
                }}
            }}
        }}
        """
        return self._paginate(query, {"teamId": team_id}, ["issues"])
