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

"""Integration tests for the CLI module."""

import json

import pytest

from create_context_graph.cli import main


# The ``runner`` and ``nams_runner`` fixtures live in tests/conftest.py so they
# can be shared with test_matrix.py, test_performance.py, and others.


class TestListDomains:
    def test_list_domains(self, runner):
        result = runner.invoke(main, ["--list-domains"])
        assert result.exit_code == 0
        assert "financial-services" in result.output
        assert "healthcare" in result.output
        assert "software-engineering" in result.output

    def test_list_shows_22_domains(self, runner):
        result = runner.invoke(main, ["--list-domains"])
        assert result.exit_code == 0
        # Count non-empty lines that look like domain entries
        lines = [line for line in result.output.strip().split("\n") if line.strip() and not line.startswith("Available")]
        assert len(lines) >= 22


class TestVersion:
    def test_version(self, runner):
        result = runner.invoke(main, ["--version"])
        assert result.exit_code == 0
        assert "version" in result.output


class TestScaffoldGeneration:
    def test_basic_scaffold(self, runner, tmp_path):
        out = tmp_path / "my-app"
        result = runner.invoke(main, [
            "my-app",
            "--domain", "financial-services",
            "--framework", "pydanticai",
            "--output-dir", str(out),
        ])
        assert result.exit_code == 0, result.output
        assert (out / "backend" / "app" / "main.py").exists()
        assert (out / "frontend" / "package.json").exists()

    def test_scaffold_with_demo_data(self, runner, tmp_path):
        out = tmp_path / "my-app"
        result = runner.invoke(main, [
            "my-app",
            "--domain", "healthcare",
            "--framework", "claude-agent-sdk",
            "--demo-data",
            "--output-dir", str(out),
        ])
        assert result.exit_code == 0, result.output
        fixture = out / "data" / "fixtures.json"
        assert fixture.exists()
        data = json.loads(fixture.read_text())
        assert len(data["entities"]) > 0

    def test_invalid_domain(self, runner, tmp_path):
        out = tmp_path / "my-app"
        result = runner.invoke(main, [
            "my-app",
            "--domain", "nonexistent-domain",
            "--framework", "pydanticai",
            "--output-dir", str(out),
        ])
        assert result.exit_code == 1

    def test_existing_nonempty_dir_fails(self, runner, tmp_path):
        out = tmp_path / "my-app"
        out.mkdir()
        (out / "existing-file.txt").write_text("hello")

        result = runner.invoke(main, [
            "my-app",
            "--domain", "financial-services",
            "--framework", "pydanticai",
            "--output-dir", str(out),
        ])
        assert result.exit_code == 1
        assert "not empty" in result.output


class TestNeo4jAuraEnv:
    """Test --neo4j-aura-env CLI flag."""

    def test_aura_env_flag(self, runner, tmp_path):
        # Create a fake Aura .env file
        aura_env = tmp_path / "aura.env"
        aura_env.write_text(
            'NEO4J_URI=neo4j+s://abc123.databases.neo4j.io\n'
            'NEO4J_USERNAME=neo4j\n'
            'NEO4J_PASSWORD=super-secret\n'
        )
        out = tmp_path / "aura-app"
        result = runner.invoke(main, [
            "aura-app",
            "--domain", "financial-services",
            "--framework", "pydanticai",
            "--neo4j-aura-env", str(aura_env),
            "--output-dir", str(out),
        ])
        assert result.exit_code == 0, result.output

        # Verify credentials were parsed into .env
        env = (out / ".env").read_text()
        assert "neo4j+s://abc123.databases.neo4j.io" in env
        assert "super-secret" in env

        # Verify no docker-compose for aura type
        assert not (out / "docker-compose.yml").exists()

    def test_neo4j_local_flag(self, runner, tmp_path):
        out = tmp_path / "local-app"
        result = runner.invoke(main, [
            "local-app",
            "--domain", "financial-services",
            "--framework", "pydanticai",
            "--neo4j-local",
            "--output-dir", str(out),
        ])
        assert result.exit_code == 0, result.output

        makefile = (out / "Makefile").read_text()
        assert "neo4j-start:" in makefile
        assert not (out / "docker-compose.yml").exists()

    def test_maf_alias_still_works(self, runner, tmp_path):
        """Verify deprecated 'maf' alias resolves to anthropic-tools."""
        out = tmp_path / "maf-app"
        result = runner.invoke(main, [
            "maf-app",
            "--domain", "financial-services",
            "--framework", "maf",
            "--output-dir", str(out),
        ])
        assert result.exit_code == 0, result.output
        agent = (out / "backend" / "app" / "agent.py").read_text()
        assert "Anthropic Tools" in agent


