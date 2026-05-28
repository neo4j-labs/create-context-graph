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

"""Deep validation tests for generated project files.

Verifies that scaffolded projects have correct structure,
valid syntax, and expected content.
"""

from __future__ import annotations

import json
import re

import pytest
import yaml

from create_context_graph.config import ProjectConfig
from create_context_graph.ontology import load_domain
from create_context_graph.renderer import ProjectRenderer


@pytest.fixture
def generated_project(tmp_path):
    """Scaffold a full project and return its path. Uses self-hosted bolt backend."""
    config = ProjectConfig(
        project_name="Deep Validation App",
        domain="financial-services",
        framework="pydanticai",
        memory_backend="bolt",
        neo4j_uri="neo4j://localhost:7687",
        neo4j_username="neo4j",
        neo4j_password="testpass123",
        neo4j_type="docker",
        anthropic_api_key="sk-ant-test-key",
        openai_api_key="sk-test-openai",
    )
    ontology = load_domain(config.domain)
    out = tmp_path / "test-project"
    renderer = ProjectRenderer(config, ontology)
    renderer.render(out)
    return out, config


class TestGeneratedPythonFiles:
    """All generated Python files must be syntactically valid."""

    PYTHON_FILES = [
        "backend/app/main.py",
        "backend/app/config.py",
        "backend/app/agent.py",
        "backend/app/routes.py",
        "backend/app/models.py",
        "backend/app/constants.py",
        "backend/app/context_graph_client.py",
        "backend/app/gds_client.py",
        "backend/app/vector_client.py",
        "backend/scripts/generate_data.py",
    ]

    @pytest.mark.parametrize("py_file", PYTHON_FILES)
    def test_python_file_compiles(self, generated_project, py_file):
        out, _ = generated_project
        path = out / py_file
        assert path.exists(), f"Missing: {py_file}"
        source = path.read_text()
        try:
            compile(source, str(path), "exec")
        except SyntaxError as e:
            pytest.fail(f"{py_file} syntax error: {e}")

    def test_init_py_exists(self, generated_project):
        out, _ = generated_project
        assert (out / "backend" / "app" / "__init__.py").exists()


@pytest.fixture
def generated_project_with_connectors(tmp_path):
    """Scaffold a self-hosted bolt project with a connector enabled so the
    ``backend/scripts/import_data.py`` template gets emitted (it is gated
    behind ``saas_connectors`` in the renderer)."""
    config = ProjectConfig(
        project_name="Import Data Bolt App",
        domain="healthcare",
        framework="strands",
        memory_backend="bolt",
        neo4j_uri="neo4j://localhost:7687",
        neo4j_username="neo4j",
        neo4j_password="testpass123",
        saas_connectors=["linear"],
    )
    ontology = load_domain(config.domain)
    out = tmp_path / "import-bolt-project"
    renderer = ProjectRenderer(config, ontology)
    renderer.render(out)
    return out, config


@pytest.fixture
def generated_project_with_connectors_nams(tmp_path):
    """NAMS counterpart: same connector, NAMS backend. Both branches of
    ``import_data.py`` are rendered into the same file regardless of backend
    — the runtime ``settings.memory_backend`` selects which one runs — so
    these fixtures exercise the same template through different ProjectConfig
    paths to catch backend-specific Jinja2 issues."""
    config = ProjectConfig(
        project_name="Import Data Nams App",
        domain="healthcare",
        framework="strands",
        memory_backend="nams",
        memory_api_key="sk-test-nams",
        saas_connectors=["linear"],
    )
    ontology = load_domain(config.domain)
    out = tmp_path / "import-nams-project"
    renderer = ProjectRenderer(config, ontology)
    renderer.render(out)
    return out, config


class TestGeneratedImportDataAsyncShape:
    """Pins the bolt ingest path's async shape so the v0.12.0 sync/async
    mismatch (``def _ingest_via_bolt`` calling ``with driver.session()`` on
    an ``AsyncDriver``) cannot regress silently. v0.12.0 shipped this bug
    because the file was never syntax-checked AND no test exercised the
    bolt branch."""

    IMPORT_DATA_REL = "backend/scripts/import_data.py"

    def _parse(self, out):
        import ast
        path = out / self.IMPORT_DATA_REL
        assert path.exists(), f"{self.IMPORT_DATA_REL} missing — connector scaffold should emit it"
        source = path.read_text()
        # First: it must compile. v0.12.0 failed this when run, but the file
        # itself was syntactically valid — so we also AST-walk below.
        try:
            tree = ast.parse(source)
        except SyntaxError as e:
            pytest.fail(f"{self.IMPORT_DATA_REL} syntax error: {e}")
        return tree, source

    def test_import_data_py_compiles_bolt(self, generated_project_with_connectors):
        out, _ = generated_project_with_connectors
        path = out / self.IMPORT_DATA_REL
        compile(path.read_text(), str(path), "exec")

    def test_import_data_py_compiles_nams(self, generated_project_with_connectors_nams):
        out, _ = generated_project_with_connectors_nams
        path = out / self.IMPORT_DATA_REL
        compile(path.read_text(), str(path), "exec")

    def test_ingest_via_bolt_is_async(self, generated_project_with_connectors):
        """``_ingest_via_bolt`` must be ``async def`` because ``get_driver()``
        returns an ``AsyncDriver``. v0.12.0 had this as plain ``def``."""
        import ast
        tree, _ = self._parse(generated_project_with_connectors[0])
        fn = next(
            (n for n in ast.walk(tree)
             if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
             and n.name == "_ingest_via_bolt"),
            None,
        )
        assert fn is not None, "_ingest_via_bolt not found"
        assert isinstance(fn, ast.AsyncFunctionDef), (
            f"_ingest_via_bolt must be async def (got {type(fn).__name__}); "
            "AsyncDriver.session() requires async with + await session.run(...)."
        )

    def test_all_session_run_calls_are_awaited(self, generated_project_with_connectors):
        """Every ``session.run(...)`` inside ``_ingest_via_bolt`` must be
        awaited. A bare ``session.run(...)`` on an async session returns a
        coroutine that the rest of the function will try to iterate
        synchronously and crash on. AST-walk catches sneaky cases the
        ``async def`` check above would miss."""
        import ast
        tree, _ = self._parse(generated_project_with_connectors[0])
        fn = next(
            n for n in ast.walk(tree)
            if isinstance(n, ast.AsyncFunctionDef) and n.name == "_ingest_via_bolt"
        )
        offenders: list[int] = []
        for node in ast.walk(fn):
            if isinstance(node, ast.Call):
                # session.run(...)
                if (isinstance(node.func, ast.Attribute)
                        and node.func.attr == "run"
                        and isinstance(node.func.value, ast.Name)
                        and node.func.value.id == "session"):
                    parent_lines = [
                        a.lineno for a in ast.walk(fn)
                        if isinstance(a, ast.Await) and isinstance(a.value, ast.Call)
                        and a.value is node
                    ]
                    if not parent_lines:
                        offenders.append(node.lineno)
        assert not offenders, (
            f"Un-awaited session.run(...) calls inside _ingest_via_bolt at "
            f"lines {offenders}. AsyncDriver requires every session.run to be awaited."
        )

    def test_both_call_sites_use_asyncio_run(self, generated_project_with_connectors):
        """``main()`` and ``_retry_deadletter()`` both invoke ``_ingest_via_bolt``;
        both must wrap with ``asyncio.run(...)``. v0.12.0 had ``main()`` call
        the function directly, which would have raised ``TypeError: object
        coroutine can't be used in 'await' expression`` after the async fix
        if the call site wasn't also updated."""
        _, source = self._parse(generated_project_with_connectors[0])
        # Two call sites; both must be wrapped.
        count = source.count("asyncio.run(_ingest_via_bolt(")
        assert count == 2, (
            f"Expected 2 ``asyncio.run(_ingest_via_bolt(...))`` call sites "
            f"(main + _retry_deadletter), got {count}."
        )


class TestGeneratedFrontendFiles:
    """Frontend files must exist and be valid."""

    def test_package_json_valid(self, generated_project):
        out, _ = generated_project
        pkg = json.loads((out / "frontend" / "package.json").read_text())
        assert "dependencies" in pkg
        assert "@chakra-ui/react" in pkg["dependencies"]
        assert "next" in pkg["dependencies"]
        assert "react" in pkg["dependencies"]
        assert "@neo4j-nvl/react" in pkg["dependencies"]
        # Both React type packages must be present — React 19's @types/react
        # used to bundle DOM types, but we declare both explicitly so the
        # type graph stays stable across future minor releases.
        assert "@types/react" in pkg["devDependencies"]
        assert "@types/react-dom" in pkg["devDependencies"]

    def test_tsconfig_valid(self, generated_project):
        out, _ = generated_project
        tsconfig = json.loads((out / "frontend" / "tsconfig.json").read_text())
        assert "compilerOptions" in tsconfig

    def test_config_ts_has_domain_data(self, generated_project):
        out, _ = generated_project
        config_ts = (out / "frontend" / "lib" / "config.ts").read_text()
        assert "DOMAIN" in config_ts
        assert "NODE_COLORS" in config_ts
        assert "NODE_SIZES" in config_ts
        assert "DEMO_SCENARIOS" in config_ts
        assert "API_BASE" in config_ts

    def test_all_components_exist(self, generated_project):
        out, _ = generated_project
        components = [
            "ChatInterface.tsx",
            "ContextGraphView.tsx",
            "DecisionTracePanel.tsx",
            "Provider.tsx",
        ]
        for comp in components:
            assert (out / "frontend" / "components" / comp).exists(), f"Missing: {comp}"

    def test_package_json_pins_safe_lodash_and_postcss(self, generated_project):
        """npm audit must come back clean on a fresh scaffold.

        @neo4j-nvl pulls in lodash@4.17.23 (vulnerable to CVE GHSA-r5fr-rjxr-66jc)
        and next@15.5.x bundles postcss@8.4.31 (vulnerable to GHSA-qx2v-qp2m-jg93).
        We force-upgrade both via the npm `overrides` field. Until upstream ships
        fixes, removing the overrides re-introduces the vulnerabilities.
        """
        out, _ = generated_project
        pkg = json.loads((out / "frontend" / "package.json").read_text())
        assert "overrides" in pkg, "Frontend package.json must declare overrides"
        ov = pkg["overrides"]
        # ^4.17.24 is unsatisfiable in the 4.17.x line (no 4.17.24 exists);
        # the rule's job is to push transitive resolutions to 4.18.x, which is
        # the next safe major. If you change this pin, re-run `npm audit`.
        assert ov.get("lodash") == "^4.17.24"
        assert ov.get("postcss") == "^8.5.10"

    def test_layout_and_page_exist(self, generated_project):
        out, _ = generated_project
        assert (out / "frontend" / "app" / "layout.tsx").exists()
        assert (out / "frontend" / "app" / "page.tsx").exists()
        assert (out / "frontend" / "app" / "globals.css").exists()

    def test_theme_exists(self, generated_project):
        out, _ = generated_project
        assert (out / "frontend" / "theme" / "index.ts").exists()

    def test_context_graph_view_ask_about_guard_is_string_typed(self, generated_project):
        """Regression for TS2322: `unknown` is not assignable to `ReactNode`.

        The "Ask about X" button guard at the bottom of the selected-node panel
        must narrow `properties.name` to a string before using it in JSX,
        otherwise `tsc` rejects the whole frontend build (carried from v0.9.0).
        """
        out, _ = generated_project
        src = (out / "frontend" / "components" / "ContextGraphView.tsx").read_text()
        assert (
            'typeof (selectedElement.data as GraphNode).properties.name === "string"'
            in src
        ), "Ask-about guard must type-narrow properties.name to avoid TS2322"


