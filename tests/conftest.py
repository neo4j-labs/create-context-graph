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

"""Shared test fixtures."""

from __future__ import annotations

from pathlib import Path

import pytest
from click.testing import CliRunner

from create_context_graph.config import ProjectConfig
from create_context_graph.ontology import load_domain


# ---------------------------------------------------------------------------
# CliRunner shim — v0.11 default backend is NAMS, which requires a key in
# non-interactive mode. Existing CLI tests across the suite (test_cli.py,
# test_matrix.py, test_performance.py, test_chat_import.py) were written when
# bolt was the default; without `--self-hosted` they all hit the new
# "NAMS API key required" guard. This wrapper auto-injects `--self-hosted`
# unless the test explicitly chose a backend, preserving bolt-test semantics
# without rewriting hundreds of invocations.
# ---------------------------------------------------------------------------


class _AutoSelfHostedRunner(CliRunner):
    """CliRunner that auto-injects ``--self-hosted`` when no backend is chosen."""

    _BACKEND_MARKERS = (
        "--self-hosted",
        "--nams-api-key",
        "--neo4j-uri",
        "--neo4j-aura-env",
        "--neo4j-local",
    )

    def invoke(self, cli, args=None, *a, **kw):  # type: ignore[override]
        if isinstance(args, list):
            joined = " ".join(args)
            if not any(marker in joined for marker in self._BACKEND_MARKERS):
                # Skip backend injection for utility commands.
                if "--list-domains" not in args and "--version" not in args:
                    args = list(args) + ["--self-hosted"]
        return super().invoke(cli, args, *a, **kw)


@pytest.fixture
def runner():
    """Pre-bolt-default CLI runner. Auto-adds ``--self-hosted`` to invocations.

    Tests that need to exercise the NAMS path should use ``nams_runner`` (a
    bare ``CliRunner()``) or pass ``--nams-api-key`` explicitly.
    """
    return _AutoSelfHostedRunner()


@pytest.fixture
def nams_runner():
    """Bare CliRunner without the auto-self-hosted shim — for NAMS-path tests."""
    return CliRunner()


def pytest_addoption(parser):
    parser.addoption("--slow", action="store_true", default=False, help="Run slow tests")
    parser.addoption("--integration", action="store_true", default=False,
                     help="Run integration tests (requires Neo4j)")
    parser.addoption("--functional", action="store_true", default=False,
                     help="Run functional tests that exercise full pipelines "
                          "against realistic on-disk fixtures (slower than unit tests)")


def pytest_collection_modifyitems(config, items):
    if not config.getoption("--slow"):
        skip_slow = pytest.mark.skip(reason="Use --slow to run")
        for item in items:
            if "slow" in item.keywords:
                item.add_marker(skip_slow)

    if not config.getoption("--integration"):
        skip_int = pytest.mark.skip(reason="Use --integration to run (requires Neo4j)")
        for item in items:
            if "integration" in item.keywords:
                item.add_marker(skip_int)

    if not config.getoption("--functional"):
        skip_func = pytest.mark.skip(reason="Use --functional to run")
        for item in items:
            if "functional" in item.keywords:
                item.add_marker(skip_func)


@pytest.fixture
def tmp_output(tmp_path: Path) -> Path:
    """Provide a clean temporary output directory."""
    out = tmp_path / "test-project"
    out.mkdir()
    return out


@pytest.fixture
def financial_config() -> ProjectConfig:
    """A minimal config for the financial-services domain (self-hosted bolt)."""
    return ProjectConfig(
        project_name="Test Financial App",
        domain="financial-services",
        framework="pydanticai",
        memory_backend="bolt",
        neo4j_uri="neo4j://localhost:7687",
        neo4j_username="neo4j",
        neo4j_password="password",
        neo4j_type="docker",
    )


@pytest.fixture
def healthcare_config() -> ProjectConfig:
    """A config for the healthcare domain with Claude Agent SDK (self-hosted bolt)."""
    return ProjectConfig(
        project_name="Test Health App",
        domain="healthcare",
        framework="claude-agent-sdk",
        memory_backend="bolt",
        neo4j_uri="neo4j://localhost:7687",
        neo4j_username="neo4j",
        neo4j_password="password",
        neo4j_type="docker",
    )


@pytest.fixture
def nams_config() -> ProjectConfig:
    """A config that targets the default NAMS backend."""
    return ProjectConfig(
        project_name="Test NAMS App",
        domain="financial-services",
        framework="strands",
        nams_api_key="test-key-123",
    )


@pytest.fixture
def financial_ontology():
    """Load the financial-services ontology."""
    return load_domain("financial-services")


@pytest.fixture
def healthcare_ontology():
    """Load the healthcare ontology."""
    return load_domain("healthcare")


@pytest.fixture
def mcp_config() -> ProjectConfig:
    """A config with MCP server enabled (self-hosted bolt)."""
    return ProjectConfig(
        project_name="Test MCP App",
        domain="financial-services",
        framework="pydanticai",
        memory_backend="bolt",
        neo4j_uri="neo4j://localhost:7687",
        neo4j_username="neo4j",
        neo4j_password="password",
        neo4j_type="docker",
        with_mcp=True,
        mcp_profile="extended",
    )
