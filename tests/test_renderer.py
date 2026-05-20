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

"""Unit tests for the renderer module."""

import json

import pytest

from create_context_graph.config import ProjectConfig
from create_context_graph.ontology import load_domain
from create_context_graph.renderer import (
    ProjectRenderer,
    _to_camel_case,
    _to_kebab_case,
    _to_pascal_case,
    _to_snake_case,
)


class TestFilters:
    def test_snake_case(self):
        assert _to_snake_case("MyClass") == "my_class"
        assert _to_snake_case("camelCase") == "camel_case"
        assert _to_snake_case("kebab-case") == "kebab_case"
        assert _to_snake_case("already_snake") == "already_snake"

    def test_camel_case(self):
        assert _to_camel_case("my_class") == "myClass"
        assert _to_camel_case("hello world") == "helloWorld"

    def test_pascal_case(self):
        assert _to_pascal_case("my_class") == "MyClass"
        assert _to_pascal_case("hello world") == "HelloWorld"

    def test_kebab_case(self):
        assert _to_kebab_case("MyClass") == "my-class"
        assert _to_kebab_case("camelCase") == "camel-case"


class TestProjectRenderer:
    def test_render_creates_directory_structure(self, financial_config, tmp_output):
        ontology = load_domain(financial_config.domain)
        renderer = ProjectRenderer(financial_config, ontology)
        renderer.render(tmp_output)

        assert (tmp_output / "backend" / "app" / "main.py").exists()
        assert (tmp_output / "backend" / "app" / "agent.py").exists()
        assert (tmp_output / "backend" / "app" / "config.py").exists()
        assert (tmp_output / "backend" / "app" / "routes.py").exists()
        assert (tmp_output / "backend" / "app" / "models.py").exists()
        assert (tmp_output / "backend" / "app" / "context_graph_client.py").exists()
        assert (tmp_output / "backend" / "app" / "gds_client.py").exists()
        assert (tmp_output / "backend" / "app" / "vector_client.py").exists()
        assert (tmp_output / "backend" / "pyproject.toml").exists()
        assert (tmp_output / "backend" / "scripts" / "generate_data.py").exists()
        assert (tmp_output / "backend" / "app" / "__init__.py").exists()

    def test_render_creates_frontend(self, financial_config, tmp_output):
        ontology = load_domain(financial_config.domain)
        renderer = ProjectRenderer(financial_config, ontology)
        renderer.render(tmp_output)

        assert (tmp_output / "frontend" / "package.json").exists()
        assert (tmp_output / "frontend" / "next.config.ts").exists()
        assert (tmp_output / "frontend" / "tsconfig.json").exists()
        assert (tmp_output / "frontend" / "app" / "layout.tsx").exists()
        assert (tmp_output / "frontend" / "app" / "page.tsx").exists()
        assert (tmp_output / "frontend" / "app" / "globals.css").exists()
        assert (tmp_output / "frontend" / "components" / "ChatInterface.tsx").exists()
        assert (tmp_output / "frontend" / "components" / "ContextGraphView.tsx").exists()
        assert (tmp_output / "frontend" / "components" / "DecisionTracePanel.tsx").exists()
        assert (tmp_output / "frontend" / "components" / "Provider.tsx").exists()
        assert (tmp_output / "frontend" / "lib" / "config.ts").exists()
        assert (tmp_output / "frontend" / "theme" / "index.ts").exists()

    def test_render_creates_base_files(self, financial_config, tmp_output):
        ontology = load_domain(financial_config.domain)
        renderer = ProjectRenderer(financial_config, ontology)
        renderer.render(tmp_output)

        assert (tmp_output / ".env").exists()
        assert (tmp_output / ".gitignore").exists()
        assert (tmp_output / "Makefile").exists()
        assert (tmp_output / "README.md").exists()
        assert (tmp_output / "docker-compose.yml").exists()  # docker type

    def test_no_docker_compose_for_aura(self, tmp_output):
        from create_context_graph.config import ProjectConfig
        config = ProjectConfig(
            project_name="Test",
            domain="financial-services",
            framework="pydanticai",
            neo4j_type="existing",
        )
        ontology = load_domain(config.domain)
        renderer = ProjectRenderer(config, ontology)
        renderer.render(tmp_output)

        assert not (tmp_output / "docker-compose.yml").exists()

    def test_render_creates_cypher(self, financial_config, tmp_output):
        ontology = load_domain(financial_config.domain)
        renderer = ProjectRenderer(financial_config, ontology)
        renderer.render(tmp_output)

        assert (tmp_output / "cypher" / "schema.cypher").exists()
        assert (tmp_output / "cypher" / "gds_projections.cypher").exists()

    def test_render_creates_data(self, financial_config, tmp_output):
        ontology = load_domain(financial_config.domain)
        renderer = ProjectRenderer(financial_config, ontology)
        renderer.render(tmp_output)

        assert (tmp_output / "data" / "ontology.yaml").exists()
        assert (tmp_output / "data" / "_base.yaml").exists()
        assert (tmp_output / "data" / "documents").is_dir()

    def test_fixtures_bundled(self, financial_config, tmp_output):
        ontology = load_domain(financial_config.domain)
        renderer = ProjectRenderer(financial_config, ontology)
        renderer.render(tmp_output)

        fixture_path = tmp_output / "data" / "fixtures.json"
        assert fixture_path.exists()
        data = json.loads(fixture_path.read_text())
        assert "entities" in data
        assert "relationships" in data

    def test_env_contains_credentials(self, financial_config, tmp_output):
        ontology = load_domain(financial_config.domain)
        renderer = ProjectRenderer(financial_config, ontology)
        renderer.render(tmp_output)

        env_content = (tmp_output / ".env").read_text()
        assert "NEO4J_URI" in env_content
        assert financial_config.neo4j_uri in env_content

    def test_readme_contains_domain(self, financial_config, tmp_output):
        ontology = load_domain(financial_config.domain)
        renderer = ProjectRenderer(financial_config, ontology)
        renderer.render(tmp_output)

        readme = (tmp_output / "README.md").read_text()
        assert "Financial Services" in readme
        assert "PydanticAI" in readme

    def test_agent_uses_correct_framework(self, financial_config, tmp_output):
        ontology = load_domain(financial_config.domain)
        renderer = ProjectRenderer(financial_config, ontology)
        renderer.render(tmp_output)

        agent = (tmp_output / "backend" / "app" / "agent.py").read_text()
        assert "PydanticAI" in agent
        assert "pydantic_ai" in agent

    def test_claude_agent_sdk_template(self, healthcare_config, tmp_output):
        ontology = load_domain(healthcare_config.domain)
        renderer = ProjectRenderer(healthcare_config, ontology)
        renderer.render(tmp_output)

        agent = (tmp_output / "backend" / "app" / "agent.py").read_text()
        assert "Claude Agent SDK" in agent
        assert "anthropic" in agent

    def test_frontend_config_has_domain_data(self, financial_config, tmp_output):
        ontology = load_domain(financial_config.domain)
        renderer = ProjectRenderer(financial_config, ontology)
        renderer.render(tmp_output)

        config_ts = (tmp_output / "frontend" / "lib" / "config.ts").read_text()
        assert "Financial Services" in config_ts
        assert "NODE_COLORS" in config_ts
        assert "DEMO_SCENARIOS" in config_ts

    def test_package_json_valid(self, financial_config, tmp_output):
        ontology = load_domain(financial_config.domain)
        renderer = ProjectRenderer(financial_config, ontology)
        renderer.render(tmp_output)

        pkg = json.loads((tmp_output / "frontend" / "package.json").read_text())
        assert "@chakra-ui/react" in pkg["dependencies"]
        assert "next" in pkg["dependencies"]

    def test_backend_pyproject_valid(self, financial_config, tmp_output):
        ontology = load_domain(financial_config.domain)
        renderer = ProjectRenderer(financial_config, ontology)
        renderer.render(tmp_output)

        content = (tmp_output / "backend" / "pyproject.toml").read_text()
        assert "fastapi" in content
        assert "neo4j" in content
        assert "pydantic-ai" in content  # framework dep

    def test_cypher_schema_has_constraints(self, financial_config, tmp_output):
        ontology = load_domain(financial_config.domain)
        renderer = ProjectRenderer(financial_config, ontology)
        renderer.render(tmp_output)

        schema = (tmp_output / "cypher" / "schema.cypher").read_text()
        assert "CREATE CONSTRAINT" in schema
        assert "CREATE INDEX" in schema

    def test_generated_python_compiles(self, financial_config, tmp_output):
        """Verify key generated Python files are syntactically valid."""
        ontology = load_domain(financial_config.domain)
        renderer = ProjectRenderer(financial_config, ontology)
        renderer.render(tmp_output)

        py_files = [
            "backend/app/main.py",
            "backend/app/config.py",
            "backend/app/agent.py",
            "backend/app/routes.py",
            "backend/app/models.py",
            "backend/app/context_graph_client.py",
            "backend/app/gds_client.py",
            "backend/app/vector_client.py",
            "backend/scripts/generate_data.py",
        ]
        for py_file in py_files:
            path = tmp_output / py_file
            source = path.read_text()
            try:
                compile(source, str(path), "exec")
            except SyntaxError as e:
                pytest.fail(f"{py_file} has syntax error: {e}")


    def test_env_example_generated(self, financial_config, tmp_output):
        """Verify .env.example is generated alongside .env."""
        ontology = load_domain(financial_config.domain)
        renderer = ProjectRenderer(financial_config, ontology)
        renderer.render(tmp_output)

        env_example = tmp_output / ".env.example"
        assert env_example.exists()
        content = env_example.read_text()
        assert "NEO4J_URI=" in content
        assert "your-password-here" in content
        assert "ANTHROPIC_API_KEY=" in content
        assert "BACKEND_PORT=" in content
        # .env.example must differ from .env (placeholders vs real values)
        env_content = (tmp_output / ".env").read_text()
        assert content != env_content

    def test_chat_interface_has_session_id(self, financial_config, tmp_output):
        """Verify ChatInterface sends session_id to backend."""
        ontology = load_domain(financial_config.domain)
        renderer = ProjectRenderer(financial_config, ontology)
        renderer.render(tmp_output)

        chat = (tmp_output / "frontend" / "components" / "ChatInterface.tsx").read_text()
        assert "session_id" in chat
        assert "sessionId" in chat
        assert "setSessionId" in chat

    def test_chat_interface_has_markdown_rendering(self, financial_config, tmp_output):
        """Verify ChatInterface uses ReactMarkdown for assistant messages."""
        ontology = load_domain(financial_config.domain)
        renderer = ProjectRenderer(financial_config, ontology)
        renderer.render(tmp_output)

        chat = (tmp_output / "frontend" / "components" / "ChatInterface.tsx").read_text()
        assert "ReactMarkdown" in chat
        assert "remarkGfm" in chat

    def test_package_json_has_markdown_deps(self, financial_config, tmp_output):
        """Verify package.json includes react-markdown and remark-gfm."""
        ontology = load_domain(financial_config.domain)
        renderer = ProjectRenderer(financial_config, ontology)
        renderer.render(tmp_output)

        pkg = json.loads((tmp_output / "frontend" / "package.json").read_text())
        assert "react-markdown" in pkg["dependencies"]
        assert "remark-gfm" in pkg["dependencies"]

    def test_context_graph_client_has_memory_functions(self, financial_config, tmp_output):
        """Verify context_graph_client.py delegates to memory module."""
        ontology = load_domain(financial_config.domain)
        renderer = ProjectRenderer(financial_config, ontology)
        renderer.render(tmp_output)

        client = (tmp_output / "backend" / "app" / "context_graph_client.py").read_text()
        assert "from app.memory import connect_memory" in client
        assert "MemoryClient" not in client
        assert "drain_tool_calls" in client
        assert "emit_entities_extracted" in client
        assert "emit_preferences_detected" in client

    def test_gds_client_no_hardcoded_entity(self, financial_config, tmp_output):
        """Verify GDS client doesn't use hardcoded 'Entity' label."""
        ontology = load_domain(financial_config.domain)
        renderer = ProjectRenderer(financial_config, ontology)
        renderer.render(tmp_output)

        gds = (tmp_output / "backend" / "app" / "gds_client.py").read_text()
        assert 'label: str = "Entity"' not in gds
        assert "ENTITY_LABELS" in gds

    def test_agent_imports_memory_functions(self, financial_config, tmp_output):
        """Verify generated agent imports from memory module."""
        ontology = load_domain(financial_config.domain)
        renderer = ProjectRenderer(financial_config, ontology)
        renderer.render(tmp_output)

        agent = (tmp_output / "backend" / "app" / "agent.py").read_text()
        assert "from app.memory import" in agent
        assert "store_message" in agent
        assert "get_context" in agent
        assert "resolve_session_id" in agent

    def test_routes_has_tool_calls_in_response(self, financial_config, tmp_output):
        """Verify routes.py includes tool_calls in ChatResponse."""
        ontology = load_domain(financial_config.domain)
        renderer = ProjectRenderer(financial_config, ontology)
        renderer.render(tmp_output)

        routes = (tmp_output / "backend" / "app" / "routes.py").read_text()
        assert "tool_calls" in routes
        assert "drain_tool_calls" in routes

    def test_readme_has_entity_type_sections(self, financial_config, tmp_output):
        """Verify README splits entity types into base and domain-specific."""
        ontology = load_domain(financial_config.domain)
        renderer = ProjectRenderer(financial_config, ontology)
        renderer.render(tmp_output)

        readme = (tmp_output / "README.md").read_text()
        assert "Base POLE+O Entities" in readme
        assert "Domain-Specific Entities" in readme

    def test_main_py_cors_uses_settings(self, financial_config, tmp_output):
        """Verify main.py reads CORS origin from settings instead of hardcoding."""
        ontology = load_domain(financial_config.domain)
        renderer = ProjectRenderer(financial_config, ontology)
        renderer.render(tmp_output)

        main = (tmp_output / "backend" / "app" / "main.py").read_text()
        assert "settings.frontend_port" in main
        assert '"http://localhost:3000"' not in main

    def test_main_py_creates_vector_index(self, financial_config, tmp_output):
        """Verify main.py creates vector index at startup."""
        ontology = load_domain(financial_config.domain)
        renderer = ProjectRenderer(financial_config, ontology)
        renderer.render(tmp_output)

        main = (tmp_output / "backend" / "app" / "main.py").read_text()
        assert "create_vector_index" in main

    def test_docker_compose_pinned_version(self, financial_config, tmp_output):
        """Verify docker-compose.yml pins Neo4j to a specific version."""
        ontology = load_domain(financial_config.domain)
        renderer = ProjectRenderer(financial_config, ontology)
        renderer.render(tmp_output)

        dc = (tmp_output / "docker-compose.yml").read_text()
        assert "neo4j:5." in dc
        # Should be pinned to patch version, not just "neo4j:5"
        assert "neo4j:5\n" not in dc

    def test_makefile_has_trap_cleanup(self, financial_config, tmp_output):
        """Verify Makefile uses trap for process cleanup."""
        ontology = load_domain(financial_config.domain)
        renderer = ProjectRenderer(financial_config, ontology)
        renderer.render(tmp_output)

        makefile = (tmp_output / "Makefile").read_text()
        assert "trap" in makefile

    def test_neo4j_local_makefile_targets(self, tmp_output):
        """Verify neo4j-local type generates neo4j-start/stop targets."""
        from create_context_graph.config import ProjectConfig
        config = ProjectConfig(
            project_name="Test Local",
            domain="financial-services",
            framework="pydanticai",
            neo4j_type="local",
        )
        ontology = load_domain(config.domain)
        renderer = ProjectRenderer(config, ontology)
        renderer.render(tmp_output)

        makefile = (tmp_output / "Makefile").read_text()
        assert "neo4j-start:" in makefile
        assert "neo4j-stop:" in makefile
        assert "@johnymontana/neo4j-local" in makefile
        assert not (tmp_output / "docker-compose.yml").exists()

    def test_aura_no_docker_or_local_targets(self, tmp_output):
        """Verify aura type has no docker or neo4j-local targets."""
        from create_context_graph.config import ProjectConfig
        config = ProjectConfig(
            project_name="Test Aura",
            domain="financial-services",
            framework="pydanticai",
            neo4j_type="aura",
            neo4j_uri="neo4j+s://abc.databases.neo4j.io",
        )
        ontology = load_domain(config.domain)
        renderer = ProjectRenderer(config, ontology)
        renderer.render(tmp_output)

        makefile = (tmp_output / "Makefile").read_text()
        assert "docker-up" not in makefile
        assert "neo4j-start" not in makefile
        assert not (tmp_output / "docker-compose.yml").exists()

    def test_globals_css_has_markdown_styles(self, financial_config, tmp_output):
        """Verify globals.css includes markdown content styles."""
        ontology = load_domain(financial_config.domain)
        renderer = ProjectRenderer(financial_config, ontology)
        renderer.render(tmp_output)

        css = (tmp_output / "frontend" / "app" / "globals.css").read_text()
        assert ".markdown-content" in css

    def test_memory_py_generated(self, financial_config, tmp_output):
        """Verify memory.py module is generated with MemoryIntegration."""
        ontology = load_domain(financial_config.domain)
        renderer = ProjectRenderer(financial_config, ontology)
        renderer.render(tmp_output)

        memory = (tmp_output / "backend" / "app" / "memory.py").read_text()
        assert "MemoryIntegration" in memory
        assert "connect_memory" in memory
        assert "close_memory" in memory
        assert "store_message" in memory
        assert "get_context" in memory
        assert "resolve_session_id" in memory

    def test_mcp_files_generated_when_enabled(self, tmp_output):
        """Verify MCP files are generated when with_mcp=True (bolt path uses requested profile)."""
        config = ProjectConfig(
            project_name="Test MCP App",
            domain="financial-services",
            framework="pydanticai",
            memory_backend="bolt",
            with_mcp=True,
            mcp_profile="extended",
        )
        ontology = load_domain(config.domain)
        renderer = ProjectRenderer(config, ontology)
        renderer.render(tmp_output)

        mcp_config = tmp_output / "mcp" / "claude_desktop_config.json"
        mcp_readme = tmp_output / "mcp" / "README.md"
        assert mcp_config.exists()
        assert mcp_readme.exists()
        content = mcp_config.read_text()
        assert "test-mcp-app-memory" in content
        assert "extended" in content

    def test_mcp_files_not_generated_by_default(self, financial_config, tmp_output):
        """Verify MCP files are NOT generated when with_mcp=False."""
        ontology = load_domain(financial_config.domain)
        renderer = ProjectRenderer(financial_config, ontology)
        renderer.render(tmp_output)

        assert not (tmp_output / "mcp").exists()

    def test_pyproject_bumps_memory_version(self, financial_config, tmp_output):
        """Verify generated pyproject.toml requires neo4j-agent-memory>=0.4.0,<0.6.0."""
        ontology = load_domain(financial_config.domain)
        renderer = ProjectRenderer(financial_config, ontology)
        renderer.render(tmp_output)

        pkg = (tmp_output / "backend" / "pyproject.toml").read_text()
        assert "neo4j-agent-memory" in pkg
        assert ">=0.4.0" in pkg
        assert "<0.6.0" in pkg
        # Self-hosted (financial_config) includes extraction + fuzzy extras
        assert "extraction" in pkg
        assert "fuzzy" in pkg

    def test_makefile_has_mcp_target_when_enabled(self, tmp_output):
        """Verify Makefile includes mcp-server target when with_mcp=True."""
        config = ProjectConfig(
            project_name="Test MCP App",
            domain="healthcare",
            framework="pydanticai",
            memory_backend="bolt",
            with_mcp=True,
        )
        ontology = load_domain(config.domain)
        renderer = ProjectRenderer(config, ontology)
        renderer.render(tmp_output)

        makefile = (tmp_output / "Makefile").read_text()
        assert "mcp-server" in makefile
        assert "neo4j_agent_memory.mcp.server" in makefile

    def test_makefile_no_mcp_target_by_default(self, financial_config, tmp_output):
        """Verify Makefile does NOT include mcp-server when with_mcp=False."""
        ontology = load_domain(financial_config.domain)
        renderer = ProjectRenderer(financial_config, ontology)
        renderer.render(tmp_output)

        makefile = (tmp_output / "Makefile").read_text()
        assert "mcp-server" not in makefile

    def test_env_example_has_session_strategy(self, financial_config, tmp_output):
        """Verify .env.example includes SESSION_STRATEGY."""
        ontology = load_domain(financial_config.domain)
        renderer = ProjectRenderer(financial_config, ontology)
        renderer.render(tmp_output)

        env = (tmp_output / ".env.example").read_text()
        assert "SESSION_STRATEGY" in env

    def test_config_py_has_session_strategy(self, financial_config, tmp_output):
        """Verify generated config.py includes session_strategy setting."""
        ontology = load_domain(financial_config.domain)
        renderer = ProjectRenderer(financial_config, ontology)
        renderer.render(tmp_output)

        config_py = (tmp_output / "backend" / "app" / "config.py").read_text()
        assert "session_strategy" in config_py

    def test_claude_code_scenarios_override_generic(self, tmp_output):
        """When claude-code connector is active, demo scenarios should be replaced."""
        config = ProjectConfig(
            project_name="cc-test",
            domain="software-engineering",
            framework="pydanticai",
            saas_connectors=["claude-code"],
        )
        ontology = load_domain(config.domain)
        renderer = ProjectRenderer(config, ontology)
        ctx = renderer._context()

        scenario_names = [s["name"] for s in ctx["demo_scenarios"]]
        assert "Session Intelligence" in scenario_names
        # Should NOT contain generic SE scenarios
        prompts = [p for s in ctx["demo_scenarios"] for p in s["prompts"]]
        assert not any("pull request" in p.lower() for p in prompts)

    def test_config_py_has_connector_fields(self, tmp_output):
        """Verify config.py includes Settings fields for each selected connector."""
        cases = [
            ("github", ["github_token", "github_repo"]),
            ("notion", ["notion_token"]),
            ("jira", ["jira_url", "jira_email", "jira_token", "jira_project"]),
            ("slack", ["slack_token", "slack_channels"]),
            ("salesforce", ["salesforce_username", "salesforce_password"]),
            ("linear", ["linear_api_key", "linear_team"]),
            ("claude-code", ["claude_code_scope", "claude_code_since"]),
        ]
        for connector_id, expected_fields in cases:
            config = ProjectConfig(
                project_name="test-config",
                domain="software-engineering",
                framework="pydanticai",
                saas_connectors=[connector_id],
            )
            ontology = load_domain(config.domain)
            renderer = ProjectRenderer(config, ontology)
            renderer.render(tmp_output)
            config_py = (tmp_output / "backend" / "app" / "config.py").read_text()
            for field in expected_fields:
                assert field in config_py, (
                    f"config.py missing '{field}' when connector '{connector_id}' is selected"
                )

    def test_pyproject_has_connector_deps(self, tmp_output):
        """Verify pyproject.toml includes the right package for each connector."""
        cases = [
            ("github", "PyGithub"),
            ("notion", "notion-client"),
            ("jira", "atlassian-python-api"),
            ("slack", "slack-sdk"),
            ("salesforce", "simple-salesforce"),
            ("gmail", "google-api-python-client"),
            ("gcal", "google-api-python-client"),
            ("google-workspace", "google-api-python-client"),
        ]
        for connector_id, expected_pkg in cases:
            config = ProjectConfig(
                project_name="test-deps",
                domain="software-engineering",
                framework="pydanticai",
                saas_connectors=[connector_id],
            )
            ontology = load_domain(config.domain)
            renderer = ProjectRenderer(config, ontology)
            renderer.render(tmp_output)
            pyproject = (tmp_output / "backend" / "pyproject.toml").read_text()
            assert expected_pkg in pyproject, (
                f"pyproject.toml missing '{expected_pkg}' when connector '{connector_id}' is selected"
            )

    def test_no_scenario_override_without_connector(self, financial_config, tmp_output):
        """Without claude-code connector, domain scenarios should be used as-is."""
        ontology = load_domain(financial_config.domain)
        renderer = ProjectRenderer(financial_config, ontology)
        ctx = renderer._context()

        # Should use the domain's own scenarios
        assert len(ctx["demo_scenarios"]) > 0
        scenario_names = [s["name"] for s in ctx["demo_scenarios"]]
        assert "Session Intelligence" not in scenario_names