class TestGeneratedEnvExample:
    """The .env.example file must exist with placeholder values."""

    def test_env_example_exists(self, generated_project):
        out, _ = generated_project
        assert (out / ".env.example").exists()

    def test_env_example_has_placeholders(self, generated_project):
        out, _ = generated_project
        content = (out / ".env.example").read_text()
        assert "your-password-here" in content
        assert "your-anthropic-key-here" in content
        assert "NEO4J_URI=" in content

    def test_env_example_no_real_credentials(self, generated_project):
        out, config = generated_project
        content = (out / ".env.example").read_text()
        assert config.neo4j_password not in content
        assert "sk-ant-test-key" not in content

    def test_config_py_does_not_bake_credentials(self, generated_project):
        """The generated config.py must not embed real Neo4j credentials.

        Defaults live in .env; config.py uses empty-string defaults so that
        secrets never end up in committed source. The .env file holds the
        user-provided values, loaded via pydantic-settings.
        """
        out, config = generated_project
        cfg_py = (out / "backend" / "app" / "config.py").read_text()
        # The user's actual password should not appear in source.
        assert config.neo4j_password not in cfg_py, (
            "config.py is leaking the Neo4j password into committed source. "
            "Defaults must be empty strings — real values belong in .env."
        )
        # Sanity-check the fields are present but empty.
        assert 'neo4j_uri: str = ""' in cfg_py
        assert 'neo4j_username: str = ""' in cfg_py
        assert 'neo4j_password: str = ""' in cfg_py
        # And .env still carries the real values for pydantic-settings to load.
        env = (out / ".env").read_text()
        assert config.neo4j_password in env


class TestGeneratedEnvFile:
    """The .env file must contain all expected keys."""

    def test_env_has_neo4j_config(self, generated_project):
        out, config = generated_project
        env = (out / ".env").read_text()
        assert "NEO4J_URI=" in env
        assert config.neo4j_uri in env
        assert "NEO4J_USERNAME=" in env
        assert "NEO4J_PASSWORD=" in env

    def test_env_has_api_keys(self, generated_project):
        out, _ = generated_project
        env = (out / ".env").read_text()
        assert "ANTHROPIC_API_KEY=" in env
        assert "OPENAI_API_KEY=" in env

    def test_env_has_ports(self, generated_project):
        out, _ = generated_project
        env = (out / ".env").read_text()
        assert "BACKEND_PORT=" in env
        assert "FRONTEND_PORT=" in env


class TestGeneratedMakefile:
    """Makefile must have all expected targets."""

    EXPECTED_TARGETS = ["start", "dev", "install", "seed", "reset", "clean", "test", "lint"]

    def test_makefile_has_targets(self, generated_project):
        out, _ = generated_project
        makefile = (out / "Makefile").read_text()
        for target in self.EXPECTED_TARGETS:
            assert f"{target}:" in makefile or f"{target} " in makefile, (
                f"Makefile missing target: {target}"
            )

    def test_makefile_has_phony(self, generated_project):
        out, _ = generated_project
        makefile = (out / "Makefile").read_text()
        assert ".PHONY" in makefile


class TestGeneratedDockerCompose:
    """docker-compose.yml must be valid YAML when neo4j_type=docker."""

    def test_docker_compose_valid_yaml(self, generated_project):
        out, _ = generated_project
        dc_path = out / "docker-compose.yml"
        assert dc_path.exists()
        data = yaml.safe_load(dc_path.read_text())
        assert "services" in data
        assert "neo4j" in data["services"]

    def test_docker_compose_pinned_version(self, generated_project):
        out, _ = generated_project
        dc = (out / "docker-compose.yml").read_text()
        # Should be pinned to specific patch version, not just major
        assert "neo4j:5." in dc
        # Must NOT be just "neo4j:5" without a patch version
        assert "image: neo4j:5\n" not in dc

    def test_no_docker_compose_for_existing(self, tmp_path):
        config = ProjectConfig(
            project_name="Existing Neo4j Test",
            domain="healthcare",
            framework="pydanticai",
            neo4j_type="existing",
        )
        ontology = load_domain(config.domain)
        out = tmp_path / "existing-project"
        renderer = ProjectRenderer(config, ontology)
        renderer.render(out)
        assert not (out / "docker-compose.yml").exists()

    def test_no_docker_compose_for_aura(self, tmp_path):
        config = ProjectConfig(
            project_name="Aura Test",
            domain="healthcare",
            framework="pydanticai",
            neo4j_type="aura",
            neo4j_uri="neo4j+s://abc.databases.neo4j.io",
        )
        ontology = load_domain(config.domain)
        out = tmp_path / "aura-project"
        renderer = ProjectRenderer(config, ontology)
        renderer.render(out)
        assert not (out / "docker-compose.yml").exists()

    def test_no_docker_compose_for_local(self, tmp_path):
        config = ProjectConfig(
            project_name="Local Test",
            domain="healthcare",
            framework="pydanticai",
            neo4j_type="local",
        )
        ontology = load_domain(config.domain)
        out = tmp_path / "local-project"
        renderer = ProjectRenderer(config, ontology)
        renderer.render(out)
        assert not (out / "docker-compose.yml").exists()


class TestGeneratedNeo4jLocalProject:
    """Projects with neo4j_type=local must have neo4j-local Makefile targets."""

    @pytest.fixture
    def local_project(self, tmp_path):
        config = ProjectConfig(
            project_name="Local Neo4j App",
            domain="financial-services",
            framework="pydanticai",
            neo4j_type="local",
        )
        ontology = load_domain(config.domain)
        out = tmp_path / "local-project"
        renderer = ProjectRenderer(config, ontology)
        renderer.render(out)
        return out, config

    def test_makefile_has_neo4j_start(self, local_project):
        out, _ = local_project
        makefile = (out / "Makefile").read_text()
        assert "neo4j-start:" in makefile

    def test_makefile_has_neo4j_stop(self, local_project):
        out, _ = local_project
        makefile = (out / "Makefile").read_text()
        assert "neo4j-stop:" in makefile

    def test_makefile_uses_neo4j_local_package(self, local_project):
        out, _ = local_project
        makefile = (out / "Makefile").read_text()
        assert "@johnymontana/neo4j-local" in makefile

    def test_readme_mentions_neo4j_start(self, local_project):
        out, _ = local_project
        readme = (out / "README.md").read_text()
        assert "neo4j-start" in readme


class TestGeneratedCypher:
    """Cypher files must have expected content."""

    def test_schema_has_constraints_and_indexes(self, generated_project):
        out, _ = generated_project
        schema = (out / "cypher" / "schema.cypher").read_text()
        assert "CREATE CONSTRAINT" in schema
        assert "CREATE INDEX" in schema
        assert "IF NOT EXISTS" in schema

    def test_schema_statements_valid(self, generated_project):
        """Each non-comment, non-empty line should be a valid Cypher statement."""
        out, _ = generated_project
        schema = (out / "cypher" / "schema.cypher").read_text()
        valid_keywords = {"CREATE", "DROP", "MATCH", "CALL", "RETURN", "WITH"}
        for line in schema.strip().split("\n"):
            line = line.strip()
            if not line or line.startswith("//"):
                continue
            first_word = line.split()[0].upper()
            assert first_word in valid_keywords, (
                f"Unexpected Cypher statement start: '{first_word}' in: {line[:80]}"
            )
            assert line.endswith(";"), f"Cypher statement missing semicolon: {line[:80]}"

    def test_gds_projections_exist(self, generated_project):
        out, _ = generated_project
        gds = (out / "cypher" / "gds_projections.cypher").read_text()
        assert "gds.graph.project" in gds


class TestGeneratedChatInterface:
    """ChatInterface must have session management and markdown rendering."""

    def test_chat_sends_session_id(self, generated_project):
        out, _ = generated_project
        chat = (out / "frontend" / "components" / "ChatInterface.tsx").read_text()
        assert "session_id: sessionId" in chat or "session_id:" in chat

    def test_chat_captures_session_id(self, generated_project):
        out, _ = generated_project
        chat = (out / "frontend" / "components" / "ChatInterface.tsx").read_text()
        assert "setSessionId" in chat

    def test_chat_has_new_conversation_button(self, generated_project):
        out, _ = generated_project
        chat = (out / "frontend" / "components" / "ChatInterface.tsx").read_text()
        assert "startNewConversation" in chat or "New" in chat

    def test_chat_uses_react_markdown(self, generated_project):
        out, _ = generated_project
        chat = (out / "frontend" / "components" / "ChatInterface.tsx").read_text()
        assert "ReactMarkdown" in chat

    def test_chat_shows_tool_calls(self, generated_project):
        out, _ = generated_project
        chat = (out / "frontend" / "components" / "ChatInterface.tsx").read_text()
        assert "toolCalls" in chat or "tool_calls" in chat

    def test_package_json_has_markdown_deps(self, generated_project):
        out, _ = generated_project
        pkg = json.loads((out / "frontend" / "package.json").read_text())
        assert "react-markdown" in pkg["dependencies"]
        assert "remark-gfm" in pkg["dependencies"]


class TestGeneratedMemoryIntegration:
    """Backend must integrate neo4j-agent-memory for conversation persistence."""

    def test_context_graph_client_delegates_to_memory(self, generated_project):
        out, _ = generated_project
        client = (out / "backend" / "app" / "context_graph_client.py").read_text()
        assert "from app.memory import connect_memory" in client
        assert "MemoryClient" not in client
        assert "emit_entities_extracted" in client

    def test_memory_module_exists(self, generated_project):
        out, _ = generated_project
        memory = (out / "backend" / "app" / "memory.py").read_text()
        assert "MemoryIntegration" in memory
        assert "store_message" in memory
        assert "get_context" in memory

    def test_agent_uses_memory_module(self, generated_project):
        out, _ = generated_project
        agent = (out / "backend" / "app" / "agent.py").read_text()
        assert "from app.memory import" in agent
        assert "store_message" in agent
        assert "get_context" in agent
        assert "resolve_session_id" in agent

    def test_routes_returns_tool_calls(self, generated_project):
        out, _ = generated_project
        routes = (out / "backend" / "app" / "routes.py").read_text()
        assert "tool_calls" in routes
        assert "drain_tool_calls" in routes


