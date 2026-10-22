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

"""GitHub connector — imports issues, PRs, commits, and contributors."""

from __future__ import annotations

import json
import logging
import os
import re
import urllib.error
import urllib.request
from itertools import islice
from typing import Any

from create_context_graph.connectors import (
    BaseConnector,
    NormalizedData,
    register_connector,
)

logger = logging.getLogger(__name__)

# Matches "fixes #123", "closes #4", "resolved #12" — case-insensitive.
_CLOSING_KEYWORD_PATTERN = re.compile(
    r"\b(?:close[sd]?|fix(?:es|ed)?|resolve[sd]?)\s+#(\d+)\b",
    re.IGNORECASE,
)
# Matches any "#123". The negative lookbehind avoids matching inside words (e.g., "abc#1").
_REFERENCE_PATTERN = re.compile(r"(?<![A-Za-z0-9_])#(\d+)\b")

_GRAPHQL_ENDPOINT = "https://api.github.com/graphql"
_GRAPHQL_CLOSING_ISSUES_QUERY = """
query($owner: String!, $name: String!, $number: Int!) {
  repository(owner: $owner, name: $name) {
    pullRequest(number: $number) {
      closingIssuesReferences(first: 50) {
        nodes { number }
      }
    }
  }
}
""".strip()


def _extract_refs(text: str) -> tuple[set[int], set[int]]:
    """Return (closes, references) sets of issue/PR numbers found in text.

    A number preceded by a closing keyword (fixes/closes/resolves) goes in `closes`
    only; all other `#N` mentions go in `references`.
    """
    if not text:
        return set(), set()
    closes = {int(m.group(1)) for m in _CLOSING_KEYWORD_PATTERN.finditer(text)}
    references = {int(m.group(1)) for m in _REFERENCE_PATTERN.finditer(text)} - closes
    return closes, references


def _fetch_closing_refs_graphql(
    token: str,
    owner: str,
    repo_name: str,
    pr_number: int,
    timeout: float = 30.0,
) -> list[int]:
    """Query GitHub GraphQL for authoritative closing-issue references on a PR.

    Returns a list of issue numbers the PR will close when merged. On any error
    (network, JSON, missing fields), returns an empty list and logs a warning.
    """
    payload = json.dumps({
        "query": _GRAPHQL_CLOSING_ISSUES_QUERY,
        "variables": {"owner": owner, "name": repo_name, "number": pr_number},
    }).encode()
    req = urllib.request.Request(
        _GRAPHQL_ENDPOINT,
        data=payload,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read())
    except (urllib.error.URLError, json.JSONDecodeError, TimeoutError) as exc:
        logger.warning("GraphQL closingIssuesReferences failed for PR #%s: %s", pr_number, exc)
        return []
    try:
        nodes = data["data"]["repository"]["pullRequest"]["closingIssuesReferences"]["nodes"]
    except (KeyError, TypeError):
        return []
    return [n["number"] for n in nodes if n and "number" in n]