class TestMultipleDomainScaffolds:
    """Integration test: scaffold generation works for multiple domains."""

    @pytest.mark.parametrize("domain_id,framework", [
        ("financial-services", "pydanticai"),
        ("healthcare", "claude-agent-sdk"),
        ("software-engineering", "openai-agents"),
        ("wildlife-management", "langgraph"),
        ("gaming", "crewai"),
        ("manufacturing", "strands"),
        ("digital-twin", "google-adk"),
        ("retail-ecommerce", "anthropic-tools"),
    ])
    def test_domain_framework_combo(self, runner, tmp_path, domain_id, framework):
        out = tmp_path / f"test-{domain_id}"
        result = runner.invoke(main, [
            f"test-{domain_id}",
            "--domain", domain_id,
            "--framework", framework,
            "--output-dir", str(out),
        ])
        assert result.exit_code == 0, f"{domain_id}/{framework} failed: {result.output}"

        # Check key files
        assert (out / "backend" / "app" / "agent.py").exists()
        assert (out / "frontend" / "lib" / "config.ts").exists()
        assert (out / "cypher" / "schema.cypher").exists()
        assert (out / "data" / "fixtures.json").exists()

        # Verify agent template matches framework
        agent = (out / "backend" / "app" / "agent.py").read_text()
        framework_markers = {
            "pydanticai": "PydanticAI",
            "claude-agent-sdk": "Claude Agent SDK",
            "openai-agents": "OpenAI Agents SDK",
            "langgraph": "LangGraph",
            "crewai": "CrewAI",
            "strands": "Strands",
            "google-adk": "Google ADK",
            "anthropic-tools": "Anthropic Tools",
        }
        marker = framework_markers.get(framework)
        if marker:
            assert marker in agent, f"Agent file missing '{marker}' for framework {framework}"


class TestCLIValidation:
    """Tests for v0.4.0 CLI improvements."""

    def test_dry_run_no_files_created(self, runner, tmp_path):
        out = tmp_path / "dry-run-test"
        result = runner.invoke(main, [
            "dry-run-test",
            "--domain", "healthcare",
            "--framework", "pydanticai",
            "--output-dir", str(out),
            "--dry-run",
        ])
        assert result.exit_code == 0
        assert "Dry run" in result.output
        assert "healthcare" in result.output
        assert not out.exists()

    def test_verbose_flag_accepted(self, runner, tmp_path):
        out = tmp_path / "verbose-test"
        result = runner.invoke(main, [
            "verbose-test",
            "--domain", "healthcare",
            "--framework", "pydanticai",
            "--output-dir", str(out),
            "--verbose",
        ])
        assert result.exit_code == 0


class TestV060CLIFlags:
    """Tests for v0.6.0 CLI additions."""

    def test_demo_flag_accepted_dry_run(self, runner, tmp_path):
        """--demo flag should be accepted and expand to --reset-database --demo-data --ingest."""
        out = tmp_path / "demo-test"
        result = runner.invoke(main, [
            "demo-test",
            "--domain", "healthcare",
            "--framework", "pydanticai",
            "--output-dir", str(out),
            "--demo",
            "--dry-run",
        ])
        assert result.exit_code == 0
        assert "Dry run" in result.output

    def test_no_project_name_auto_generates_slug(self, runner, tmp_path):
        """When PROJECT_NAME is omitted but --domain and --framework are provided, auto-generate slug."""
        out = tmp_path / "auto-slug"
        result = runner.invoke(main, [
            "--domain", "healthcare",
            "--framework", "pydanticai",
            "--output-dir", str(out),
            "--dry-run",
        ])
        assert result.exit_code == 0, result.output
        assert "Dry run" in result.output
        assert "healthcare-pydanticai-app" in result.output

    def test_google_api_key_flag(self, runner, tmp_path):
        """--google-api-key should flow through to rendered .env."""
        out = tmp_path / "gkey-test"
        result = runner.invoke(main, [
            "gkey-test",
            "--domain", "healthcare",
            "--framework", "google-adk",
            "--google-api-key", "test-gkey-123",
            "--output-dir", str(out),
        ])
        assert result.exit_code == 0, result.output
        env_content = (out / ".env").read_text()
        assert "GOOGLE_API_KEY=test-gkey-123" in env_content

    def test_google_adk_warning_without_key(self, runner, tmp_path):
        """google-adk without --google-api-key should print a warning."""
        out = tmp_path / "adk-warn"
        result = runner.invoke(main, [
            "adk-warn",
            "--domain", "healthcare",
            "--framework", "google-adk",
            "--output-dir", str(out),
        ])
        assert result.exit_code == 0, result.output
        assert "Warning" in result.output
        assert "GOOGLE_API_KEY" in result.output

    def test_openai_api_key_flag(self, runner, tmp_path):
        """--openai-api-key should flow through to rendered .env."""
        out = tmp_path / "okey-test"
        result = runner.invoke(main, [
            "okey-test",
            "--domain", "healthcare",
            "--framework", "pydanticai",
            "--openai-api-key", "sk-test-openai",
            "--output-dir", str(out),
        ])
        assert result.exit_code == 0, result.output
        env_content = (out / ".env").read_text()
        assert "OPENAI_API_KEY=sk-test-openai" in env_content