class TestGeneratedFrontendSyntax:
    """Frontend files must have valid structure."""

    TSX_FILES = [
        "frontend/components/ChatInterface.tsx",
        "frontend/components/ContextGraphView.tsx",
        "frontend/components/DecisionTracePanel.tsx",
        "frontend/components/Provider.tsx",
        "frontend/app/layout.tsx",
        "frontend/app/page.tsx",
    ]

    @pytest.mark.parametrize("tsx_file", TSX_FILES)
    def test_tsx_has_valid_imports(self, generated_project, tsx_file):
        """TSX files must have import statements."""
        out, _ = generated_project
        path = out / tsx_file
        assert path.exists(), f"Missing: {tsx_file}"
        content = path.read_text()
        assert "import" in content, f"{tsx_file} missing imports"

    @pytest.mark.parametrize("tsx_file", TSX_FILES)
    def test_tsx_has_export(self, generated_project, tsx_file):
        """TSX files must export a component or function."""
        out, _ = generated_project
        path = out / tsx_file
        content = path.read_text()
        assert "export" in content, f"{tsx_file} missing export"

    def test_config_ts_has_required_exports(self, generated_project):
        out, _ = generated_project
        config = (out / "frontend" / "lib" / "config.ts").read_text()
        for name in ["DOMAIN", "NODE_COLORS", "NODE_SIZES", "DEMO_SCENARIOS", "API_BASE"]:
            assert name in config, f"config.ts missing {name}"


class TestGeneratedTestScaffold:
    """Backend must include a test scaffold."""

    def test_test_file_exists(self, generated_project):
        out, _ = generated_project
        assert (out / "backend" / "tests" / "test_routes.py").exists()
        assert (out / "backend" / "tests" / "__init__.py").exists()

    def test_test_file_compiles(self, generated_project):
        out, _ = generated_project
        source = (out / "backend" / "tests" / "test_routes.py").read_text()
        try:
            compile(source, "test_routes.py", "exec")
        except SyntaxError as e:
            pytest.fail(f"test_routes.py syntax error: {e}")

    def test_test_file_has_health_test(self, generated_project):
        out, _ = generated_project
        content = (out / "backend" / "tests" / "test_routes.py").read_text()
        assert "def test_health" in content

    def test_test_file_has_scenarios_test(self, generated_project):
        out, _ = generated_project
        content = (out / "backend" / "tests" / "test_routes.py").read_text()
        assert "def test_scenarios" in content

    def test_test_file_has_domain_assertion(self, generated_project):
        out, _ = generated_project
        content = (out / "backend" / "tests" / "test_routes.py").read_text()
        assert "financial-services" in content

    def test_test_file_mocks_is_connected(self, generated_project):
        out, _ = generated_project
        content = (out / "backend" / "tests" / "test_routes.py").read_text()
        assert "app.main.is_connected" in content, (
            "mock_neo4j must patch app.main.is_connected (not context_graph_client) "
            "so test_health sees 'ok' — patch where the name is used, not where it's defined"
        )


class TestGeneratedBackendPyproject:
    """Backend pyproject.toml must have correct structure."""

    def test_has_project_section(self, generated_project):
        out, _ = generated_project
        content = (out / "backend" / "pyproject.toml").read_text()
        assert "[project]" in content
        assert "fastapi" in content
        assert "neo4j" in content

    def test_has_hatch_packages(self, generated_project):
        out, _ = generated_project
        content = (out / "backend" / "pyproject.toml").read_text()
        assert 'packages = ["app"]' in content

    def test_has_framework_dep(self, generated_project):
        out, _ = generated_project
        content = (out / "backend" / "pyproject.toml").read_text()
        assert "pydantic-ai" in content


class TestGeneratedReadme:
    """README must contain domain and framework info."""

    def test_readme_has_domain(self, generated_project):
        out, _ = generated_project
        readme = (out / "README.md").read_text()
        assert "Financial Services" in readme

    def test_readme_has_framework(self, generated_project):
        out, _ = generated_project
        readme = (out / "README.md").read_text()
        assert "PydanticAI" in readme

    def test_readme_has_quick_start(self, generated_project):
        out, _ = generated_project
        readme = (out / "README.md").read_text()
        assert "make install" in readme
        assert "make start" in readme


class TestGeneratedDataFiles:
    """Data directory must have ontology and fixtures."""

    def test_ontology_yaml_exists(self, generated_project):
        out, _ = generated_project
        assert (out / "data" / "ontology.yaml").exists()

    def test_base_yaml_exists(self, generated_project):
        out, _ = generated_project
        assert (out / "data" / "_base.yaml").exists()

    def test_fixtures_json_valid(self, generated_project):
        out, _ = generated_project
        fixture_path = out / "data" / "fixtures.json"
        assert fixture_path.exists()
        data = json.loads(fixture_path.read_text())
        assert "entities" in data
        assert "relationships" in data
        assert "documents" in data
        assert "traces" in data

    def test_documents_dir_exists(self, generated_project):
        out, _ = generated_project
        assert (out / "data" / "documents").is_dir()


class TestV040Features:
    """Tests for v0.4.0 improvements."""

    def test_constants_py_generated(self, generated_project):
        out, _ = generated_project
        constants = out / "backend" / "app" / "constants.py"
        assert constants.exists()
        content = constants.read_text()
        assert "DEFAULT_VECTOR_INDEX" in content
        assert "COMMUNITY_GRAPH" in content
        assert "PAGERANK_GRAPH" in content

    def test_health_endpoint_in_main(self, generated_project):
        out, _ = generated_project
        main = (out / "backend" / "app" / "main.py").read_text()
        assert "get_neo4j_status" in main or "_neo4j_available" in main
        assert "/health" in main
        assert "degraded" in main

    def test_graceful_neo4j_degradation(self, generated_project):
        out, _ = generated_project
        main = (out / "backend" / "app" / "main.py").read_text()
        assert "Neo4j unavailable" in main or "degraded mode" in main

    def test_is_connected_helper(self, generated_project):
        out, _ = generated_project
        client = (out / "backend" / "app" / "context_graph_client.py").read_text()
        assert "def is_connected()" in client

    def test_query_timeout(self, generated_project):
        out, _ = generated_project
        client = (out / "backend" / "app" / "context_graph_client.py").read_text()
        assert "timeout" in client

    def test_gds_label_validation(self, generated_project):
        out, _ = generated_project
        gds = (out / "backend" / "app" / "gds_client.py").read_text()
        assert "ENTITY_LABELS" in gds
        assert "Invalid label" in gds

    def test_routes_input_validation(self, generated_project):
        out, _ = generated_project
        routes = (out / "backend" / "app" / "routes.py").read_text()
        assert "max_length" in routes
        assert "Field(" in routes

    def test_routes_neo4j_check_on_chat(self, generated_project):
        out, _ = generated_project
        routes = (out / "backend" / "app" / "routes.py").read_text()
        assert "is_connected()" in routes
        assert "503" in routes

    def test_cors_configurable(self, generated_project):
        out, _ = generated_project
        main = (out / "backend" / "app" / "main.py").read_text()
        assert "CORS_ORIGINS" in main

    def test_env_example_has_warnings(self, generated_project):
        out, _ = generated_project
        env_example = (out / ".env.example").read_text()
        assert "WARNING" in env_example or "Change" in env_example

    def test_json_error_handling_in_agent(self, generated_project):
        out, _ = generated_project
        agent = (out / "backend" / "app" / "agent.py").read_text()
        assert "JSONDecodeError" in agent or "json.JSONDecodeError" in agent

    def test_vector_client_has_logging(self, generated_project):
        out, _ = generated_project
        vc = (out / "backend" / "app" / "vector_client.py").read_text()
        assert "logger" in vc

    def test_frontend_semantic_html(self, generated_project):
        """Frontend uses semantic HTML landmarks."""
        out, _ = generated_project
        page = (out / "frontend" / "app" / "page.tsx").read_text()
        assert 'as="main"' in page or 'as="section"' in page
        assert 'aria-label' in page

    def test_document_browser_has_pagination(self, generated_project):
        out, _ = generated_project
        doc_browser = (out / "frontend" / "components" / "DocumentBrowser.tsx").read_text()
        assert "PAGE_SIZE" in doc_browser
        assert "page" in doc_browser.lower()


class TestHealthcareEnumCompilation:
    """Verify healthcare models.py with blood type enums compiles."""

    def test_healthcare_models_compile(self, tmp_path):
        from create_context_graph.config import ProjectConfig

        config = ProjectConfig(
            project_name="Healthcare Test",
            domain="healthcare",
            framework="pydanticai",
        )
        ontology = load_domain("healthcare")
        out = tmp_path / "healthcare-test"
        renderer = ProjectRenderer(config, ontology)
        renderer.render(out)

        models_path = out / "backend" / "app" / "models.py"
        assert models_path.exists()
        source = models_path.read_text()
        compile(source, "models.py", "exec")
        assert "A_PLUS" in source
        assert "A_MINUS" in source


class TestV0131ModelsPolish:
    """v0.13.1 — generated Pydantic models use ``Field(...)`` for required
    fields (idiomatic Pydantic v2) instead of the bare ``...`` Ellipsis literal,
    and the ``/schema/models`` endpoint exposes their JSON Schemas to make the
    generated ``app.models`` module load-bearing rather than dead code."""

    def test_required_fields_use_field_factory(self, tmp_path):
        from create_context_graph.config import ProjectConfig

        config = ProjectConfig(
            project_name="Field Polish Test",
            domain="healthcare",
            framework="pydanticai",
        )
        ontology = load_domain("healthcare")
        out = tmp_path / "field-polish-test"
        renderer = ProjectRenderer(config, ontology)
        renderer.render(out)

        models_src = (out / "backend" / "app" / "models.py").read_text()
        # Idiomatic Pydantic v2: required fields use Field(...) so contributors
        # can extend with constraints (Field(..., min_length=1)) without churning
        # the whole declaration shape.
        assert "Field(...)" in models_src
        # The legacy bare ``= ...`` Ellipsis literal must be gone.
        for line in models_src.splitlines():
            stripped = line.strip()
            if stripped.startswith("#") or not stripped:
                continue
            # The only legitimate trailing ``= ...`` would be inside a Field()
            # call (e.g. ``Field(..., description="x")``), which we already
            # match above.  Match ``: <type> = ...`` field declarations.
            assert not re.search(r":\s*[A-Za-z_][A-Za-z0-9_\[\]\| ]*\s*=\s*\.\.\.\s*$", stripped), (
                f"Bare ``= ...`` field declaration found — should be ``= Field(...)``: {line!r}"
            )

    def test_schema_models_endpoint_present(self, tmp_path):
        from create_context_graph.config import ProjectConfig

        config = ProjectConfig(
            project_name="Schema Models Endpoint Test",
            domain="healthcare",
            framework="pydanticai",
        )
        ontology = load_domain("healthcare")
        out = tmp_path / "schema-models-test"
        renderer = ProjectRenderer(config, ontology)
        renderer.render(out)

        routes_src = (out / "backend" / "app" / "routes.py").read_text()
        assert '@router.get("/schema/models")' in routes_src, (
            "routes.py must expose /schema/models so the generated models.py is "
            "load-bearing"
        )
        assert "from app import models as entity_models" in routes_src
        assert "model_json_schema" in routes_src

    def test_schema_models_endpoint_compiles(self, tmp_path):
        """Compile-check the generated routes.py — catches Jinja2 escaping
        regressions in the new endpoint."""
        from create_context_graph.config import ProjectConfig

        config = ProjectConfig(
            project_name="Routes Compile Test",
            domain="healthcare",
            framework="pydanticai",
        )
        ontology = load_domain("healthcare")
        out = tmp_path / "routes-compile-test"
        renderer = ProjectRenderer(config, ontology)
        renderer.render(out)

        routes_path = out / "backend" / "app" / "routes.py"
        compile(routes_path.read_text(), "routes.py", "exec")


