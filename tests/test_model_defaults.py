"""Model identifiers are dependencies with retirement dates.

Every model literal in the CLI and the generated templates must resolve through
``create_context_graph.constants`` so a provider retirement is a one-line fix,
and nothing rendered may reference an id a provider has retired.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from create_context_graph import constants
from create_context_graph.config import ProjectConfig, SUPPORTED_FRAMEWORKS
from create_context_graph.ontology import load_domain
from create_context_graph.renderer import ProjectRenderer

SRC = Path(__file__).resolve().parent.parent / "src" / "create_context_graph"
SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"


def _render(tmp_path: Path, framework: str, **kwargs) -> Path:
    cfg = ProjectConfig(
        project_name=f"Model Defaults {framework}",
        domain="healthcare",
        framework=framework,
        memory_backend="bolt",
        **kwargs,
    )
    out = tmp_path / framework
    out.mkdir(parents=True)
    ProjectRenderer(cfg, load_domain(cfg.domain)).render(out)
    return out


class TestConstants:
    def test_defaults_are_not_retired(self):
        for value in constants.MODEL_DEFAULTS.values():
            for retired in constants.RETIRED_MODEL_IDS:
                assert retired not in value, f"{value} references retired id {retired}"

    def test_retired_ids_absent_from_source_and_templates(self):
        """No template, connector, or CLI module may hard-code a retired id."""
        offenders: list[str] = []
        for path in list(SRC.rglob("*.py")) + list(SRC.rglob("*.j2")) + list(SCRIPTS.rglob("*.py")):
            if path.name == "constants.py":
                continue
            text = path.read_text(errors="ignore")
            for retired in constants.RETIRED_MODEL_IDS:
                if retired in text:
                    offenders.append(f"{path.relative_to(SRC.parent.parent)}: {retired}")
        assert not offenders, "\n".join(offenders)


class TestGeneratedSettings:
    @pytest.mark.parametrize("framework", SUPPORTED_FRAMEWORKS)
    def test_agent_reads_model_from_settings(self, tmp_path, framework):
        out = _render(tmp_path, framework)
        agent = (out / "backend" / "app" / "agent.py").read_text()
        config = (out / "backend" / "app" / "config.py").read_text()
        assert f'anthropic_model: str = "{constants.DEFAULT_ANTHROPIC_MODEL}"' in config
        assert f'openai_model: str = "{constants.DEFAULT_OPENAI_AGENT_MODEL}"' in config
        assert f'gemini_model: str = "{constants.DEFAULT_GEMINI_MODEL}"' in config
        # No literal model id in any agent template — they must read settings.
        assert not re.search(r"claude-(sonnet|opus|haiku)-[0-9]", agent), framework
        assert "gemini-" not in agent, framework
        if framework == "google-adk":
            assert "settings.gemini_model" in agent
        elif framework == "openai-agents":
            assert "settings.openai_model" in agent
        else:
            assert "settings.anthropic_model" in agent

    def test_env_example_documents_overrides(self, tmp_path):
        out = _render(tmp_path, "pydanticai")
        env_example = (out / ".env.example").read_text()
        assert f"# ANTHROPIC_MODEL={constants.DEFAULT_ANTHROPIC_MODEL}" in env_example
        assert f"# OPENAI_MODEL={constants.DEFAULT_OPENAI_AGENT_MODEL}" in env_example
        assert f"# GEMINI_MODEL={constants.DEFAULT_GEMINI_MODEL}" in env_example
        for retired in constants.RETIRED_MODEL_IDS:
            assert retired not in env_example

    def test_crewai_env_disables_telemetry(self, tmp_path):
        out = _render(tmp_path, "crewai")
        env = (out / ".env").read_text()
        assert "CREWAI_DISABLE_TELEMETRY=true" in env
        other = _render(tmp_path / "other", "pydanticai")
        assert "CREWAI_DISABLE_TELEMETRY" not in (other / ".env").read_text()