class TestLinearConnectorCLI:
    """Tests for --connector linear CLI integration."""

    def test_linear_connector_dry_run(self, runner, tmp_path):
        """--connector linear should appear in dry-run output."""
        out = tmp_path / "linear-dry"
        result = runner.invoke(main, [
            "linear-dry",
            "--domain", "software-engineering",
            "--framework", "pydanticai",
            "--connector", "linear",
            "--dry-run",
            "--output-dir", str(out),
        ])
        assert result.exit_code == 0, result.output
        assert "linear" in result.output
        assert "Connectors" in result.output

    def test_linear_connector_warning_without_key(self, runner, tmp_path):
        """--connector linear without --linear-api-key should print a warning."""
        out = tmp_path / "linear-warn"
        result = runner.invoke(main, [
            "linear-warn",
            "--domain", "software-engineering",
            "--framework", "pydanticai",
            "--connector", "linear",
            "--output-dir", str(out),
        ])
        assert result.exit_code == 0, result.output
        assert "Warning" in result.output
        assert "LINEAR_API_KEY" in result.output

    def test_linear_connector_generates_files(self, runner, tmp_path):
        """--connector linear should generate the linear_connector.py in the project."""
        out = tmp_path / "linear-gen"
        result = runner.invoke(main, [
            "linear-gen",
            "--domain", "software-engineering",
            "--framework", "pydanticai",
            "--connector", "linear",
            "--output-dir", str(out),
        ])
        assert result.exit_code == 0, result.output
        # Linear connector template should be rendered
        assert (out / "backend" / "app" / "connectors" / "linear_connector.py").exists()
        assert (out / "backend" / "app" / "connectors" / "__init__.py").exists()
        # Import script should exist
        assert (out / "backend" / "scripts" / "import_data.py").exists()

    def test_linear_connector_env_vars(self, runner, tmp_path):
        """--connector linear should add LINEAR_API_KEY and LINEAR_TEAM to .env."""
        out = tmp_path / "linear-env"
        result = runner.invoke(main, [
            "linear-env",
            "--domain", "software-engineering",
            "--framework", "pydanticai",
            "--connector", "linear",
            "--output-dir", str(out),
        ])
        assert result.exit_code == 0, result.output
        env = (out / ".env").read_text()
        assert "LINEAR_API_KEY" in env
        assert "LINEAR_TEAM" in env

    def test_linear_connector_env_example(self, runner, tmp_path):
        """--connector linear should add LINEAR_API_KEY to .env.example."""
        out = tmp_path / "linear-envex"
        result = runner.invoke(main, [
            "linear-envex",
            "--domain", "software-engineering",
            "--framework", "pydanticai",
            "--connector", "linear",
            "--output-dir", str(out),
        ])
        assert result.exit_code == 0, result.output
        env_example = (out / ".env.example").read_text()
        assert "LINEAR_API_KEY" in env_example

    def test_linear_connector_config_has_settings(self, runner, tmp_path):
        """Generated config.py should have linear_api_key and linear_team fields."""
        out = tmp_path / "linear-cfg"
        result = runner.invoke(main, [
            "linear-cfg",
            "--domain", "software-engineering",
            "--framework", "pydanticai",
            "--connector", "linear",
            "--output-dir", str(out),
        ])
        assert result.exit_code == 0, result.output
        config_content = (out / "backend" / "app" / "config.py").read_text()
        assert "linear_api_key" in config_content
        assert "linear_team" in config_content

    def test_linear_connector_import_data_script(self, runner, tmp_path):
        """Generated import_data.py should include Linear connector imports."""
        out = tmp_path / "linear-imp"
        result = runner.invoke(main, [
            "linear-imp",
            "--domain", "software-engineering",
            "--framework", "pydanticai",
            "--connector", "linear",
            "--output-dir", str(out),
        ])
        assert result.exit_code == 0, result.output
        import_script = (out / "backend" / "scripts" / "import_data.py").read_text()
        assert "LinearConnector" in import_script
        assert "linear_api_key" in import_script

    def test_linear_api_key_flag(self, runner, tmp_path):
        """--linear-api-key should be accepted without error."""
        out = tmp_path / "linear-key"
        result = runner.invoke(main, [
            "linear-key",
            "--domain", "software-engineering",
            "--framework", "pydanticai",
            "--connector", "linear",
            "--linear-api-key", "lin_api_test123",
            "--dry-run",
            "--output-dir", str(out),
        ])
        assert result.exit_code == 0, result.output
        # Should NOT show the warning since key is provided
        assert "Warning" not in result.output or "LINEAR_API_KEY" not in result.output

    def test_linear_team_flag(self, runner, tmp_path):
        """--linear-team flag should be accepted."""
        out = tmp_path / "linear-team"
        result = runner.invoke(main, [
            "linear-team",
            "--domain", "software-engineering",
            "--framework", "pydanticai",
            "--connector", "linear",
            "--linear-api-key", "lin_api_test123",
            "--linear-team", "ENG",
            "--dry-run",
            "--output-dir", str(out),
        ])
        assert result.exit_code == 0, result.output

    def test_linear_connector_template_compiles(self, runner, tmp_path):
        """Generated linear_connector.py should be valid Python."""
        out = tmp_path / "linear-compile"
        result = runner.invoke(main, [
            "linear-compile",
            "--domain", "software-engineering",
            "--framework", "pydanticai",
            "--connector", "linear",
            "--output-dir", str(out),
        ])
        assert result.exit_code == 0, result.output
        connector_path = out / "backend" / "app" / "connectors" / "linear_connector.py"
        source = connector_path.read_text()
        try:
            compile(source, str(connector_path), "exec")
        except SyntaxError as e:
            pytest.fail(f"linear_connector.py has syntax error: {e}")

    def test_linear_connector_has_decision_traces(self, runner, tmp_path):
        """Generated linear_connector.py should include decision trace support."""
        out = tmp_path / "linear-traces"
        result = runner.invoke(main, [
            "linear-traces",
            "--domain", "software-engineering",
            "--framework", "pydanticai",
            "--connector", "linear",
            "--output-dir", str(out),
        ])
        assert result.exit_code == 0, result.output
        connector_path = out / "backend" / "app" / "connectors" / "linear_connector.py"
        source = connector_path.read_text()
        assert "_describe_history_step" in source
        assert '"traces"' in source or "'traces'" in source

    def test_linear_with_multiple_connectors(self, runner, tmp_path):
        """Linear connector can be combined with other connectors."""
        out = tmp_path / "linear-multi"
        result = runner.invoke(main, [
            "linear-multi",
            "--domain", "software-engineering",
            "--framework", "pydanticai",
            "--connector", "linear",
            "--connector", "github",
            "--output-dir", str(out),
        ])
        assert result.exit_code == 0, result.output
        connectors_dir = out / "backend" / "app" / "connectors"
        assert (connectors_dir / "linear_connector.py").exists()
        assert (connectors_dir / "github_connector.py").exists()


