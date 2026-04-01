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

"""Jinja2 template engine for project scaffolding."""

from __future__ import annotations

import re
import shutil
from importlib.resources import files
from pathlib import Path

from jinja2 import Environment, PackageLoader

from create_context_graph.config import ProjectConfig
from create_context_graph.ontology import (
    DomainOntology,
    generate_cypher_schema,
    generate_pydantic_models,
    generate_visualization_config,
)


# ---------------------------------------------------------------------------
# Custom Jinja2 filters
# ---------------------------------------------------------------------------


def _to_snake_case(value: str) -> str:
    s = re.sub(r"[\s\-]+", "_", value)
    s = re.sub(r"([A-Z]+)([A-Z][a-z])", r"\1_\2", s)
    s = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", s)
    return s.lower()


def _to_camel_case(value: str) -> str:
    parts = re.split(r"[\s_\-]+", value)
    return parts[0].lower() + "".join(p.title() for p in parts[1:])


def _to_pascal_case(value: str) -> str:
    parts = re.split(r"[\s_\-]+", value)
    return "".join(p.title() for p in parts)


def _to_kebab_case(value: str) -> str:
    return _to_snake_case(value).replace("_", "-")


# ---------------------------------------------------------------------------
# Renderer
# ---------------------------------------------------------------------------


