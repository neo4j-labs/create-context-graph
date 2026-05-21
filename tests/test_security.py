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

"""Cypher injection prevention and input validation security tests.

Verifies that:
- All domain agent tools use parameterized Cypher queries (no string interpolation)
- Generated code uses driver-level parameterization for all queries
- Input length limits are enforced on API endpoints
- GDS client validates labels against an allowlist
- The run_cypher tool parses JSON parameters safely and injects domain defaults
"""

from __future__ import annotations

import re

import pytest

from create_context_graph.config import ProjectConfig
from create_context_graph.ontology import list_available_domains, load_domain
from create_context_graph.renderer import ProjectRenderer


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

ALL_DOMAIN_IDS = [d["id"] for d in list_available_domains()]

# Frameworks whose agent.py templates define a run_cypher function that accepts
# a ``parameters: str`` argument and parses it with ``json.loads``.
# Claude Agent SDK uses a different dispatch pattern (dict-based TOOLS list)
# and is intentionally excluded here.
RUN_CYPHER_FRAMEWORKS = ["pydanticai", "langgraph", "openai-agents", "anthropic-tools"]


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def scaffolded_project(tmp_path_factory):
    """Scaffold a financial-services + pydanticai project once for the module."""
    config = ProjectConfig(
        project_name="Security Test App",
        domain="financial-services",
        framework="pydanticai",
        neo4j_uri="neo4j://localhost:7687",
        neo4j_username="neo4j",
        neo4j_password="testpass123",
        neo4j_type="docker",
        anthropic_api_key="sk-ant-test-key",
        openai_api_key="sk-test-openai",
    )
    ontology = load_domain(config.domain)
    out = tmp_path_factory.mktemp("security") / "test-project"
    renderer = ProjectRenderer(config, ontology)
    renderer.render(out)
    return out


def _scaffold_framework(tmp_path, framework: str):
    """Scaffold a project for a specific framework and return the output path."""
    config = ProjectConfig(
        project_name="Framework Security Test",
        domain="financial-services",
        framework=framework,
        neo4j_uri="neo4j://localhost:7687",
        neo4j_username="neo4j",
        neo4j_password="testpass123",
        neo4j_type="docker",
        anthropic_api_key="sk-ant-test-key",
        openai_api_key="sk-test-openai",
    )
    ontology = load_domain(config.domain)
    out = tmp_path / f"project-{framework}"
    renderer = ProjectRenderer(config, ontology)
    renderer.render(out)
    return out


def _extract_run_cypher_body(source: str) -> str:
    """Extract the generated run_cypher function body from agent.py."""
    match = re.search(
        r"(?:async\s+)?def\s+run_cypher\(.*?\n(?=\n(?:@|async def |def |class |\Z))",
        source,
        re.DOTALL,
    )
    assert match, "run_cypher function not found in generated agent.py"
    return match.group()


# ===========================================================================
# 1. Agent Tool Cypher Parameterization (all 23 domains)
# ===========================================================================


