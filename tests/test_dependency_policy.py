"""Pins the generated-project dependency policy (DEPENDENCY_UPGRADE_PLAN.md §6).

Generated projects are installed fresh and unlocked on an arbitrary day, so
every dependency they declare needs a verified floor and an upper bound, and
the memory-layer extras must not force resolver backtracks.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from create_context_graph.config import FRAMEWORK_DEPENDENCIES, ProjectConfig, SUPPORTED_FRAMEWORKS
from create_context_graph.ontology import load_domain
from create_context_graph.renderer import ProjectRenderer


def _render(tmp_path: Path, framework: str, **kwargs) -> Path:
    cfg = ProjectConfig(project_name=f"Policy {framework}", domain="healthcare", framework=framework, **kwargs)
    out = tmp_path / f"{framework}-{kwargs.get('memory_backend', 'nams')}-{int(bool(kwargs.get('with_mcp')))}"
    out.mkdir(parents=True)
    ProjectRenderer(cfg, load_domain(cfg.domain)).render(out)
    return out


def _pyproject(out: Path) -> str:
    return (out / "backend" / "pyproject.toml").read_text()


class TestFrameworkDependencySpecs:
    @pytest.mark.parametrize("framework", SUPPORTED_FRAMEWORKS)
    def test_every_framework_dep_has_floor_and_cap(self, framework):
        for dep in FRAMEWORK_DEPENDENCIES[framework]:
            assert ">=" in dep, dep
            assert "<" in dep, f"{dep} has no upper bound"

    def test_dead_dependencies_are_gone(self):
        all_deps = " ".join(d for deps in FRAMEWORK_DEPENDENCIES.values() for d in deps)
        assert "claude-agent-sdk" not in all_deps  # never imported by the template
        assert "nest-asyncio" not in all_deps  # archived; ADK awaits async tools natively
        assert "pydantic-ai>=" not in all_deps  # meta-package drags openai>=3 + 76 dists
        assert "pydantic-ai-slim[anthropic]" in all_deps
        assert "langchain>=" in all_deps  # create_agent lives in `langchain`


class TestMemoryExtras:
    @pytest.mark.parametrize("framework", ["pydanticai", "openai-agents"])
    def test_native_sdk_frameworks_skip_litellm(self, tmp_path, framework):
        pkg = _pyproject(_render(tmp_path, framework, nams_api_key="k"))
        assert "neo4j-agent-memory[nams]>=0.5.0,<0.6.0" in pkg
        assert not re.search(r'^\s*"litellm', pkg, re.M), "litellm must not be a dependency"

    @pytest.mark.parametrize("framework", ["strands", "crewai", "google-adk", "langgraph", "anthropic-tools", "claude-agent-sdk"])
    def test_other_frameworks_keep_litellm_with_security_floor(self, tmp_path, framework):
        pkg = _pyproject(_render(tmp_path, framework, nams_api_key="k"))
        assert "neo4j-agent-memory[nams,litellm]>=0.5.0,<0.6.0" in pkg
        assert '"litellm>=1.84.0,<2"' in pkg

    def test_mcp_adds_cli_and_mcp_extras(self, tmp_path):
        pkg = _pyproject(_render(tmp_path, "strands", nams_api_key="k", with_mcp=True))
        assert "neo4j-agent-memory[nams,litellm,cli,mcp]" in pkg

    def test_mcp_extras_skipped_on_pydanticai(self, tmp_path):
        """fastmcp<3 pins mcp<2, which conflicts with pydantic-ai-slim's mcp 2.x."""
        pkg = _pyproject(_render(tmp_path, "pydanticai", nams_api_key="k", with_mcp=True))
        assert "mcp" not in pkg.split("neo4j-agent-memory")[1].split('"')[0]