class TestAllFrameworksRender:
    """Verify every agent framework template renders and compiles."""

    FRAMEWORK_MARKERS = {
        "pydanticai": "pydantic_ai",
        "claude-agent-sdk": "anthropic",
        "openai-agents": "agents",
        "langgraph": "langgraph",
        "crewai": "crewai",
        "strands": "strands",
        "google-adk": "google.adk",
        "anthropic-tools": "TOOL_REGISTRY",
    }

    @pytest.mark.parametrize("framework", [
        "pydanticai",
        "claude-agent-sdk",
        "openai-agents",
        "langgraph",
        "crewai",
        "strands",
        "google-adk",
        "anthropic-tools",
    ])
    def test_framework_agent_compiles(self, framework, tmp_path):
        from create_context_graph.config import ProjectConfig

        config = ProjectConfig(
            project_name="Test",
            domain="financial-services",
            framework=framework,
        )
        ontology = load_domain(config.domain)
        out = tmp_path / f"test-{framework}"
        renderer = ProjectRenderer(config, ontology)
        renderer.render(out)

        agent_path = out / "backend" / "app" / "agent.py"
        assert agent_path.exists(), f"No agent.py for {framework}"

        source = agent_path.read_text()
        try:
            compile(source, str(agent_path), "exec")
        except SyntaxError as e:
            pytest.fail(f"agent.py for {framework} has syntax error: {e}")

        # Check framework-specific marker is present
        marker = self.FRAMEWORK_MARKERS[framework]
        assert marker in source, (
            f"agent.py for {framework} missing expected import/marker '{marker}'"
        )

    @pytest.mark.parametrize("framework", [
        "pydanticai",
        "claude-agent-sdk",
        "openai-agents",
        "langgraph",
        "crewai",
        "strands",
        "google-adk",
        "anthropic-tools",
    ])
    def test_framework_pyproject_has_deps(self, framework, tmp_path):
        from create_context_graph.config import FRAMEWORK_DEPENDENCIES, ProjectConfig

        config = ProjectConfig(
            project_name="Test",
            domain="financial-services",
            framework=framework,
        )
        ontology = load_domain(config.domain)
        out = tmp_path / f"test-{framework}"
        renderer = ProjectRenderer(config, ontology)
        renderer.render(out)

        pyproject = (out / "backend" / "pyproject.toml").read_text()
        for dep in FRAMEWORK_DEPENDENCIES[framework]:
            # Extract package name (before >=)
            pkg_name = dep.split(">=")[0].split("[")[0].strip()
            assert pkg_name in pyproject, (
                f"pyproject.toml for {framework} missing dependency '{pkg_name}'"
            )