class TestV0131TemplateIdRemoval:
    """v0.13.1 — the dead ``template_id`` parameter on ``list_documents_nams``
    is removed. NAMS routes already raise 501 if template filtering is
    requested, so the parameter could never reach the function in a way
    that mattered."""

    def test_list_documents_nams_signature_has_no_template_id(self, tmp_path):
        from create_context_graph.config import ProjectConfig

        config = ProjectConfig(
            project_name="Template ID Removal Test",
            domain="healthcare",
            framework="pydanticai",
        )
        ontology = load_domain("healthcare")
        out = tmp_path / "template-id-removal-test"
        renderer = ProjectRenderer(config, ontology)
        renderer.render(out)

        adapter_src = (out / "backend" / "app" / "memory_adapter.py").read_text()
        # New signature.
        assert "async def list_documents_nams(\n    skip: int, limit: int" in adapter_src
        # Legacy signature must be gone.
        assert "list_documents_nams(\n    template_id" not in adapter_src

        routes_src = (out / "backend" / "app" / "routes.py").read_text()
        # Call site updated.
        assert "list_documents_nams(skip, limit)" in routes_src
        assert "list_documents_nams(template_id" not in routes_src


class TestGISCartographyEnumCompilation:
    """Verify gis-cartography models.py with 3d_model enum compiles."""

    def test_gis_models_compile(self, tmp_path):
        from create_context_graph.config import ProjectConfig

        config = ProjectConfig(
            project_name="GIS Test",
            domain="gis-cartography",
            framework="pydanticai",
        )
        ontology = load_domain("gis-cartography")
        out = tmp_path / "gis-test"
        renderer = ProjectRenderer(config, ontology)
        renderer.render(out)

        models_path = out / "backend" / "app" / "models.py"
        assert models_path.exists()
        source = models_path.read_text()
        compile(source, "models.py", "exec")
        assert "_3D_MODEL" in source


# ---------------------------------------------------------------------------
# Streaming SSE support tests
# ---------------------------------------------------------------------------

# All 8 frameworks now ship a streaming handler. Strands uses Agent.stream_async
# directly; CrewAI subscribes to LLMStreamChunkEvent on the global event bus
# with stream=True. (See agent.py.j2 in each framework's template.)
STREAMING_FRAMEWORKS = [
    "pydanticai",
    "anthropic-tools",
    "claude-agent-sdk",
    "openai-agents",
    "langgraph",
    "google-adk",
    "strands",
    "crewai",
]
NON_STREAMING_FRAMEWORKS: list[str] = []


class TestStreamingEndpoint:
    """Verify /chat/stream SSE endpoint is generated in routes.py."""

    def test_routes_has_stream_endpoint(self, generated_project):
        out, _ = generated_project
        routes = (out / "backend" / "app" / "routes.py").read_text()
        assert "/chat/stream" in routes
        assert "StreamingResponse" in routes
        assert "text/event-stream" in routes

    def test_routes_has_event_generator(self, generated_project):
        out, _ = generated_project
        routes = (out / "backend" / "app" / "routes.py").read_text()
        assert "event_generator" in routes
        assert "event_queue" in routes

    def test_routes_imports_streaming(self, generated_project):
        out, _ = generated_project
        routes = (out / "backend" / "app" / "routes.py").read_text()
        assert "from starlette.responses import StreamingResponse" in routes
        assert "import asyncio" in routes

    def test_original_chat_endpoint_preserved(self, generated_project):
        out, _ = generated_project
        routes = (out / "backend" / "app" / "routes.py").read_text()
        assert '@router.post("/chat", response_model=ChatResponse)' in routes


class TestCollectorEventQueue:
    """Verify CypherResultCollector has event queue support."""

    def test_collector_has_event_queue_methods(self, generated_project):
        out, _ = generated_project
        client = (out / "backend" / "app" / "context_graph_client.py").read_text()
        assert "set_event_queue" in client
        assert "clear_event_queue" in client
        assert "emit_tool_start" in client
        assert "emit_text_delta" in client
        assert "emit_done" in client
        assert "_push_event" in client

    def test_collector_imports_asyncio(self, generated_project):
        out, _ = generated_project
        client = (out / "backend" / "app" / "context_graph_client.py").read_text()
        assert "import asyncio" in client


class TestStreamingAgentTemplates:
    """Verify streaming handler is exported for Tier 1/2 frameworks."""

    @pytest.mark.parametrize("framework", STREAMING_FRAMEWORKS)
    def test_streaming_handler_exported(self, tmp_path, framework):
        config = ProjectConfig(
            project_name="Stream Test",
            domain="financial-services",
            framework=framework,
        )
        ontology = load_domain("financial-services")
        out = tmp_path / "stream-test"
        renderer = ProjectRenderer(config, ontology)
        renderer.render(out)

        agent_source = (out / "backend" / "app" / "agent.py").read_text()
        assert "handle_message_stream" in agent_source
        compile(agent_source, "agent.py", "exec")

    @pytest.mark.parametrize("framework", NON_STREAMING_FRAMEWORKS)
    def test_non_streaming_frameworks_no_stream_handler(self, tmp_path, framework):
        config = ProjectConfig(
            project_name="No Stream Test",
            domain="financial-services",
            framework=framework,
        )
        ontology = load_domain("financial-services")
        out = tmp_path / "no-stream-test"
        renderer = ProjectRenderer(config, ontology)
        renderer.render(out)

        agent_source = (out / "backend" / "app" / "agent.py").read_text()
        assert "handle_message_stream" not in agent_source

    @pytest.mark.parametrize("framework", STREAMING_FRAMEWORKS)
    def test_streaming_handler_uses_collector(self, tmp_path, framework):
        config = ProjectConfig(
            project_name="Collector Test",
            domain="financial-services",
            framework=framework,
        )
        ontology = load_domain("financial-services")
        out = tmp_path / "collector-test"
        renderer = ProjectRenderer(config, ontology)
        renderer.render(out)

        agent_source = (out / "backend" / "app" / "agent.py").read_text()
        assert "get_collector" in agent_source
        assert "emit_text_delta" in agent_source
        assert "emit_done" in agent_source

    def test_strands_streaming_uses_stream_async(self, tmp_path):
        """Strands streaming must use Agent.stream_async (token-level deltas)."""
        config = ProjectConfig(
            project_name="Strands Stream",
            domain="financial-services",
            framework="strands",
        )
        out = tmp_path / "strands-stream"
        ProjectRenderer(config, load_domain("financial-services")).render(out)
        src = (out / "backend" / "app" / "agent.py").read_text()
        assert "agent.stream_async" in src
        # `data` field is what Strands events expose for text deltas
        assert 'event.get("data")' in src
        # Loop must be captured before streaming so sync @tool fallbacks work
        assert "_capture_loop()" in src

    def test_crewai_streaming_uses_event_bus(self, tmp_path):
        """CrewAI streaming must subscribe to LLMStreamChunkEvent on the bus."""
        config = ProjectConfig(
            project_name="CrewAI Stream",
            domain="financial-services",
            framework="crewai",
        )
        out = tmp_path / "crewai-stream"
        ProjectRenderer(config, load_domain("financial-services")).render(out)
        src = (out / "backend" / "app" / "agent.py").read_text()
        # Stream chunks ride the global event bus, not a callback kwarg
        assert "crewai_event_bus" in src
        assert "LLMStreamChunkEvent" in src
        assert "register_handler" in src
        # Crew must be in stream mode for chunks to actually fire
        assert "stream=True" in src
        # And the handler must be detached after the kickoff so subsequent
        # requests don't double-emit (memory leak / mis-routed deltas).
        assert ".off(" in src


class TestStreamingFrontend:
    """Verify ChatInterface has streaming support."""

    def test_chat_interface_uses_streaming(self, generated_project):
        out, _ = generated_project
        chat = (out / "frontend" / "components" / "ChatInterface.tsx").read_text()
        assert "/chat/stream" in chat
        assert "ReadableStream" in chat or "getReader" in chat
        assert "text_delta" in chat
        assert "tool_start" in chat
        assert "tool_end" in chat

    def test_chat_interface_has_timeline(self, generated_project):
        out, _ = generated_project
        chat = (out / "frontend" / "components" / "ChatInterface.tsx").read_text()
        assert "Timeline" in chat

    def test_chat_interface_has_skeleton(self, generated_project):
        out, _ = generated_project
        chat = (out / "frontend" / "components" / "ChatInterface.tsx").read_text()
        assert "Skeleton" in chat

    def test_chat_interface_has_collapsible(self, generated_project):
        out, _ = generated_project
        chat = (out / "frontend" / "components" / "ChatInterface.tsx").read_text()
        assert "Collapsible" in chat


class TestQABugFixes:
    """Verify fixes for QA report bugs (v0.4.3)."""

    def test_config_extra_ignore(self, generated_project):
        """BUG-001: Settings model must accept extra env vars."""
        out, _ = generated_project
        config = (out / "backend" / "app" / "config.py").read_text()
        assert '"extra"' in config or "'extra'" in config
        assert "ignore" in config

    def test_neo4j_connected_flag(self, generated_project):
        """BUG-002: is_connected() must use tracked state, not sync verify."""
        out, _ = generated_project
        client = (out / "backend" / "app" / "context_graph_client.py").read_text()
        assert "_connected" in client
        assert "return _connected" in client

    def test_routes_all_endpoints_guarded(self, generated_project):
        """BUG-003: All Neo4j endpoints must have connectivity guards."""
        out, _ = generated_project
        routes = (out / "backend" / "app" / "routes.py").read_text()
        assert "_require_neo4j" in routes
        # Verify guard appears in key endpoints (not just /chat)
        assert routes.count("_require_neo4j()") >= 10

    def test_cypher_endpoint_503_before_400(self, generated_project):
        """BUG-004: /cypher must return 503 for connection errors, 400 for syntax."""
        out, _ = generated_project
        routes = (out / "backend" / "app" / "routes.py").read_text()
        # Find the cypher endpoint and verify guard comes before try/except
        cypher_idx = routes.index("def cypher(")
        guard_idx = routes.index("_require_neo4j()", cypher_idx)
        try_idx = routes.index("try:", cypher_idx)
        assert guard_idx < try_idx

    def test_message_unique_ids(self, generated_project):
        """BUG-008: Messages must use unique IDs, not array indices as keys."""
        out, _ = generated_project
        chat = (out / "frontend" / "components" / "ChatInterface.tsx").read_text()
        assert "crypto.randomUUID()" in chat
        assert "key={msg.id}" in chat

    def test_session_storage_warning(self, generated_project):
        """BUG-009: Storage failures must log a warning."""
        out, _ = generated_project
        chat = (out / "frontend" / "components" / "ChatInterface.tsx").read_text()
        assert "console.warn" in chat

    def test_dynamic_loading_fallback(self, generated_project):
        """BUG-014: Dynamic ContextGraphView import must have loading state."""
        out, _ = generated_project
        page = (out / "frontend" / "app" / "page.tsx").read_text()
        assert "loading:" in page

    def test_eslint_in_dependencies(self, generated_project):
        """BUG-017: ESLint must be in devDependencies."""
        out, _ = generated_project
        import json
        pkg = json.loads((out / "frontend" / "package.json").read_text())
        assert "eslint" in pkg.get("devDependencies", {})
        assert "eslint-config-next" in pkg.get("devDependencies", {})

    def test_dockerignore_generated(self, generated_project):
        """BUG-018: .dockerignore must be generated."""
        out, _ = generated_project
        dockerignore = out / ".dockerignore"
        assert dockerignore.exists()
        content = dockerignore.read_text()
        assert "node_modules" in content
        assert ".venv" in content