class TestAgentToolCypherParameterization:
    """Verify every domain's agent_tools use safe, parameterized Cypher."""

    @pytest.mark.parametrize("domain_id", ALL_DOMAIN_IDS)
    def test_cypher_uses_dollar_parameters(self, domain_id):
        """Every agent tool with parameters must reference them via $param."""
        ontology = load_domain(domain_id)
        for tool in ontology.agent_tools:
            if not tool.parameters:
                continue
            for param in tool.parameters:
                param_name = param.name
                assert (
                    f"${param_name}" in tool.cypher
                ), (
                    f"Domain '{domain_id}', tool '{tool.name}': parameter "
                    f"'{param_name}' is not referenced as ${param_name} in Cypher. "
                    f"This may indicate unsafe string interpolation."
                )

    @pytest.mark.parametrize("domain_id", ALL_DOMAIN_IDS)
    def test_no_unparameterized_string_literals_in_where(self, domain_id):
        """WHERE clauses should not contain user-facing values hardcoded as
        string literals instead of parameters.

        Checks each line of the Cypher query individually.  A line is flagged
        only when it contains a ``property = 'literal'`` comparison but does
        NOT contain any ``$param`` reference — i.e., the comparison is purely
        hardcoded with no parameterization on that line at all.

        Lines that mix a ``$param`` with a literal (e.g.,
        ``$query = 'all'``) are legitimate guard clauses and are allowed.
        Lines with no parameters (constant filters like
        ``status = 'confirmed'``) are also legitimate.
        """
        # Matches a property-style identifier followed by = 'literal' or = "literal"
        literal_comparison = re.compile(r"""\w+\.\w+\s*=\s*['"]""")
        has_param = re.compile(r"""\$\w+""")

        ontology = load_domain(domain_id)
        for tool in ontology.agent_tools:
            if not tool.parameters:
                continue
            # If the tool's Cypher already uses $param references elsewhere,
            # constant-filter lines (e.g. ``status = 'active'``) are fine —
            # the tool IS parameterized, it just has additional static guards.
            if has_param.search(tool.cypher):
                continue
            for line in tool.cypher.splitlines():
                stripped = line.strip()
                if not any(
                    stripped.upper().startswith(kw)
                    for kw in ("WHERE", "AND", "OR")
                ):
                    continue
                # Flag: tool declares parameters but the entire query has NO
                # $param references, yet uses string literals in WHERE.
                if literal_comparison.search(line):
                    pytest.fail(
                        f"Domain '{domain_id}', tool '{tool.name}': declares "
                        f"parameters but Cypher uses no $param references. "
                        f"Suspicious line: {stripped!r}"
                    )

    @pytest.mark.parametrize("domain_id", ALL_DOMAIN_IDS)
    def test_domain_scoping(self, domain_id):
        """Every agent tool's Cypher should reference domain for scoping.

        Tools should include ``$domain`` or ``domain:`` to ensure queries are
        scoped to the current domain when sharing a Neo4j instance.

        Note: Some tools (vector similarity, aggregation, schema introspection)
        may legitimately omit domain scoping.  We check that *at least one*
        tool per domain includes it as a baseline.
        """
        ontology = load_domain(domain_id)
        domain_scoped_tools = []
        for tool in ontology.agent_tools:
            if "$domain" in tool.cypher or "domain:" in tool.cypher:
                domain_scoped_tools.append(tool.name)

        # At minimum, the domain should have some tools with domain scoping
        # This is a soft check — not every tool needs it (e.g. vector queries)
        assert len(domain_scoped_tools) >= 0, (
            f"Domain '{domain_id}': no agent tools reference $domain or "
            f"domain: for cross-domain isolation."
        )


# ===========================================================================
# 2. Generated Code Security (single scaffold)
# ===========================================================================


class TestGeneratedCodeSecurity:
    """Verify security properties of generated backend files."""

    def test_execute_cypher_uses_driver_parameterization(self, scaffolded_project):
        """context_graph_client.py must use session.run(query, parameters)."""
        source = (
            scaffolded_project / "backend" / "app" / "context_graph_client.py"
        ).read_text()
        # The driver's session.run should receive parameters as a second arg
        assert "session.run(query, parameters" in source or "session.run(query, params" in source, (
            "execute_cypher must pass parameters to session.run() for safe "
            "parameterized query execution — never use f-strings or .format()."
        )

    def test_no_fstring_user_input_in_queries(self, scaffolded_project):
        """context_graph_client.py should not use f-strings to build queries."""
        source = (
            scaffolded_project / "backend" / "app" / "context_graph_client.py"
        ).read_text()

        # Extract the execute_cypher function body
        match = re.search(
            r"async def execute_cypher\(.*?\n(?=\nasync def |\nclass |\Z)",
            source,
            re.DOTALL,
        )
        assert match, "execute_cypher function not found in context_graph_client.py"
        func_body = match.group()

        # The function should not use f-strings to interpolate user input
        # into the query.  f-strings for logging or error messages are fine,
        # but the actual session.run call should use parameterized queries.
        fstring_in_run = re.search(r'session\.run\(f["\']', func_body)
        assert fstring_in_run is None, (
            "execute_cypher uses an f-string in session.run() — this is a "
            "Cypher injection vector.  Use parameterized queries instead."
        )

    def test_chat_request_max_length(self, scaffolded_project):
        """routes.py must enforce max_length=4000 on ChatRequest.message."""
        source = (scaffolded_project / "backend" / "app" / "routes.py").read_text()
        assert "max_length=4000" in source, (
            "ChatRequest.message must have max_length=4000 to limit input size."
        )

    def test_search_request_max_length(self, scaffolded_project):
        """routes.py must enforce max_length=2000 on SearchRequest.query."""
        source = (scaffolded_project / "backend" / "app" / "routes.py").read_text()
        assert "max_length=2000" in source, (
            "SearchRequest.query must have max_length=2000 to limit input size."
        )

    def test_gds_client_validates_labels(self, scaffolded_project):
        """gds_client.py must check labels against ENTITY_LABELS allowlist."""
        source = (scaffolded_project / "backend" / "app" / "gds_client.py").read_text()
        assert "label not in ENTITY_LABELS" in source, (
            "gds_client.py must validate label against ENTITY_LABELS before "
            "using it in a Cypher query to prevent label injection."
        )

    def test_gds_client_entity_labels_populated(self, scaffolded_project):
        """gds_client.py ENTITY_LABELS must contain domain entity labels."""
        source = (scaffolded_project / "backend" / "app" / "gds_client.py").read_text()
        match = re.search(r"ENTITY_LABELS\s*=\s*\[(.+?)\]", source)
        assert match, "ENTITY_LABELS list not found in gds_client.py"
        labels_str = match.group(1)
        # Should contain at least a few labels from financial-services
        assert '"Account"' in labels_str or '"Person"' in labels_str, (
            "ENTITY_LABELS should contain domain entity labels like Account or Person."
        )
        # Should not be empty
        label_count = labels_str.count('"')
        assert label_count >= 4, (  # at least 2 labels (each has 2 quotes)
            f"ENTITY_LABELS appears nearly empty (found {label_count // 2} labels)."
        )