class TestGoogleWorkspaceConnectorCLI:
    """Tests for --connector google-workspace CLI integration."""

    def test_gws_connector_dry_run(self, runner, tmp_path):
        """--connector google-workspace should appear in dry-run output."""
        out = tmp_path / "gws-dry"
        result = runner.invoke(main, [
            "gws-dry",
            "--domain", "software-engineering",
            "--framework", "pydanticai",
            "--connector", "google-workspace",
            "--dry-run",
            "--output-dir", str(out),
        ])
        assert result.exit_code == 0, result.output
        assert "google-workspace" in result.output
        assert "Connectors" in result.output

    def test_gws_connector_generates_files(self, runner, tmp_path):
        """--connector google-workspace should generate connector files."""
        out = tmp_path / "gws-gen"
        result = runner.invoke(main, [
            "gws-gen",
            "--domain", "software-engineering",
            "--framework", "pydanticai",
            "--connector", "google-workspace",
            "--output-dir", str(out),
        ])
        assert result.exit_code == 0, result.output
        assert (out / "backend" / "app" / "connectors" / "google_workspace_connector.py").exists()
        assert (out / "backend" / "app" / "connectors" / "__init__.py").exists()
        assert (out / "backend" / "scripts" / "import_data.py").exists()

    def test_gws_connector_env_vars(self, runner, tmp_path):
        """--connector google-workspace should add GWS env vars to .env."""
        out = tmp_path / "gws-env"
        result = runner.invoke(main, [
            "gws-env",
            "--domain", "software-engineering",
            "--framework", "pydanticai",
            "--connector", "google-workspace",
            "--output-dir", str(out),
        ])
        assert result.exit_code == 0, result.output
        env = (out / ".env").read_text()
        assert "GOOGLE_CLIENT_ID" in env
        assert "GWS_FOLDER_ID" in env

    def test_gws_connector_env_example(self, runner, tmp_path):
        """--connector google-workspace should add GWS env vars to .env.example."""
        out = tmp_path / "gws-envex"
        result = runner.invoke(main, [
            "gws-envex",
            "--domain", "software-engineering",
            "--framework", "pydanticai",
            "--connector", "google-workspace",
            "--output-dir", str(out),
        ])
        assert result.exit_code == 0, result.output
        env_example = (out / ".env.example").read_text()
        assert "GOOGLE_CLIENT_ID" in env_example
        assert "GOOGLE_CLIENT_SECRET" in env_example
        assert "GWS_FOLDER_ID" in env_example

    def test_gws_connector_import_data_script(self, runner, tmp_path):
        """Generated import_data.py should include GWS connector imports."""
        out = tmp_path / "gws-imp"
        result = runner.invoke(main, [
            "gws-imp",
            "--domain", "software-engineering",
            "--framework", "pydanticai",
            "--connector", "google-workspace",
            "--output-dir", str(out),
        ])
        assert result.exit_code == 0, result.output
        import_script = (out / "backend" / "scripts" / "import_data.py").read_text()
        assert "GoogleWorkspaceConnector" in import_script

    def test_gws_connector_template_compiles(self, runner, tmp_path):
        """Generated google_workspace_connector.py should be valid Python."""
        out = tmp_path / "gws-compile"
        result = runner.invoke(main, [
            "gws-compile",
            "--domain", "software-engineering",
            "--framework", "pydanticai",
            "--connector", "google-workspace",
            "--output-dir", str(out),
        ])
        assert result.exit_code == 0, result.output
        connector_path = out / "backend" / "app" / "connectors" / "google_workspace_connector.py"
        source = connector_path.read_text()
        try:
            compile(source, str(connector_path), "exec")
        except SyntaxError as e:
            pytest.fail(f"google_workspace_connector.py has syntax error: {e}")

    def test_gws_flags_accepted(self, runner, tmp_path):
        """All --gws-* flags should be accepted."""
        out = tmp_path / "gws-flags"
        result = runner.invoke(main, [
            "gws-flags",
            "--domain", "software-engineering",
            "--framework", "pydanticai",
            "--connector", "google-workspace",
            "--gws-folder-id", "1aBcDeFg",
            "--gws-include-calendar",
            "--gws-include-gmail",
            "--gws-no-revisions",
            "--gws-since", "2026-01-01",
            "--gws-mime-types", "docs,pdf",
            "--gws-max-files", "100",
            "--dry-run",
            "--output-dir", str(out),
        ])
        assert result.exit_code == 0, result.output

    def test_gws_with_linear_connector(self, runner, tmp_path):
        """Google Workspace connector can be combined with Linear."""
        out = tmp_path / "gws-linear"
        result = runner.invoke(main, [
            "gws-linear",
            "--domain", "software-engineering",
            "--framework", "pydanticai",
            "--connector", "google-workspace",
            "--connector", "linear",
            "--output-dir", str(out),
        ])
        assert result.exit_code == 0, result.output
        connectors_dir = out / "backend" / "app" / "connectors"
        assert (connectors_dir / "google_workspace_connector.py").exists()
        assert (connectors_dir / "linear_connector.py").exists()