class TestDeferredBugFixes:
    """Verify fixes for deferred QA bugs (BUG-010, BUG-011, BUG-013, BUG-016)."""

    @pytest.mark.parametrize("framework", ["openai-agents", "strands", "crewai", "google-adk"])
    def test_structured_conversation_history(self, tmp_path, framework):
        """BUG-010: Affected frameworks must use structured history format."""
        config = ProjectConfig(
            project_name="History Test",
            domain="financial-services",
            framework=framework,
        )
        ontology = load_domain("financial-services")
        out = tmp_path / "history-test"
        renderer = ProjectRenderer(config, ontology)
        renderer.render(out)
        agent = (out / "backend" / "app" / "agent.py").read_text()
        assert "<conversation_history>" in agent
        assert "Previous conversation:" not in agent

    def test_google_adk_session_reuse(self, tmp_path):
        """BUG-010: Google ADK must skip history injection for existing sessions."""
        config = ProjectConfig(
            project_name="ADK Session Test",
            domain="financial-services",
            framework="google-adk",
        )
        ontology = load_domain("financial-services")
        out = tmp_path / "adk-test"
        renderer = ProjectRenderer(config, ontology)
        renderer.render(out)
        agent = (out / "backend" / "app" / "agent.py").read_text()
        # Verify conditional logic: existing sessions skip history
        assert "if session_id in _sessions:" in agent
        assert "ADK manages multi-turn internally" in agent

    def test_google_adk_has_streaming(self, tmp_path):
        """BUG-011: Google ADK must have handle_message_stream."""
        config = ProjectConfig(
            project_name="ADK Stream Test",
            domain="financial-services",
            framework="google-adk",
        )
        ontology = load_domain("financial-services")
        out = tmp_path / "adk-stream-test"
        renderer = ProjectRenderer(config, ontology)
        renderer.render(out)
        agent = (out / "backend" / "app" / "agent.py").read_text()
        assert "handle_message_stream" in agent
        assert "emit_text_delta" in agent
        assert "emit_done" in agent
        compile(agent, "agent.py", "exec")

    def test_crewai_requires_python_311(self, tmp_path):
        """BUG-016: CrewAI projects must require Python 3.11+."""
        config = ProjectConfig(
            project_name="CrewAI Version Test",
            domain="financial-services",
            framework="crewai",
        )
        ontology = load_domain("financial-services")
        out = tmp_path / "crewai-test"
        renderer = ProjectRenderer(config, ontology)
        renderer.render(out)
        pyproject = (out / "backend" / "pyproject.toml").read_text()
        assert '>=3.11, <3.14' in pyproject

    def test_non_crewai_requires_python_310(self, generated_project):
        """BUG-016: Non-CrewAI projects must require Python 3.10+."""
        out, _ = generated_project
        pyproject = (out / "backend" / "pyproject.toml").read_text()
        assert '>=3.10, <3.14' in pyproject

    def test_strands_no_nest_asyncio_dep(self, tmp_path):
        """Phase 0: Strands must not depend on nest-asyncio."""
        config = ProjectConfig(
            project_name="Strands Dep Test",
            domain="financial-services",
            framework="strands",
        )
        ontology = load_domain("financial-services")
        out = tmp_path / "strands-dep-test"
        renderer = ProjectRenderer(config, ontology)
        renderer.render(out)
        pyproject = (out / "backend" / "pyproject.toml").read_text()
        assert "nest-asyncio" not in pyproject


class TestAsyncBridgingFixes:
    """Verify sync frameworks use run_coroutine_threadsafe instead of asyncio.run()."""

    @pytest.mark.parametrize("framework", ["crewai", "strands"])
    def test_uses_run_coroutine_threadsafe(self, tmp_path, framework):
        config = ProjectConfig(
            project_name="Async Bridge Test",
            domain="financial-services",
            framework=framework,
        )
        ontology = load_domain("financial-services")
        out = tmp_path / f"async-bridge-{framework}"
        renderer = ProjectRenderer(config, ontology)
        renderer.render(out)
        agent_py = (out / "backend" / "app" / "agent.py").read_text()
        assert "run_coroutine_threadsafe" in agent_py
        assert "_capture_loop" in agent_py

    @pytest.mark.parametrize("framework", ["crewai", "strands"])
    def test_no_bare_asyncio_run(self, tmp_path, framework):
        """asyncio.run() should only appear in the fallback, not as primary."""
        config = ProjectConfig(
            project_name="No Bare Asyncio Test",
            domain="financial-services",
            framework=framework,
        )
        ontology = load_domain("financial-services")
        out = tmp_path / f"no-bare-asyncio-{framework}"
        renderer = ProjectRenderer(config, ontology)
        renderer.render(out)
        agent_py = (out / "backend" / "app" / "agent.py").read_text()
        # asyncio.run should only appear in the fallback branch of _run_sync
        lines_with_asyncio_run = [
            line.strip() for line in agent_py.splitlines()
            if "asyncio.run(" in line and not line.strip().startswith("#")
        ]
        assert len(lines_with_asyncio_run) <= 1, (
            f"Expected at most 1 asyncio.run() call (fallback), found {len(lines_with_asyncio_run)}"
        )


class TestMaxIterationGuards:
    """Verify agentic loop frameworks have bounded iterations."""

    @pytest.mark.parametrize("framework", ["anthropic-tools", "claude-agent-sdk"])
    def test_has_max_iterations(self, tmp_path, framework):
        config = ProjectConfig(
            project_name="Max Iter Test",
            domain="financial-services",
            framework=framework,
        )
        ontology = load_domain("financial-services")
        out = tmp_path / f"max-iter-{framework}"
        renderer = ProjectRenderer(config, ontology)
        renderer.render(out)
        agent_py = (out / "backend" / "app" / "agent.py").read_text()
        assert "max_iterations" in agent_py or "range(" in agent_py
        # Must not have unbounded while True loops for the agentic loop
        assert "while True:" not in agent_py, "Agentic loop should use bounded iteration"


class TestOpenAIStreamFiltering:
    """Verify OpenAI Agents filters tool argument deltas from text stream."""

    def test_filters_tool_deltas(self, tmp_path):
        config = ProjectConfig(
            project_name="OpenAI Filter Test",
            domain="financial-services",
            framework="openai-agents",
        )
        ontology = load_domain("financial-services")
        out = tmp_path / "openai-filter"
        renderer = ProjectRenderer(config, ontology)
        renderer.render(out)
        agent_py = (out / "backend" / "app" / "agent.py").read_text()
        # Should filter by event type, not just check for delta attribute
        assert "output_text.delta" in agent_py or "ResponseTextDeltaEvent" in agent_py


class TestCollectorThreadSafety:
    """Verify CypherResultCollector has thread-safe event pushing."""

    def test_collector_has_threadsafe_push(self, generated_project):
        out, _ = generated_project
        client_py = (out / "backend" / "app" / "context_graph_client.py").read_text()
        assert "call_soon_threadsafe" in client_py
        assert "threading" in client_py

    def test_collector_captures_loop(self, generated_project):
        out, _ = generated_project
        client_py = (out / "backend" / "app" / "context_graph_client.py").read_text()
        assert "_loop" in client_py


class TestResetDatabase:
    """Verify reset_database() handles connection lifecycle correctly (fix for #26)."""

    def test_reset_database_connects_when_not_connected(self, generated_project):
        """reset_database must open its own connection when _driver is None."""
        out, _ = generated_project
        client = (out / "backend" / "app" / "context_graph_client.py").read_text()
        assert "was_connected = _driver is not None" in client
        assert "await connect_neo4j()" in client

    def test_reset_database_closes_connection_it_opened(self, generated_project):
        """reset_database must close a connection it opened (try/finally pattern)."""
        out, _ = generated_project
        client = (out / "backend" / "app" / "context_graph_client.py").read_text()
        assert "try:" in client
        assert "finally:" in client
        assert "await close_neo4j()" in client

    def test_reset_database_preserves_existing_connection(self, generated_project):
        """reset_database must NOT close a pre-existing connection."""
        out, _ = generated_project
        client = (out / "backend" / "app" / "context_graph_client.py").read_text()
        # The guard ensures close_neo4j is only called when was_connected is False
        assert "if not was_connected:" in client

    def test_reset_database_uses_detach_delete(self, generated_project):
        """reset_database must use DETACH DELETE to clear all nodes and relationships."""
        out, _ = generated_project
        client = (out / "backend" / "app" / "context_graph_client.py").read_text()
        assert "MATCH (n) DETACH DELETE n" in client


class TestToolPromptSuffix:
    """Verify all agent frameworks include tool-use emphasis in system prompt."""

    @pytest.mark.parametrize("framework", [
        "pydanticai", "claude-agent-sdk", "openai-agents", "langgraph",
        "crewai", "strands", "google-adk", "anthropic-tools",
    ])
    def test_has_tool_use_emphasis(self, tmp_path, framework):
        config = ProjectConfig(
            project_name="Tool Prompt Test",
            domain="financial-services",
            framework=framework,
        )
        ontology = load_domain("financial-services")
        out = tmp_path / f"tool-prompt-{framework}"
        renderer = ProjectRenderer(config, ontology)
        renderer.render(out)
        agent_py = (out / "backend" / "app" / "agent.py").read_text()
        assert "MUST use the available tools" in agent_py


class TestChatHistoryScoping:
    """Verify chat history localStorage keys are scoped by domain."""

    def test_storage_key_includes_domain(self, generated_project):
        out, _ = generated_project
        chat_tsx = (out / "frontend" / "components" / "ChatInterface.tsx").read_text()
        assert "DOMAIN.id" in chat_tsx or "DOMAIN" in chat_tsx
        # Must not have hardcoded generic key
        assert '"ccg-chat-history"' not in chat_tsx

    def test_imports_domain_config(self, generated_project):
        out, _ = generated_project
        chat_tsx = (out / "frontend" / "components" / "ChatInterface.tsx").read_text()
        assert "DOMAIN" in chat_tsx


