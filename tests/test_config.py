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

"""Unit tests for the config module."""


from create_context_graph.config import (
    FRAMEWORK_DEPENDENCIES,
    FRAMEWORK_DISPLAY_NAMES,
    SUPPORTED_FRAMEWORKS,
    ProjectConfig,
)


class TestProjectConfig:
    def test_basic_creation(self):
        config = ProjectConfig(
            project_name="My App",
            domain="healthcare",
            framework="pydanticai",
        )
        assert config.project_name == "My App"
        assert config.domain == "healthcare"
        assert config.framework == "pydanticai"

    def test_project_slug_from_name(self):
        config = ProjectConfig(
            project_name="My Cool App",
            domain="healthcare",
            framework="pydanticai",
        )
        assert config.project_slug == "my-cool-app"

    def test_project_slug_special_chars(self):
        config = ProjectConfig(
            project_name="Test App!@# 123",
            domain="healthcare",
            framework="pydanticai",
        )
        assert config.project_slug == "test-app-123"

    def test_project_slug_leading_trailing(self):
        config = ProjectConfig(
            project_name="  --My App--  ",
            domain="healthcare",
            framework="pydanticai",
        )
        assert config.project_slug == "my-app"

    def test_defaults(self):
        config = ProjectConfig(
            project_name="Test",
            domain="healthcare",
            framework="pydanticai",
        )
        assert config.neo4j_uri == "neo4j://localhost:7687"
        assert config.neo4j_username == "neo4j"
        assert config.neo4j_password == "password"
        assert config.neo4j_type == "docker"
        assert config.data_source == "demo"
        assert config.generate_data is False
        assert config.anthropic_api_key is None
        assert config.openai_api_key is None
        assert config.google_api_key is None

    def test_framework_display_name(self):
        config = ProjectConfig(
            project_name="Test",
            domain="healthcare",
            framework="claude-agent-sdk",
        )
        assert config.framework_display_name == "Claude Agent SDK"

    def test_framework_deps(self):
        config = ProjectConfig(
            project_name="Test",
            domain="healthcare",
            framework="pydanticai",
        )
        assert len(config.framework_deps) > 0
        assert any("pydantic-ai" in dep for dep in config.framework_deps)

    def test_all_frameworks_have_display_names(self):
        for fw in SUPPORTED_FRAMEWORKS:
            assert fw in FRAMEWORK_DISPLAY_NAMES

    def test_all_frameworks_have_deps(self):
        for fw in SUPPORTED_FRAMEWORKS:
            assert fw in FRAMEWORK_DEPENDENCIES

    def test_crewai_includes_anthropic_extra(self):
        """crewai agent template uses anthropic LLM, so the extra is required."""
        deps = FRAMEWORK_DEPENDENCIES["crewai"]
        assert any("anthropic" in dep for dep in deps)

    def test_existing_neo4j_config(self):
        config = ProjectConfig(
            project_name="Test",
            domain="healthcare",
            framework="pydanticai",
            neo4j_type="existing",
            neo4j_uri="neo4j+s://abc.databases.neo4j.io",
        )
        assert config.neo4j_type == "existing"
        assert "neo4j+s" in config.neo4j_uri

    def test_aura_neo4j_config(self):
        config = ProjectConfig(
            project_name="Test",
            domain="healthcare",
            framework="pydanticai",
            neo4j_type="aura",
            neo4j_uri="neo4j+s://abc.databases.neo4j.io",
        )
        assert config.neo4j_type == "aura"

    def test_local_neo4j_config(self):
        config = ProjectConfig(
            project_name="Test",
            domain="healthcare",
            framework="pydanticai",
            neo4j_type="local",
        )
        assert config.neo4j_type == "local"


class TestFrameworkAliasRemoval:
    """The 'maf' alias was removed; verify the surface is clean."""

    def test_anthropic_tools_in_supported(self):
        assert "anthropic-tools" in SUPPORTED_FRAMEWORKS

    def test_maf_not_in_supported(self):
        assert "maf" not in SUPPORTED_FRAMEWORKS

    def test_no_framework_aliases_export(self):
        # Importing FRAMEWORK_ALIASES used to work; the attribute is now gone.
        import create_context_graph.config as cfg
        assert not hasattr(cfg, "FRAMEWORK_ALIASES")

    def test_no_resolved_framework_property(self):
        config = ProjectConfig(
            project_name="Test",
            domain="healthcare",
            framework="anthropic-tools",
        )
        assert not hasattr(config, "resolved_framework")

    def test_maf_framework_rejected_by_validation(self):
        # ProjectConfig accepts arbitrary strings, but rendering blows up.
        # The wizard / Click choice will reject 'maf' before it gets here.
        config = ProjectConfig(
            project_name="Test",
            domain="healthcare",
            framework="maf",
        )
        # No alias resolution — display name falls back to the raw key.
        assert config.framework_display_name == "maf"
        # No dependencies registered for 'maf'.
        assert config.framework_deps == []


class TestGoogleApiKey:
    def test_google_api_key_default_none(self):
        config = ProjectConfig(
            project_name="Test",
            domain="healthcare",
            framework="pydanticai",
        )
        assert config.google_api_key is None

    def test_google_api_key_set(self):
        config = ProjectConfig(
            project_name="Test",
            domain="real-estate",
            framework="google-adk",
            google_api_key="test-key-123",
        )
        assert config.google_api_key == "test-key-123"

    def test_memory_defaults(self):
        """Verify default values for memory enhancement fields."""
        config = ProjectConfig(
            project_name="Test",
            domain="healthcare",
            framework="pydanticai",
        )
        assert config.with_mcp is False
        assert config.mcp_profile == "extended"
        assert config.session_strategy == "per_conversation"
        assert config.auto_extract is True
        assert config.auto_preferences is True

    def test_mcp_config(self):
        """Verify MCP fields can be set."""
        config = ProjectConfig(
            project_name="Test",
            domain="healthcare",
            framework="pydanticai",
            with_mcp=True,
            mcp_profile="core",
        )
        assert config.with_mcp is True
        assert config.mcp_profile == "core"

    def test_session_strategy_values(self):
        """Verify all session strategy values are accepted."""
        for strategy in ["per_conversation", "per_day", "persistent"]:
            config = ProjectConfig(
                project_name="Test",
                domain="healthcare",
                framework="pydanticai",
                session_strategy=strategy,
            )
            assert config.session_strategy == strategy

    def test_auto_extract_disabled(self):
        """Verify auto_extract and auto_preferences can be disabled."""
        config = ProjectConfig(
            project_name="Test",
            domain="healthcare",
            framework="pydanticai",
            auto_extract=False,
            auto_preferences=False,
        )
        assert config.auto_extract is False
        assert config.auto_preferences is False
