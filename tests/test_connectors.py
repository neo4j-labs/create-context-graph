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

"""Unit tests for SaaS data connectors."""

import json
from unittest.mock import MagicMock, patch

import pytest

from create_context_graph.connectors import (
    CONNECTOR_REGISTRY,
    NormalizedData,
    get_connector,
    list_connectors,
    merge_connector_results,
)


# ---------------------------------------------------------------------------
# NormalizedData model tests
# ---------------------------------------------------------------------------


class TestNormalizedData:
    def test_empty_data(self):
        data = NormalizedData()
        assert data.entities == {}
        assert data.relationships == []
        assert data.documents == []

    def test_with_data(self):
        data = NormalizedData(
            entities={"Person": [{"name": "Alice"}]},
            relationships=[{"type": "KNOWS", "source": "Alice", "target": "Bob"}],
            documents=[{"title": "Doc", "content": "Hello"}],
        )
        assert len(data.entities["Person"]) == 1
        assert len(data.relationships) == 1
        assert len(data.documents) == 1

    def test_merge(self):
        d1 = NormalizedData(
            entities={"Person": [{"name": "Alice"}]},
            relationships=[{"type": "KNOWS"}],
            documents=[{"title": "Doc1"}],
        )
        d2 = NormalizedData(
            entities={
                "Person": [{"name": "Bob"}],
                "Org": [{"name": "Acme"}],
            },
            relationships=[{"type": "WORKS_FOR"}],
            documents=[{"title": "Doc2"}],
        )
        merged = d1.merge(d2)
        assert len(merged.entities["Person"]) == 2
        assert len(merged.entities["Org"]) == 1
        assert len(merged.relationships) == 2
        assert len(merged.documents) == 2


# ---------------------------------------------------------------------------
# Registry tests
# ---------------------------------------------------------------------------


class TestConnectorRegistry:
    def test_all_eight_registered(self):
        assert len(CONNECTOR_REGISTRY) == 8

    def test_expected_connectors(self):
        expected = {"github", "notion", "jira", "slack", "gmail", "gcal", "salesforce", "linear"}
        assert set(CONNECTOR_REGISTRY.keys()) == expected

    def test_get_connector(self):
        conn = get_connector("github")
        assert conn.service_name == "GitHub"

    def test_get_unknown_raises(self):
        with pytest.raises(ValueError, match="Unknown connector"):
            get_connector("unknown-service")

    def test_list_connectors(self):
        result = list_connectors()
        assert len(result) == 8
        ids = {c["id"] for c in result}
        assert "github" in ids

    def test_all_have_credential_prompts(self):
        for name, cls in CONNECTOR_REGISTRY.items():
            conn = cls()
            prompts = conn.get_credential_prompts()
            assert isinstance(prompts, list)


# ---------------------------------------------------------------------------
# Merge helper
# ---------------------------------------------------------------------------


class TestMergeResults:
    def test_empty_list(self):
        result = merge_connector_results([])
        assert result.entities == {}

    def test_merge_multiple(self):
        r1 = NormalizedData(entities={"A": [{"name": "a"}]})
        r2 = NormalizedData(entities={"B": [{"name": "b"}]})
        r3 = NormalizedData(entities={"A": [{"name": "c"}]})
        merged = merge_connector_results([r1, r2, r3])
        assert len(merged.entities["A"]) == 2
        assert len(merged.entities["B"]) == 1


# ---------------------------------------------------------------------------
# Individual connector tests (mocked external APIs)
# ---------------------------------------------------------------------------


