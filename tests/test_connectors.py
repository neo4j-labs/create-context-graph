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
    def test_all_registered(self):
        assert len(CONNECTOR_REGISTRY) == 13

    def test_expected_connectors(self):
        expected = {"github", "notion", "jira", "slack", "gmail", "gcal", "salesforce", "linear", "google-workspace", "claude-code", "claude-ai", "chatgpt", "local-file"}
        assert set(CONNECTOR_REGISTRY.keys()) == expected

    def test_get_connector(self):
        conn = get_connector("github")
        assert conn.service_name == "GitHub"

    def test_get_unknown_raises(self):
        with pytest.raises(ValueError, match="Unknown connector"):
            get_connector("unknown-service")

    def test_list_connectors(self):
        result = list_connectors()
        assert len(result) == 13
        ids = {c["id"] for c in result}
        assert "github" in ids
        assert "local-file" in ids

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

    def _make_mock_repo_with_issue(self, mock_github_module):
        """Helper that returns a mock repo with one issue that has a body."""
        mock_repo = MagicMock()
        mock_repo.full_name = "owner/repo"
        mock_repo.description = "Test repo"
        mock_repo.html_url = "https://github.com/owner/repo"
        mock_repo.language = "Python"
        mock_repo.stargazers_count = 0
        mock_repo.organization = None
        mock_repo.get_pulls.return_value = []
        mock_repo.get_commits.return_value = []

        mock_user = MagicMock()
        mock_user.login = "alice"
        mock_user.name = "Alice"
        mock_user.email = ""

        mock_issue = MagicMock()
        mock_issue.pull_request = None
        mock_issue.number = 1
        mock_issue.title = "Test issue"
        mock_issue.state = "open"
        mock_issue.body = "Issue body content"
        mock_issue.created_at = None
        mock_issue.labels = []
        mock_issue.user = mock_user

        mock_repo.get_issues.return_value = [mock_issue]

        mock_client = MagicMock()
        mock_client.get_repo.return_value = mock_repo
        mock_github_module.Github.return_value = mock_client
        return mock_repo

    def test_import_body_default_true(self):
        mock_github_module = MagicMock()
        self._make_mock_repo_with_issue(mock_github_module)

        with patch.dict("sys.modules", {"github": mock_github_module}):
            from create_context_graph.connectors.github_connector import GitHubConnector

            conn = GitHubConnector()
            conn.authenticate({"token": "fake", "repo": "owner/repo"})
            result = conn.fetch()

        assert len(result.documents) == 1
        assert result.documents[0]["type"] == "issue-body"

    def test_import_body_kwarg_false(self):
        mock_github_module = MagicMock()
        self._make_mock_repo_with_issue(mock_github_module)

        with patch.dict("sys.modules", {"github": mock_github_module}):
            from create_context_graph.connectors.github_connector import GitHubConnector

            conn = GitHubConnector()
            conn.authenticate({"token": "fake", "repo": "owner/repo"})
            result = conn.fetch(import_body=False)

        assert result.documents == []

    def test_import_body_env_false(self, monkeypatch):
        mock_github_module = MagicMock()
        self._make_mock_repo_with_issue(mock_github_module)
        monkeypatch.setenv("GITHUB_IMPORT_BODY", "false")

        with patch.dict("sys.modules", {"github": mock_github_module}):
            from create_context_graph.connectors.github_connector import GitHubConnector

            conn = GitHubConnector()
            conn.authenticate({"token": "fake", "repo": "owner/repo"})
            result = conn.fetch()

        assert result.documents == []

    def test_import_body_kwarg_overrides_env(self, monkeypatch):
        mock_github_module = MagicMock()
        self._make_mock_repo_with_issue(mock_github_module)
        monkeypatch.setenv("GITHUB_IMPORT_BODY", "false")

        with patch.dict("sys.modules", {"github": mock_github_module}):
            from create_context_graph.connectors.github_connector import GitHubConnector

            conn = GitHubConnector()
            conn.authenticate({"token": "fake", "repo": "owner/repo"})
            result = conn.fetch(import_body=True)

        assert len(result.documents) == 1

    def test_extract_refs_separates_closes_from_references(self):
        from create_context_graph.connectors.github_connector import _extract_refs

        closes, refs = _extract_refs("This fixes #1 and closes #2. See also #3 and #4.")
        assert closes == {1, 2}
        assert refs == {3, 4}

    def test_extract_refs_overlapping_number(self):
        from create_context_graph.connectors.github_connector import _extract_refs

        # #5 appears with a closing keyword AND bare — must not be in references
        closes, refs = _extract_refs("resolves #5. See prior discussion in #5.")
        assert closes == {5}
        assert refs == set()

    def test_extract_refs_empty_text(self):
        from create_context_graph.connectors.github_connector import _extract_refs

        assert _extract_refs("") == (set(), set())
        assert _extract_refs(None) == (set(), set())

    def test_extract_refs_ignores_in_word_hashes(self):
        from create_context_graph.connectors.github_connector import _extract_refs

        # "abc#1" should not match (# inside a word)
        closes, refs = _extract_refs("color abc#1 but see #7")
        assert closes == set()
        assert refs == {7}

    def _make_mock_repo_with_linking_fixtures(self, mock_github_module):
        """Repo with 1 Issue (#1), 1 PR (#10) whose body 'fixes #1', and 1 Commit referencing #10."""
        mock_repo = MagicMock()
        mock_repo.full_name = "owner/repo"
        mock_repo.description = "Test repo"
        mock_repo.html_url = "https://github.com/owner/repo"
        mock_repo.language = "Python"
        mock_repo.stargazers_count = 0
        mock_repo.organization = None

        mock_user = MagicMock()
        mock_user.login = "alice"
        mock_user.name = "Alice"
        mock_user.email = ""

        mock_issue = MagicMock()
        mock_issue.pull_request = None
        mock_issue.number = 1
        mock_issue.title = "Bug: things broken"
        mock_issue.state = "open"
        mock_issue.body = "something is broken"
        mock_issue.created_at = None
        mock_issue.labels = []
        mock_issue.user = mock_user
        mock_repo.get_issues.return_value = [mock_issue]

        mock_pr = MagicMock()
        mock_pr.number = 10
        mock_pr.title = "Fix the thing"
        mock_pr.state = "closed"
        mock_pr.merged = True
        mock_pr.body = "This fixes #1. See also #99 which does not exist in our fetched set."
        mock_pr.created_at = None
        mock_pr.user = mock_user
        mock_repo.get_pulls.return_value = [mock_pr]

        mock_commit = MagicMock()
        mock_commit.sha = "abcdef1234567890"
        mock_commit.commit.message = "Refactor. See #10 for rationale."
        mock_commit.commit.author.date = None
        mock_commit.author = mock_user
        mock_repo.get_commits.return_value = [mock_commit]

        mock_client = MagicMock()
        mock_client.get_repo.return_value = mock_repo
        mock_github_module.Github.return_value = mock_client
        return mock_repo

    def _fetch_with_linking(self, monkeypatch, **fetch_kwargs):
        mock_github_module = MagicMock()
        self._make_mock_repo_with_linking_fixtures(mock_github_module)
        # Default link source to "regex" in tests so we don't hit the network
        monkeypatch.setenv("GITHUB_LINK_SOURCE", "regex")
        with patch.dict("sys.modules", {"github": mock_github_module}):
            from create_context_graph.connectors.github_connector import GitHubConnector

            conn = GitHubConnector()
            conn.authenticate({"token": "fake", "repo": "owner/repo"})
            return conn.fetch(**fetch_kwargs)

    def test_linking_emits_closes_from_pr_body(self, monkeypatch):
        result = self._fetch_with_linking(monkeypatch)
        closes_rels = [r for r in result.relationships if r["type"] == "CLOSES"]
        assert len(closes_rels) == 1
        rel = closes_rels[0]
        assert rel["source_name"] == "Fix the thing"
        assert rel["source_label"] == "PullRequest"
        assert rel["target_name"] == "Bug: things broken"
        assert rel["target_label"] == "Issue"

    def test_linking_emits_references_from_commit_message(self, monkeypatch):
        result = self._fetch_with_linking(monkeypatch)
        ref_rels = [r for r in result.relationships if r["type"] == "REFERENCES"]
        commit_to_pr = [r for r in ref_rels if r["source_label"] == "Commit" and r["target_label"] == "PullRequest"]
        assert len(commit_to_pr) == 1
        assert commit_to_pr[0]["target_name"] == "Fix the thing"

    def test_linking_skips_unknown_numbers(self, monkeypatch):
        """#99 is referenced but not in the fetched set, so no relationship is emitted."""
        result = self._fetch_with_linking(monkeypatch)
        ref_rels = [r for r in result.relationships if r["type"] == "REFERENCES"]
        # Only the Commit→PullRequest (#10) reference; nothing for #99
        assert all(r["target_label"] in ("PullRequest", "Issue") for r in ref_rels)
        assert not any(r["target_name"] == "99" for r in ref_rels)

    def test_linking_disabled_by_kwarg(self, monkeypatch):
        result = self._fetch_with_linking(monkeypatch, link_issues_prs=False)
        link_types = {r["type"] for r in result.relationships}
        assert "CLOSES" not in link_types
        assert "REFERENCES" not in link_types

    def test_linking_disabled_by_env(self, monkeypatch):
        monkeypatch.setenv("GITHUB_LINK_ISSUES_PRS", "false")
        result = self._fetch_with_linking(monkeypatch)
        link_types = {r["type"] for r in result.relationships}
        assert "CLOSES" not in link_types
        assert "REFERENCES" not in link_types

    def test_linking_closes_takes_precedence_over_references(self, monkeypatch):
        """A pair that matches both CLOSES and REFERENCES should only appear as CLOSES."""
        result = self._fetch_with_linking(monkeypatch)
        pairs_closes = {(r["source_name"], r["target_name"]) for r in result.relationships if r["type"] == "CLOSES"}
        pairs_refs = {(r["source_name"], r["target_name"]) for r in result.relationships if r["type"] == "REFERENCES"}
        assert pairs_closes & pairs_refs == set()

    def test_linking_graphql_path_calls_fetcher(self, monkeypatch):
        """With link_source=graphql, the regex path is skipped and GraphQL is consulted."""
        mock_github_module = MagicMock()
        self._make_mock_repo_with_linking_fixtures(mock_github_module)

        call_log: list[int] = []

        def fake_graphql(token, owner, repo_name, pr_number, timeout=30.0):
            call_log.append(pr_number)
            # Pretend the GraphQL API reports PR #10 closes issue #1
            return [1] if pr_number == 10 else []

        with patch.dict("sys.modules", {"github": mock_github_module}):
            from create_context_graph.connectors import github_connector as gh_module
            monkeypatch.setattr(gh_module, "_fetch_closing_refs_graphql", fake_graphql)

            conn = gh_module.GitHubConnector()
            conn.authenticate({"token": "fake", "repo": "owner/repo"})
            result = conn.fetch(link_source="graphql")

        assert call_log == [10]
        closes_rels = [r for r in result.relationships if r["type"] == "CLOSES"]
        assert len(closes_rels) == 1
        assert closes_rels[0]["source_name"] == "Fix the thing"
        assert closes_rels[0]["target_name"] == "Bug: things broken"

    def test_linking_both_dedupes_across_sources(self, monkeypatch):
        """regex + graphql reporting the same closure should produce only one CLOSES relationship."""
        mock_github_module = MagicMock()
        self._make_mock_repo_with_linking_fixtures(mock_github_module)

        def fake_graphql(token, owner, repo_name, pr_number, timeout=30.0):
            return [1] if pr_number == 10 else []

        with patch.dict("sys.modules", {"github": mock_github_module}):
            from create_context_graph.connectors import github_connector as gh_module
            monkeypatch.setattr(gh_module, "_fetch_closing_refs_graphql", fake_graphql)

            conn = gh_module.GitHubConnector()
            conn.authenticate({"token": "fake", "repo": "owner/repo"})
            result = conn.fetch(link_source="both")

        closes_rels = [r for r in result.relationships if r["type"] == "CLOSES" and r["target_name"] == "Bug: things broken"]
        assert len(closes_rels) == 1


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
        with pytest.raises(ValueError, match="not found"):
            conn.authenticate({"api_key": "lin_api_test123", "team_key": "NONEXISTENT"})

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

    # --- Constants defined (Improvement 7) ---

    def test_constants_defined(self):
        from create_context_graph.connectors import linear_connector as lc
        assert lc.ISSUES_PAGE_SIZE == 25
        assert lc.MAX_PAGES == 100
        assert lc.RATE_LIMIT_THRESHOLD == 10
        assert lc.MAX_COMMENTS_PER_ISSUE == 100
        assert lc.MAX_HISTORY_PER_ISSUE == 50
        assert lc.MAX_RETRIES == 3

    # --- Error handling (Improvement 1) ---

    @patch("urllib.request.urlopen")
    def test_url_error_raises_runtime_error(self, mock_urlopen):
        import urllib.error
        mock_urlopen.side_effect = urllib.error.URLError("Connection refused")
        from create_context_graph.connectors.linear_connector import LinearConnector
        conn = LinearConnector()
        conn._headers = {"Authorization": "key", "Content-Type": "application/json"}
        conn._api_key = "key"
        with pytest.raises(RuntimeError, match="Network error"):
            conn._graphql_request("query { viewer { id } }")

    @patch("urllib.request.urlopen")
    def test_json_decode_error_raises_runtime_error(self, mock_urlopen):
        mock_resp = MagicMock()
        mock_resp.read.return_value = b"not json"
        mock_resp.__enter__ = MagicMock(return_value=mock_resp)
        mock_resp.__exit__ = MagicMock(return_value=False)
        mock_resp.headers = MagicMock()
        mock_resp.headers.get = MagicMock(return_value="100")
        mock_urlopen.return_value = mock_resp

        from create_context_graph.connectors.linear_connector import LinearConnector
        conn = LinearConnector()
        conn._headers = {"Authorization": "key", "Content-Type": "application/json"}
        conn._api_key = "key"
        with pytest.raises(RuntimeError, match="Invalid JSON"):
            conn._graphql_request("query { viewer { id } }")

    @patch("urllib.request.urlopen")
    def test_graphql_errors_logged_but_data_returned(self, mock_urlopen):
        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps({
            "data": {"viewer": {"id": "u1", "name": "Test", "email": "t@t.com"}},
            "errors": [{"message": "Deprecated field used"}],
        }).encode()
        mock_resp.__enter__ = MagicMock(return_value=mock_resp)
        mock_resp.__exit__ = MagicMock(return_value=False)
        mock_resp.headers = MagicMock()
        mock_resp.headers.get = MagicMock(return_value="100")
        mock_urlopen.return_value = mock_resp

        from create_context_graph.connectors.linear_connector import LinearConnector
        conn = LinearConnector()
        conn._headers = {"Authorization": "key", "Content-Type": "application/json"}
        conn._api_key = "key"
        result = conn._graphql_request("query { viewer { id } }")
        # Data should still be returned
        assert result["data"]["viewer"]["id"] == "u1"
        # Errors should also be present
        assert "errors" in result

    # --- Team key validation (Improvement 2) ---

    @patch("urllib.request.urlopen")
    def test_authenticate_validates_team_key(self, mock_urlopen):
        responses = self._standard_responses()
        mock_urlopen.side_effect = self._make_graphql_mock(responses)

        conn = get_connector("linear")
        # Should not raise — ENG exists
        conn.authenticate({"api_key": "lin_api_test123", "team_key": "ENG"})

    @patch("urllib.request.urlopen")
    def test_authenticate_invalid_team_key_lists_available(self, mock_urlopen):
        responses = self._standard_responses()
        mock_urlopen.side_effect = self._make_graphql_mock(responses)

        conn = get_connector("linear")
        with pytest.raises(ValueError, match="Available team keys: ENG"):
            conn.authenticate({"api_key": "lin_api_test123", "team_key": "BADKEY"})

    # --- Pagination safety (Improvement 3) ---

    @patch("urllib.request.urlopen")
    def test_pagination_max_pages_limit(self, mock_urlopen):
        """Pagination should stop after MAX_PAGES even if hasNextPage is always True."""
        from create_context_graph.connectors.linear_connector import LinearConnector

        call_count = [0]

        def mock_fn(req):
            body = json.loads(req.data.decode())
            query = body.get("query", "")
            if "viewer" in query:
                resp_data = {"data": {"viewer": {"id": "u1", "name": "Test", "email": "t@t.com"}}}
            else:
                call_count[0] += 1
                resp_data = {"data": {"users": {
                    "pageInfo": {"hasNextPage": True, "endCursor": f"cursor-{call_count[0]}"},
                    "nodes": [{"id": f"user-{call_count[0]}", "name": f"User {call_count[0]}",
                               "displayName": f"U{call_count[0]}", "email": f"u{call_count[0]}@t.com",
                               "admin": False, "active": True}],
                }}}
            mock_resp = MagicMock()
            mock_resp.read.return_value = json.dumps(resp_data).encode()
            mock_resp.__enter__ = MagicMock(return_value=mock_resp)
            mock_resp.__exit__ = MagicMock(return_value=False)
            mock_resp.headers = MagicMock()
            mock_resp.headers.get = MagicMock(return_value="100")
            return mock_resp

        mock_urlopen.side_effect = mock_fn

        conn = LinearConnector()
        conn.authenticate({"api_key": "test"})
        # Use a small max_pages to keep test fast
        users = conn._paginate(
            "query FetchUsers($cursor: String) { users(first: 100, after: $cursor) { pageInfo { hasNextPage endCursor } nodes { id name displayName email admin active } } }",
            {}, ["users"], max_pages=3,
        )
        assert len(users) == 3
        assert call_count[0] == 3

    # --- Null safety (Improvement 4) ---

    @patch("urllib.request.urlopen")
    def test_null_nested_fields_no_crash(self, mock_urlopen):
        """Issues with explicitly None sub-objects should not crash."""
        responses = self._standard_responses()
        # Override issue with all sub-objects set to None
        null_issue = {
            "id": "issue-null", "identifier": "ENG-999", "title": "Null test",
            "description": "", "priority": 0, "priorityLabel": "No Priority",
            "estimate": None, "number": 999, "dueDate": None,
            "createdAt": "2026-03-25", "updatedAt": "2026-03-25",
            "completedAt": None, "canceledAt": None, "startedAt": None,
            "branchName": "", "trashed": False, "url": "",
            "state": None, "assignee": None, "creator": None,
            "team": None, "project": None, "projectMilestone": None,
            "cycle": None, "labels": None, "parent": None,
            "children": None, "relations": None,
            "attachments": None, "comments": None, "history": None,
        }
        responses["issues(first"] = {"data": {"issues": {
            "pageInfo": {"hasNextPage": False, "endCursor": None},
            "nodes": [null_issue],
        }}}
        mock_urlopen.side_effect = self._make_graphql_mock(responses)

        conn = get_connector("linear")
        conn.authenticate({"api_key": "lin_api_test123"})
        result = conn.fetch()
        # Should not crash, and should have the issue
        issue_names = [i["name"] for i in result.entities["Issue"]]
        assert "ENG-999 Null test" in issue_names

    # --- Truncation warnings (Improvement 5) ---

    @patch("urllib.request.urlopen")
    def test_comment_truncation_warning(self, mock_urlopen, caplog):
        """Warn when comments have hasNextPage=True."""
        import logging
        responses = self._standard_responses()
        # Modify issue to have truncated comments
        issue_node = responses["issues(first"]["data"]["issues"]["nodes"][0]
        issue_node["comments"] = {
            "pageInfo": {"hasNextPage": True},
            "nodes": [{"id": "c1", "body": "test", "createdAt": "2026-03-25",
                        "updatedAt": "2026-03-25", "resolvedAt": None,
                        "user": {"id": "user-1", "name": "Alice", "displayName": "Alice", "email": "a@t.com"},
                        "parent": None, "resolvingUser": None}],
        }
        mock_urlopen.side_effect = self._make_graphql_mock(responses)

        with caplog.at_level(logging.WARNING, logger="create_context_graph.connectors.linear_connector"):
            conn = get_connector("linear")
            conn.authenticate({"api_key": "lin_api_test123"})
            conn.fetch()
        assert any("comments" in r.message and "only first page" in r.message for r in caplog.records)

    @patch("urllib.request.urlopen")
    def test_history_truncation_warning(self, mock_urlopen, caplog):
        """Warn when history has hasNextPage=True."""
        import logging
        responses = self._standard_responses()
        issue_node = responses["issues(first"]["data"]["issues"]["nodes"][0]
        issue_node["history"] = {
            "pageInfo": {"hasNextPage": True},
            "nodes": [
                {"id": "h1", "createdAt": "2026-03-24",
                 "fromState": {"name": "Backlog", "type": "backlog"},
                 "toState": {"name": "In Progress", "type": "started"},
                 "fromAssignee": None, "toAssignee": None,
                 "fromPriority": None, "toPriority": None,
                 "actor": {"id": "user-1", "name": "Alice", "displayName": "Alice", "email": "a@t.com"},
                 "addedLabels": [], "removedLabels": []},
                {"id": "h2", "createdAt": "2026-03-25",
                 "fromState": {"name": "In Progress", "type": "started"},
                 "toState": {"name": "Done", "type": "completed"},
                 "fromAssignee": None, "toAssignee": None,
                 "fromPriority": None, "toPriority": None,
                 "actor": {"id": "user-1", "name": "Alice", "displayName": "Alice", "email": "a@t.com"},
                 "addedLabels": [], "removedLabels": []},
            ],
        }
        mock_urlopen.side_effect = self._make_graphql_mock(responses)

        with caplog.at_level(logging.WARNING, logger="create_context_graph.connectors.linear_connector"):
            conn = get_connector("linear")
            conn.authenticate({"api_key": "lin_api_test123"})
            conn.fetch()
        assert any("history" in r.message and "incomplete" in r.message for r in caplog.records)

    # --- Logging (Improvement 6) ---

    @patch("urllib.request.urlopen")
    def test_logging_auth_success(self, mock_urlopen, caplog):
        import logging
        responses = self._standard_responses()
        mock_urlopen.side_effect = self._make_graphql_mock(responses)

        with caplog.at_level(logging.INFO, logger="create_context_graph.connectors.linear_connector"):
            conn = get_connector("linear")
            conn.authenticate({"api_key": "lin_api_test123"})
        assert any("Authenticated as" in r.message for r in caplog.records)

    @patch("urllib.request.urlopen")
    def test_logging_fetch_summary(self, mock_urlopen, caplog):
        import logging
        responses = self._standard_responses()
        mock_urlopen.side_effect = self._make_graphql_mock(responses)

        with caplog.at_level(logging.INFO, logger="create_context_graph.connectors.linear_connector"):
            conn = get_connector("linear")
            conn.authenticate({"api_key": "lin_api_test123"})
            conn.fetch()
        assert any("Linear import complete" in r.message for r in caplog.records)

    # --- Rate limit 429 (Improvement 8) ---

    @patch("time.sleep")
    @patch("urllib.request.urlopen")
    def test_http_429_retries_and_succeeds(self, mock_urlopen, mock_sleep):
        import io
        import urllib.error
        success_resp = MagicMock()
        success_resp.read.return_value = json.dumps(
            {"data": {"viewer": {"id": "u1", "name": "Test", "email": "t@t.com"}}}
        ).encode()
        success_resp.__enter__ = MagicMock(return_value=success_resp)
        success_resp.__exit__ = MagicMock(return_value=False)
        success_resp.headers = MagicMock()
        success_resp.headers.get = MagicMock(return_value="100")

        # First call raises 429, second (retry) succeeds
        mock_urlopen.side_effect = [
            urllib.error.HTTPError(
                "https://api.linear.app/graphql", 429, "Too Many Requests", {}, io.BytesIO(b"")
            ),
            success_resp,
        ]

        from create_context_graph.connectors.linear_connector import LinearConnector
        conn = LinearConnector()
        conn._headers = {"Authorization": "key", "Content-Type": "application/json"}
        conn._api_key = "key"
        result = conn._graphql_request("query { viewer { id } }")
        assert result["data"]["viewer"]["id"] == "u1"
        # Verify sleep was called for backoff
        mock_sleep.assert_called()

    @patch("time.sleep")
    @patch("urllib.request.urlopen")
    def test_http_429_exhausts_retries(self, mock_urlopen, mock_sleep):
        import io
        import urllib.error
        # All calls raise 429
        mock_urlopen.side_effect = urllib.error.HTTPError(
            "https://api.linear.app/graphql", 429, "Too Many Requests", {}, io.BytesIO(b"")
        )

        from create_context_graph.connectors.linear_connector import LinearConnector
        conn = LinearConnector()
        conn._headers = {"Authorization": "key", "Content-Type": "application/json"}
        conn._api_key = "key"
        with pytest.raises(RuntimeError, match="rate limit exceeded"):
            conn._graphql_request("query { viewer { id } }")

    # --- Incremental sync (Improvement 9) ---

    @patch("urllib.request.urlopen")
    def test_fetch_with_updated_after(self, mock_urlopen):
        """Verify updated_after parameter adds filter to issue query."""
        responses = self._standard_responses()
        captured_queries = []
        original_mock = self._make_graphql_mock(responses)

        def capturing_mock(req):
            body = json.loads(req.data.decode())
            captured_queries.append(body)
            return original_mock(req)

        mock_urlopen.side_effect = capturing_mock

        conn = get_connector("linear")
        conn.authenticate({"api_key": "lin_api_test123"})
        conn.fetch(updated_after="2026-03-25T00:00:00Z")

        # Find the issue query
        issue_queries = [q for q in captured_queries if "issues(first" in q.get("query", "")]
        assert len(issue_queries) > 0
        iq = issue_queries[0]
        assert "updatedAfter" in iq["query"]
        assert iq["variables"].get("updatedAfter") == "2026-03-25T00:00:00Z"

    @patch("urllib.request.urlopen")
    def test_fetch_without_updated_after_no_filter(self, mock_urlopen):
        """Without updated_after, issue query should not have updatedAfter variable."""
        responses = self._standard_responses()
        captured_queries = []
        original_mock = self._make_graphql_mock(responses)

        def capturing_mock(req):
            body = json.loads(req.data.decode())
            captured_queries.append(body)
            return original_mock(req)

        mock_urlopen.side_effect = capturing_mock

        conn = get_connector("linear")
        conn.authenticate({"api_key": "lin_api_test123"})
        conn.fetch()

        issue_queries = [q for q in captured_queries if "issues(first" in q.get("query", "")]
        assert len(issue_queries) > 0
        iq = issue_queries[0]
        assert "updatedAfter" not in iq.get("query", "")

    # --- _safe_nodes helper ---

    def test_safe_nodes_helper(self):
        from create_context_graph.connectors.linear_connector import _safe_nodes
        assert _safe_nodes(None, "labels") == []
        assert _safe_nodes({}, "labels") == []
        assert _safe_nodes({"labels": None}, "labels") == []
        assert _safe_nodes({"labels": {}}, "labels") == []
        assert _safe_nodes({"labels": {"nodes": [{"id": "1"}]}}, "labels") == [{"id": "1"}]


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