class TestHydrationFix:
    """Verify sessionStorage reads are deferred to useEffect."""

    def test_no_direct_sessionstorage_in_usestate(self, generated_project):
        out, _ = generated_project
        chat_tsx = (out / "frontend" / "components" / "ChatInterface.tsx").read_text()
        # Should not call loadStoredMessages in useState initializer
        assert "useState<Message[]>(loadStoredMessages)" not in chat_tsx
        assert "useState(loadStoredMessages)" not in chat_tsx

    def test_has_hydrated_state(self, generated_project):
        out, _ = generated_project
        chat_tsx = (out / "frontend" / "components" / "ChatInterface.tsx").read_text()
        assert "hydrated" in chat_tsx


class TestNeo4jAgentMemoryDeps:
    """Verify neo4j-agent-memory uses local embeddings by default."""

    def test_pyproject_has_sentence_transformers(self, generated_project):
        out, _ = generated_project
        pyproject = (out / "backend" / "pyproject.toml").read_text()
        assert "neo4j-agent-memory" in pyproject
        assert "sentence-transformers" in pyproject
        # Should NOT have openai extra — local embeddings by default
        assert "openai" not in pyproject.split("neo4j-agent-memory")[1].split('"')[0]

    def test_memory_module_has_integration(self, generated_project):
        out, _ = generated_project
        memory = (out / "backend" / "app" / "memory.py").read_text()
        assert "MemoryIntegration" in memory
        assert "SessionStrategy" in memory


class TestStreamingEndpointTimeout:
    """Verify SSE endpoint has overall timeout."""

    def test_routes_has_overall_timeout(self, generated_project):
        out, _ = generated_project
        routes_py = (out / "backend" / "app" / "routes.py").read_text()
        assert "overall_timeout" in routes_py


class TestDomainSpecificNamePools:
    """Verify static data uses domain-specific names."""

    def test_label_names_exist(self):
        from create_context_graph.name_pools import LABEL_NAMES
        assert "Diagnosis" in LABEL_NAMES
        assert "Account" in LABEL_NAMES
        assert "Repository" in LABEL_NAMES
        assert "Species" in LABEL_NAMES

    def test_get_names_for_label_uses_label_pool(self):
        from create_context_graph.name_pools import get_names_for_label
        names = get_names_for_label("Diagnosis", "OBJECT", 5)
        # Should be medical terms, not generic object names
        assert any("Diabetes" in n or "Hypertension" in n for n in names)

    def test_get_names_for_label_falls_back(self):
        from create_context_graph.name_pools import get_names_for_label
        names = get_names_for_label("UnknownLabel", "PERSON", 3)
        # Should fall back to PERSON_NAMES pool
        assert len(names) == 3


class TestV051Regressions:
    """Regression tests for v0.5.1 bug fixes."""

    def test_pydanticai_tools_return_json_string(self, tmp_path):
        """PydanticAI tools must return str (JSON-serialized), not list[dict]."""
        config = ProjectConfig(
            project_name="pydantic-fix",
            domain="healthcare",
            framework="pydanticai",
        )
        ontology = load_domain("healthcare")
        out = tmp_path / "pydantic-fix"
        renderer = ProjectRenderer(config, ontology)
        renderer.render(out)

        agent_source = (out / "backend" / "app" / "agent.py").read_text()
        # Tools should return str, not list[dict]
        assert "-> str:" in agent_source
        assert "-> list[dict]:" not in agent_source
        # Should use json.dumps for serialization
        assert "json.dumps" in agent_source
        compile(agent_source, "agent.py", "exec")

    def test_google_adk_agent_name_no_hyphens(self, tmp_path):
        """Google ADK agent name must not contain hyphens (invalid identifier)."""
        for domain_id in ["real-estate", "financial-services", "oil-gas"]:
            config = ProjectConfig(
                project_name=f"adk-{domain_id}",
                domain=domain_id,
                framework="google-adk",
            )
            ontology = load_domain(domain_id)
            out = tmp_path / f"adk-{domain_id}"
            renderer = ProjectRenderer(config, ontology)
            renderer.render(out)

            agent_source = (out / "backend" / "app" / "agent.py").read_text()
            # Extract the agent name= value
            import re
            match = re.search(r'name="(\w+)"', agent_source)
            assert match, f"Could not find agent name in {domain_id}"
            agent_name = match.group(1)
            assert "-" not in agent_name, (
                f"Agent name '{agent_name}' contains hyphens for domain {domain_id}"
            )
            assert agent_name.isidentifier(), (
                f"Agent name '{agent_name}' is not a valid Python identifier"
            )

    def test_strands_has_max_tokens(self, tmp_path):
        """Strands AnthropicModel must include max_tokens parameter."""
        config = ProjectConfig(
            project_name="strands-fix",
            domain="trip-planning",
            framework="strands",
        )
        ontology = load_domain("trip-planning")
        out = tmp_path / "strands-fix"
        renderer = ProjectRenderer(config, ontology)
        renderer.render(out)

        agent_source = (out / "backend" / "app" / "agent.py").read_text()
        assert "max_tokens" in agent_source
        compile(agent_source, "agent.py", "exec")

    def test_env_has_hf_telemetry_setting(self, tmp_path):
        """Generated .env should suppress HuggingFace warnings."""
        config = ProjectConfig(
            project_name="hf-fix",
            domain="healthcare",
            framework="pydanticai",
        )
        ontology = load_domain("healthcare")
        out = tmp_path / "hf-fix"
        renderer = ProjectRenderer(config, ontology)
        renderer.render(out)

        env_content = (out / ".env").read_text()
        assert "HF_HUB_DISABLE_TELEMETRY" in env_content

    def test_name_pools_confidence_clamped(self):
        """Confidence/score/rating float values should be clamped to 0-1 range."""
        from create_context_graph.name_pools import generate_property_value
        for _ in range(20):
            val = generate_property_value("confidence", "float", "Test", "Decision", 0)
            assert 0.0 <= val <= 1.0, f"confidence={val} out of range"
            val = generate_property_value("efficiency_rating", "float", "Line A", "ProductionLine", 0)
            assert 0.0 <= val <= 100.0, f"efficiency_rating={val} out of range"

    def test_name_pools_currency_realistic(self):
        """Currency property should return actual currency codes, not template strings."""
        from create_context_graph.name_pools import generate_property_value
        val = generate_property_value("currency", "string", "Wire Transfer", "Transaction", 0)
        assert val in ["USD", "EUR", "GBP", "JPY", "CAD", "AUD", "CHF", "CNY", "INR", "BRL"]

    def test_name_pools_ticker_realistic(self):
        """Ticker property should return actual ticker symbols."""
        from create_context_graph.name_pools import generate_property_value
        val = generate_property_value("ticker", "string", "Apple Inc", "Security", 0)
        assert len(val) <= 5 and val.isupper()

    def test_name_pools_description_no_workflow(self):
        """Description values should not contain 'management workflow' boilerplate."""
        from create_context_graph.name_pools import generate_property_value
        val = generate_property_value("description", "string", "Test Entity", "Patient", 0)
        assert "management workflow" not in val

    def test_chat_interface_has_thinking_filter(self, generated_project):
        """ChatInterface should have thinking text separation logic."""
        out, _ = generated_project
        chat = (out / "frontend" / "components" / "ChatInterface.tsx").read_text()
        assert "splitThinkingAndResponse" in chat
        assert "THINKING_PATTERNS" in chat
        assert "Show reasoning" in chat


class TestV052DomainFiltering:
    """Tests for v0.5.2 cross-domain isolation fixes."""

    def test_config_has_domain_id(self, generated_project):
        """Generated config.py should have domain_id setting."""
        out, _ = generated_project
        config_source = (out / "backend" / "app" / "config.py").read_text()
        assert "domain_id" in config_source
        assert "financial-services" in config_source

    def test_env_has_domain_id(self, generated_project):
        """Generated .env should have DOMAIN_ID."""
        out, _ = generated_project
        env_content = (out / ".env").read_text()
        assert "DOMAIN_ID=" in env_content

    def test_routes_filter_documents_by_domain(self, generated_project):
        """Document queries in routes.py should filter by domain."""
        out, _ = generated_project
        routes_source = (out / "backend" / "app" / "routes.py").read_text()
        assert "d.domain" in routes_source, "Documents query should filter by domain"
        assert "t.domain" in routes_source, "Traces query should filter by domain"

    def test_routes_filter_entities_by_domain(self, generated_project):
        """Entity detail queries should filter by domain."""
        out, _ = generated_project
        routes_source = (out / "backend" / "app" / "routes.py").read_text()
        assert "n.domain IS NULL OR n.domain = $domain" in routes_source

    def test_context_graph_client_domain_filtering(self, generated_project):
        """context_graph_client functions should filter by domain."""
        out, _ = generated_project
        client_source = (out / "backend" / "app" / "context_graph_client.py").read_text()
        assert "n.domain IS NULL OR n.domain = $domain" in client_source
        assert "settings.domain_id" in client_source

    def test_generate_data_tags_domain(self, generated_project):
        """generate_data.py should tag entities with domain property."""
        out, _ = generated_project
        gen_data = (out / "backend" / "scripts" / "generate_data.py").read_text()
        assert '"domain": settings.domain_id' in gen_data
        assert "d.domain = $domain" in gen_data
        assert "t.domain = $domain" in gen_data