class TestGitHubConnector:
    def test_requires_pygithub(self):
        conn = get_connector("github")
        with patch.dict("sys.modules", {"github": None}):
            with pytest.raises(ImportError):
                conn.authenticate({"token": "fake", "repo": "owner/repo"})

    def test_fetch_returns_normalized_data(self):
        # Mock the GitHub module
        mock_github_module = MagicMock()
        mock_repo = MagicMock()
        mock_repo.full_name = "owner/repo"
        mock_repo.description = "Test repo"
        mock_repo.html_url = "https://github.com/owner/repo"
        mock_repo.language = "Python"
        mock_repo.stargazers_count = 10
        mock_repo.organization = None
        mock_repo.get_issues.return_value = []
        mock_repo.get_pulls.return_value = []
        mock_repo.get_commits.return_value = []

        mock_client = MagicMock()
        mock_client.get_repo.return_value = mock_repo
        mock_github_module.Github.return_value = mock_client

        with patch.dict("sys.modules", {"github": mock_github_module}):
            from create_context_graph.connectors.github_connector import GitHubConnector

            conn = GitHubConnector()
            conn.authenticate({"token": "fake", "repo": "owner/repo"})
            result = conn.fetch()

        assert isinstance(result, NormalizedData)
        assert "Repository" in result.entities
        assert len(result.entities["Repository"]) == 1


class TestNotionConnector:
    def test_fetch_returns_normalized_data(self):
        mock_notion_module = MagicMock()
        mock_client = MagicMock()
        mock_client.search.return_value = {"results": []}
        mock_notion_module.Client.return_value = mock_client

        with patch.dict("sys.modules", {"notion_client": mock_notion_module}):
            from create_context_graph.connectors.notion_connector import NotionConnector

            conn = NotionConnector()
            conn.authenticate({"token": "fake"})
            result = conn.fetch()

        assert isinstance(result, NormalizedData)


class TestJiraConnector:
    def test_fetch_returns_normalized_data(self):
        mock_atlassian_module = MagicMock()
        mock_jira = MagicMock()
        mock_jira.project.return_value = {"name": "Test Project"}
        mock_jira.jql.return_value = {"issues": []}
        mock_atlassian_module.Jira.return_value = mock_jira

        with patch.dict("sys.modules", {"atlassian": mock_atlassian_module}):
            from create_context_graph.connectors.jira_connector import JiraConnector

            conn = JiraConnector()
            conn.authenticate({
                "url": "https://test.atlassian.net",
                "email": "test@test.com",
                "token": "fake",
                "project": "TEST",
            })
            result = conn.fetch()

        assert isinstance(result, NormalizedData)
        assert "Project" in result.entities


class TestSlackConnector:
    def test_fetch_returns_normalized_data(self):
        mock_slack_module = MagicMock()
        mock_client = MagicMock()
        mock_client.conversations_list.return_value = {"channels": []}
        mock_slack_module.WebClient.return_value = mock_client

        with patch.dict("sys.modules", {"slack_sdk": mock_slack_module}):
            from create_context_graph.connectors.slack_connector import SlackConnector

            conn = SlackConnector()
            conn.authenticate({"token": "xoxb-fake", "channels": "all"})
            result = conn.fetch()

        assert isinstance(result, NormalizedData)


class TestGmailConnector:
    @patch("create_context_graph.connectors.gmail_connector.check_gws_cli", return_value=True)
    @patch("create_context_graph.connectors.gmail_connector.run_gws_command")
    def test_fetch_via_gws(self, mock_gws, mock_check):
        mock_gws.return_value = []

        from create_context_graph.connectors.gmail_connector import GmailConnector

        conn = GmailConnector()
        conn.authenticate({})
        result = conn.fetch()

        assert isinstance(result, NormalizedData)

    @patch("create_context_graph.connectors.gmail_connector.check_gws_cli", return_value=False)
    def test_fallback_needs_credentials(self, mock_check):
        from create_context_graph.connectors.gmail_connector import GmailConnector

        conn = GmailConnector()
        prompts = conn.get_credential_prompts()
        assert len(prompts) == 2  # client_id and client_secret


class TestGCalConnector:
    @patch("create_context_graph.connectors.gcal_connector.check_gws_cli", return_value=True)
    @patch("create_context_graph.connectors.gcal_connector.run_gws_command")
    def test_fetch_via_gws(self, mock_gws, mock_check):
        mock_gws.return_value = []

        from create_context_graph.connectors.gcal_connector import GCalConnector

        conn = GCalConnector()
        conn.authenticate({})
        result = conn.fetch()

        assert isinstance(result, NormalizedData)