class TestCustomDomainRender:
    """Regression: renderer must complete a full scaffold when the user
    supplies ``custom_domain_yaml`` (via ``--custom-domain`` LLM generation).

    The original bug at renderer.py:557 imported ``_get_domains_path`` *only*
    inside the ``else`` branch of the custom-vs-builtin domain check, but
    referenced it again on the next line for the ``_base.yaml`` copy. On the
    custom-domain path the import never fired, Python treated the name as a
    local (because the inner branch wrote to it), and the renderer raised
    ``UnboundLocalError`` after ``data/ontology.yaml`` was already written —
    leaving a partial scaffold the user couldn't recover from.
    """

    def _custom_yaml(self) -> str:
        """A realistic ontology YAML matching what generate_custom_domain returns."""
        import importlib.resources
        # Reuse the healthcare YAML as a stand-in — the renderer doesn't care
        # whether the YAML came from an LLM or a packaged file, only that it's
        # valid ontology content keyed by domain.id.
        path = (
            importlib.resources.files("create_context_graph")
            / "domains"
            / "healthcare.yaml"
        )
        return path.read_text()

    def test_renders_full_scaffold_with_custom_domain_yaml(self, tmp_path):
        from create_context_graph.config import ProjectConfig
        from create_context_graph.ontology import load_domain_from_yaml_string

        yaml_str = self._custom_yaml()
        ontology = load_domain_from_yaml_string(yaml_str)
        config = ProjectConfig(
            project_name="CustomScaffold",
            domain=ontology.domain.id,
            framework="langgraph",
            custom_domain_yaml=yaml_str,
        )
        out = tmp_path / "custom-scaffold"
        # The original bug raised UnboundLocalError mid-render. Just calling
        # render() to completion is the regression assertion.
        ProjectRenderer(config, ontology).render(out)

        # Sanity: the expected key files all exist and are non-empty.
        for relpath in (
            "backend/app/agent.py",
            "backend/app/main.py",
            "backend/pyproject.toml",
            "data/ontology.yaml",
            "data/_base.yaml",
            "frontend/package.json",
            "Makefile",
            ".env",
            "README.md",
        ):
            f = out / relpath
            assert f.exists(), f"Custom-domain render did not produce {relpath}"
            assert f.stat().st_size > 0, f"{relpath} is empty"

        # The custom YAML was written verbatim (not the packaged copy).
        written = (out / "data" / "ontology.yaml").read_text()
        assert written == yaml_str

        # _base.yaml comes from the package, not the custom YAML.
        base = (out / "data" / "_base.yaml").read_text()
        assert "inherits" not in base  # _base.yaml is the root — nothing to inherit
        assert "entity_types:" in base or "domain:" in base

    def test_base_yaml_copied_regardless_of_custom_domain(self, tmp_path):
        """The bug surfaced specifically because _base.yaml copy lives OUTSIDE
        the custom-vs-builtin branch — so both branches must produce it.
        """
        from create_context_graph.config import ProjectConfig
        from create_context_graph.ontology import load_domain, load_domain_from_yaml_string

        # Builtin domain path
        builtin_cfg = ProjectConfig(
            project_name="Builtin",
            domain="healthcare",
            framework="pydanticai",
        )
        builtin_out = tmp_path / "builtin"
        ProjectRenderer(builtin_cfg, load_domain("healthcare")).render(builtin_out)
        assert (builtin_out / "data" / "_base.yaml").exists()

        # Custom domain path
        yaml_str = self._custom_yaml()
        custom_cfg = ProjectConfig(
            project_name="Custom",
            domain="healthcare",
            framework="pydanticai",
            custom_domain_yaml=yaml_str,
        )
        custom_out = tmp_path / "custom"
        ProjectRenderer(custom_cfg, load_domain_from_yaml_string(yaml_str)).render(
            custom_out
        )
        assert (custom_out / "data" / "_base.yaml").exists()

        # Both _base.yaml copies must come from the package — identical content.
        assert (builtin_out / "data" / "_base.yaml").read_text() == (
            custom_out / "data" / "_base.yaml"
        ).read_text()