class ProjectRenderer:
    """Renders Jinja2 templates to produce a scaffolded project directory."""

    def __init__(self, config: ProjectConfig, ontology: DomainOntology):
        self.config = config
        self.ontology = ontology
        self.env = Environment(
            loader=PackageLoader("create_context_graph", "templates"),
            keep_trailing_newline=True,
            trim_blocks=True,
            lstrip_blocks=True,
        )
        # Register custom filters
        self.env.filters["snake_case"] = _to_snake_case
        self.env.filters["camel_case"] = _to_camel_case
        self.env.filters["pascal_case"] = _to_pascal_case
        self.env.filters["kebab_case"] = _to_kebab_case

    def _context(self) -> dict:
        """Build the template context dictionary."""
        # Partition entity types into base POLE+O and domain-specific
        base_labels = {"Person", "Organization", "Location", "Event", "Object"}
        all_entity_types = [et.model_dump() for et in self.ontology.entity_types]
        base_entity_types = [et for et in all_entity_types if et["label"] in base_labels]
        domain_entity_types = [et for et in all_entity_types if et["label"] not in base_labels]

        return {
            "project": self.config.model_dump(),
            "project_name": self.config.project_name,
            "project_slug": self.config.project_slug,
            "domain": self.ontology.domain.model_dump(),
            "ontology": self.ontology.model_dump(),
            "entity_types": all_entity_types,
            "base_entity_types": base_entity_types,
            "domain_entity_types": domain_entity_types,
            "relationships": [r.model_dump() for r in self.ontology.relationships],
            "demo_scenarios": [s.model_dump() for s in self.ontology.demo_scenarios],
            "agent_tools": [t.model_dump() for t in self.ontology.agent_tools],
            "framework": self.config.resolved_framework,
            "framework_display_name": self.config.framework_display_name,
            "framework_deps": self.config.framework_deps,
            "neo4j_uri": self.config.neo4j_uri,
            "neo4j_username": self.config.neo4j_username,
            "neo4j_password": self.config.neo4j_password,
            "neo4j_type": self.config.neo4j_type,
            "anthropic_api_key": self.config.anthropic_api_key or "",
            "openai_api_key": self.config.openai_api_key or "",
            "google_api_key": self.config.google_api_key or "",
            "system_prompt": self.ontology.system_prompt,
            "cypher_schema": generate_cypher_schema(self.ontology),
            "pydantic_models": generate_pydantic_models(self.ontology),
            "visualization": generate_visualization_config(self.ontology),
            "saas_connectors": self.config.saas_connectors,
        }

    def _render_template(self, template_name: str, output_path: Path, ctx: dict) -> None:
        """Render a single template to the output path."""
        template = self.env.get_template(template_name)
        content = template.render(**ctx)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(content)

    def render(self, output_dir: Path) -> None:
        """Render the complete project to output_dir."""
        output_dir.mkdir(parents=True, exist_ok=True)
        ctx = self._context()

        self._render_base(output_dir, ctx)
        self._render_backend(output_dir / "backend", ctx)
        self._render_frontend(output_dir / "frontend", ctx)
        self._render_cypher(output_dir / "cypher", ctx)
        self._render_data(output_dir / "data", ctx)

    def _render_base(self, output_dir: Path, ctx: dict) -> None:
        """Render root-level project files."""
        base_templates = {
            "base/dot_env.j2": ".env",
            "base/dot_env_example.j2": ".env.example",
            "base/Makefile.j2": "Makefile",
            "base/README.md.j2": "README.md",
            "base/gitignore.j2": ".gitignore",
        }
        for template_name, output_name in base_templates.items():
            self._render_template(template_name, output_dir / output_name, ctx)

        # Docker compose only if docker selected
        if self.config.neo4j_type == "docker":
            self._render_template(
                "base/docker-compose.yml.j2",
                output_dir / "docker-compose.yml",
                ctx,
            )

        # Deployment templates (always generated)
        self._render_template(
            "base/Dockerfile.backend.j2",
            output_dir / "Dockerfile.backend",
            ctx,
        )
        self._render_template(
            "base/Dockerfile.frontend.j2",
            output_dir / "Dockerfile.frontend",
            ctx,
        )
        self._render_template(
            "base/docker-compose.prod.yml.j2",
            output_dir / "docker-compose.prod.yml",
            ctx,
        )
        self._render_template(
            "base/dockerignore.j2",
            output_dir / ".dockerignore",
            ctx,
        )

    def _render_backend(self, backend_dir: Path, ctx: dict) -> None:
        """Render the FastAPI backend."""
        shared_templates = {
            "backend/shared/main.py.j2": "app/main.py",
            "backend/shared/config.py.j2": "app/config.py",
            "backend/shared/context_graph_client.py.j2": "app/context_graph_client.py",
            "backend/shared/constants.py.j2": "app/constants.py",
            "backend/shared/gds_client.py.j2": "app/gds_client.py",
            "backend/shared/vector_client.py.j2": "app/vector_client.py",
            "backend/shared/models.py.j2": "app/models.py",
            "backend/shared/routes.py.j2": "app/routes.py",
            "backend/shared/pyproject.toml.j2": "pyproject.toml",
        }
        for template_name, output_name in shared_templates.items():
            self._render_template(template_name, backend_dir / output_name, ctx)

        # __init__.py for app package
        (backend_dir / "app").mkdir(parents=True, exist_ok=True)
        (backend_dir / "app" / "__init__.py").write_text("")

        # Framework-specific agent template
        fw_key = self.config.resolved_framework.replace("-", "_")
        agent_template = f"backend/agents/{fw_key}/agent.py.j2"
        try:
            self._render_template(agent_template, backend_dir / "app" / "agent.py", ctx)
        except Exception:
            # Fallback: render a minimal agent stub
            self._render_template(
                "backend/shared/agent_stub.py.j2",
                backend_dir / "app" / "agent.py",
                ctx,
            )

        # Data generation script
        self._render_template(
            "backend/shared/generate_data.py.j2",
            backend_dir / "scripts" / "generate_data.py",
            ctx,
        )

        # Test scaffold
        tests_dir = backend_dir / "tests"
        tests_dir.mkdir(parents=True, exist_ok=True)
        (tests_dir / "__init__.py").write_text("")
        self._render_template(
            "backend/tests/test_routes.py.j2",
            tests_dir / "test_routes.py",
            ctx,
        )

        # SaaS connector modules (only if connectors are configured)
        if self.config.saas_connectors:
            connector_dir = backend_dir / "app" / "connectors"
            connector_dir.mkdir(parents=True, exist_ok=True)

            # Base __init__.py
            self._render_template(
                "backend/connectors/__init__.py.j2",
                connector_dir / "__init__.py",
                ctx,
            )

            # Individual connector modules
            connector_templates = {
                "github": "github_connector",
                "notion": "notion_connector",
                "jira": "jira_connector",
                "slack": "slack_connector",
                "gmail": "gmail_connector",
                "gcal": "gcal_connector",
                "salesforce": "salesforce_connector",
                "linear": "linear_connector",
            }
            for conn_id in self.config.saas_connectors:
                template_name = connector_templates.get(conn_id)
                if template_name:
                    self._render_template(
                        f"backend/connectors/{template_name}.py.j2",
                        connector_dir / f"{template_name}.py",
                        ctx,
                    )

            # Import data script
            self._render_template(
                "backend/connectors/import_data.py.j2",
                backend_dir / "scripts" / "import_data.py",
                ctx,
            )

    def _render_frontend(self, frontend_dir: Path, ctx: dict) -> None:
        """Render the Next.js + Chakra UI v3 + NVL frontend."""
        templates = {
            "frontend/package.json.j2": "package.json",
            "frontend/next.config.ts.j2": "next.config.ts",
            "frontend/tsconfig.json.j2": "tsconfig.json",
            "frontend/app/layout.tsx.j2": "app/layout.tsx",
            "frontend/app/page.tsx.j2": "app/page.tsx",
            "frontend/app/globals.css.j2": "app/globals.css",
            "frontend/components/ChatInterface.tsx.j2": "components/ChatInterface.tsx",
            "frontend/components/ContextGraphView.tsx.j2": "components/ContextGraphView.tsx",
            "frontend/components/DecisionTracePanel.tsx.j2": "components/DecisionTracePanel.tsx",
            "frontend/components/DocumentBrowser.tsx.j2": "components/DocumentBrowser.tsx",
            "frontend/components/ErrorBoundary.tsx.j2": "components/ErrorBoundary.tsx",
            "frontend/components/Provider.tsx.j2": "components/Provider.tsx",
            "frontend/lib/config.ts.j2": "lib/config.ts",
            "frontend/theme/index.ts.j2": "theme/index.ts",
            "frontend/playwright.config.ts.j2": "playwright.config.ts",
            "frontend/e2e/app.spec.ts.j2": "e2e/app.spec.ts",
        }
        for template_name, output_name in templates.items():
            self._render_template(template_name, frontend_dir / output_name, ctx)

    def _render_cypher(self, cypher_dir: Path, ctx: dict) -> None:
        """Render Cypher schema files."""
        self._render_template("cypher/schema.cypher.j2", cypher_dir / "schema.cypher", ctx)
        self._render_template(
            "cypher/gds_projections.cypher.j2",
            cypher_dir / "gds_projections.cypher",
            ctx,
        )

    def _render_data(self, data_dir: Path, ctx: dict) -> None:
        """Copy ontology and create data directory structure."""
        data_dir.mkdir(parents=True, exist_ok=True)
        (data_dir / "documents").mkdir(exist_ok=True)

        # Copy the domain ontology YAML
        if self.config.custom_domain_yaml:
            # Write custom domain YAML directly
            (data_dir / "ontology.yaml").write_text(self.config.custom_domain_yaml)
        else:
            from create_context_graph.ontology import _get_domains_path

            domain_yaml = _get_domains_path() / f"{self.config.domain}.yaml"
            if domain_yaml.exists():
                shutil.copy2(domain_yaml, data_dir / "ontology.yaml")

        # Also copy base
        base_yaml = _get_domains_path() / "_base.yaml"
        if base_yaml.exists():
            shutil.copy2(base_yaml, data_dir / "_base.yaml")

        # Copy pre-generated fixtures if available
        fixtures_dir = Path(str(files("create_context_graph") / "fixtures"))
        fixture_file = fixtures_dir / f"{self.config.domain}.json"
        if fixture_file.exists():
            shutil.copy2(fixture_file, data_dir / "fixtures.json")
