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
        initiatives_resp = {"data": {"initiatives": {
            "pageInfo": {"hasNextPage": False, "endCursor": None},
            "nodes": [{
                "id": "init-1", "name": "Q2 Goals", "description": "Q2 strategic goals",
                "status": "Active", "health": "onTrack", "targetDate": "2026-06-30",
                "url": "https://linear.app/init/q2",
                "owner": {"id": "user-1", "name": "Alice", "displayName": "Alice A", "email": "alice@test.com"},
                "projects": {"nodes": [{"id": "proj-1", "name": "v2 Launch"}]},
            }],
        }}}
        projects_resp = {"data": {"projects": {
            "pageInfo": {"hasNextPage": False, "endCursor": None},
            "nodes": [{
                "id": "proj-1", "name": "v2 Launch", "description": "Version 2 launch",
                "state": "started", "startDate": "2026-01-01", "targetDate": "2026-06-01",
                "progress": 0.45, "health": "atRisk", "url": "https://linear.app/proj/v2-launch",
                "lead": {"id": "user-1", "name": "Alice", "displayName": "Alice A", "email": "alice@test.com"},
                "members": {"nodes": [
                    {"id": "user-1", "name": "Alice", "displayName": "Alice A", "email": "alice@test.com"},
                ]},
                "teams": {"nodes": [{"id": "team-1", "name": "Engineering", "key": "ENG"}]},
                "projectMilestones": {"nodes": [
                    {"id": "ms-1", "name": "Beta Release", "description": "Beta launch", "targetDate": "2026-04-15", "status": "planned", "progress": 0.2},
                ]},
                "projectUpdates": {"nodes": [
                    {"id": "upd-1", "body": "Sprint velocity is below target. Descoping 2 features.", "health": "atRisk", "createdAt": "2026-03-28",
                     "user": {"id": "user-1", "name": "Alice", "displayName": "Alice A", "email": "alice@test.com"}},
                ]},
            }],
        }}}
        cycles_resp = {"data": {"team": {"cycles": {"nodes": [
            {"id": "cycle-1", "name": "Sprint 10", "number": 10, "startsAt": "2026-03-25", "endsAt": "2026-04-08", "progress": 0.3},
        ]}}}}
        issues_resp = {"data": {"issues": {
            "pageInfo": {"hasNextPage": False, "endCursor": None},
            "nodes": [
                {
                    "id": "issue-1", "identifier": "ENG-101", "title": "Fix login bug",
                    "description": "The login page crashes when email contains a plus sign.",
                    "priority": 2, "priorityLabel": "High", "estimate": 3,
                    "number": 101, "dueDate": "2026-04-15",
                    "createdAt": "2026-03-20", "updatedAt": "2026-03-28",
                    "completedAt": None, "canceledAt": None, "startedAt": "2026-03-21",
                    "branchName": "eng/eng-101-fix-login-bug", "trashed": False,
                    "url": "https://linear.app/issue/ENG-101",
                    "state": {"id": "state-1", "name": "In Progress", "type": "started", "color": "#f59e0b", "position": 2},
                    "assignee": {"id": "user-1", "name": "Alice", "email": "alice@test.com", "displayName": "Alice A"},
                    "creator": {"id": "user-2", "name": "Bob", "email": "bob@test.com", "displayName": "Bob B"},
                    "team": {"id": "team-1", "name": "Engineering", "key": "ENG"},
                    "project": {"id": "proj-1", "name": "v2 Launch"},
                    "projectMilestone": {"id": "ms-1", "name": "Beta Release"},
                    "cycle": {"id": "cycle-1", "number": 10, "name": "Sprint 10", "startsAt": "2026-03-25", "endsAt": "2026-04-08"},
                    "labels": {"nodes": [{"id": "label-1", "name": "Bug", "color": "#ef4444"}]},
                    "parent": None,
                    "children": {"nodes": []},
                    "relations": {"nodes": [
                        {"id": "rel-1", "type": "blocks", "relatedIssue": {"id": "issue-2", "identifier": "ENG-102", "title": "Add OAuth support"}},
                    ]},
                    "attachments": {"nodes": [
                        {"id": "att-1", "title": "Figma mockup", "url": "https://figma.com/file/abc", "sourceType": "figma", "createdAt": "2026-03-21"},
                    ]},
                    "comments": {"nodes": [
                        {"id": "comment-1", "body": "Should we use OAuth2 or session tokens?", "createdAt": "2026-03-22", "updatedAt": "2026-03-22", "resolvedAt": "2026-03-23",
                         "user": {"id": "user-1", "name": "Alice", "displayName": "Alice A", "email": "alice@test.com"},
                         "parent": None,
                         "resolvingUser": {"id": "user-2", "name": "Bob", "displayName": "Bob B", "email": "bob@test.com"}},
                        {"id": "comment-2", "body": "OAuth2 for better mobile support.", "createdAt": "2026-03-22T10:00:00Z", "updatedAt": "2026-03-22T10:00:00Z", "resolvedAt": None,
                         "user": {"id": "user-2", "name": "Bob", "displayName": "Bob B", "email": "bob@test.com"},
                         "parent": {"id": "comment-1"},
                         "resolvingUser": None},
                    ]},
                    "history": {"nodes": [
                        {"id": "hist-1", "createdAt": "2026-03-20",
                         "fromState": None, "toState": {"name": "Backlog", "type": "backlog"},
                         "fromAssignee": None, "toAssignee": None,
                         "fromPriority": None, "toPriority": 2,
                         "actor": {"id": "user-2", "name": "Bob", "displayName": "Bob B", "email": "bob@test.com"},
                         "addedLabels": [{"name": "Bug"}], "removedLabels": []},
                        {"id": "hist-2", "createdAt": "2026-03-21",
                         "fromState": {"name": "Backlog", "type": "backlog"}, "toState": {"name": "In Progress", "type": "started"},
                         "fromAssignee": None, "toAssignee": {"name": "Alice"},
                         "fromPriority": None, "toPriority": None,
                         "actor": {"id": "user-1", "name": "Alice", "displayName": "Alice A", "email": "alice@test.com"},
                         "addedLabels": [], "removedLabels": []},
                    ]},
                },
                {
                    "id": "issue-2", "identifier": "ENG-102", "title": "Add OAuth support",
                    "description": "Implement OAuth2 login flow.",
                    "priority": 3, "priorityLabel": "Medium", "estimate": 8,
                    "number": 102, "dueDate": None,
                    "createdAt": "2026-03-22", "updatedAt": "2026-03-29",
                    "completedAt": None, "canceledAt": None, "startedAt": None,
                    "branchName": "eng/eng-102-add-oauth", "trashed": False,
                    "url": "https://linear.app/issue/ENG-102",
                    "state": {"id": "state-2", "name": "Backlog", "type": "backlog", "color": "#6b7280", "position": 0},
                    "assignee": None,
                    "creator": {"id": "user-1", "name": "Alice", "email": "alice@test.com", "displayName": "Alice A"},
                    "team": {"id": "team-1", "name": "Engineering", "key": "ENG"},
                    "project": {"id": "proj-1", "name": "v2 Launch"},
                    "projectMilestone": None,
                    "cycle": None,
                    "labels": {"nodes": [{"id": "label-2", "name": "Feature", "color": "#22c55e"}]},
                    "parent": {"id": "issue-1", "identifier": "ENG-101", "title": "Fix login bug"},
                    "children": {"nodes": []},
                    "relations": {"nodes": []},
                    "attachments": {"nodes": []},
                    "comments": {"nodes": []},
                    "history": {"nodes": []},
                },
            ],
        }}}

        documents_resp = {"data": {"documents": {
            "pageInfo": {"hasNextPage": False, "endCursor": None},
            "nodes": [
                {"id": "doc-1", "title": "Architecture Decision Record", "content": "# ADR: Use OAuth2\n\nWe chose OAuth2 for authentication.",
                 "createdAt": "2026-03-15", "updatedAt": "2026-03-15",
                 "creator": {"id": "user-1", "name": "Alice", "displayName": "Alice A", "email": "alice@test.com"},
                 "project": {"id": "proj-1", "name": "v2 Launch"}},
            ],
        }}}

        # Keys use unique query substrings to avoid ambiguity
        return {
            "viewer": viewer_resp,
            "issueLabels": labels_resp,
            "initiatives(first": initiatives_resp,
            "projects(first": projects_resp,
            "documents(first": documents_resp,
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
        for label in ["Person", "Team", "Project", "Cycle", "Issue", "Label",
                       "WorkflowState", "Comment", "ProjectUpdate", "ProjectMilestone",
                       "Initiative", "Attachment"]:
            assert label in result.entities, f"Missing entity label: {label}"

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
        assert len(result.entities["WorkflowState"]) == 2
        assert len(result.entities["Comment"]) == 2
        assert len(result.entities["ProjectUpdate"]) == 1
        assert len(result.entities["ProjectMilestone"]) == 1
        assert len(result.entities["Initiative"]) == 1
        assert len(result.entities["Attachment"]) == 1

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

        assert len(result.documents) == 4  # 2 issue descriptions + 1 project update + 1 linear doc
        issue_docs = [d for d in result.documents if d["type"] == "linear-issue"]
        assert len(issue_docs) == 2
        assert any("ENG-101" in d["title"] for d in issue_docs)

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

    @patch("urllib.request.urlopen")
    def test_issue_relations_blocks(self, mock_urlopen):
        responses = self._standard_responses()
        mock_urlopen.side_effect = self._make_graphql_mock(responses)

        conn = get_connector("linear")
        conn.authenticate({"api_key": "lin_api_test123"})
        result = conn.fetch()

        blocks_rels = [r for r in result.relationships if r["type"] == "BLOCKS"]
        assert len(blocks_rels) == 1
        assert "ENG-101" in blocks_rels[0]["source_name"]
        assert "ENG-102" in blocks_rels[0]["target_name"]

    @patch("urllib.request.urlopen")
    def test_comment_threading(self, mock_urlopen):
        responses = self._standard_responses()
        mock_urlopen.side_effect = self._make_graphql_mock(responses)

        conn = get_connector("linear")
        conn.authenticate({"api_key": "lin_api_test123"})
        result = conn.fetch()

        # Should have 2 comments
        assert len(result.entities["Comment"]) == 2
        # Reply relationship
        reply_rels = [r for r in result.relationships if r["type"] == "REPLY_TO"]
        assert len(reply_rels) == 1
        assert reply_rels[0]["source_label"] == "Comment"
        assert reply_rels[0]["target_label"] == "Comment"

    @patch("urllib.request.urlopen")
    def test_comment_resolution(self, mock_urlopen):
        responses = self._standard_responses()
        mock_urlopen.side_effect = self._make_graphql_mock(responses)

        conn = get_connector("linear")
        conn.authenticate({"api_key": "lin_api_test123"})
        result = conn.fetch()

        resolved_rels = [r for r in result.relationships if r["type"] == "RESOLVED_BY"]
        assert len(resolved_rels) == 1
        assert resolved_rels[0]["target_name"] == "Bob"

    @patch("urllib.request.urlopen")
    def test_project_milestones(self, mock_urlopen):
        responses = self._standard_responses()
        mock_urlopen.side_effect = self._make_graphql_mock(responses)

        conn = get_connector("linear")
        conn.authenticate({"api_key": "lin_api_test123"})
        result = conn.fetch()

        assert len(result.entities["ProjectMilestone"]) == 1
        assert result.entities["ProjectMilestone"][0]["name"] == "Beta Release"
        # Project → Milestone relationship
        ms_rels = [r for r in result.relationships if r["type"] == "HAS_MILESTONE"]
        assert len(ms_rels) == 1
        # Issue → Milestone
        in_ms_rels = [r for r in result.relationships if r["type"] == "IN_MILESTONE"]
        assert len(in_ms_rels) == 1

    @patch("urllib.request.urlopen")
    def test_project_updates(self, mock_urlopen):
        responses = self._standard_responses()
        mock_urlopen.side_effect = self._make_graphql_mock(responses)

        conn = get_connector("linear")
        conn.authenticate({"api_key": "lin_api_test123"})
        result = conn.fetch()

        assert len(result.entities["ProjectUpdate"]) == 1
        upd = result.entities["ProjectUpdate"][0]
        assert upd["health"] == "atRisk"
        # Update relationships
        has_update_rels = [r for r in result.relationships if r["type"] == "HAS_UPDATE"]
        assert len(has_update_rels) == 1
        posted_rels = [r for r in result.relationships if r["type"] == "POSTED_BY"]
        assert len(posted_rels) == 1
        # Update body as document
        update_docs = [d for d in result.documents if d["type"] == "linear-project-update"]
        assert len(update_docs) == 1

    @patch("urllib.request.urlopen")
    def test_initiatives(self, mock_urlopen):
        responses = self._standard_responses()
        mock_urlopen.side_effect = self._make_graphql_mock(responses)

        conn = get_connector("linear")
        conn.authenticate({"api_key": "lin_api_test123"})
        result = conn.fetch()

        assert len(result.entities["Initiative"]) == 1
        assert result.entities["Initiative"][0]["name"] == "Q2 Goals"
        # Initiative → Person (OWNED_BY)
        owned_rels = [r for r in result.relationships if r["type"] == "OWNED_BY"]
        assert len(owned_rels) == 1
        # Initiative → Project
        contains_rels = [r for r in result.relationships if r["type"] == "CONTAINS_PROJECT"]
        assert len(contains_rels) == 1

    @patch("urllib.request.urlopen")
    def test_attachments(self, mock_urlopen):
        responses = self._standard_responses()
        mock_urlopen.side_effect = self._make_graphql_mock(responses)

        conn = get_connector("linear")
        conn.authenticate({"api_key": "lin_api_test123"})
        result = conn.fetch()

        assert len(result.entities["Attachment"]) == 1
        assert result.entities["Attachment"][0]["sourceType"] == "figma"
        att_rels = [r for r in result.relationships if r["type"] == "HAS_ATTACHMENT"]
        assert len(att_rels) == 1

    @patch("urllib.request.urlopen")
    def test_linear_docs_as_documents(self, mock_urlopen):
        responses = self._standard_responses()
        mock_urlopen.side_effect = self._make_graphql_mock(responses)

        conn = get_connector("linear")
        conn.authenticate({"api_key": "lin_api_test123"})
        result = conn.fetch()

        linear_docs = [d for d in result.documents if d["type"] == "linear-doc"]
        assert len(linear_docs) == 1
        assert "Architecture Decision Record" in linear_docs[0]["title"]

    @patch("urllib.request.urlopen")
    def test_history_decision_traces(self, mock_urlopen):
        """Issue ENG-101 has 2 history entries → should produce a decision trace."""
        responses = self._standard_responses()
        mock_urlopen.side_effect = self._make_graphql_mock(responses)

        from create_context_graph.connectors.linear_connector import LinearConnector
        conn = LinearConnector()
        conn.authenticate({"api_key": "lin_api_test123"})
        # Access the internal trace generation by calling fetch
        conn.fetch()
        # The traces are generated internally but NormalizedData doesn't have a traces field.
        # We verify that the history transform function works correctly.
        from create_context_graph.connectors.linear_connector import _describe_history_step
        step = _describe_history_step({
            "createdAt": "2026-03-21",
            "fromState": {"name": "Backlog", "type": "backlog"},
            "toState": {"name": "In Progress", "type": "started"},
            "fromAssignee": None,
            "toAssignee": {"name": "Alice"},
            "fromPriority": None, "toPriority": None,
            "actor": {"id": "u1", "name": "Alice", "displayName": "Alice", "email": "a@t.com"},
            "addedLabels": [], "removedLabels": [],
        })
        assert step is not None
        assert "Backlog" in step["thought"]
        assert "In Progress" in step["thought"]
        assert "Alice" in step["action"]

    @patch("urllib.request.urlopen")
    def test_history_no_trace_for_single_entry(self, mock_urlopen):
        """Issue ENG-102 has 0 history entries → no decision trace."""
        from create_context_graph.connectors.linear_connector import _describe_history_step
        # An entry with no changes should return None
        step = _describe_history_step({
            "createdAt": "2026-03-22",
            "fromState": None, "toState": None,
            "fromAssignee": None, "toAssignee": None,
            "fromPriority": None, "toPriority": None,
            "actor": None,
            "addedLabels": [], "removedLabels": [],
        })
        assert step is None

    @patch("urllib.request.urlopen")
    def test_additional_issue_fields(self, mock_urlopen):
        responses = self._standard_responses()
        mock_urlopen.side_effect = self._make_graphql_mock(responses)

        conn = get_connector("linear")
        conn.authenticate({"api_key": "lin_api_test123"})
        result = conn.fetch()

        issue = [i for i in result.entities["Issue"] if i["identifier"] == "ENG-101"][0]
        assert issue["branchName"] == "eng/eng-101-fix-login-bug"
        assert issue["number"] == 101
        assert issue["startedAt"] == "2026-03-21"
        assert issue["trashed"] is False

    @patch("urllib.request.urlopen")
    def test_all_relationship_types(self, mock_urlopen):
        """Verify the full set of relationship types from the enhanced import."""
        responses = self._standard_responses()
        mock_urlopen.side_effect = self._make_graphql_mock(responses)

        conn = get_connector("linear")
        conn.authenticate({"api_key": "lin_api_test123"})
        result = conn.fetch()

        rel_types = {r["type"] for r in result.relationships}
        # P0: blocking relations
        assert "BLOCKS" in rel_types
        # P1: comments
        assert "HAS_COMMENT" in rel_types
        assert "AUTHORED_BY" in rel_types
        assert "REPLY_TO" in rel_types
        assert "RESOLVED_BY" in rel_types
        # P1: project updates/milestones
        assert "HAS_UPDATE" in rel_types
        assert "POSTED_BY" in rel_types
        assert "HAS_MILESTONE" in rel_types
        assert "IN_MILESTONE" in rel_types
        # P2: initiatives
        assert "OWNED_BY" in rel_types
        assert "CONTAINS_PROJECT" in rel_types
        # P2: attachments
        assert "HAS_ATTACHMENT" in rel_types


    # --- History transform edge cases ---

    def test_history_step_priority_change(self):
        from create_context_graph.connectors.linear_connector import _describe_history_step
        step = _describe_history_step({
            "createdAt": "2026-03-25",
            "fromState": None, "toState": None,
            "fromAssignee": None, "toAssignee": None,
            "fromPriority": 3, "toPriority": 1,
            "actor": {"id": "u1", "name": "Alice", "displayName": "Alice", "email": "a@t.com"},
            "addedLabels": [], "removedLabels": [],
        })
        assert step is not None
        assert "Medium" in step["thought"]
        assert "Urgent" in step["thought"]
        assert "Alice" in step["action"]

    def test_history_step_label_changes(self):
        from create_context_graph.connectors.linear_connector import _describe_history_step
        step = _describe_history_step({
            "createdAt": "2026-03-25",
            "fromState": None, "toState": None,
            "fromAssignee": None, "toAssignee": None,
            "fromPriority": None, "toPriority": None,
            "actor": {"id": "u1", "name": "Bob", "displayName": "Bob", "email": "b@t.com"},
            "addedLabels": [{"name": "Urgent"}, {"name": "P0"}],
            "removedLabels": [{"name": "Backlog"}],
        })
        assert step is not None
        assert "Urgent" in step["thought"]
        assert "P0" in step["thought"]
        assert "Backlog" in step["thought"]

    def test_history_step_reassignment(self):
        from create_context_graph.connectors.linear_connector import _describe_history_step
        step = _describe_history_step({
            "createdAt": "2026-03-25",
            "fromState": None, "toState": None,
            "fromAssignee": {"name": "Alice"},
            "toAssignee": {"name": "Bob"},
            "fromPriority": None, "toPriority": None,
            "actor": {"id": "u1", "name": "Manager", "displayName": "Manager", "email": "m@t.com"},
            "addedLabels": [], "removedLabels": [],
        })
        assert step is not None
        assert "Alice" in step["thought"]
        assert "Bob" in step["thought"]
        assert "Manager" in step["action"]

    def test_history_step_system_actor(self):
        """History entry with no actor should use 'System' as actor name."""
        from create_context_graph.connectors.linear_connector import _describe_history_step
        step = _describe_history_step({
            "createdAt": "2026-03-25",
            "fromState": {"name": "Todo", "type": "unstarted"},
            "toState": {"name": "Done", "type": "completed"},
            "fromAssignee": None, "toAssignee": None,
            "fromPriority": None, "toPriority": None,
            "actor": None,
            "addedLabels": [], "removedLabels": [],
        })
        assert step is not None
        assert "System" in step["action"]

    def test_history_step_combined_changes(self):
        """A single history entry with state + assignee + priority changes."""
        from create_context_graph.connectors.linear_connector import _describe_history_step
        step = _describe_history_step({
            "createdAt": "2026-03-25",
            "fromState": {"name": "Backlog", "type": "backlog"},
            "toState": {"name": "In Progress", "type": "started"},
            "fromAssignee": None,
            "toAssignee": {"name": "Alice"},
            "fromPriority": 4, "toPriority": 2,
            "actor": {"id": "u1", "name": "Alice", "displayName": "Alice", "email": "a@t.com"},
            "addedLabels": [{"name": "Sprint"}], "removedLabels": [],
        })
        assert step is not None
        # Should capture all changes
        assert "Backlog" in step["thought"]
        assert "In Progress" in step["thought"]
        assert "unassigned" in step["thought"]
        assert "Alice" in step["thought"]
        assert "Low" in step["thought"]  # priority 4
        assert "High" in step["thought"]  # priority 2
        assert "Sprint" in step["thought"]

    # --- Pagination test ---

    @patch("urllib.request.urlopen")
    def test_pagination_multi_page(self, mock_urlopen):
        """Verify cursor-based pagination fetches all pages."""
        page1_resp = {"data": {"users": {
            "pageInfo": {"hasNextPage": True, "endCursor": "cursor-1"},
            "nodes": [
                {"id": "user-1", "name": "Alice", "displayName": "Alice", "email": "a@t.com", "admin": True, "active": True},
            ],
        }}}
        page2_resp = {"data": {"users": {
            "pageInfo": {"hasNextPage": False, "endCursor": None},
            "nodes": [
                {"id": "user-2", "name": "Bob", "displayName": "Bob", "email": "b@t.com", "admin": False, "active": True},
            ],
        }}}

        call_count = [0]

        def mock_urlopen_fn(req):
            body = json.loads(req.data.decode())
            query = body.get("query", "")
            cursor = body.get("variables", {}).get("cursor")

            if "viewer" in query:
                resp_data = {"data": {"viewer": {"id": "u1", "name": "Test", "email": "t@t.com"}}}
            elif "users" in query:
                call_count[0] += 1
                resp_data = page2_resp if cursor == "cursor-1" else page1_resp
            else:
                resp_data = {"data": {}}

            mock_resp = MagicMock()
            mock_resp.read.return_value = json.dumps(resp_data).encode()
            mock_resp.__enter__ = MagicMock(return_value=mock_resp)
            mock_resp.__exit__ = MagicMock(return_value=False)
            mock_resp.headers = MagicMock()
            mock_resp.headers.get = MagicMock(return_value="100")
            return mock_resp

        mock_urlopen.side_effect = mock_urlopen_fn

        from create_context_graph.connectors.linear_connector import LinearConnector
        conn = LinearConnector()
        conn.authenticate({"api_key": "lin_api_test"})
        users = conn._fetch_users()
        assert len(users) == 2
        assert call_count[0] == 2  # 2 pages fetched

    # --- Error handling tests ---

    @patch("urllib.request.urlopen")
    def test_http_401_raises_value_error(self, mock_urlopen):
        import urllib.error
        mock_urlopen.side_effect = urllib.error.HTTPError(
            "https://api.linear.app/graphql", 401, "Unauthorized", {}, None
        )
        from create_context_graph.connectors.linear_connector import LinearConnector
        conn = LinearConnector()
        conn._headers = {"Authorization": "bad", "Content-Type": "application/json"}
        conn._api_key = "bad"
        with pytest.raises(ValueError, match="Invalid Linear API key"):
            conn._graphql_request("query { viewer { id } }")

    @patch("urllib.request.urlopen")
    def test_http_500_raises_runtime_error(self, mock_urlopen):
        import io
        import urllib.error
        mock_urlopen.side_effect = urllib.error.HTTPError(
            "https://api.linear.app/graphql", 500, "Internal Server Error", {},
            io.BytesIO(b'{"error": "server error"}')
        )
        from create_context_graph.connectors.linear_connector import LinearConnector
        conn = LinearConnector()
        conn._headers = {"Authorization": "key", "Content-Type": "application/json"}
        conn._api_key = "key"
        with pytest.raises(RuntimeError, match="Linear API error.*500"):
            conn._graphql_request("query { viewer { id } }")

    @patch("urllib.request.urlopen")
    def test_empty_workspace(self, mock_urlopen):
        """A workspace with no data should return empty entities without errors."""
        empty_responses = {
            "viewer": {"data": {"viewer": {"id": "u1", "name": "Test", "email": "t@t.com"}}},
            "teams": {"data": {"teams": {"nodes": []}}},
            "users(first": {"data": {"users": {"pageInfo": {"hasNextPage": False}, "nodes": []}}},
            "issueLabels": {"data": {"issueLabels": {"pageInfo": {"hasNextPage": False}, "nodes": []}}},
            "initiatives(first": {"data": {"initiatives": {"pageInfo": {"hasNextPage": False}, "nodes": []}}},
            "projects(first": {"data": {"projects": {"pageInfo": {"hasNextPage": False}, "nodes": []}}},
            "documents(first": {"data": {"documents": {"pageInfo": {"hasNextPage": False}, "nodes": []}}},
        }
        mock_urlopen.side_effect = self._make_graphql_mock(empty_responses)

        conn = get_connector("linear")
        conn.authenticate({"api_key": "lin_api_test"})
        result = conn.fetch()

        assert isinstance(result, NormalizedData)
        total_entities = sum(len(v) for v in result.entities.values())
        assert total_entities == 0
        assert len(result.relationships) == 0
        assert len(result.documents) == 0

    # --- Relationship source/target label consistency ---

    @patch("urllib.request.urlopen")
    def test_all_relationships_have_required_keys(self, mock_urlopen):
        """Every relationship must have type, source, target, source_label, target_label."""
        responses = self._standard_responses()
        mock_urlopen.side_effect = self._make_graphql_mock(responses)

        conn = get_connector("linear")
        conn.authenticate({"api_key": "lin_api_test123"})
        result = conn.fetch()

        required_keys = {"type", "source_name", "target_name", "source_label", "target_label"}
        for rel in result.relationships:
            missing = required_keys - set(rel.keys())
            assert not missing, f"Relationship {rel['type']} missing keys: {missing}"

    @patch("urllib.request.urlopen")
    def test_entity_labels_match_relationship_labels(self, mock_urlopen):
        """Relationship source/target labels should reference entity types that exist."""
        responses = self._standard_responses()
        mock_urlopen.side_effect = self._make_graphql_mock(responses)

        conn = get_connector("linear")
        conn.authenticate({"api_key": "lin_api_test123"})
        result = conn.fetch()

        entity_labels = set(result.entities.keys())
        for rel in result.relationships:
            assert rel["source_label"] in entity_labels, (
                f"Relationship {rel['type']} has source_label '{rel['source_label']}' "
                f"which is not in entity labels: {entity_labels}"
            )
            assert rel["target_label"] in entity_labels, (
                f"Relationship {rel['type']} has target_label '{rel['target_label']}' "
                f"which is not in entity labels: {entity_labels}"
            )

    # --- RELATION_TYPE_MAP coverage ---

    def test_relation_type_map_completeness(self):
        from create_context_graph.connectors.linear_connector import RELATION_TYPE_MAP
        expected_types = {"blocks", "blocked-by", "related", "duplicate"}
        assert set(RELATION_TYPE_MAP.keys()) == expected_types

    def test_priority_labels_completeness(self):
        from create_context_graph.connectors.linear_connector import PRIORITY_LABELS
        assert len(PRIORITY_LABELS) == 5
        assert PRIORITY_LABELS[0] == "No Priority"
        assert PRIORITY_LABELS[1] == "Urgent"
        assert PRIORITY_LABELS[4] == "Low"


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