class TestClaudeCodeConnectorCLI:
    """Tests for --connector claude-code CLI integration."""

    def test_claude_code_connector_dry_run(self, runner, tmp_path):
        """--connector claude-code should appear in dry-run output."""
        out = tmp_path / "cc-dry"
        result = runner.invoke(main, [
            "cc-dry",
            "--domain", "software-engineering",
            "--framework", "pydanticai",
            "--connector", "claude-code",
            "--dry-run",
            "--output-dir", str(out),
        ])
        assert result.exit_code == 0, result.output
        assert "claude-code" in result.output

    def test_claude_code_generates_files(self, runner, tmp_path):
        """--connector claude-code should generate connector files."""
        out = tmp_path / "cc-gen"
        result = runner.invoke(main, [
            "cc-gen",
            "--domain", "software-engineering",
            "--framework", "pydanticai",
            "--connector", "claude-code",
            "--output-dir", str(out),
        ])
        assert result.exit_code == 0, result.output
        assert (out / "backend" / "app" / "connectors" / "claude_code_connector.py").exists()
        assert (out / "backend" / "app" / "connectors" / "__init__.py").exists()
        assert (out / "backend" / "scripts" / "import_data.py").exists()

    def test_claude_code_import_data_includes_connector(self, runner, tmp_path):
        """Generated import_data.py should reference ClaudeCodeConnector."""
        out = tmp_path / "cc-import"
        result = runner.invoke(main, [
            "cc-import",
            "--domain", "software-engineering",
            "--framework", "pydanticai",
            "--connector", "claude-code",
            "--output-dir", str(out),
        ])
        assert result.exit_code == 0, result.output
        import_data = (out / "backend" / "scripts" / "import_data.py").read_text()
        assert "ClaudeCodeConnector" in import_data

    def test_claude_code_scope_flag(self, runner, tmp_path):
        """--claude-code-scope should be accepted."""
        out = tmp_path / "cc-scope"
        result = runner.invoke(main, [
            "cc-scope",
            "--domain", "software-engineering",
            "--framework", "pydanticai",
            "--connector", "claude-code",
            "--claude-code-scope", "all",
            "--dry-run",
            "--output-dir", str(out),
        ])
        assert result.exit_code == 0, result.output

    def test_claude_code_flags(self, runner, tmp_path):
        """All --claude-code-* flags should be accepted."""
        out = tmp_path / "cc-flags"
        result = runner.invoke(main, [
            "cc-flags",
            "--domain", "software-engineering",
            "--framework", "pydanticai",
            "--connector", "claude-code",
            "--claude-code-scope", "all",
            "--claude-code-project", "/Users/will/projects/foo",
            "--claude-code-since", "2026-03-01",
            "--claude-code-max-sessions", "50",
            "--claude-code-content", "full",
            "--dry-run",
            "--output-dir", str(out),
        ])
        assert result.exit_code == 0, result.output

    def test_claude_code_with_other_connector(self, runner, tmp_path):
        """Claude Code connector can be combined with other connectors."""
        out = tmp_path / "cc-multi"
        result = runner.invoke(main, [
            "cc-multi",
            "--domain", "software-engineering",
            "--framework", "pydanticai",
            "--connector", "claude-code",
            "--connector", "linear",
            "--output-dir", str(out),
        ])
        assert result.exit_code == 0, result.output
        connectors_dir = out / "backend" / "app" / "connectors"
        assert (connectors_dir / "claude_code_connector.py").exists()
        assert (connectors_dir / "linear_connector.py").exists()

    def test_claude_code_agent_tools_injected(self, runner, tmp_path):
        """Agent should include session intelligence tools when claude-code is active."""
        out = tmp_path / "cc-tools"
        result = runner.invoke(main, [
            "cc-tools",
            "--domain", "software-engineering",
            "--framework", "claude-agent-sdk",
            "--connector", "claude-code",
            "--output-dir", str(out),
        ])
        assert result.exit_code == 0, result.output
        agent_py = (out / "backend" / "app" / "agent.py").read_text()
        # Should contain session-specific tools
        assert "search_sessions" in agent_py
        assert "decision_history" in agent_py
        assert "file_timeline" in agent_py
        assert "my_preferences" in agent_py

    def test_claude_code_config_settings_fields(self, runner, tmp_path):
        """Generated config.py should have claude_code_* Settings fields."""
        out = tmp_path / "cc-config"
        result = runner.invoke(main, [
            "cc-config",
            "--domain", "software-engineering",
            "--framework", "pydanticai",
            "--connector", "claude-code",
            "--output-dir", str(out),
        ])
        assert result.exit_code == 0, result.output
        config_py = (out / "backend" / "app" / "config.py").read_text()
        assert "claude_code_scope" in config_py
        assert "claude_code_max_sessions" in config_py
        assert "claude_code_content_mode" in config_py
        assert "claude_code_base_path" in config_py

    def test_claude_code_import_data_dict_access(self, runner, tmp_path):
        """Generated import_data.py should use dict access, not attribute access."""
        out = tmp_path / "cc-dict"
        result = runner.invoke(main, [
            "cc-dict",
            "--domain", "software-engineering",
            "--framework", "pydanticai",
            "--connector", "claude-code",
            "--output-dir", str(out),
        ])
        assert result.exit_code == 0, result.output
        import_data = (out / "backend" / "scripts" / "import_data.py").read_text()
        assert 'data["entities"]' in import_data
        assert "data.entities" not in import_data

    def test_claude_code_connector_entity_types(self, runner, tmp_path):
        """Generated connector should extract all entity types including Decision/Preference."""
        out = tmp_path / "cc-entities"
        result = runner.invoke(main, [
            "cc-entities",
            "--domain", "software-engineering",
            "--framework", "pydanticai",
            "--connector", "claude-code",
            "--output-dir", str(out),
        ])
        assert result.exit_code == 0, result.output
        connector = (out / "backend" / "app" / "connectors" / "claude_code_connector.py").read_text()
        for entity in ["GitBranch", "Error", "Decision", "Preference", "Alternative"]:
            assert entity in connector, f"Missing entity type: {entity}"
        for rel in ["ON_BRANCH", "ENCOUNTERED_ERROR", "MADE_DECISION", "CHOSE", "REJECTED",
                     "NEXT", "PRECEDED_BY", "USED_TOOL", "EXPRESSES_PREFERENCE"]:
            assert rel in connector, f"Missing relationship type: {rel}"

    def test_claude_code_connector_has_redaction(self, runner, tmp_path):
        """Generated connector should include secret redaction."""
        out = tmp_path / "cc-redact"
        result = runner.invoke(main, [
            "cc-redact",
            "--domain", "software-engineering",
            "--framework", "pydanticai",
            "--connector", "claude-code",
            "--output-dir", str(out),
        ])
        assert result.exit_code == 0, result.output
        connector = (out / "backend" / "app" / "connectors" / "claude_code_connector.py").read_text()
        assert "REDACTED" in connector
        assert "_SECRET_PATTERNS" in connector

    def test_claude_code_scenarios_override(self, runner, tmp_path):
        """Claude Code connector should replace generic SE scenarios with session-specific ones."""
        out = tmp_path / "cc-scenarios"
        result = runner.invoke(main, [
            "cc-scenarios",
            "--domain", "software-engineering",
            "--framework", "pydanticai",
            "--connector", "claude-code",
            "--output-dir", str(out),
        ])
        assert result.exit_code == 0, result.output
        frontend_config = (out / "frontend" / "lib" / "config.ts").read_text()
        assert "Session Intelligence" in frontend_config
        assert "pull requests" not in frontend_config.lower()

    def test_with_mcp_flag(self, runner, tmp_path):
        """Verify --with-mcp generates MCP config files."""
        out = tmp_path / "my-app"
        result = runner.invoke(main, [
            "my-app",
            "--domain", "financial-services",
            "--framework", "pydanticai",
            "--with-mcp",
            "--output-dir", str(out),
        ])
        assert result.exit_code == 0, result.output
        assert (out / "mcp" / "claude_desktop_config.json").exists()
        assert (out / "mcp" / "README.md").exists()
        makefile = (out / "Makefile").read_text()
        assert "mcp-server" in makefile

    def test_session_strategy_flag(self, runner, tmp_path):
        """Verify --session-strategy flows through to generated config."""
        out = tmp_path / "my-app"
        result = runner.invoke(main, [
            "my-app",
            "--domain", "healthcare",
            "--framework", "pydanticai",
            "--session-strategy", "persistent",
            "--output-dir", str(out),
        ])
        assert result.exit_code == 0, result.output
        config = (out / "backend" / "app" / "config.py").read_text()
        assert "persistent" in config

    def test_no_auto_extract_flag(self, runner, tmp_path):
        """Verify --no-auto-extract disables entity extraction."""
        out = tmp_path / "my-app"
        result = runner.invoke(main, [
            "my-app",
            "--domain", "healthcare",
            "--framework", "pydanticai",
            "--no-auto-extract",
            "--output-dir", str(out),
        ])
        assert result.exit_code == 0, result.output
        memory = (out / "backend" / "app" / "memory.py").read_text()
        assert "auto_extract=false" in memory.lower() or "auto_extract=False" in memory


    def test_mcp_profile_core_flag(self, runner, tmp_path):
        """Verify --mcp-profile core sets core profile."""
        out = tmp_path / "my-app"
        result = runner.invoke(main, [
            "my-app",
            "--domain", "financial-services",
            "--framework", "pydanticai",
            "--with-mcp",
            "--mcp-profile", "core",
            "--output-dir", str(out),
        ])
        assert result.exit_code == 0, result.output
        mcp_config = (out / "mcp" / "claude_desktop_config.json").read_text()
        assert "core" in mcp_config

    def test_dry_run_shows_memory_config(self, runner, tmp_path):
        """Verify --dry-run shows memory configuration."""
        result = runner.invoke(main, [
            "my-app",
            "--domain", "healthcare",
            "--framework", "pydanticai",
            "--session-strategy", "per_day",
            "--with-mcp",
            "--dry-run",
        ])
        assert result.exit_code == 0, result.output
        assert "per_day" in result.output
        assert "MCP" in result.output


