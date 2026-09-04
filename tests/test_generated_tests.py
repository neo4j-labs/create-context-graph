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

"""Tests that scaffold projects and execute their generated test suites.

These tests verify that the generated test_routes.py files are
discoverable by pytest, importable, and pass when executed in an
isolated virtual environment with dependencies installed.
"""

from __future__ import annotations

import os
import subprocess

import pytest

from create_context_graph.config import ProjectConfig
from create_context_graph.ontology import load_domain
from create_context_graph.renderer import ProjectRenderer


def _scaffold_project(
    tmp_path, domain="financial-services", framework="pydanticai", memory_backend="nams"
):
    """Scaffold a project and return the output directory."""
    config = ProjectConfig(
        project_name="Generated Test App",
        domain=domain,
        framework=framework,
        memory_backend=memory_backend,
        neo4j_uri="neo4j://localhost:7687",
        neo4j_username="neo4j",
        neo4j_password="testpass123",
        neo4j_type="docker",
    )
    ontology = load_domain(config.domain)
    out = tmp_path / "test-project"
    renderer = ProjectRenderer(config, ontology)
    renderer.render(out)
    return out


@pytest.mark.slow
class TestGeneratedTestCollection:
    """Verify generated tests are discoverable by pytest."""

    def test_generated_tests_discoverable(self, tmp_path):
        """Scaffold a project and verify pytest can collect the generated tests."""
        project_dir = _scaffold_project(tmp_path, domain="financial-services", framework="pydanticai")
        backend_dir = project_dir / "backend"

        # Create a venv and install dependencies so imports resolve
        venv_dir = tmp_path / "venv"
        result = subprocess.run(
            ["uv", "venv", str(venv_dir)],
            capture_output=True,
            text=True,
            timeout=60,
        )
        assert result.returncode == 0, (
            f"venv creation failed:\nstdout: {result.stdout}\nstderr: {result.stderr}"
        )

        env = {
            **os.environ,
            "VIRTUAL_ENV": str(venv_dir),
            "PATH": f"{venv_dir}/bin:{os.environ['PATH']}",
        }

        # Install the backend package
        result = subprocess.run(
            ["uv", "pip", "install", "-e", "."],
            cwd=str(backend_dir),
            env=env,
            capture_output=True,
            text=True,
            timeout=120,
        )
        assert result.returncode == 0, (
            f"pip install failed:\nstdout: {result.stdout}\nstderr: {result.stderr}"
        )

        # Install pytest into the isolated venv (needed to run generated tests)
        result = subprocess.run(
            ["uv", "pip", "install", "pytest"],
            env=env,
            capture_output=True,
            text=True,
            timeout=120,
        )
        assert result.returncode == 0, (
            f"pytest install failed:\nstdout: {result.stdout}\nstderr: {result.stderr}"
        )

        # Collect tests without running them
        result = subprocess.run(
            [str(venv_dir / "bin" / "python"), "-m", "pytest", "--collect-only", "tests/"],
            cwd=str(backend_dir),
            env=env,
            capture_output=True,
            text=True,
            timeout=60,
        )
        assert result.returncode == 0, (
            f"pytest --collect-only failed (exit {result.returncode}):\n"
            f"stdout: {result.stdout}\nstderr: {result.stderr}"
        )
        assert "test_health" in result.stdout, (
            f"test_health not found in collected tests:\n{result.stdout}"
        )
        assert "test_scenarios" in result.stdout, (
            f"test_scenarios not found in collected tests:\n{result.stdout}"
        )


@pytest.mark.slow
class TestGeneratedTestExecution:
    """Scaffold projects, install deps, and run the generated test suites."""

    @pytest.mark.parametrize(
        ("framework", "memory_backend"),
        [
            ("pydanticai", "nams"),
            ("claude-agent-sdk", "nams"),
            ("langgraph", "nams"),
            ("anthropic-tools", "nams"),
            # One bolt scaffold so the self-hosted branch of the generated
            # test file (memory_error surfacing in /health) executes for real.
            ("pydanticai", "bolt"),
        ],
    )
    def test_generated_tests_pass(self, tmp_path, framework, memory_backend):
        """Scaffold a project, install deps, and verify generated tests pass."""
        project_dir = _scaffold_project(
            tmp_path,
            domain="financial-services",
            framework=framework,
            memory_backend=memory_backend,
        )
        backend_dir = project_dir / "backend"

        # Create an isolated venv
        venv_dir = tmp_path / "venv"
        result = subprocess.run(
            ["uv", "venv", str(venv_dir)],
            capture_output=True,
            text=True,
            timeout=60,
        )
        assert result.returncode == 0, (
            f"venv creation failed for {framework}:\n"
            f"stdout: {result.stdout}\nstderr: {result.stderr}"
        )

        env = {
            **os.environ,
            "VIRTUAL_ENV": str(venv_dir),
            "PATH": f"{venv_dir}/bin:{os.environ['PATH']}",
        }

        # Install the backend package with all dependencies
        result = subprocess.run(
            ["uv", "pip", "install", "-e", "."],
            cwd=str(backend_dir),
            env=env,
            capture_output=True,
            text=True,
            timeout=120,
        )
        assert result.returncode == 0, (
            f"pip install failed for {framework}:\n"
            f"stdout: {result.stdout}\nstderr: {result.stderr}"
        )

        # Install pytest into the isolated venv (needed to run generated tests)
        result = subprocess.run(
            ["uv", "pip", "install", "pytest"],
            env=env,
            capture_output=True,
            text=True,
            timeout=120,
        )
        assert result.returncode == 0, (
            f"pytest install failed:\nstdout: {result.stdout}\nstderr: {result.stderr}"
        )

        # Run the generated tests
        result = subprocess.run(
            [str(venv_dir / "bin" / "python"), "-m", "pytest", "tests/", "-v"],
            cwd=str(backend_dir),
            env=env,
            capture_output=True,
            text=True,
            timeout=60,
        )
        assert result.returncode == 0, (
            f"Generated tests FAILED for {framework} (exit {result.returncode}):\n"
            f"--- stdout ---\n{result.stdout}\n"
            f"--- stderr ---\n{result.stderr}"
        )
        # Verify both tests actually ran
        assert "test_health" in result.stdout, (
            f"test_health did not appear in test output for {framework}:\n{result.stdout}"
        )
        assert "test_scenarios" in result.stdout, (
            f"test_scenarios did not appear in test output for {framework}:\n{result.stdout}"
        )
        # Backend-specific health tests (v0.14.0) must have run too
        expected_health_test = (
            "test_health_degrades_when_nams_client_missing"
            if memory_backend == "nams"
            else "test_health_surfaces_live_memory_write_failures"
        )
        assert expected_health_test in result.stdout, (
            f"{expected_health_test} did not run for {framework}/{memory_backend}:\n"
            f"{result.stdout}"
        )