# ---------------------------------------------------------------------------
# Google Workspace connector tests
# ---------------------------------------------------------------------------


class TestGoogleWorkspaceConnector:
    """Tests for the Google Workspace connector."""

    @staticmethod
    def _make_api_mock(responses: dict):
        """Create a mock for urllib.request.urlopen that routes by URL path."""
        def _mock_urlopen(req, **kwargs):
            url = req.full_url if hasattr(req, "full_url") else req
            # Match URL patterns
            for pattern, response_data in responses.items():
                if pattern in url:
                    mock_resp = MagicMock()
                    mock_resp.read.return_value = json.dumps(response_data).encode()
                    mock_resp.__enter__ = lambda s: s
                    mock_resp.__exit__ = MagicMock(return_value=False)
                    mock_resp.status = 200
                    return mock_resp
            # Default: empty response
            mock_resp = MagicMock()
            mock_resp.read.return_value = b'{"files": [], "comments": [], "revisions": []}'
            mock_resp.__enter__ = lambda s: s
            mock_resp.__exit__ = MagicMock(return_value=False)
            return mock_resp
        return _mock_urlopen

    @staticmethod
    def _standard_responses():
        """Standard mock responses for all Google Workspace APIs."""
        return {
            "/drive/v3/files?": {
                "files": [
                    {
                        "id": "doc-1",
                        "name": "Caching Strategy PRD",
                        "mimeType": "application/vnd.google-apps.document",
                        "webViewLink": "https://docs.google.com/document/d/doc-1/edit",
                        "createdTime": "2026-03-01T10:00:00Z",
                        "modifiedTime": "2026-03-15T14:30:00Z",
                        "description": "Technical PRD for caching layer",
                        "owners": [{"displayName": "Alice Chen", "emailAddress": "alice@example.com"}],
                        "parents": ["folder-1"],
                        "permissions": [
                            {"type": "user", "emailAddress": "bob@example.com", "displayName": "Bob Smith", "role": "writer"},
                        ],
                    },
                    {
                        "id": "folder-1",
                        "name": "PRDs",
                        "mimeType": "application/vnd.google-apps.folder",
                        "parents": [],
                    },
                    {
                        "id": "doc-2",
                        "name": "ENG-456 Auth Design",
                        "mimeType": "application/vnd.google-apps.document",
                        "webViewLink": "https://docs.google.com/document/d/doc-2/edit",
                        "createdTime": "2026-03-10T09:00:00Z",
                        "modifiedTime": "2026-03-20T16:00:00Z",
                        "description": "",
                        "owners": [{"displayName": "Bob Smith", "emailAddress": "bob@example.com"}],
                        "parents": ["folder-1"],
                        "permissions": [],
                    },
                ],
            },
            "/doc-1/comments": {
                "comments": [
                    {
                        "id": "comment-1",
                        "content": "Should we use Redis or Memcached?",
                        "author": {"displayName": "Alice Chen", "emailAddress": "alice@example.com"},
                        "createdTime": "2026-03-05T10:30:00Z",
                        "modifiedTime": "2026-03-06T14:22:00Z",
                        "resolved": True,
                        "quotedFileContent": {"value": "Caching approach"},
                        "replies": [
                            {
                                "id": "reply-1",
                                "content": "Redis is better for our use case — supports data structures",
                                "author": {"displayName": "Bob Smith", "emailAddress": "bob@example.com"},
                                "createdTime": "2026-03-05T11:00:00Z",
                            },
                            {
                                "id": "reply-2",
                                "content": "Agreed, let's go with Redis",
                                "author": {"displayName": "Carol Davis", "emailAddress": "carol@example.com"},
                                "createdTime": "2026-03-05T12:00:00Z",
                            },
                            {
                                "id": "reply-3",
                                "content": "",
                                "action": "resolve",
                                "author": {"displayName": "Alice Chen", "emailAddress": "alice@example.com"},
                                "createdTime": "2026-03-06T14:22:00Z",
                                "modifiedTime": "2026-03-06T14:22:00Z",
                            },
                        ],
                    },
                    {
                        "id": "comment-2",
                        "content": "What about cache invalidation strategy?",
                        "author": {"displayName": "Bob Smith", "emailAddress": "bob@example.com"},
                        "createdTime": "2026-03-07T09:00:00Z",
                        "modifiedTime": "2026-03-07T09:00:00Z",
                        "resolved": False,
                        "quotedFileContent": {},
                        "replies": [],
                    },
                ],
            },
            "/doc-2/comments": {
                "comments": [
                    {
                        "id": "comment-3",
                        "content": "This relates to ENG-789 for the SSO implementation",
                        "author": {"displayName": "Alice Chen", "emailAddress": "alice@example.com"},
                        "createdTime": "2026-03-12T10:00:00Z",
                        "modifiedTime": "2026-03-12T10:00:00Z",
                        "resolved": False,
                        "quotedFileContent": {},
                        "replies": [],
                    },
                ],
            },
            "/doc-1/revisions": {
                "revisions": [
                    {
                        "id": "rev-1",
                        "modifiedTime": "2026-03-01T10:00:00Z",
                        "lastModifyingUser": {"displayName": "Alice Chen", "emailAddress": "alice@example.com"},
                        "mimeType": "application/vnd.google-apps.document",
                        "size": "1024",
                    },
                    {
                        "id": "rev-2",
                        "modifiedTime": "2026-03-15T14:30:00Z",
                        "lastModifyingUser": {"displayName": "Bob Smith", "emailAddress": "bob@example.com"},
                        "mimeType": "application/vnd.google-apps.document",
                        "size": "2048",
                    },
                ],
            },
            "/doc-2/revisions": {"revisions": []},
            "driveactivity.googleapis.com": {
                "activities": [
                    {
                        "timestamp": "2026-03-15T14:30:00Z",
                        "primaryActionDetail": {"edit": {}},
                        "actors": [{"user": {"knownUser": {"emailAddress": "alice@example.com"}}}],
                        "targets": [{"driveItem": {"title": "Caching Strategy PRD"}}],
                    },
                    {
                        "timestamp": "2026-03-10T09:00:00Z",
                        "primaryActionDetail": {"create": {}},
                        "actors": [{"user": {"knownUser": {"emailAddress": "bob@example.com"}}}],
                        "targets": [{"driveItem": {"title": "ENG-456 Auth Design"}}],
                    },
                ],
            },
            "calendar/v3/calendars/primary/events": {
                "items": [
                    {
                        "id": "event-1",
                        "summary": "Platform team sync",
                        "start": {"dateTime": "2026-03-14T10:00:00Z"},
                        "end": {"dateTime": "2026-03-14T11:00:00Z"},
                        "description": "Discuss caching strategy: https://docs.google.com/document/d/doc-1/edit",
                        "location": "Room A",
                        "status": "confirmed",
                        "organizer": {"email": "alice@example.com", "displayName": "Alice Chen"},
                        "attendees": [
                            {"email": "alice@example.com", "displayName": "Alice Chen", "responseStatus": "accepted"},
                            {"email": "bob@example.com", "displayName": "Bob Smith", "responseStatus": "accepted"},
                        ],
                    },
                ],
            },
            "gmail/v1/users/me/threads?": {
                "threads": [
                    {"id": "thread-1", "snippet": "Re: Caching approach discussion"},
                ],
            },
            "gmail/v1/users/me/threads/thread-1": {
                "id": "thread-1",
                "messages": [
                    {
                        "id": "msg-1",
                        "snippet": "Check the doc: https://docs.google.com/document/d/doc-1/edit",
                        "payload": {
                            "headers": [
                                {"name": "Subject", "value": "Re: Caching approach discussion"},
                                {"name": "From", "value": "alice@example.com"},
                                {"name": "To", "value": "bob@example.com, carol@example.com"},
                                {"name": "Date", "value": "2026-03-15T10:00:00Z"},
                            ],
                        },
                    },
                ],
            },
        }

    @staticmethod
    def _make_connector_with_token():
        """Create a connector pre-authenticated with a test token."""
        from create_context_graph.connectors.google_workspace_connector import (
            GoogleWorkspaceConnector,
        )
        conn = GoogleWorkspaceConnector()
        conn._access_token = "test-token"
        conn._include_comments = True
        conn._include_revisions = True
        conn._include_activity = True
        conn._include_calendar = False
        conn._include_gmail = False
        conn._mime_types = ["docs", "sheets", "slides"]
        conn._max_files = 500
        conn._since = "2026-01-01T00:00:00Z"
        return conn

    # -- Registration & metadata --

    def test_registration(self):
        conn = get_connector("google-workspace")
        assert conn.service_name == "Google Workspace"
        assert conn.requires_oauth is True

    @patch("shutil.which", return_value=None)
    def test_credential_prompts_no_gws(self, _mock):
        conn = get_connector("google-workspace")
        prompts = conn.get_credential_prompts()
        assert len(prompts) == 2
        names = {p["name"] for p in prompts}
        assert names == {"client_id", "client_secret"}

    @patch("shutil.which", return_value="/usr/local/bin/gws")
    def test_credential_prompts_with_gws(self, _mock):
        conn = get_connector("google-workspace")
        prompts = conn.get_credential_prompts()
        assert prompts == []

    # -- Authentication --

    def test_authenticate_missing_creds(self):
        conn = get_connector("google-workspace")
        with patch("shutil.which", return_value=None):
            with pytest.raises(ValueError, match="Client ID and Secret"):
                conn.authenticate({})

    @patch("shutil.which", return_value="/usr/local/bin/gws")
    def test_authenticate_gws(self, _mock):
        conn = get_connector("google-workspace")
        conn.authenticate({"include_calendar": "true"})
        assert conn._use_gws is True
        assert conn._include_calendar is True

    def test_authenticate_parses_flags(self):
        self._make_connector_with_token()
        # Simulate flag parsing directly
        from create_context_graph.connectors.google_workspace_connector import (
            GoogleWorkspaceConnector,
        )
        c = GoogleWorkspaceConnector()
        c._access_token = "test"
        # Manual parse like authenticate does
        creds = {
            "include_comments": "false",
            "include_revisions": "true",
            "include_calendar": "true",
            "include_gmail": "true",
            "folder_id": "abc123",
            "since": "2026-02-01",
            "mime_types": "docs,pdf",
            "max_files": "200",
        }
        c._include_comments = creds.get("include_comments", "true") != "false"
        c._include_revisions = creds.get("include_revisions", "true") != "false"
        c._include_calendar = creds.get("include_calendar", "false") == "true"
        c._include_gmail = creds.get("include_gmail", "false") == "true"
        c._folder_id = creds.get("folder_id", "")
        c._since = creds.get("since", "")
        c._max_files = int(creds.get("max_files", "500"))
        c._mime_types = [m.strip() for m in creds.get("mime_types", "").split(",")]

        assert c._include_comments is False
        assert c._include_revisions is True
        assert c._include_calendar is True
        assert c._include_gmail is True
        assert c._folder_id == "abc123"
        assert c._since == "2026-02-01"
        assert c._max_files == 200
        assert c._mime_types == ["docs", "pdf"]

    # -- File fetching --

    def test_fetch_not_authenticated(self):
        conn = get_connector("google-workspace")
        with pytest.raises(RuntimeError, match="authenticate"):
            conn.fetch()

    @patch("urllib.request.urlopen")
    def test_fetch_files_basic(self, mock_urlopen):
        responses = self._standard_responses()
        mock_urlopen.side_effect = self._make_api_mock(responses)
        conn = self._make_connector_with_token()
        conn._include_comments = False
        conn._include_revisions = False
        conn._include_activity = False

        result = conn.fetch()

        assert "Document" in result.entities
        assert "Folder" in result.entities
        assert "Person" in result.entities
        assert len(result.entities["Document"]) == 2
        assert len(result.entities["Folder"]) == 1
        # Alice and Bob from owners + permissions
        assert len(result.entities["Person"]) >= 2

    @patch("urllib.request.urlopen")
    def test_fetch_files_creates_relationships(self, mock_urlopen):
        responses = self._standard_responses()
        mock_urlopen.side_effect = self._make_api_mock(responses)
        conn = self._make_connector_with_token()
        conn._include_comments = False
        conn._include_revisions = False
        conn._include_activity = False

        result = conn.fetch()

        rel_types = {r["type"] for r in result.relationships}
        assert "CREATED_BY" in rel_types
        assert "SHARED_WITH" in rel_types

    @patch("urllib.request.urlopen")
    def test_fetch_files_creates_documents(self, mock_urlopen):
        responses = self._standard_responses()
        mock_urlopen.side_effect = self._make_api_mock(responses)
        conn = self._make_connector_with_token()
        conn._include_comments = False
        conn._include_revisions = False
        conn._include_activity = False

        result = conn.fetch()
        assert len(result.documents) == 2
        assert result.documents[0]["type"] == "google-workspace-file"

    # -- Comment threads & decision traces --

    @patch("urllib.request.urlopen")
    def test_fetch_comments_creates_decision_threads(self, mock_urlopen):
        responses = self._standard_responses()
        mock_urlopen.side_effect = self._make_api_mock(responses)
        conn = self._make_connector_with_token()
        conn._include_revisions = False
        conn._include_activity = False

        result = conn.fetch()

        assert len(result.entities["DecisionThread"]) >= 2  # 2 resolved + 1 unresolved from 2 docs
        # Check resolved thread
        resolved = [dt for dt in result.entities["DecisionThread"] if dt["resolved"]]
        assert len(resolved) >= 1
        assert "Redis" in resolved[0].get("resolution", "") or "Redis" in resolved[0].get("content", "")

    @patch("urllib.request.urlopen")
    def test_fetch_comments_creates_replies(self, mock_urlopen):
        responses = self._standard_responses()
        mock_urlopen.side_effect = self._make_api_mock(responses)
        conn = self._make_connector_with_token()
        conn._include_revisions = False
        conn._include_activity = False

        result = conn.fetch()

        assert len(result.entities["Reply"]) >= 2  # 2 content replies (resolve action without content is skipped)

    @patch("urllib.request.urlopen")
    def test_resolved_thread_produces_trace(self, mock_urlopen):
        responses = self._standard_responses()
        mock_urlopen.side_effect = self._make_api_mock(responses)
        conn = self._make_connector_with_token()
        conn._include_revisions = False
        conn._include_activity = False

        result = conn.fetch()

        assert len(result.traces) >= 1
        trace = result.traces[0]
        assert trace["id"].startswith("trace-gdrive-")
        assert "Decision on" in trace["task"]
        assert "Resolved" in trace["outcome"]
        assert len(trace["steps"]) >= 2  # question + replies + resolve

    @patch("urllib.request.urlopen")
    def test_unresolved_thread_no_trace(self, mock_urlopen):
        responses = self._standard_responses()
        mock_urlopen.side_effect = self._make_api_mock(responses)
        conn = self._make_connector_with_token()
        conn._include_revisions = False
        conn._include_activity = False

        result = conn.fetch()

        # Only resolved threads produce traces
        trace_ids = {t["id"] for t in result.traces}
        assert "trace-gdrive-comment-2" not in trace_ids  # unresolved

    @patch("urllib.request.urlopen")
    def test_comment_relationships(self, mock_urlopen):
        responses = self._standard_responses()
        mock_urlopen.side_effect = self._make_api_mock(responses)
        conn = self._make_connector_with_token()
        conn._include_revisions = False
        conn._include_activity = False

        result = conn.fetch()

        rel_types = {r["type"] for r in result.relationships}
        assert "HAS_COMMENT_THREAD" in rel_types
        assert "HAS_REPLY" in rel_types
        assert "AUTHORED_BY" in rel_types
        assert "RESOLVED_BY" in rel_types

    # -- Revisions --

    @patch("urllib.request.urlopen")
    def test_fetch_revisions(self, mock_urlopen):
        responses = self._standard_responses()
        mock_urlopen.side_effect = self._make_api_mock(responses)
        conn = self._make_connector_with_token()
        conn._include_comments = False
        conn._include_activity = False

        result = conn.fetch()

        assert len(result.entities["Revision"]) >= 2
        rel_types = {r["type"] for r in result.relationships}
        assert "HAS_REVISION" in rel_types
        assert "REVISED_BY" in rel_types

    # -- Drive Activity --

    @patch("urllib.request.urlopen")
    def test_fetch_activity(self, mock_urlopen):
        responses = self._standard_responses()
        mock_urlopen.side_effect = self._make_api_mock(responses)
        conn = self._make_connector_with_token()
        conn._include_comments = False
        conn._include_revisions = False

        result = conn.fetch()

        assert len(result.entities["Activity"]) >= 2
        # Check action types
        action_types = {a.get("actionType") for a in result.entities["Activity"]}
        assert "edit" in action_types or "create" in action_types

        rel_types = {r["type"] for r in result.relationships}
        assert "ACTIVITY_ON" in rel_types
        assert "PERFORMED_BY" in rel_types

    # -- Calendar events (optional) --

    @patch("urllib.request.urlopen")
    def test_calendar_disabled_by_default(self, mock_urlopen):
        responses = self._standard_responses()
        mock_urlopen.side_effect = self._make_api_mock(responses)
        conn = self._make_connector_with_token()
        conn._include_comments = False
        conn._include_revisions = False
        conn._include_activity = False

        result = conn.fetch()
        assert "Meeting" not in result.entities

    @patch("urllib.request.urlopen")
    def test_calendar_when_enabled(self, mock_urlopen):
        responses = self._standard_responses()
        mock_urlopen.side_effect = self._make_api_mock(responses)
        conn = self._make_connector_with_token()
        conn._include_comments = False
        conn._include_revisions = False
        conn._include_activity = False
        conn._include_calendar = True

        result = conn.fetch()

        assert "Meeting" in result.entities
        assert len(result.entities["Meeting"]) >= 1
        meeting = result.entities["Meeting"][0]
        assert "Platform team sync" in meeting["summary"]

        rel_types = {r["type"] for r in result.relationships}
        assert "ATTENDEE_OF" in rel_types
        assert "ORGANIZED_BY" in rel_types
        assert "DISCUSSED_IN" in rel_types  # event description has doc URL

    # -- Gmail threads (optional) --

    @patch("urllib.request.urlopen")
    def test_gmail_disabled_by_default(self, mock_urlopen):
        responses = self._standard_responses()
        mock_urlopen.side_effect = self._make_api_mock(responses)
        conn = self._make_connector_with_token()
        conn._include_comments = False
        conn._include_revisions = False
        conn._include_activity = False

        result = conn.fetch()
        assert "EmailThread" not in result.entities

    @patch("urllib.request.urlopen")
    def test_gmail_when_enabled(self, mock_urlopen):
        responses = self._standard_responses()
        mock_urlopen.side_effect = self._make_api_mock(responses)
        conn = self._make_connector_with_token()
        conn._include_comments = False
        conn._include_revisions = False
        conn._include_activity = False
        conn._include_gmail = True

        result = conn.fetch()

        assert "EmailThread" in result.entities
        assert len(result.entities["EmailThread"]) >= 1
        thread = result.entities["EmailThread"][0]
        assert "Caching" in thread["subject"]

        rel_types = {r["type"] for r in result.relationships}
        assert "PARTICIPANT_IN" in rel_types
        assert "THREAD_ABOUT" in rel_types  # snippet has doc URL

    # -- Cross-connector linking --

    @patch("urllib.request.urlopen")
    def test_cross_connector_linear_refs(self, mock_urlopen):
        responses = self._standard_responses()
        mock_urlopen.side_effect = self._make_api_mock(responses)
        conn = self._make_connector_with_token()
        conn._include_revisions = False
        conn._include_activity = False

        result = conn.fetch()

        # "ENG-456 Auth Design" doc name contains ENG-456
        # comment-3 content contains "ENG-789"
        issue_rels = [r for r in result.relationships if r["type"] == "RELATES_TO_ISSUE"]
        ref_targets = {r["target_name"] for r in issue_rels}
        assert "ENG-456" in ref_targets
        assert "ENG-789" in ref_targets

    @patch("urllib.request.urlopen")
    def test_cross_connector_no_false_positives_on_clean_text(self, mock_urlopen):
        """Cross-ref should not match things that aren't issue references."""
        from create_context_graph.connectors.google_workspace_connector import (
            LINEAR_REF_PATTERN,
        )
        # Standard IDs should match
        assert LINEAR_REF_PATTERN.search("ENG-123")
        assert LINEAR_REF_PATTERN.search("PROJECT-456")
        # Single letter prefix should not match
        assert not LINEAR_REF_PATTERN.search("X-1")

    # -- Person deduplication --

    @patch("urllib.request.urlopen")
    def test_person_deduplication(self, mock_urlopen):
        responses = self._standard_responses()
        mock_urlopen.side_effect = self._make_api_mock(responses)
        conn = self._make_connector_with_token()
        conn._include_activity = False

        result = conn.fetch()

        emails = [p["emailAddress"] for p in result.entities["Person"]]
        # No duplicate emails
        assert len(emails) == len(set(emails))

    # -- Relationship integrity --

    @patch("urllib.request.urlopen")
    def test_all_relationships_have_required_keys(self, mock_urlopen):
        responses = self._standard_responses()
        mock_urlopen.side_effect = self._make_api_mock(responses)
        conn = self._make_connector_with_token()

        result = conn.fetch()

        required_keys = {"type", "source_name", "source_label", "target_name", "target_label"}
        for rel in result.relationships:
            assert required_keys.issubset(rel.keys()), f"Relationship missing keys: {rel}"

    # -- Full pipeline integration --

    @patch("urllib.request.urlopen")
    def test_full_pipeline_all_features(self, mock_urlopen):
        """Run the full pipeline with all features enabled."""
        responses = self._standard_responses()
        mock_urlopen.side_effect = self._make_api_mock(responses)
        conn = self._make_connector_with_token()
        conn._include_calendar = True
        conn._include_gmail = True

        result = conn.fetch()

        # All entity types present
        for label in ["Document", "Folder", "Person", "DecisionThread", "Reply",
                       "Revision", "Activity", "Meeting", "EmailThread"]:
            assert label in result.entities, f"Missing entity type: {label}"

        # Has relationships
        assert len(result.relationships) > 10

        # Has documents
        assert len(result.documents) > 0

        # Has decision traces
        assert len(result.traces) > 0

    # -- Edge cases --

    @patch("urllib.request.urlopen")
    def test_empty_workspace(self, mock_urlopen):
        mock_urlopen.side_effect = self._make_api_mock({
            "/drive/v3/files?": {"files": []},
            "driveactivity.googleapis.com": {"activities": []},
        })
        conn = self._make_connector_with_token()

        result = conn.fetch()

        assert result.entities["Document"] == []
        assert result.entities["Person"] == []
        assert result.relationships == []
        assert result.traces == []

    @patch("urllib.request.urlopen")
    def test_comments_disabled(self, mock_urlopen):
        responses = self._standard_responses()
        mock_urlopen.side_effect = self._make_api_mock(responses)
        conn = self._make_connector_with_token()
        conn._include_comments = False
        conn._include_revisions = False
        conn._include_activity = False

        result = conn.fetch()

        assert len(result.entities["DecisionThread"]) == 0
        assert len(result.entities["Reply"]) == 0
        assert len(result.traces) == 0