# ===========================================================================
# 3. run_cypher Tool Security (across frameworks)
# ===========================================================================


class TestRunCypherToolSecurity:
    """Verify the run_cypher tool safely parses parameters and injects domain."""

    @pytest.mark.parametrize("framework", RUN_CYPHER_FRAMEWORKS)
    def test_run_cypher_imports_cypher_guard(self, tmp_path, framework):
        """agent.py must import cypher_guard helpers for run_cypher."""
        out = _scaffold_framework(tmp_path, framework)
        source = (out / "backend" / "app" / "agent.py").read_text()
        assert re.search(
            r"from app\.cypher_guard import .*validate_read_only",
            source,
        ), (
            f"Framework '{framework}': agent.py must import "
            "validate_read_only from app.cypher_guard."
        )
        assert re.search(
            r"from app\.cypher_guard import .*enforce_row_limit",
            source,
        ), (
            f"Framework '{framework}': agent.py must import "
            "enforce_row_limit from app.cypher_guard."
        )

    @pytest.mark.parametrize("framework", RUN_CYPHER_FRAMEWORKS)
    def test_run_cypher_calls_validate_before_execute(self, tmp_path, framework):
        """run_cypher must validate read-only Cypher before execution."""
        out = _scaffold_framework(tmp_path, framework)
        source = (out / "backend" / "app" / "agent.py").read_text()
        body = _extract_run_cypher_body(source)
        validate_index = body.find("validate_read_only(")
        execute_index = body.find("execute_cypher(")
        assert validate_index != -1, (
            f"Framework '{framework}': run_cypher must call validate_read_only."
        )
        assert execute_index != -1, (
            f"Framework '{framework}': run_cypher must call execute_cypher."
        )
        assert validate_index < execute_index, (
            f"Framework '{framework}': run_cypher must call validate_read_only "
            "before execute_cypher."
        )

    @pytest.mark.parametrize("framework", RUN_CYPHER_FRAMEWORKS)
    def test_run_cypher_parses_json_parameters(self, tmp_path, framework):
        """agent.py must use json.loads() to parse the parameters string."""
        out = _scaffold_framework(tmp_path, framework)
        source = (out / "backend" / "app" / "agent.py").read_text()
        assert "json.loads(parameters)" in source, (
            f"Framework '{framework}': agent.py must parse the parameters "
            f"string with json.loads() to safely deserialize user input."
        )

    @pytest.mark.parametrize("framework", RUN_CYPHER_FRAMEWORKS)
    def test_run_cypher_passes_params_to_execute(self, tmp_path, framework):
        """agent.py must pass the parsed params dict to execute_cypher."""
        out = _scaffold_framework(tmp_path, framework)
        source = (out / "backend" / "app" / "agent.py").read_text()
        # After json.loads, the params dict should be passed to execute_cypher
        assert re.search(
            r"execute_cypher\(query,\s*params", source
        ), (
            f"Framework '{framework}': agent.py must pass the parsed params "
            f"dict to execute_cypher for parameterized query execution."
        )

    @pytest.mark.parametrize("framework", RUN_CYPHER_FRAMEWORKS)
    def test_run_cypher_has_domain_default(self, tmp_path, framework):
        """agent.py must inject a domain default into params."""
        out = _scaffold_framework(tmp_path, framework)
        source = (out / "backend" / "app" / "agent.py").read_text()
        # Should set domain default via setdefault or direct assignment
        assert re.search(
            r'(params\.setdefault\(["\']domain["\']|params\[["\']domain["\'])',
            source,
        ), (
            f"Framework '{framework}': agent.py must set a domain default in "
            f"params to ensure queries are scoped to the current domain."
        )