class TestV052FrameworkFixes:
    """Tests for v0.5.2 agent framework bug fixes."""

    def test_google_adk_part_constructor(self, tmp_path):
        """Google ADK should use Part(text=...) not Part.from_text(...)."""
        config = ProjectConfig(
            project_name="adk-fix",
            domain="healthcare",
            framework="google-adk",
        )
        ontology = load_domain("healthcare")
        out = tmp_path / "adk-fix"
        renderer = ProjectRenderer(config, ontology)
        renderer.render(out)

        agent_source = (out / "backend" / "app" / "agent.py").read_text()
        assert "Part(text=" in agent_source
        assert "Part.from_text(" not in agent_source

    def test_strands_has_timeout(self, tmp_path):
        """Strands agent should have asyncio.wait_for timeout."""
        config = ProjectConfig(
            project_name="strands-timeout",
            domain="healthcare",
            framework="strands",
        )
        ontology = load_domain("healthcare")
        out = tmp_path / "strands-timeout"
        renderer = ProjectRenderer(config, ontology)
        renderer.render(out)

        agent_source = (out / "backend" / "app" / "agent.py").read_text()
        assert "asyncio.wait_for" in agent_source
        assert "timeout=" in agent_source
        assert "TimeoutError" in agent_source

    def test_crewai_has_timeout(self, tmp_path):
        """CrewAI agent should have asyncio.wait_for timeout."""
        config = ProjectConfig(
            project_name="crewai-timeout",
            domain="healthcare",
            framework="crewai",
        )
        ontology = load_domain("healthcare")
        out = tmp_path / "crewai-timeout"
        renderer = ProjectRenderer(config, ontology)
        renderer.render(out)

        agent_source = (out / "backend" / "app" / "agent.py").read_text()
        assert "asyncio.wait_for" in agent_source
        assert "timeout=" in agent_source
        assert "TimeoutError" in agent_source

    def test_anthropic_tools_streaming_error_handling(self, tmp_path):
        """Anthropic tools streaming should have try/except around the loop."""
        config = ProjectConfig(
            project_name="anthropic-fix",
            domain="healthcare",
            framework="anthropic-tools",
        )
        ontology = load_domain("healthcare")
        out = tmp_path / "anthropic-fix"
        renderer = ProjectRenderer(config, ontology)
        renderer.render(out)

        agent_source = (out / "backend" / "app" / "agent.py").read_text()
        assert "Streaming error" in agent_source
        assert "Tool error" in agent_source or "tool_err" in agent_source

    def test_run_cypher_catches_exceptions(self, tmp_path):
        """All frameworks' run_cypher should catch execute_cypher exceptions."""
        for fw in ["pydanticai", "langgraph", "openai-agents", "crewai", "strands", "google-adk", "anthropic-tools"]:
            config = ProjectConfig(
                project_name=f"cypher-fix-{fw}",
                domain="healthcare",
                framework=fw,
            )
            ontology = load_domain("healthcare")
            out = tmp_path / f"cypher-fix-{fw}"
            renderer = ProjectRenderer(config, ontology)
            renderer.render(out)

            agent_source = (out / "backend" / "app" / "agent.py").read_text()
            assert "Cypher query failed" in agent_source, f"{fw} run_cypher should catch Cypher exceptions"

    def test_agent_tools_inject_domain(self, tmp_path):
        """Agent tools should inject domain parameter for run_cypher."""
        for fw in ["pydanticai", "langgraph", "openai-agents", "crewai", "strands", "google-adk", "anthropic-tools"]:
            config = ProjectConfig(
                project_name=f"domain-{fw}",
                domain="healthcare",
                framework=fw,
            )
            ontology = load_domain("healthcare")
            out = tmp_path / f"domain-{fw}"
            renderer = ProjectRenderer(config, ontology)
            renderer.render(out)

            agent_source = (out / "backend" / "app" / "agent.py").read_text()
            assert "domain" in agent_source, f"{fw} should reference domain"
            assert "settings.domain_id" in agent_source, f"{fw} run_cypher should inject domain"


class TestV052FrontendFixes:
    """Tests for v0.5.2 frontend improvements."""

    def test_activity_based_timeout(self, generated_project):
        """ChatInterface should use activity-based timeout reset."""
        out, _ = generated_project
        chat = (out / "frontend" / "components" / "ChatInterface.tsx").read_text()
        assert "resetTimeout" in chat, "Should have activity-based timeout reset"
        assert "120000" in chat, "Should use 120s timeout"

    def test_thinking_filter_handles_empty_response(self, generated_project):
        """splitThinkingAndResponse should return full text when response is empty."""
        out, _ = generated_project
        chat = (out / "frontend" / "components" / "ChatInterface.tsx").read_text()
        assert "!response && thinking" in chat, "Should handle empty response case"

    def test_thinking_filter_preserves_errors(self, generated_project):
        """splitThinkingAndResponse should not classify error text as thinking."""
        out, _ = generated_project
        chat = (out / "frontend" / "components" / "ChatInterface.tsx").read_text()
        assert "error" in chat.lower()
        # Check for the error detection logic
        assert "\\berror\\b" in chat or "error" in chat


class TestV060GoogleApiKey:
    """Tests for v0.6.0 Google API key support."""

    def test_env_has_google_api_key(self, tmp_path):
        """Generated .env should include GOOGLE_API_KEY."""
        config = ProjectConfig(
            project_name="adk-test",
            domain="healthcare",
            framework="google-adk",
            google_api_key="test-google-key",
        )
        ontology = load_domain("healthcare")
        out = tmp_path / "adk-test"
        renderer = ProjectRenderer(config, ontology)
        renderer.render(out)
        env_content = (out / ".env").read_text()
        assert "GOOGLE_API_KEY=test-google-key" in env_content

    def test_env_example_has_google_api_key(self, tmp_path):
        """Generated .env.example should document GOOGLE_API_KEY."""
        config = ProjectConfig(
            project_name="adk-example",
            domain="healthcare",
            framework="google-adk",
        )
        ontology = load_domain("healthcare")
        out = tmp_path / "adk-example"
        renderer = ProjectRenderer(config, ontology)
        renderer.render(out)
        env_example = (out / ".env.example").read_text()
        assert "GOOGLE_API_KEY" in env_example


class TestV060CrewAIFix:
    """Tests for v0.6.0 CrewAI explicit LLM config."""

    def test_crewai_has_explicit_llm(self, tmp_path):
        """CrewAI agent should configure LLM explicitly."""
        config = ProjectConfig(
            project_name="crewai-llm",
            domain="healthcare",
            framework="crewai",
        )
        ontology = load_domain("healthcare")
        out = tmp_path / "crewai-llm"
        renderer = ProjectRenderer(config, ontology)
        renderer.render(out)
        agent_source = (out / "backend" / "app" / "agent.py").read_text()
        assert "llm=" in agent_source, "CrewAI should configure LLM explicitly"
        assert "anthropic/" in agent_source, "CrewAI should use Anthropic provider"

    def test_crewai_has_logging(self, tmp_path):
        """CrewAI agent should have logging."""
        config = ProjectConfig(
            project_name="crewai-log",
            domain="healthcare",
            framework="crewai",
        )
        ontology = load_domain("healthcare")
        out = tmp_path / "crewai-log"
        renderer = ProjectRenderer(config, ontology)
        renderer.render(out)
        agent_source = (out / "backend" / "app" / "agent.py").read_text()
        assert "logger" in agent_source, "CrewAI should use logging"


class TestV060StrandsFix:
    """Tests for v0.6.0 Strands result extraction fix."""

    def test_strands_has_extract_text(self, tmp_path):
        """Strands agent should have robust text extraction."""
        config = ProjectConfig(
            project_name="strands-extract",
            domain="healthcare",
            framework="strands",
        )
        ontology = load_domain("healthcare")
        out = tmp_path / "strands-extract"
        renderer = ProjectRenderer(config, ontology)
        renderer.render(out)
        agent_source = (out / "backend" / "app" / "agent.py").read_text()
        assert "_extract_text" in agent_source, "Strands should have _extract_text helper"
        assert "hasattr" in agent_source, "Should check for various result attributes"


class TestV060DomainAwareNamePools:
    """Tests for v0.6.0 domain-aware base entity pools."""

    def test_healthcare_person_names_are_medical(self):
        from create_context_graph.name_pools import get_names_for_pole_type
        names = get_names_for_pole_type("PERSON", 5, domain_id="healthcare")
        # Healthcare person names should include "Dr." or "Nurse" prefixes
        assert any("Dr." in n or "Nurse" in n or "Pharmacist" in n for n in names)

    def test_generic_person_names_without_domain(self):
        from create_context_graph.name_pools import get_names_for_pole_type
        names = get_names_for_pole_type("PERSON", 5)
        # Without domain, should use generic names
        assert not any("Dr." in n for n in names)

    def test_contraindications_not_templated(self):
        from create_context_graph.name_pools import generate_property_value
        val = generate_property_value("contraindications", "string", "Metformin", "Medication", 0)
        assert " - " not in val, "Contraindications should not use template pattern"

    def test_dosage_form_realistic(self):
        from create_context_graph.name_pools import generate_property_value
        val = generate_property_value("dosage_form", "string", "Metformin", "Medication", 0)
        assert val in ["Tablet", "Capsule", "Injectable", "Oral Solution", "Topical Cream",
                        "Inhaler", "Transdermal Patch", "Suppository", "Sublingual Tablet",
                        "Extended-Release Tablet", "Chewable Tablet", "Nasal Spray"]

    def test_allergies_realistic(self):
        from create_context_graph.name_pools import generate_property_value
        val = generate_property_value("allergies", "string", "Patient A", "Patient", 0)
        assert " - " not in val, "Allergies should not use template pattern"

    def test_sector_realistic(self):
        from create_context_graph.name_pools import generate_property_value
        val = generate_property_value("sector", "string", "Apple Inc", "Security", 0)
        assert val in ["Technology", "Healthcare", "Financial Services", "Energy",
                        "Consumer Discretionary", "Industrials", "Real Estate",
                        "Utilities", "Materials", "Communications", "Consumer Staples"]

    def test_domain_aware_roles(self):
        from create_context_graph.name_pools import generate_property_value
        val = generate_property_value("role", "string", "Sarah", "Person", 0, domain_id="healthcare")
        healthcare_roles = ["Attending Physician", "Charge Nurse", "Resident", "Pharmacist",
                           "Lab Technician", "Radiologist", "Physical Therapist", "Surgeon"]
        assert val in healthcare_roles

    def test_population_trend_realistic(self):
        from create_context_graph.name_pools import generate_property_value
        val = generate_property_value("population_trend", "string", "Tiger", "Species", 0)
        assert val in ["increasing", "stable", "decreasing", "unknown"]

    def test_domain_organization_names(self):
        from create_context_graph.name_pools import get_names_for_pole_type
        names = get_names_for_pole_type("ORGANIZATION", 5, domain_id="healthcare")
        assert any("Hospital" in n or "Medical" in n or "Health" in n for n in names)

    def test_domain_event_names(self):
        from create_context_graph.name_pools import get_names_for_pole_type
        names = get_names_for_pole_type("EVENT", 5, domain_id="healthcare")
        assert any("Grand Rounds" in n or "Code Blue" in n or "Committee" in n or "Audit" in n for n in names)

    def test_domain_location_names(self):
        from create_context_graph.name_pools import get_names_for_pole_type
        names = get_names_for_pole_type("LOCATION", 5, domain_id="financial-services")
        assert any("Trading" in n or "Branch" in n or "Office" in n or "Headquarters" in n for n in names)

    def test_habitat_realistic(self):
        from create_context_graph.name_pools import generate_property_value
        val = generate_property_value("habitat", "string", "Tiger", "Species", 0)
        assert " - " not in val
        assert "forest" in val.lower() or "savanna" in val.lower() or "reef" in val.lower() or "tundra" in val.lower() or "wetland" in val.lower()

    def test_mechanism_of_action_realistic(self):
        from create_context_graph.name_pools import generate_property_value
        val = generate_property_value("mechanism_of_action", "string", "Metformin", "Medication", 0)
        assert " - " not in val
        assert "inhibit" in val.lower() or "block" in val.lower() or "reduct" in val.lower() or "select" in val.lower()

    def test_manufacturer_uses_org_names(self):
        from create_context_graph.name_pools import generate_property_value
        val = generate_property_value("manufacturer", "string", "Widget A", "Part", 0)
        assert " - " not in val

    def test_generator_passes_domain_id(self):
        """Static generator should produce domain-aware names for healthcare Person entities."""
        from create_context_graph.generator import _generate_static_entities
        from create_context_graph.ontology import load_domain
        ontology = load_domain("healthcare")
        # Find the Person entity type
        person_et = next((et for et in ontology.entity_types if et.label == "Person"), None)
        if person_et:
            entities = _generate_static_entities(person_et, domain_id="healthcare")
            names = [e["name"] for e in entities]
            assert any("Dr." in n or "Nurse" in n or "Pharmacist" in n for n in names), \
                f"Healthcare Person entities should have medical names, got: {names}"