class TestLocalFileConnectorCLI:
    """Tests for --connector local-file CLI integration."""

    def test_requires_path(self, runner, tmp_path):
        """--connector local-file without --local-file-path should error."""
        out = tmp_path / "lf-nopath"
        result = runner.invoke(main, [
            "lf-nopath",
            "--domain", "software-engineering",
            "--framework", "pydanticai",
            "--connector", "local-file",
            "--dry-run",
            "--output-dir", str(out),
        ])
        assert result.exit_code != 0
        assert "local-file-path" in result.output

    def test_dry_run_with_path(self, runner, tmp_path):
        """--connector local-file with --local-file-path should succeed in dry-run."""
        docs = tmp_path / "docs"
        docs.mkdir()
        out = tmp_path / "lf-dry"
        result = runner.invoke(main, [
            "lf-dry",
            "--domain", "software-engineering",
            "--framework", "pydanticai",
            "--connector", "local-file",
            "--local-file-path", str(docs),
            "--dry-run",
            "--output-dir", str(out),
        ])
        assert result.exit_code == 0, result.output
        assert "local-file" in result.output

    def test_generates_connector_file(self, runner, tmp_path):
        """--connector local-file should generate the template into the project."""
        docs = tmp_path / "docs"
        docs.mkdir()
        out = tmp_path / "lf-gen"
        result = runner.invoke(main, [
            "lf-gen",
            "--domain", "software-engineering",
            "--framework", "pydanticai",
            "--connector", "local-file",
            "--local-file-path", str(docs),
            "--output-dir", str(out),
        ])
        assert result.exit_code == 0, result.output
        target = out / "backend" / "app" / "connectors" / "local_file_connector.py"
        assert target.exists()
        # The generated file must be valid Python.
        import ast
        ast.parse(target.read_text())

    def test_multiple_paths_and_exclude(self, runner, tmp_path):
        """All --local-file-* flags should be accepted."""
        a = tmp_path / "a"
        b = tmp_path / "b"
        a.mkdir()
        b.mkdir()
        out = tmp_path / "lf-multi"
        result = runner.invoke(main, [
            "lf-multi",
            "--domain", "software-engineering",
            "--framework", "pydanticai",
            "--connector", "local-file",
            "--local-file-path", str(a),
            "--local-file-path", str(b),
            "--local-file-pattern", "**/*.md",
            "--local-file-no-recursive",
            "--local-file-follow-links",
            "--local-file-exclude", "**/node_modules/**",
            "--dry-run",
            "--output-dir", str(out),
        ])
        assert result.exit_code == 0, result.output