class TestBoltExtras:
    def test_bolt_uses_cpu_torch_index_and_locked_spacy_model(self, tmp_path):
        pkg = _pyproject(_render(tmp_path, "strands", memory_backend="bolt"))
        assert "neo4j-agent-memory[litellm,sentence-transformers,extraction,fuzzy]>=0.5.0,<0.6.0" in pkg
        assert 'url = "https://download.pytorch.org/whl/cpu"' in pkg
        assert "sys_platform == 'linux'" in pkg
        assert "en-core-web-sm @ https://github.com/explosion/spacy-models/releases/download/en_core_web_sm-3.8.0/" in pkg

    def test_nams_has_no_torch_index_or_spacy_model(self, tmp_path):
        pkg = _pyproject(_render(tmp_path, "strands", nams_api_key="k"))
        assert "pytorch-cpu" not in pkg
        assert "en-core-web-sm" not in pkg
        assert "sentence-transformers" not in pkg


class TestBackendFloorsAndCaps:
    def test_core_web_stack_specs(self, tmp_path):
        pkg = _pyproject(_render(tmp_path, "pydanticai", nams_api_key="k"))
        for spec in (
            '"fastapi>=0.137"',
            '"starlette>=1.3.1"',
            '"uvicorn[standard]>=0.50"',
            '"pydantic>=2.12,<3"',
            '"pydantic-settings>=2.14.2,<3"',
            '"python-dotenv>=1.1"',
            '"neo4j>=6.1,<7"',
            '"httpx2>=2.7"',
            '"pytest>=9.0.3,<10"',
        ):
            assert spec in pkg, spec
        assert 'requires = ["hatchling>=1.27,<2"]' in pkg

    def test_local_file_connector_declares_parsers(self, tmp_path):
        cfg = ProjectConfig(
            project_name="LF", domain="healthcare", framework="pydanticai",
            memory_backend="bolt", saas_connectors=["local-file"],
        )
        out = tmp_path / "lf"
        out.mkdir()
        ProjectRenderer(cfg, load_domain(cfg.domain)).render(out)
        pkg = _pyproject(out)
        assert '"markdown-it-py>=4.0,<5"' in pkg
        assert '"mdit-py-plugins>=0.5,<1"' in pkg

    def test_connector_floors_have_caps(self, tmp_path):
        cfg = ProjectConfig(
            project_name="Conn", domain="healthcare", framework="pydanticai",
            nams_api_key="k", saas_connectors=["github", "notion", "jira", "slack", "salesforce", "gmail"],
        )
        out = tmp_path / "conn"
        out.mkdir()
        ProjectRenderer(cfg, load_domain(cfg.domain)).render(out)
        pkg = _pyproject(out)
        for name in ("PyGithub", "notion-client", "atlassian-python-api", "slack-sdk", "simple-salesforce", "google-api-python-client", "google-auth-oauthlib"):
            match = re.search(rf'"{re.escape(name)}>=([^"]+)"', pkg)
            assert match, name
            assert "<" in match.group(1), f"{name} spec {match.group(1)} has no cap"


class TestGdsProjections:
    def test_no_native_projection_calls(self, tmp_path):
        """Native gds.graph.project(name, labels, rels) is slated for deprecation."""
        out = _render(tmp_path, "pydanticai", memory_backend="bolt")
        gds = (out / "backend" / "app" / "gds_client.py").read_text()
        cypher = (out / "cypher" / "gds_projections.cypher").read_text()
        # Native form: gds.graph.project('name', 'Label'|'*', '*') — a quoted label
        # as the second argument. The Cypher-projection aggregation passes nodes.
        assert not re.search(r"gds\.graph\.project\('[^']*',\s*'", gds)
        assert not re.search(r"gds\.graph\.project\(\s*\n\s*'", cypher)
        assert "WITH gds.graph.project(" in gds and "WITH gds.graph.project(" in cypher


class TestToolchainPins:
    def test_google_adk_no_longer_needs_asyncio_loop_override(self, tmp_path):
        out = _render(tmp_path, "google-adk", nams_api_key="k")
        makefile = (out / "Makefile").read_text()
        dockerfile = (out / "Dockerfile.backend").read_text()
        assert "--loop asyncio" not in makefile
        assert "--loop asyncio" not in dockerfile

    def test_sync_frameworks_keep_asyncio_loop_override(self, tmp_path):
        out = _render(tmp_path, "strands", nams_api_key="k")
        assert "--loop asyncio" in (out / "Makefile").read_text()