class TestV060IngestHelpers:
    """Tests for v0.6.0 ingest.py helper functions."""

    def test_get_pole_type_known_label(self):
        from create_context_graph.ingest import _get_pole_type
        from create_context_graph.ontology import load_domain
        ontology = load_domain("healthcare")
        assert _get_pole_type("Patient", ontology) == "PERSON"
        assert _get_pole_type("Medication", ontology) == "OBJECT"

    def test_get_pole_type_unknown_label(self):
        from create_context_graph.ingest import _get_pole_type
        from create_context_graph.ontology import load_domain
        ontology = load_domain("healthcare")
        assert _get_pole_type("UnknownLabel", ontology) == "OBJECT"


class TestV060ChatInterfaceUI:
    """Tests for v0.6.0 ChatInterface UI improvements."""

    def test_chat_has_avatars(self, generated_project):
        """ChatInterface should have user and assistant avatars."""
        out, _ = generated_project
        chat = (out / "frontend" / "components" / "ChatInterface.tsx").read_text()
        assert "Bot" in chat, "Should import Bot icon"
        assert "User" in chat, "Should import User icon"
        assert "Circle" in chat, "Should use Circle for avatar"

    def test_chat_has_keyboard_hint(self, generated_project):
        """ChatInterface should show keyboard shortcut hint."""
        out, _ = generated_project
        chat = (out / "frontend" / "components" / "ChatInterface.tsx").read_text()
        assert "Enter to send" in chat, "Should show Enter hint"
        assert "Shift+Enter" in chat, "Should show Shift+Enter hint"

    def test_chat_suggested_questions_no_truncation(self, generated_project):
        """Suggested questions should not truncate with 60 char limit."""
        out, _ = generated_project
        chat = (out / "frontend" / "components" / "ChatInterface.tsx").read_text()
        assert "slice(0, 60)" not in chat, "Should not truncate at 60 chars"

    def test_chat_has_sparkles_icon(self, generated_project):
        """Suggested questions should use Sparkles icon."""
        out, _ = generated_project
        chat = (out / "frontend" / "components" / "ChatInterface.tsx").read_text()
        assert "Sparkles" in chat, "Should import Sparkles icon"

    def test_chat_tool_progress_counter(self, generated_project):
        """Loading state should show tool progress count."""
        out, _ = generated_project
        chat = (out / "frontend" / "components" / "ChatInterface.tsx").read_text()
        assert "Running tool" in chat, "Should show running tool count"

    def test_e2e_demo_prompt_text_matches_chat_interface(self, generated_project):
        """E2E test expectations must match the actual UI text.

        Regression guard for the v0.11.2 mismatch where app.spec.ts looked for
        "try a demo scenario" but ChatInterface had been refactored to render
        "Try these". The two strings must agree, otherwise the Playwright
        suite fails out of the box on every scaffold.
        """
        out, _ = generated_project
        chat = (out / "frontend" / "components" / "ChatInterface.tsx").read_text()
        spec = (out / "frontend" / "e2e" / "app.spec.ts").read_text()

        # Whatever header text the UI uses, the E2E spec must look for it.
        assert ">Try these<" in chat, "ChatInterface should render the 'Try these' header"
        assert "/try these/i" in spec, "E2E spec must search for the same header text"
        # And the obsolete string must not have crept back in.
        assert "try a demo scenario" not in spec


class TestV061DataQuality:
    """Tests for v0.6.1 data quality improvements."""

    def test_description_no_comprehensive_profile(self):
        """Entity descriptions should not use generic 'Comprehensive profile' template."""
        from create_context_graph.name_pools import generate_property_value
        for label in ("Patient", "Person", "Provider"):
            val = generate_property_value("description", "string", "Test Name", label, 0, domain_id="healthcare")
            assert "comprehensive" not in val.lower(), f"{label} description should not say 'comprehensive': {val}"

    def test_description_person_uses_domain_role(self):
        """Person-type entity descriptions should include a domain-specific role."""
        from create_context_graph.name_pools import generate_property_value
        val = generate_property_value("description", "string", "Dr. Chen", "Patient", 0, domain_id="healthcare")
        assert "healthcare" in val.lower(), f"Healthcare patient description should mention healthcare: {val}"

    def test_description_organization_uses_domain_industry(self):
        """Organization-type entity descriptions should use domain-specific industry."""
        from create_context_graph.name_pools import generate_property_value
        val = generate_property_value("description", "string", "Metro Hospital", "Organization", 0, domain_id="healthcare")
        assert "hospital" in val.lower() or "healthcare" in val.lower(), (
            f"Healthcare org description should mention hospital/healthcare: {val}"
        )

    def test_description_default_label(self):
        """Non-person/non-org labels should use generic template."""
        from create_context_graph.name_pools import generate_property_value
        val = generate_property_value("description", "string", "Sample Item", "Medication", 0, domain_id="healthcare")
        assert "medication" in val.lower(), f"Medication description should mention label: {val}"

    def test_industry_healthcare_not_technology(self):
        """Healthcare domain organizations should have healthcare-related industries."""
        from create_context_graph.name_pools import generate_property_value
        for i in range(6):
            val = generate_property_value("industry", "string", "Test Org", "Organization", i, domain_id="healthcare")
            assert val != "Technology", f"Healthcare industry should not be 'Technology', got: {val}"

    def test_industry_all_domains_have_pools(self):
        """All 23 domains should have entries in DOMAIN_INDUSTRY_POOL."""
        from create_context_graph.name_pools import DOMAIN_INDUSTRY_POOL
        from create_context_graph.ontology import list_available_domains
        domains = list_available_domains()
        for domain in domains:
            domain_id = domain["id"] if isinstance(domain, dict) else domain
            assert domain_id in DOMAIN_INDUSTRY_POOL, f"Missing DOMAIN_INDUSTRY_POOL for {domain_id}"

    def test_observation_with_entities_references_name(self):
        """Decision trace observations should reference entity names when entities are provided."""
        from create_context_graph.generator import _generate_static_observation
        entities = {"Patient": [{"name": "Dr. Sarah Chen"}]}
        obs = _generate_static_observation("query patient records", "Healthcare", entities)
        assert "Dr. Sarah Chen" in obs, f"Observation should reference entity name: {obs}"

    def test_observation_without_entities_still_works(self):
        """Decision trace observations should work without entity context."""
        from create_context_graph.generator import _generate_static_observation
        obs = _generate_static_observation("query records", "Healthcare", None)
        assert "healthcare" in obs.lower(), f"Observation should mention domain: {obs}"


class TestV061FrontendFeatures:
    """Tests for v0.6.1 frontend feature additions."""

    def test_thinking_filter_has_continuation_patterns(self, generated_project):
        """ChatInterface should have CONTINUATION_PATTERNS for multi-sentence thinking."""
        out, _ = generated_project
        chat = (out / "frontend" / "components" / "ChatInterface.tsx").read_text()
        assert "CONTINUATION_PATTERNS" in chat, "Should define CONTINUATION_PATTERNS"
        assert "inThinkingBlock" in chat, "Should track thinking block state"

    def test_document_browser_uses_react_markdown(self, generated_project):
        """DocumentBrowser should render content with ReactMarkdown."""
        out, _ = generated_project
        doc_browser = (out / "frontend" / "components" / "DocumentBrowser.tsx").read_text()
        assert "ReactMarkdown" in doc_browser, "Should import ReactMarkdown"
        assert "remarkGfm" in doc_browser, "Should import remarkGfm"

    def test_graph_view_has_node_tooltip(self, generated_project):
        """ContextGraphView should have node hover tooltips."""
        out, _ = generated_project
        graph = (out / "frontend" / "components" / "ContextGraphView.tsx").read_text()
        assert "title: tooltip" in graph, "Nodes should have title/tooltip property"

    def test_graph_view_has_ask_about_button(self, generated_project):
        """ContextGraphView should have an 'Ask about' button on node click."""
        out, _ = generated_project
        graph = (out / "frontend" / "components" / "ContextGraphView.tsx").read_text()
        assert "onAskAbout" in graph, "Should have onAskAbout prop"
        assert "Ask about" in graph, "Should render 'Ask about' button text"

    def test_page_wires_ask_about(self, generated_project):
        """page.tsx should wire the askAbout callback between graph and chat."""
        out, _ = generated_project
        page = (out / "frontend" / "app" / "page.tsx").read_text()
        assert "askAboutInput" in page, "Should have askAboutInput state"
        assert "handleAskAbout" in page, "Should have handleAskAbout callback"
        assert "externalInput" in page, "Should pass externalInput to ChatInterface"

    def test_health_polling_60s(self, generated_project):
        """Health check should poll every 60 seconds, not 30."""
        out, _ = generated_project
        page = (out / "frontend" / "app" / "page.tsx").read_text()
        assert "60000" in page, "Should poll every 60 seconds"
        assert "30000" not in page, "Should not poll every 30 seconds"

    def test_generate_data_uses_on_create_match_set(self, generated_project):
        """generate_data.py should use ON CREATE SET / ON MATCH SET for safe upserts."""
        out, _ = generated_project
        gen_data = (out / "backend" / "scripts" / "generate_data.py").read_text()
        assert "ON CREATE SET" in gen_data, "Should use ON CREATE SET"
        assert "ON MATCH SET" in gen_data, "Should use ON MATCH SET"


class TestV061DomainTools:
    """Tests for v0.6.1 list/get-by-id tools added to all domains."""

    def test_all_domains_have_list_tool(self):
        """Every domain should have at least one list_* tool."""
        from create_context_graph.ontology import list_available_domains, load_domain
        for domain in list_available_domains():
            did = domain["id"] if isinstance(domain, dict) else domain
            ontology = load_domain(did)
            tool_names = [t.name for t in ontology.agent_tools]
            has_list = any(t.startswith("list_") for t in tool_names)
            assert has_list, f"Domain {did} should have a list_* tool, got: {tool_names}"

    def test_all_domains_have_get_by_id_tool(self):
        """Every domain should have at least one get_*_by_id or get_*_by_name tool."""
        from create_context_graph.ontology import list_available_domains, load_domain
        for domain in list_available_domains():
            did = domain["id"] if isinstance(domain, dict) else domain
            ontology = load_domain(did)
            tool_names = [t.name for t in ontology.agent_tools]
            has_get = any("_by_id" in t or "_by_name" in t for t in tool_names)
            assert has_get, f"Domain {did} should have a get_by_id tool, got: {tool_names}"

    def test_all_domains_have_minimum_tool_count(self):
        """Every domain should have at least 7 agent tools."""
        from create_context_graph.ontology import list_available_domains, load_domain
        for domain in list_available_domains():
            did = domain["id"] if isinstance(domain, dict) else domain
            ontology = load_domain(did)
            count = len(ontology.agent_tools)
            assert count >= 7, f"Domain {did} should have >= 7 tools, got {count}"