class TestFrameworkAgentNotStubFallback:
    """Regression guard for the silent stub-fallback at ``renderer.py:430``.

    Carried forward from the v0.11.0 langgraph bug where a Jinja error in the
    framework's agent.py.j2 was swallowed by an over-broad ``except Exception``
    and produced a 36-line stub (``backend/shared/agent_stub.py.j2``) with the
    same name. Tests like ``test_framework_agent_compiles`` would pass on the
    stub because it's valid Python — the only way to catch the regression is
    to assert framework-specific *content* and the absence of the stub's
    distinguishing phrase.

    The renderer was also tightened to only catch ``TemplateNotFound`` (a real
    missing-template case) and let Jinja syntax / undefined errors propagate,
    so a future template breakage becomes a hard test failure instead of a
    silent stub. Both halves of the fix need to be in place; this test catches
    the *consequence* if the broad-except is ever re-introduced.
    """

    # Two distinctive markers per framework — at least one of which is a
    # unique-to-that-framework symbol (import path, decorator, registry, etc.)
    # that would NOT appear in the agent_stub.py.j2 fallback.
    FRAMEWORK_SIGNATURES = {
        "pydanticai": ["from pydantic_ai import", "@agent.tool"],
        "claude-agent-sdk": ["import anthropic", "client.messages.stream"],
        "openai-agents": ["from agents import", "Runner.run"],
        "langgraph": ["from langgraph.prebuilt import create_react_agent", "ChatAnthropic"],
        "crewai": ["from crewai import", "Crew("],
        "strands": ["from strands import Agent", "stream_async"],
        "google-adk": ["from google.adk", "FunctionTool"],
        "anthropic-tools": ["TOOL_REGISTRY", "@register_tool"],
    }

    STUB_FINGERPRINT = "This is a stub implementation"

    @pytest.mark.parametrize("framework", list(FRAMEWORK_SIGNATURES))
    def test_rendered_agent_is_not_the_stub(self, framework, tmp_path):
        """The framework template must render — not the stub fallback."""
        from create_context_graph.config import ProjectConfig

        config = ProjectConfig(
            project_name="StubGuard",
            domain="financial-services",
            framework=framework,
        )
        out = tmp_path / f"stub-guard-{framework}"
        ProjectRenderer(config, load_domain(config.domain)).render(out)

        source = (out / "backend" / "app" / "agent.py").read_text()
        assert self.STUB_FINGERPRINT not in source, (
            f"{framework} rendered the agent_stub fallback. "
            "See renderer.py:430 — only TemplateNotFound should trigger it."
        )
        for marker in self.FRAMEWORK_SIGNATURES[framework]:
            assert marker in source, (
                f"{framework} agent missing distinctive marker '{marker}'. "
                "Either the template silently fell back to the stub, or the "
                "template was edited away from the framework's idiomatic API."
            )

    def test_stub_fallback_only_when_template_missing(self, tmp_path):
        """Sanity: the stub is still reachable when the template genuinely
        doesn't exist. Uses a monkey-patched fw_key to simulate an unmapped
        framework (the kind of state a half-added new framework would be in).
        """
        from create_context_graph.config import ProjectConfig

        # ProjectConfig allows arbitrary framework strings (the Click choice
        # in cli.py is what gates user input); use that to land on a key with
        # no template directory.
        config = ProjectConfig(
            project_name="MissingTemplate",
            domain="financial-services",
            framework="no-such-framework",
        )
        out = tmp_path / "missing-template"
        renderer = ProjectRenderer(config, load_domain(config.domain))

        import warnings

        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            renderer.render(out)
            stub_warnings = [
                w for w in caught if "placeholder stub" in str(w.message)
            ]
            assert stub_warnings, "Missing template must warn loudly"

        source = (out / "backend" / "app" / "agent.py").read_text()
        assert self.STUB_FINGERPRINT in source

    def test_template_error_propagates(self, tmp_path):
        """Sanity: a Jinja error (not TemplateNotFound) must surface, NOT
        silently degrade to the stub.

        Uses a synthetic ``_render_template`` patch to inject an Undefined
        error that mimics the kind of template bug that previously got
        swallowed.
        """
        from unittest.mock import patch

        from jinja2.exceptions import UndefinedError

        from create_context_graph.config import ProjectConfig

        config = ProjectConfig(
            project_name="ErrorPropagates",
            domain="financial-services",
            framework="pydanticai",
        )
        out = tmp_path / "error-propagates"
        renderer = ProjectRenderer(config, load_domain(config.domain))

        original = renderer._render_template

        def fail_only_agent(template_name, output_path, ctx):
            if "agents/pydanticai/agent.py.j2" in template_name:
                raise UndefinedError("simulated template bug")
            return original(template_name, output_path, ctx)

        with patch.object(renderer, "_render_template", side_effect=fail_only_agent):
            with pytest.raises(UndefinedError, match="simulated template bug"):
                renderer.render(out)
