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

"""Jira connector — imports issues, sprints, and users."""

from __future__ import annotations

from typing import Any
from urllib.parse import urlparse

from create_context_graph.connectors import (
    BaseConnector,
    NormalizedData,
    register_connector,
)


def _is_jira_cloud(url: str) -> bool:
    """True when ``url``'s host is an Atlassian Cloud site (``*.atlassian.net``).

    Checks the parsed hostname, not a substring, so ``https://evil.example/x.atlassian.net``
    is not mistaken for Cloud.
    """
    host = (urlparse(url).hostname or "").lower()
    return host == "atlassian.net" or host.endswith(".atlassian.net")


@register_connector("jira")

class JiraConnector(BaseConnector):
    """Import data from Jira projects."""

    service_name = "Jira"
    service_description = "Import issues, sprints, and users from a Jira project"
    requires_oauth = False

    def __init__(self):
        self._jira = None
        self._project_key = None

    def get_credential_prompts(self) -> list[dict[str, Any]]:
        return [
            {
                "name": "url",
                "prompt": "Jira instance URL:",
                "secret": False,
                "description": "e.g. https://your-org.atlassian.net",
            },
            {
                "name": "email",
                "prompt": "Jira email:",
                "secret": False,
                "description": "Your Atlassian account email",
            },
            {
                "name": "token",
                "prompt": "Jira API token:",
                "secret": True,
                "description": "API token from https://id.atlassian.com/manage-profile/security/api-tokens",
            },
            {
                "name": "project",
                "prompt": "Jira project key:",
                "secret": False,
                "description": "e.g. PROJ, ENG, BACKEND",
            },
        ]

    def authenticate(self, credentials: dict[str, str]) -> None:
        try:
            from atlassian import Jira
        except ImportError:
            raise ImportError(
                "atlassian-python-api is required for the Jira connector. "
                "Install it with: pip install atlassian-python-api"
            )

        # Jira Cloud removed /rest/api/2/search (CHANGE-2046); with cloud=True
        # atlassian-python-api>=4.0 routes jql() to /search/jql instead.
        # Data Center / Server keep the classic endpoint.
        self._jira = Jira(
            url=credentials["url"],
            username=credentials["email"],
            password=credentials["token"],
            cloud=_is_jira_cloud(credentials["url"]),
        )
        self._project_key = credentials["project"]

    def fetch(self, **kwargs: Any) -> NormalizedData:
        if not self._jira or not self._project_key:
            raise RuntimeError("Call authenticate() first")

        limit = kwargs.get("limit", 100)
        entities: dict[str, list[dict]] = {
            "Person": [],
            "Project": [],
            "Issue": [],
            "Sprint": [],
        }
        relationships: list[dict] = []
        documents: list[dict] = []
        seen_users: set[str] = set()
        seen_sprints: set[str] = set()

        def _add_user(user_data: dict | None) -> str | None:
            if not user_data:
                return None
            display_name = user_data.get("displayName", "")
            account_id = user_data.get("accountId", display_name)
            if account_id in seen_users:
                return display_name
            seen_users.add(account_id)
            entities["Person"].append({
                "name": display_name,
                "email": user_data.get("emailAddress", ""),
                "role": "jira-user",
                "description": f"Jira user: {display_name}",
            })
            return display_name

        # Project entity
        try:
            project = self._jira.project(self._project_key)
            entities["Project"].append({
                "name": project.get("name", self._project_key),
                "description": project.get("description", ""),
                "project_key": self._project_key,
            })
        except Exception:
            entities["Project"].append({
                "name": self._project_key,
                "description": "",
                "project_key": self._project_key,
            })

        # Issues
        jql = f"project = {self._project_key} ORDER BY updated DESC"
        issues = self._jira.jql(jql, limit=limit)

        for issue_data in issues.get("issues", []):
            fields = issue_data.get("fields", {})
            issue_key = issue_data.get("key", "")
            summary = fields.get("summary", "")

            entities["Issue"].append({
                "name": f"{issue_key}: {summary}",
                "issue_key": issue_key,
                "status": fields.get("status", {}).get("name", ""),
                "issue_type": fields.get("issuetype", {}).get("name", ""),
                "priority": fields.get("priority", {}).get("name", ""),
                "created": fields.get("created", ""),
                "updated": fields.get("updated", ""),
            })

            # Assignee
            assignee = _add_user(fields.get("assignee"))
            if assignee:
                relationships.append({
                    "type": "ASSIGNED_TO",
                    "source_name": f"{issue_key}: {summary}",
                    "source_label": "Issue",
                    "target_name": assignee,
                    "target_label": "Person",
                })

            # Reporter
            reporter = _add_user(fields.get("reporter"))
            if reporter:
                relationships.append({
                    "type": "REPORTED_BY",
                    "source_name": f"{issue_key}: {summary}",
                    "source_label": "Issue",
                    "target_name": reporter,
                    "target_label": "Person",
                })

            # Sprint
            sprint_field = fields.get("sprint")
            if sprint_field and isinstance(sprint_field, dict):
                sprint_name = sprint_field.get("name", "")
                if sprint_name and sprint_name not in seen_sprints:
                    seen_sprints.add(sprint_name)
                    entities["Sprint"].append({
                        "name": sprint_name,
                        "state": sprint_field.get("state", ""),
                        "start_date": sprint_field.get("startDate", ""),
                        "end_date": sprint_field.get("endDate", ""),
                    })
                if sprint_name:
                    relationships.append({
                        "type": "IN_SPRINT",
                        "source_name": f"{issue_key}: {summary}",
                        "source_label": "Issue",
                        "target_name": sprint_name,
                        "target_label": "Sprint",
                    })

            # Belongs to project
            relationships.append({
                "type": "BELONGS_TO",
                "source_name": f"{issue_key}: {summary}",
                "source_label": "Issue",
                "target_name": self._project_key,
                "target_label": "Project",
            })

            # Document from description
            description = fields.get("description", "")
            if description:
                documents.append({
                    "title": f"{issue_key}: {summary}",
                    "content": description,
                    "type": "jira-issue",
                    "metadata": {
                        "key": issue_key,
                        "status": fields.get("status", {}).get("name", ""),
                        "type": fields.get("issuetype", {}).get("name", ""),
                    },
                })

        return NormalizedData(
            entities=entities,
            relationships=relationships,
            documents=documents,
        )