@register_connector("github")
class GitHubConnector(BaseConnector):
    """Import data from GitHub repositories."""

    service_name = "GitHub"
    service_description = "Import issues, PRs, commits, and contributors from a GitHub repository"
    requires_oauth = False

    def __init__(self):
        self._client = None
        self._repo = None
        self._token: str = ""
        self._owner: str = ""
        self._repo_name: str = ""

    def get_credential_prompts(self) -> list[dict[str, Any]]:
        return [
            {
                "name": "token",
                "prompt": "GitHub personal access token:",
                "secret": True,
                "description": "Token with repo read access (Settings > Developer settings > Personal access tokens)",
            },
            {
                "name": "repo",
                "prompt": "GitHub repository (owner/repo):",
                "secret": False,
                "description": "e.g. neo4j-labs/create-context-graph",
            },
        ]

    def authenticate(self, credentials: dict[str, str]) -> None:
        try:
            from github import Auth, Github
        except ImportError:
            raise ImportError(
                "PyGithub is required for the GitHub connector. "
                "Install it with: pip install PyGithub"
            )

        # Positional-token construction is deprecated (removed in PyGithub 3).
        self._client = Github(auth=Auth.Token(credentials["token"]))
        self._repo = self._client.get_repo(credentials["repo"])
        self._token = credentials["token"]
        if "/" in credentials["repo"]:
            self._owner, self._repo_name = credentials["repo"].split("/", 1)

    def fetch(self, **kwargs: Any) -> NormalizedData:
        if not self._repo:
            raise RuntimeError("Call authenticate() first")

        default_limit = kwargs.get("limit", 20)
        issues_limit = kwargs.get("issues_limit", default_limit)
        prs_limit = kwargs.get("prs_limit", default_limit)
        commits_limit = kwargs.get("commits_limit", default_limit)
        _env_import_body = os.environ.get("GITHUB_IMPORT_BODY", "true").lower() not in ("false", "0", "no")
        import_body = kwargs.get("import_body", _env_import_body)
        _env_link = os.environ.get("GITHUB_LINK_ISSUES_PRS", "true").lower() not in ("false", "0", "no")
        link_issues_prs = kwargs.get("link_issues_prs", _env_link)
        link_source = kwargs.get("link_source", os.environ.get("GITHUB_LINK_SOURCE", "both")).lower()
        if link_source not in ("regex", "graphql", "both"):
            link_source = "both"
        entities: dict[str, list[dict]] = {
            "Person": [],
            "Organization": [],
            "Repository": [],
            "Issue": [],
            "PullRequest": [],
            "Commit": [],
        }
        relationships: list[dict] = []
        documents: list[dict] = []
        seen_users: set[str] = set()
        # (source_name, source_label, full_text) — scanned for issue/PR refs after all entities are fetched
        text_sources: list[tuple[str, str, str]] = []
        # Number -> (label, name) for resolving #N references
        number_to_entity: dict[int, tuple[str, str]] = {}
        pr_numbers_fetched: list[int] = []

        # Repository entity
        repo = self._repo
        entities["Repository"].append({
            "name": repo.full_name,
            "description": repo.description or "",
            "url": repo.html_url,
            "language": repo.language or "",
            "stars": repo.stargazers_count,
        })

        # Organization
        if repo.organization:
            entities["Organization"].append({
                "name": repo.organization.login,
                "description": repo.organization.name or repo.organization.login,
            })
            relationships.append({
                "type": "BELONGS_TO",
                "source_name":repo.full_name,
                "source_label": "Repository",
                "target_name":repo.organization.login,
                "target_label": "Organization",
            })

        def _add_user(user) -> str:
            if user and user.login not in seen_users:
                seen_users.add(user.login)
                entities["Person"].append({
                    "name": user.name or user.login,
                    "email": user.email or "",
                    "role": "contributor",
                    "description": f"GitHub user @{user.login}",
                })
            return user.login if user else "unknown"

        # Issues
        for issue in islice(repo.get_issues(state="all", sort="updated", direction="desc"), issues_limit):
            if issue.pull_request:
                continue  # Skip PRs in issues list
            user_name = _add_user(issue.user)
            entities["Issue"].append({
                "name": issue.title,
                "issue_number": issue.number,
                "state": issue.state,
                "created_at": issue.created_at.isoformat() if issue.created_at else "",
                "labels": ",".join(label.name for label in issue.labels),
            })
            relationships.append({
                "type": "OPENED",
                "source_name":user_name,
                "source_label": "Person",
                "target_name":issue.title,
                "target_label": "Issue",
            })
            if import_body and issue.body:
                documents.append({
                    "title": f"Issue #{issue.number}: {issue.title}",
                    "content": issue.body,
                    "type": "issue-body",
                    "metadata": {
                        "number": issue.number,
                        "state": issue.state,
                        "author": user_name,
                    },
                })
            number_to_entity[issue.number] = ("Issue", issue.title)
            if issue.body:
                text_sources.append((issue.title, "Issue", issue.body))

        # Pull Requests
        for pr in islice(repo.get_pulls(state="all", sort="updated", direction="desc"), prs_limit):
            user_name = _add_user(pr.user)
            entities["PullRequest"].append({
                "name": pr.title,
                "pr_number": pr.number,
                "state": pr.state,
                "merged": pr.merged,
                "created_at": pr.created_at.isoformat() if pr.created_at else "",
            })
            relationships.append({
                "type": "OPENED",
                "source_name":user_name,
                "source_label": "Person",
                "target_name":pr.title,
                "target_label": "PullRequest",
            })
            if import_body and pr.body:
                documents.append({
                    "title": f"PR #{pr.number}: {pr.title}",
                    "content": pr.body,
                    "type": "pr-body",
                    "metadata": {
                        "number": pr.number,
                        "state": pr.state,
                        "merged": pr.merged,
                        "author": user_name,
                    },
                })
            number_to_entity[pr.number] = ("PullRequest", pr.title)
            pr_numbers_fetched.append(pr.number)
            if pr.body:
                text_sources.append((pr.title, "PullRequest", pr.body))

        # Recent commits
        for commit in islice(repo.get_commits(), commits_limit):
            author_name = "unknown"
            if commit.author:
                author_name = _add_user(commit.author)
            full_message = commit.commit.message or ""
            entities["Commit"].append({
                "name": commit.sha[:8],
                "message": full_message.split("\n")[0],
                "sha": commit.sha,
                "date": commit.commit.author.date.isoformat() if commit.commit.author.date else "",
            })
            relationships.append({
                "type": "COMMITTED",
                "source_name":author_name,
                "source_label": "Person",
                "target_name":commit.sha[:8],
                "target_label": "Commit",
            })
            relationships.append({
                "type": "COMMITTED_TO",
                "source_name":commit.sha[:8],
                "source_label": "Commit",
                "target_name":repo.full_name,
                "target_label": "Repository",
            })
            if full_message:
                text_sources.append((commit.sha[:8], "Commit", full_message))

        # Add CONTRIBUTED_TO relationships for all users
        for user in seen_users:
            relationships.append({
                "type": "CONTRIBUTED_TO",
                "source_name":user,
                "source_label": "Person",
                "target_name":repo.full_name,
                "target_label": "Repository",
            })

        # Link issues / PRs / commits via CLOSES and REFERENCES
        if link_issues_prs:
            # CLOSES pairs are tracked so REFERENCES is never added for the same edge,
            # and so regex + GraphQL don't double-count the same closure.
            closes_pairs: set[tuple[str, str, str, str]] = set()

            def _add_closes(src_name: str, src_label: str, tgt_name: str, tgt_label: str) -> None:
                key = (src_name, src_label, tgt_name, tgt_label)
                if key in closes_pairs or (src_name, src_label) == (tgt_name, tgt_label):
                    return
                closes_pairs.add(key)
                relationships.append({
                    "type": "CLOSES",
                    "source_name": src_name,
                    "source_label": src_label,
                    "target_name": tgt_name,
                    "target_label": tgt_label,
                })

            def _add_references(src_name: str, src_label: str, tgt_name: str, tgt_label: str) -> None:
                if (src_name, src_label, tgt_name, tgt_label) in closes_pairs:
                    return
                if (src_name, src_label) == (tgt_name, tgt_label):
                    return
                relationships.append({
                    "type": "REFERENCES",
                    "source_name": src_name,
                    "source_label": src_label,
                    "target_name": tgt_name,
                    "target_label": tgt_label,
                })

            if link_source in ("regex", "both"):
                for src_name, src_label, text in text_sources:
                    closes, refs = _extract_refs(text)
                    for num in closes:
                        target = number_to_entity.get(num)
                        if target:
                            _add_closes(src_name, src_label, target[1], target[0])
                    for num in refs:
                        target = number_to_entity.get(num)
                        if target:
                            _add_references(src_name, src_label, target[1], target[0])

            if link_source in ("graphql", "both") and self._token and self._owner and self._repo_name:
                for pr_number in pr_numbers_fetched:
                    pr_entity = number_to_entity.get(pr_number)
                    if not pr_entity:
                        continue
                    closing_nums = _fetch_closing_refs_graphql(
                        self._token, self._owner, self._repo_name, pr_number,
                    )
                    for issue_num in closing_nums:
                        target = number_to_entity.get(issue_num)
                        if target:
                            _add_closes(pr_entity[1], pr_entity[0], target[1], target[0])

        return NormalizedData(
            entities=entities,
            relationships=relationships,
            documents=documents,
        )