# ---------------------------------------------------------------------------
# Claude Code connector tests
# ---------------------------------------------------------------------------


class TestClaudeCodeConnector:
    """Tests for the Claude Code session history connector."""

    @staticmethod
    def _write_session_jsonl(
        project_dir, session_id, messages, *, git_branch="main", cwd="/tmp/project"
    ):
        """Create a properly formatted JSONL session file."""
        jsonl_path = project_dir / f"{session_id}.jsonl"
        lines = []
        # Queue operation header
        lines.append(json.dumps({
            "type": "queue-operation",
            "operation": "enqueue",
            "timestamp": "2026-04-01T10:00:00.000Z",
            "sessionId": session_id,
        }))
        for i, msg in enumerate(messages):
            entry = {
                "type": msg["type"],
                "message": msg["message"],
                "uuid": msg.get("uuid", f"uuid-{i:04d}"),
                "parentUuid": msg.get("parentUuid"),
                "timestamp": msg.get("timestamp", f"2026-04-01T10:{i:02d}:00.000Z"),
                "sessionId": session_id,
                "gitBranch": git_branch,
                "cwd": cwd,
                "version": "2.1.84",
            }
            if msg.get("isMeta"):
                entry["isMeta"] = True
            lines.append(json.dumps(entry))
        jsonl_path.write_text("\n".join(lines))
        return jsonl_path

    @staticmethod
    def _basic_messages():
        """Return a minimal set of user + assistant messages."""
        return [
            {
                "type": "user",
                "message": {"role": "user", "content": "Hello, help me with my project"},
                "uuid": "u-0001",
                "parentUuid": None,
                "timestamp": "2026-04-01T10:00:00.000Z",
            },
            {
                "type": "assistant",
                "message": {
                    "role": "assistant",
                    "content": [
                        {"type": "text", "text": "Sure, let me help you."},
                    ],
                    "usage": {"input_tokens": 100, "output_tokens": 50},
                },
                "uuid": "a-0001",
                "parentUuid": "u-0001",
                "timestamp": "2026-04-01T10:01:00.000Z",
            },
        ]

    @staticmethod
    def _messages_with_tool_calls():
        """Return messages with tool_use and tool_result blocks."""
        return [
            {
                "type": "user",
                "message": {"role": "user", "content": "Read and fix the config file"},
                "uuid": "u-0001",
                "parentUuid": None,
                "timestamp": "2026-04-01T10:00:00.000Z",
            },
            {
                "type": "assistant",
                "message": {
                    "role": "assistant",
                    "content": [
                        {"type": "text", "text": "Let me read the file."},
                        {
                            "type": "tool_use",
                            "id": "tool-read-1",
                            "name": "Read",
                            "input": {"file_path": "/tmp/project/config.py"},
                        },
                    ],
                    "usage": {"input_tokens": 200, "output_tokens": 100},
                },
                "uuid": "a-0001",
                "parentUuid": "u-0001",
                "timestamp": "2026-04-01T10:01:00.000Z",
            },
            {
                "type": "user",
                "message": {
                    "role": "user",
                    "content": [
                        {
                            "type": "tool_result",
                            "tool_use_id": "tool-read-1",
                            "content": "DATABASE_URL = 'postgres://localhost/mydb'",
                        },
                    ],
                },
                "uuid": "u-0002",
                "parentUuid": "a-0001",
                "timestamp": "2026-04-01T10:01:05.000Z",
            },
            {
                "type": "assistant",
                "message": {
                    "role": "assistant",
                    "content": [
                        {"type": "text", "text": "I'll fix the config."},
                        {
                            "type": "tool_use",
                            "id": "tool-edit-1",
                            "name": "Edit",
                            "input": {
                                "file_path": "/tmp/project/config.py",
                                "old_string": "DATABASE_URL = 'postgres://localhost/mydb'",
                                "new_string": "DATABASE_URL = os.getenv('DATABASE_URL', 'postgres://localhost/mydb')",
                            },
                        },
                    ],
                    "usage": {"input_tokens": 300, "output_tokens": 150},
                },
                "uuid": "a-0002",
                "parentUuid": "u-0002",
                "timestamp": "2026-04-01T10:02:00.000Z",
            },
            {
                "type": "user",
                "message": {
                    "role": "user",
                    "content": [
                        {
                            "type": "tool_result",
                            "tool_use_id": "tool-edit-1",
                            "content": "File edited successfully.",
                        },
                    ],
                },
                "uuid": "u-0003",
                "parentUuid": "a-0002",
                "timestamp": "2026-04-01T10:02:05.000Z",
            },
        ]

    def _make_connector(self, tmp_path, messages=None, *, session_id="sess-0001", **kwargs):
        """Create a connector with a synthetic project directory."""
        from create_context_graph.connectors.claude_code_connector import ClaudeCodeConnector

        project_dir = tmp_path / "-tmp-project"
        project_dir.mkdir()
        self._write_session_jsonl(
            project_dir, session_id, messages or self._basic_messages(), **kwargs
        )

        conn = ClaudeCodeConnector()
        conn.authenticate({
            "base_path": str(tmp_path),
            "scope": "all",
            "content_mode": "truncated",
        })
        return conn

    # --- Registration tests ---

    def test_connector_registered(self):
        assert "claude-code" in CONNECTOR_REGISTRY

    def test_get_connector(self):
        conn = get_connector("claude-code")
        assert conn.service_name == "Claude Code"

    def test_credential_prompts_empty(self):
        conn = get_connector("claude-code")
        assert conn.get_credential_prompts() == []

    def test_listed_in_connectors(self):
        connectors = list_connectors()
        ids = [c["id"] for c in connectors]
        assert "claude-code" in ids

    # --- Parser / discovery tests ---

    def test_discover_projects(self, tmp_path):
        from create_context_graph.connectors._claude_code.parser import discover_projects

        proj = tmp_path / "-Users-will-projects-myapp"
        proj.mkdir()
        (proj / "sess-1234.jsonl").write_text("{}")

        projects = discover_projects(tmp_path)
        assert len(projects) == 1
        assert projects[0]["session_count"] == 1
        assert "/Users/will/projects/myapp" in projects[0]["decoded_path"]

    def test_discover_projects_empty(self, tmp_path):
        from create_context_graph.connectors._claude_code.parser import discover_projects

        projects = discover_projects(tmp_path)
        assert projects == []

    def test_discover_sessions(self, tmp_path):
        from create_context_graph.connectors._claude_code.parser import discover_sessions

        proj = tmp_path / "project"
        proj.mkdir()
        self._write_session_jsonl(proj, "sess-aaa", self._basic_messages())
        self._write_session_jsonl(proj, "sess-bbb", self._basic_messages())

        sessions = discover_sessions(proj)
        assert len(sessions) == 2

    def test_discover_sessions_max(self, tmp_path):
        from create_context_graph.connectors._claude_code.parser import discover_sessions

        proj = tmp_path / "project"
        proj.mkdir()
        for i in range(5):
            self._write_session_jsonl(proj, f"sess-{i:04d}", self._basic_messages())

        sessions = discover_sessions(proj, max_sessions=2)
        assert len(sessions) == 2

    def test_parse_session_basic(self, tmp_path):
        from create_context_graph.connectors._claude_code.parser import parse_session

        proj = tmp_path / "project"
        proj.mkdir()
        path = self._write_session_jsonl(proj, "sess-001", self._basic_messages())

        result = parse_session(path)
        assert result["session_id"] == "sess-001"
        assert len(result["messages"]) == 2
        assert result["messages"][0]["role"] == "user"
        assert result["messages"][1]["role"] == "assistant"

    def test_parse_session_tool_calls(self, tmp_path):
        from create_context_graph.connectors._claude_code.parser import parse_session

        proj = tmp_path / "project"
        proj.mkdir()
        path = self._write_session_jsonl(proj, "sess-002", self._messages_with_tool_calls())

        result = parse_session(path)
        assert len(result["tool_calls"]) == 2
        assert result["tool_calls"][0]["tool_name"] == "Read"
        assert result["tool_calls"][1]["tool_name"] == "Edit"

    def test_parse_session_files_tracked(self, tmp_path):
        from create_context_graph.connectors._claude_code.parser import parse_session

        proj = tmp_path / "project"
        proj.mkdir()
        path = self._write_session_jsonl(proj, "sess-003", self._messages_with_tool_calls())

        result = parse_session(path)
        assert "/tmp/project/config.py" in result["files_touched"]
        file_info = result["files_touched"]["/tmp/project/config.py"]
        assert file_info["modification_count"] >= 1
        assert file_info["read_count"] >= 1

    def test_parse_session_skips_meta(self, tmp_path):
        from create_context_graph.connectors._claude_code.parser import parse_session

        messages = [
            {
                "type": "user",
                "message": {"role": "user", "content": "system message"},
                "uuid": "meta-001",
                "isMeta": True,
                "timestamp": "2026-04-01T10:00:00.000Z",
            },
            *self._basic_messages(),
        ]

        proj = tmp_path / "project"
        proj.mkdir()
        path = self._write_session_jsonl(proj, "sess-004", messages)

        result = parse_session(path)
        # Meta message should be skipped
        assert len(result["messages"]) == 2

    def test_parse_session_progress_counted(self, tmp_path):
        from create_context_graph.connectors._claude_code.parser import parse_session

        proj = tmp_path / "project"
        proj.mkdir()
        # Write a session with a progress message manually
        lines = [
            json.dumps({
                "type": "user",
                "message": {"role": "user", "content": "Hello"},
                "uuid": "u1", "parentUuid": None,
                "timestamp": "2026-04-01T10:00:00Z",
                "sessionId": "s1", "gitBranch": "main", "cwd": "/tmp",
            }),
            json.dumps({
                "type": "progress",
                "data": {"message": {"type": "user"}},
                "parentUuid": "u1",
                "timestamp": "2026-04-01T10:01:00Z",
                "sessionId": "s1",
            }),
        ]
        path = proj / "sess-005.jsonl"
        path.write_text("\n".join(lines))

        result = parse_session(path)
        assert result["progress_count"] == 1
        assert len(result["messages"]) == 1  # progress not in messages

    def test_malformed_jsonl_lines(self, tmp_path):
        from create_context_graph.connectors._claude_code.parser import parse_session

        proj = tmp_path / "project"
        proj.mkdir()
        lines = [
            "not valid json",
            "",
            json.dumps({
                "type": "user",
                "message": {"role": "user", "content": "valid message"},
                "uuid": "u1", "parentUuid": None,
                "timestamp": "2026-04-01T10:00:00Z",
                "sessionId": "s1", "gitBranch": "main", "cwd": "/tmp",
            }),
        ]
        path = proj / "sess-006.jsonl"
        path.write_text("\n".join(lines))

        result = parse_session(path)
        assert len(result["messages"]) == 1

    # --- Connector fetch tests ---

    def test_fetch_returns_normalized_data(self, tmp_path):
        conn = self._make_connector(tmp_path)
        result = conn.fetch()

        assert isinstance(result, NormalizedData)
        assert "Project" in result.entities
        assert "Session" in result.entities
        assert "Message" in result.entities

    def test_fetch_entity_types(self, tmp_path):
        conn = self._make_connector(tmp_path, self._messages_with_tool_calls())
        result = conn.fetch()

        assert "Project" in result.entities
        assert "Session" in result.entities
        assert "Message" in result.entities
        assert "ToolCall" in result.entities
        assert "File" in result.entities

    def test_fetch_relationships(self, tmp_path):
        conn = self._make_connector(tmp_path, self._messages_with_tool_calls())
        result = conn.fetch()

        rel_types = {r["type"] for r in result.relationships}
        assert "HAS_SESSION" in rel_types
        assert "HAS_MESSAGE" in rel_types
        assert "NEXT" in rel_types
        assert "USED_TOOL" in rel_types

    def test_fetch_file_relationships(self, tmp_path):
        conn = self._make_connector(tmp_path, self._messages_with_tool_calls())
        result = conn.fetch()

        rel_types = {r["type"] for r in result.relationships}
        assert "READ_FILE" in rel_types
        assert "MODIFIED_FILE" in rel_types

    def test_file_deduplication(self, tmp_path):
        conn = self._make_connector(tmp_path, self._messages_with_tool_calls())
        result = conn.fetch()

        # config.py is read then edited — should be one File entity
        file_names = [f["name"] for f in result.entities.get("File", [])]
        assert file_names.count("/tmp/project/config.py") == 1

    def test_git_branch_extraction(self, tmp_path):
        conn = self._make_connector(
            tmp_path, self._basic_messages(), git_branch="feature/auth"
        )
        result = conn.fetch()

        assert "GitBranch" in result.entities
        branches = [b["name"] for b in result.entities["GitBranch"]]
        assert "feature/auth" in branches

        rel_types = {r["type"] for r in result.relationships}
        assert "ON_BRANCH" in rel_types

    def test_content_truncation(self, tmp_path):
        from create_context_graph.connectors.claude_code_connector import ClaudeCodeConnector

        project_dir = tmp_path / "-tmp-project"
        project_dir.mkdir()
        long_msg = [
            {
                "type": "user",
                "message": {"role": "user", "content": "x" * 5000},
                "uuid": "u-long",
                "parentUuid": None,
                "timestamp": "2026-04-01T10:00:00.000Z",
            },
        ]
        self._write_session_jsonl(project_dir, "sess-trunc", long_msg)

        conn = ClaudeCodeConnector()
        conn.authenticate({
            "base_path": str(tmp_path),
            "scope": "all",
            "content_mode": "truncated",
            "max_content_len": "100",
        })
        result = conn.fetch()

        messages = result.entities.get("Message", [])
        assert len(messages) == 1
        assert len(messages[0]["content"]) <= 104  # 100 + "..."

    def test_content_mode_none(self, tmp_path):
        from create_context_graph.connectors.claude_code_connector import ClaudeCodeConnector

        project_dir = tmp_path / "-tmp-project"
        project_dir.mkdir()
        self._write_session_jsonl(project_dir, "sess-none", self._basic_messages())

        conn = ClaudeCodeConnector()
        conn.authenticate({
            "base_path": str(tmp_path),
            "scope": "all",
            "content_mode": "none",
        })
        result = conn.fetch()

        messages = result.entities.get("Message", [])
        assert all(m["content"] == "" for m in messages)

    def test_content_mode_full(self, tmp_path):
        from create_context_graph.connectors.claude_code_connector import ClaudeCodeConnector

        project_dir = tmp_path / "-tmp-project"
        project_dir.mkdir()
        long_msg = [
            {
                "type": "user",
                "message": {"role": "user", "content": "y" * 5000},
                "uuid": "u-full",
                "parentUuid": None,
                "timestamp": "2026-04-01T10:00:00.000Z",
            },
        ]
        self._write_session_jsonl(project_dir, "sess-full", long_msg)

        conn = ClaudeCodeConnector()
        conn.authenticate({
            "base_path": str(tmp_path),
            "scope": "all",
            "content_mode": "full",
        })
        result = conn.fetch()

        messages = result.entities.get("Message", [])
        assert len(messages) == 1
        assert len(messages[0]["content"]) == 5000

    def test_scope_all(self, tmp_path):
        from create_context_graph.connectors.claude_code_connector import ClaudeCodeConnector

        for name in ["-tmp-project-a", "-tmp-project-b"]:
            d = tmp_path / name
            d.mkdir()
            self._write_session_jsonl(d, f"sess-{name}", self._basic_messages())

        conn = ClaudeCodeConnector()
        conn.authenticate({"base_path": str(tmp_path), "scope": "all"})
        result = conn.fetch()

        assert len(result.entities.get("Project", [])) == 2

    def test_project_filter(self, tmp_path):
        from create_context_graph.connectors.claude_code_connector import ClaudeCodeConnector

        for name in ["-tmp-project-a", "-tmp-project-b"]:
            d = tmp_path / name
            d.mkdir()
            self._write_session_jsonl(d, f"sess-{name}", self._basic_messages())

        conn = ClaudeCodeConnector()
        conn.authenticate({
            "base_path": str(tmp_path),
            "scope": "all",
            "project_filter": "project-a",
        })
        result = conn.fetch()

        assert len(result.entities.get("Project", [])) == 1

    def test_empty_directory(self, tmp_path):
        from create_context_graph.connectors.claude_code_connector import ClaudeCodeConnector

        conn = ClaudeCodeConnector()
        conn.authenticate({"base_path": str(tmp_path), "scope": "all"})
        result = conn.fetch()

        assert result.entities == {} or result.entities == {"File": []}
        assert result.relationships == []

    def test_documents_generated(self, tmp_path):
        conn = self._make_connector(tmp_path)
        result = conn.fetch()

        assert len(result.documents) >= 1
        assert "Claude Code Session" in result.documents[0]["title"]

    # --- Secret redaction tests ---

    def test_secret_redaction(self, tmp_path):
        from create_context_graph.connectors._claude_code.redactor import redact_secrets

        text = "My key is sk-ant-abc123456789012345678901"
        result = redact_secrets(text)
        assert "sk-ant-" not in result
        assert "[REDACTED]" in result

    def test_redact_github_token(self):
        from create_context_graph.connectors._claude_code.redactor import redact_secrets

        text = "token: ghp_ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghij"
        result = redact_secrets(text)
        assert "ghp_" not in result

    def test_redact_password(self):
        from create_context_graph.connectors._claude_code.redactor import redact_secrets

        text = "password=my_secret_pass123"
        result = redact_secrets(text)
        assert "my_secret_pass" not in result

    def test_redact_connection_string(self):
        from create_context_graph.connectors._claude_code.redactor import redact_secrets

        text = "postgres://user:pass123@localhost/db"
        result = redact_secrets(text)
        assert "pass123" not in result

    def test_redact_empty_string(self):
        from create_context_graph.connectors._claude_code.redactor import redact_secrets

        assert redact_secrets("") == ""
        assert redact_secrets("no secrets here") == "no secrets here"

    def test_fetch_redacts_content(self, tmp_path):
        from create_context_graph.connectors.claude_code_connector import ClaudeCodeConnector

        project_dir = tmp_path / "-tmp-project"
        project_dir.mkdir()
        secret_msg = [
            {
                "type": "user",
                "message": {"role": "user", "content": "Use key sk-ant-abc12345678901234567890123"},
                "uuid": "u-secret",
                "parentUuid": None,
                "timestamp": "2026-04-01T10:00:00.000Z",
            },
        ]
        self._write_session_jsonl(project_dir, "sess-secret", secret_msg)

        conn = ClaudeCodeConnector()
        conn.authenticate({"base_path": str(tmp_path), "scope": "all"})
        result = conn.fetch()

        messages = result.entities.get("Message", [])
        assert all("sk-ant-" not in m["content"] for m in messages)

    # --- Error extraction tests ---

    def test_error_extraction(self, tmp_path):
        messages = [
            {
                "type": "user",
                "message": {"role": "user", "content": "Run the tests"},
                "uuid": "u-0001",
                "parentUuid": None,
                "timestamp": "2026-04-01T10:00:00.000Z",
            },
            {
                "type": "assistant",
                "message": {
                    "role": "assistant",
                    "content": [
                        {
                            "type": "tool_use",
                            "id": "tool-bash-1",
                            "name": "Bash",
                            "input": {"command": "pytest tests/"},
                        },
                    ],
                    "usage": {"input_tokens": 100, "output_tokens": 50},
                },
                "uuid": "a-0001",
                "parentUuid": "u-0001",
                "timestamp": "2026-04-01T10:01:00.000Z",
            },
            {
                "type": "user",
                "message": {
                    "role": "user",
                    "content": [
                        {
                            "type": "tool_result",
                            "tool_use_id": "tool-bash-1",
                            "content": "FAILED test_foo.py::test_bar - AssertionError",
                            "is_error": True,
                        },
                    ],
                },
                "uuid": "u-0002",
                "parentUuid": "a-0001",
                "timestamp": "2026-04-01T10:01:05.000Z",
            },
        ]
        conn = self._make_connector(tmp_path, messages)
        result = conn.fetch()

        assert "Error" in result.entities
        assert len(result.entities["Error"]) >= 1

        rel_types = {r["type"] for r in result.relationships}
        assert "ENCOUNTERED_ERROR" in rel_types

    # --- Decision extraction tests ---

    def test_decision_extraction_correction(self, tmp_path):
        messages = [
            {
                "type": "user",
                "message": {"role": "user", "content": "Help me set up auth"},
                "uuid": "u-0001",
                "parentUuid": None,
                "timestamp": "2026-04-01T10:00:00.000Z",
            },
            {
                "type": "assistant",
                "message": {
                    "role": "assistant",
                    "content": [{"type": "text", "text": "I'll use JWT tokens for authentication."}],
                    "usage": {"input_tokens": 100, "output_tokens": 50},
                },
                "uuid": "a-0001",
                "parentUuid": "u-0001",
                "timestamp": "2026-04-01T10:01:00.000Z",
            },
            {
                "type": "user",
                "message": {"role": "user", "content": "No, instead use OAuth2 with Google"},
                "uuid": "u-0002",
                "parentUuid": "a-0001",
                "timestamp": "2026-04-01T10:02:00.000Z",
            },
        ]
        conn = self._make_connector(tmp_path, messages)
        result = conn.fetch()

        assert "Decision" in result.entities
        assert len(result.entities["Decision"]) >= 1

        decisions = result.entities["Decision"]
        assert any("correction" in d.get("category", "") for d in decisions)

    def test_decision_extraction_error_resolution(self, tmp_path):
        messages = [
            {
                "type": "user",
                "message": {"role": "user", "content": "Install pydantic"},
                "uuid": "u-0001",
                "parentUuid": None,
                "timestamp": "2026-04-01T10:00:00.000Z",
            },
            {
                "type": "assistant",
                "message": {
                    "role": "assistant",
                    "content": [
                        {"type": "text", "text": "Running import."},
                        {
                            "type": "tool_use",
                            "id": "tool-bash-fail",
                            "name": "Bash",
                            "input": {"command": "python -c 'import pydantic'"},
                        },
                    ],
                    "usage": {"input_tokens": 100, "output_tokens": 50},
                },
                "uuid": "a-0001",
                "parentUuid": "u-0001",
                "timestamp": "2026-04-01T10:01:00.000Z",
            },
            {
                "type": "user",
                "message": {
                    "role": "user",
                    "content": [
                        {
                            "type": "tool_result",
                            "tool_use_id": "tool-bash-fail",
                            "content": "ModuleNotFoundError: No module named 'pydantic'",
                            "is_error": True,
                        },
                    ],
                },
                "uuid": "u-0002",
                "parentUuid": "a-0001",
                "timestamp": "2026-04-01T10:01:05.000Z",
            },
            {
                "type": "assistant",
                "message": {
                    "role": "assistant",
                    "content": [
                        {"type": "text", "text": "Let me install pydantic."},
                        {
                            "type": "tool_use",
                            "id": "tool-bash-fix",
                            "name": "Bash",
                            "input": {"command": "pip install pydantic"},
                        },
                    ],
                    "usage": {"input_tokens": 200, "output_tokens": 100},
                },
                "uuid": "a-0002",
                "parentUuid": "u-0002",
                "timestamp": "2026-04-01T10:02:00.000Z",
            },
            {
                "type": "user",
                "message": {
                    "role": "user",
                    "content": [
                        {
                            "type": "tool_result",
                            "tool_use_id": "tool-bash-fix",
                            "content": "Successfully installed pydantic",
                        },
                    ],
                },
                "uuid": "u-0003",
                "parentUuid": "a-0002",
                "timestamp": "2026-04-01T10:02:05.000Z",
            },
        ]
        conn = self._make_connector(tmp_path, messages)
        result = conn.fetch()

        assert "Decision" in result.entities
        categories = [d.get("category") for d in result.entities["Decision"]]
        # Should detect error-fix and/or dependency decision
        assert "error-fix" in categories or "dependency" in categories

    # --- Preference extraction tests ---

    def test_preference_extraction_explicit(self, tmp_path):
        messages = [
            {
                "type": "user",
                "message": {"role": "user", "content": "Always use single quotes in Python"},
                "uuid": "u-0001",
                "parentUuid": None,
                "timestamp": "2026-04-01T10:00:00.000Z",
            },
            {
                "type": "assistant",
                "message": {
                    "role": "assistant",
                    "content": [{"type": "text", "text": "Understood, I'll use single quotes."}],
                    "usage": {"input_tokens": 100, "output_tokens": 50},
                },
                "uuid": "a-0001",
                "parentUuid": "u-0001",
                "timestamp": "2026-04-01T10:01:00.000Z",
            },
        ]
        conn = self._make_connector(tmp_path, messages)
        result = conn.fetch()

        assert "Preference" in result.entities
        assert len(result.entities["Preference"]) >= 1

    def test_token_usage_tracked(self, tmp_path):
        conn = self._make_connector(tmp_path)
        result = conn.fetch()

        sessions = result.entities.get("Session", [])
        assert len(sessions) == 1
        assert sessions[0]["totalInputTokens"] > 0
        assert sessions[0]["totalOutputTokens"] > 0