class TestSalesforceConnector:
    def test_requires_simple_salesforce(self):
        conn = get_connector("salesforce")
        with patch.dict("sys.modules", {"simple_salesforce": None}):
            with pytest.raises(ImportError):
                conn.authenticate({
                    "username": "test",
                    "password": "test",
                    "security_token": "test",
                    "domain": "login",
                })


class TestLinearConnector:
    """Tests for the Linear connector with mocked GraphQL API."""

    def _make_graphql_mock(self, responses: dict):
        """Create a mock for urllib.request.urlopen that returns different responses
        based on the GraphQL query content. Keys are matched longest-first to avoid
        substring collisions (e.g., 'teams' matching inside a 'projects' query)."""

        def mock_urlopen(req):
            body = req.data.decode()
            data = json.loads(body)
            query = data.get("query", "")

            # Match longest key first to avoid substring collisions
            for key in sorted(responses, key=len, reverse=True):
                resp = responses[key]
                if key in query:
                    response_bytes = json.dumps(resp).encode()
                    mock_resp = MagicMock()
                    mock_resp.read.return_value = response_bytes
                    mock_resp.__enter__ = MagicMock(return_value=mock_resp)
                    mock_resp.__exit__ = MagicMock(return_value=False)
                    mock_resp.headers = MagicMock()
                    mock_resp.headers.get = MagicMock(return_value="100")
                    return mock_resp

            # Default: empty response
            response_bytes = json.dumps({"data": {}}).encode()
            mock_resp = MagicMock()
            mock_resp.read.return_value = response_bytes
            mock_resp.__enter__ = MagicMock(return_value=mock_resp)
            mock_resp.__exit__ = MagicMock(return_value=False)
            mock_resp.headers = MagicMock()
            mock_resp.headers.get = MagicMock(return_value="100")
            return mock_resp

        return mock_urlopen

    def _standard_responses(self):
        """Standard mock responses for a basic Linear workspace.

        Keys use unique substrings from the actual GraphQL queries to avoid
        ambiguity (e.g., 'projects(first' won't collide with 'teams {').
        """
        viewer_resp = {"data": {"viewer": {"id": "user-1", "name": "Test User", "email": "test@test.com"}}}
        teams_resp = {"data": {"teams": {"nodes": [
            {"id": "team-1", "name": "Engineering", "key": "ENG", "description": "Engineering team"},
        ]}}}
        users_resp = {"data": {"users": {
            "pageInfo": {"hasNextPage": False, "endCursor": None},
            "nodes": [
                {"id": "user-1", "name": "Alice", "displayName": "Alice A", "email": "alice@test.com", "admin": True, "active": True},
                {"id": "user-2", "name": "Bob", "displayName": "Bob B", "email": "bob@test.com", "admin": False, "active": True},
            ],
        }}}
        team_members_resp = {"data": {"team": {"members": {"nodes": [
            {"id": "user-1", "name": "Alice", "displayName": "Alice A", "email": "alice@test.com", "admin": True, "active": True},
            {"id": "user-2", "name": "Bob", "displayName": "Bob B", "email": "bob@test.com", "admin": False, "active": True},
        ]}}}}
        labels_resp = {"data": {"issueLabels": {
            "pageInfo": {"hasNextPage": False, "endCursor": None},
            "nodes": [
                {"id": "label-1", "name": "Bug", "color": "#ef4444", "description": "Bug reports"},
                {"id": "label-2", "name": "Feature", "color": "#22c55e", "description": "Feature requests"},
            ],
        }}}
        projects_resp = {"data": {"projects": {
            "pageInfo": {"hasNextPage": False, "endCursor": None},
            "nodes": [{
                "id": "proj-1", "name": "v2 Launch", "description": "Version 2 launch",
                "state": "started", "startDate": "2026-01-01", "targetDate": "2026-06-01",
                "progress": 0.45, "url": "https://linear.app/proj/v2-launch",
                "lead": {"id": "user-1", "name": "Alice", "displayName": "Alice A", "email": "alice@test.com"},
                "members": {"nodes": [
                    {"id": "user-1", "name": "Alice", "displayName": "Alice A", "email": "alice@test.com"},
                ]},
                "teams": {"nodes": [{"id": "team-1", "name": "Engineering", "key": "ENG"}]},
            }],
        }}}
        cycles_resp = {"data": {"team": {"cycles": {"nodes": [
            {"id": "cycle-1", "name": "Sprint 10", "number": 10, "startsAt": "2026-03-25", "endsAt": "2026-04-08", "progress": 0.3, "url": "https://linear.app/cycle/10"},
        ]}}}}
        issues_resp = {"data": {"issues": {
            "pageInfo": {"hasNextPage": False, "endCursor": None},
            "nodes": [
                {
                    "id": "issue-1", "identifier": "ENG-101", "title": "Fix login bug",
                    "description": "The login page crashes when email contains a plus sign.",
                    "priority": 2, "priorityLabel": "High", "estimate": 3,
                    "dueDate": "2026-04-15", "createdAt": "2026-03-20", "updatedAt": "2026-03-28",
                    "url": "https://linear.app/issue/ENG-101",
                    "state": {"id": "state-1", "name": "In Progress", "type": "started", "color": "#f59e0b", "position": 2},
                    "assignee": {"id": "user-1", "name": "Alice", "email": "alice@test.com", "displayName": "Alice A"},
                    "creator": {"id": "user-2", "name": "Bob", "email": "bob@test.com", "displayName": "Bob B"},
                    "team": {"id": "team-1", "name": "Engineering", "key": "ENG"},
                    "project": {"id": "proj-1", "name": "v2 Launch"},
                    "cycle": {"id": "cycle-1", "number": 10, "name": "Sprint 10", "startsAt": "2026-03-25", "endsAt": "2026-04-08"},
                    "labels": {"nodes": [{"id": "label-1", "name": "Bug", "color": "#ef4444"}]},
                    "parent": None,
                    "children": {"nodes": []},
                },
                {
                    "id": "issue-2", "identifier": "ENG-102", "title": "Add OAuth support",
                    "description": "Implement OAuth2 login flow.",
                    "priority": 3, "priorityLabel": "Medium", "estimate": 8,
                    "dueDate": None, "createdAt": "2026-03-22", "updatedAt": "2026-03-29",
                    "url": "https://linear.app/issue/ENG-102",
                    "state": {"id": "state-2", "name": "Backlog", "type": "backlog", "color": "#6b7280", "position": 0},
                    "assignee": None,
                    "creator": {"id": "user-1", "name": "Alice", "email": "alice@test.com", "displayName": "Alice A"},
                    "team": {"id": "team-1", "name": "Engineering", "key": "ENG"},
                    "project": {"id": "proj-1", "name": "v2 Launch"},
                    "cycle": None,
                    "labels": {"nodes": [{"id": "label-2", "name": "Feature", "color": "#22c55e"}]},
                    "parent": {"id": "issue-1", "identifier": "ENG-101", "title": "Fix login bug"},
                    "children": {"nodes": []},
                },
            ],
        }}}

        # Keys use unique query substrings to avoid ambiguity
        return {
            "viewer": viewer_resp,
            "issueLabels": labels_resp,
            "projects(first": projects_resp,
            "issues(first": issues_resp,
            "users(first": users_resp,
            "members": team_members_resp,
            "cycles": cycles_resp,
            "teams": teams_resp,
        }

    def test_credential_prompts(self):
        conn = get_connector("linear")
        prompts = conn.get_credential_prompts()
        assert len(prompts) == 2
        names = {p["name"] for p in prompts}
        assert "api_key" in names
        assert "team_key" in names
        assert any(p["secret"] for p in prompts)

    @patch("urllib.request.urlopen")
    def test_authenticate_success(self, mock_urlopen):
        responses = self._standard_responses()
        mock_urlopen.side_effect = self._make_graphql_mock(responses)

        conn = get_connector("linear")
        conn.authenticate({"api_key": "lin_api_test123"})
        # Should not raise

    def test_authenticate_missing_key(self):
        conn = get_connector("linear")
        with pytest.raises(ValueError, match="API key is required"):
            conn.authenticate({"api_key": ""})

    @patch("urllib.request.urlopen")
    def test_authenticate_invalid_key(self, mock_urlopen):
        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps({
            "errors": [{"message": "Authentication failed"}]
        }).encode()
        mock_resp.__enter__ = MagicMock(return_value=mock_resp)
        mock_resp.__exit__ = MagicMock(return_value=False)
        mock_resp.headers = MagicMock()
        mock_resp.headers.get = MagicMock(return_value="100")
        mock_urlopen.return_value = mock_resp

        conn = get_connector("linear")
        with pytest.raises(ValueError, match="authentication failed"):
            conn.authenticate({"api_key": "lin_api_bad"})

    @patch("urllib.request.urlopen")
    def test_fetch_entity_mapping(self, mock_urlopen):
        responses = self._standard_responses()
        mock_urlopen.side_effect = self._make_graphql_mock(responses)

        conn = get_connector("linear")
        conn.authenticate({"api_key": "lin_api_test123"})
        result = conn.fetch()

        assert isinstance(result, NormalizedData)
        # Check all expected entity labels exist
        assert "Person" in result.entities
        assert "Team" in result.entities
        assert "Project" in result.entities
        assert "Cycle" in result.entities
        assert "Issue" in result.entities
        assert "Label" in result.entities
        assert "WorkflowState" in result.entities

    @patch("urllib.request.urlopen")
    def test_fetch_entity_counts(self, mock_urlopen):
        responses = self._standard_responses()
        mock_urlopen.side_effect = self._make_graphql_mock(responses)

        conn = get_connector("linear")
        conn.authenticate({"api_key": "lin_api_test123"})
        result = conn.fetch()

        assert len(result.entities["Team"]) == 1
        assert len(result.entities["Issue"]) == 2
        assert len(result.entities["Project"]) == 1
        assert len(result.entities["Cycle"]) == 1
        assert len(result.entities["Label"]) == 2
        assert len(result.entities["WorkflowState"]) == 2  # 2 unique states

    @patch("urllib.request.urlopen")
    def test_fetch_relationships(self, mock_urlopen):
        responses = self._standard_responses()
        mock_urlopen.side_effect = self._make_graphql_mock(responses)

        conn = get_connector("linear")
        conn.authenticate({"api_key": "lin_api_test123"})
        result = conn.fetch()

        rel_types = {r["type"] for r in result.relationships}
        assert "ASSIGNED_TO" in rel_types
        assert "CREATED_BY" in rel_types
        assert "BELONGS_TO_PROJECT" in rel_types
        assert "BELONGS_TO_TEAM" in rel_types
        assert "IN_CYCLE" in rel_types
        assert "HAS_STATE" in rel_types
        assert "HAS_LABEL" in rel_types
        assert "MEMBER_OF" in rel_types
        assert "CYCLE_FOR" in rel_types

    @patch("urllib.request.urlopen")
    def test_fetch_child_of_relationship(self, mock_urlopen):
        responses = self._standard_responses()
        mock_urlopen.side_effect = self._make_graphql_mock(responses)

        conn = get_connector("linear")
        conn.authenticate({"api_key": "lin_api_test123"})
        result = conn.fetch()

        child_rels = [r for r in result.relationships if r["type"] == "CHILD_OF"]
        assert len(child_rels) == 1
        assert child_rels[0]["source_label"] == "Issue"
        assert child_rels[0]["target_label"] == "Issue"

    @patch("urllib.request.urlopen")
    def test_fetch_documents(self, mock_urlopen):
        responses = self._standard_responses()
        mock_urlopen.side_effect = self._make_graphql_mock(responses)

        conn = get_connector("linear")
        conn.authenticate({"api_key": "lin_api_test123"})
        result = conn.fetch()

        assert len(result.documents) == 2  # Both issues have descriptions
        assert all(d["type"] == "linear-issue" for d in result.documents)
        assert any("ENG-101" in d["title"] for d in result.documents)

    @patch("urllib.request.urlopen")
    def test_fetch_deduplication(self, mock_urlopen):
        responses = self._standard_responses()
        mock_urlopen.side_effect = self._make_graphql_mock(responses)

        conn = get_connector("linear")
        conn.authenticate({"api_key": "lin_api_test123"})
        result = conn.fetch()

        # Alice appears as org user, team member, assignee, creator, project lead, project member
        # But should only be in entities once
        alice_count = sum(1 for p in result.entities["Person"] if p["name"] == "Alice")
        assert alice_count == 1

        # Bug label appears in workspace labels and on issue-1
        bug_count = sum(1 for lbl in result.entities["Label"] if lbl["name"] == "Bug")
        assert bug_count == 1

    @patch("urllib.request.urlopen")
    def test_fetch_team_filter(self, mock_urlopen):
        responses = self._standard_responses()
        mock_urlopen.side_effect = self._make_graphql_mock(responses)

        conn = get_connector("linear")
        conn.authenticate({"api_key": "lin_api_test123", "team_key": "ENG"})
        result = conn.fetch()

        assert len(result.entities["Team"]) == 1
        assert result.entities["Team"][0]["key"] == "ENG"

    @patch("urllib.request.urlopen")
    def test_fetch_team_filter_not_found(self, mock_urlopen):
        responses = self._standard_responses()
        mock_urlopen.side_effect = self._make_graphql_mock(responses)

        conn = get_connector("linear")
        conn.authenticate({"api_key": "lin_api_test123", "team_key": "NONEXISTENT"})
        with pytest.raises(ValueError, match="not found"):
            conn.fetch()

    @patch("urllib.request.urlopen")
    def test_issue_name_format(self, mock_urlopen):
        responses = self._standard_responses()
        mock_urlopen.side_effect = self._make_graphql_mock(responses)

        conn = get_connector("linear")
        conn.authenticate({"api_key": "lin_api_test123"})
        result = conn.fetch()

        issue_names = [i["name"] for i in result.entities["Issue"]]
        assert "ENG-101 Fix login bug" in issue_names
        assert "ENG-102 Add OAuth support" in issue_names

    @patch("urllib.request.urlopen")
    def test_priority_labels(self, mock_urlopen):
        responses = self._standard_responses()
        mock_urlopen.side_effect = self._make_graphql_mock(responses)

        conn = get_connector("linear")
        conn.authenticate({"api_key": "lin_api_test123"})
        result = conn.fetch()

        issues = result.entities["Issue"]
        high_priority = [i for i in issues if i["identifier"] == "ENG-101"]
        assert high_priority[0]["priorityLabel"] == "High"


# ---------------------------------------------------------------------------
# OAuth helper tests
# ---------------------------------------------------------------------------


class TestOAuthHelpers:
    def test_check_gws_cli(self):
        from create_context_graph.connectors.oauth import check_gws_cli

        # Should return bool regardless of system state
        result = check_gws_cli()
        assert isinstance(result, bool)

    @patch("shutil.which", return_value=None)
    def test_check_gws_cli_not_found(self, mock_which):
        from create_context_graph.connectors.oauth import check_gws_cli

        assert check_gws_cli() is False

    @patch("shutil.which", return_value="/usr/local/bin/gws")
    def test_check_gws_cli_found(self, mock_which):
        from create_context_graph.connectors.oauth import check_gws_cli

        assert check_gws_cli() is True
