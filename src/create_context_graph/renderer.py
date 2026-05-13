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
# Google Workspace connector agent tools (injected when connector is active)
# ---------------------------------------------------------------------------

_GWS_AGENT_TOOLS: list[dict] = [
    {
        "name": "find_decisions",
        "description": "Search for resolved comment threads (decisions) by keyword, document, person, or time range. Returns the question, deliberation, resolution, and participants.",
        "cypher": "MATCH (dt:DecisionThread {resolved: true})-[:HAS_COMMENT_THREAD]-(doc:Document) WHERE toLower(dt.content) CONTAINS toLower($keyword) OR toLower(doc.name) CONTAINS toLower($keyword) OPTIONAL MATCH (dt)-[:AUTHORED_BY]->(p:Person) RETURN dt.name AS decision, dt.content AS question, dt.resolution AS resolution, doc.name AS document, collect(DISTINCT p.name) AS participants LIMIT 10",
        "parameters": [{"name": "keyword", "type": "string", "required": True}],
    },
    {
        "name": "decision_context",
        "description": "Given a topic or issue identifier, find all decision threads, meetings, and email threads that provide context for how and why a decision was made.",
        "cypher": "MATCH (dt:DecisionThread) WHERE toLower(dt.content) CONTAINS toLower($topic) OPTIONAL MATCH (dt)-[:HAS_COMMENT_THREAD]-(doc:Document) OPTIONAL MATCH (doc)-[:DISCUSSED_IN]-(m:Meeting) OPTIONAL MATCH (dt)-[:RELATES_TO_ISSUE]->(issue) RETURN dt.name AS decision, dt.resolution AS resolution, doc.name AS document, m.name AS meeting, issue.name AS related_issue LIMIT 15",
        "parameters": [{"name": "topic", "type": "string", "required": True}],
    },
    {
        "name": "who_decided",
        "description": "Find the people involved in decisions about a specific document, project, or topic, weighted by participation frequency.",
        "cypher": "MATCH (p:Person)<-[:AUTHORED_BY|RESOLVED_BY]-(dt:DecisionThread)-[:HAS_COMMENT_THREAD]-(doc:Document) WHERE toLower(doc.name) CONTAINS toLower($topic) OR toLower(dt.content) CONTAINS toLower($topic) RETURN p.name AS person, p.emailAddress AS email, count(DISTINCT dt) AS decision_count ORDER BY decision_count DESC LIMIT 10",
        "parameters": [{"name": "topic", "type": "string", "required": True}],
    },
    {
        "name": "document_timeline",
        "description": "Show the complete history of a document: creation, edits, comments, decisions, and related meetings in chronological order.",
        "cypher": "MATCH (doc:Document) WHERE toLower(doc.name) CONTAINS toLower($document_name) OPTIONAL MATCH (doc)-[:HAS_REVISION]->(rev:Revision) OPTIONAL MATCH (doc)-[:HAS_COMMENT_THREAD]->(dt:DecisionThread) OPTIONAL MATCH (doc)-[:DISCUSSED_IN]-(m:Meeting) WITH doc, collect(DISTINCT {type: 'revision', name: rev.name, time: rev.modifiedTime}) AS revisions, collect(DISTINCT {type: 'decision', name: dt.name, resolved: dt.resolved, time: dt.createdTime}) AS decisions, collect(DISTINCT {type: 'meeting', name: m.name, time: m.startTime}) AS meetings RETURN doc.name AS document, revisions, decisions, meetings LIMIT 5",
        "parameters": [{"name": "document_name", "type": "string", "required": True}],
    },
    {
        "name": "open_questions",
        "description": "Find unresolved comment threads across all documents, optionally filtered by document name. Surfaces decisions still pending.",
        "cypher": "MATCH (dt:DecisionThread {resolved: false})-[:HAS_COMMENT_THREAD]-(doc:Document) WHERE $filter = '' OR toLower(doc.name) CONTAINS toLower($filter) OPTIONAL MATCH (dt)-[:AUTHORED_BY]->(p:Person) RETURN dt.name AS thread, dt.content AS question, doc.name AS document, p.name AS author, dt.createdTime AS created ORDER BY dt.createdTime DESC LIMIT 15",
        "parameters": [{"name": "filter", "type": "string", "required": False, "default": ""}],
    },
    {
        "name": "meeting_decisions",
        "description": "Given a meeting or event name, find all documents that were discussed and any decision threads that were created or resolved around the meeting time.",
        "cypher": "MATCH (m:Meeting) WHERE toLower(m.summary) CONTAINS toLower($meeting_name) OPTIONAL MATCH (m)<-[:DISCUSSED_IN]-(doc:Document) OPTIONAL MATCH (doc)-[:HAS_COMMENT_THREAD]->(dt:DecisionThread) OPTIONAL MATCH (m)<-[:ATTENDEE_OF]-(p:Person) RETURN m.name AS meeting, m.startTime AS time, collect(DISTINCT doc.name) AS documents, collect(DISTINCT {decision: dt.name, resolved: dt.resolved}) AS decisions, collect(DISTINCT p.name) AS attendees LIMIT 5",
        "parameters": [{"name": "meeting_name", "type": "string", "required": True}],
    },
    {
        "name": "knowledge_contributors",
        "description": "Identify the top contributors to a folder or project by combining authorship (revisions), decision participation (comments), and meeting attendance.",
        "cypher": "MATCH (p:Person) WHERE EXISTS { MATCH (p)<-[:REVISED_BY]-(:Revision)<-[:HAS_REVISION]-(:Document) } OR EXISTS { MATCH (p)<-[:AUTHORED_BY]-(:DecisionThread) } WITH p OPTIONAL MATCH (p)<-[:REVISED_BY]-(rev:Revision) WITH p, count(DISTINCT rev) AS revision_count OPTIONAL MATCH (p)<-[:AUTHORED_BY]-(dt:DecisionThread) WITH p, revision_count, count(DISTINCT dt) AS decision_count OPTIONAL MATCH (p)-[:ATTENDEE_OF]->(m:Meeting) RETURN p.name AS person, p.emailAddress AS email, revision_count, decision_count, count(DISTINCT m) AS meeting_count, revision_count + decision_count * 2 + count(DISTINCT m) AS total_score ORDER BY total_score DESC LIMIT 10",
        "parameters": [],
    },
    {
        "name": "trace_decision_to_source",
        "description": "Given a fact or claim, trace it back through the decision chain: which comment thread established it, which document contains it, who authored it, what meeting preceded it.",
        "cypher": "MATCH (dt:DecisionThread) WHERE toLower(dt.content) CONTAINS toLower($claim) OR toLower(dt.resolution) CONTAINS toLower($claim) MATCH (dt)-[:HAS_COMMENT_THREAD]-(doc:Document) OPTIONAL MATCH (dt)-[:AUTHORED_BY]->(author:Person) OPTIONAL MATCH (dt)-[:RESOLVED_BY]->(resolver:Person) OPTIONAL MATCH (doc)-[:DISCUSSED_IN]-(m:Meeting) RETURN dt.name AS decision, dt.content AS question, dt.resolution AS resolution, doc.name AS document, author.name AS raised_by, resolver.name AS resolved_by, m.name AS related_meeting LIMIT 5",
        "parameters": [{"name": "claim", "type": "string", "required": True}],
    },
    {
        "name": "stale_documents",
        "description": "Find documents that haven't been updated recently but have open comment threads or are referenced by active issues.",
        "cypher": "MATCH (doc:Document) WHERE doc.modifiedTime IS NOT NULL AND doc.modifiedTime <> '' AND datetime(doc.modifiedTime) < datetime() - duration({days: $days_threshold}) AND EXISTS { MATCH (doc)-[:HAS_COMMENT_THREAD]->(:DecisionThread {resolved: false}) } RETURN doc.name AS document, doc.modifiedTime AS last_modified, doc.webViewLink AS link ORDER BY datetime(doc.modifiedTime) ASC LIMIT 15",
        "parameters": [{"name": "days_threshold", "type": "integer", "required": False, "default": 30}],
    },
    {
        "name": "cross_reference",
        "description": "Given a Linear issue identifier (e.g., ENG-123), find all related Google Workspace context: documents that reference it, decisions about it, meetings where it was discussed.",
        "cypher": "MATCH (context)-[:RELATES_TO_ISSUE]->(issue) WHERE issue.name CONTAINS $identifier OR issue.identifier = $identifier OPTIONAL MATCH (context)-[:HAS_COMMENT_THREAD]-(doc:Document) RETURN context.name AS source, labels(context)[0] AS source_type, issue.name AS issue, doc.name AS document LIMIT 20",
        "parameters": [{"name": "identifier", "type": "string", "required": True}],
    },
]

# ---------------------------------------------------------------------------
# Claude Code session connector agent tools
# ---------------------------------------------------------------------------

_CLAUDE_CODE_AGENT_TOOLS: list[dict] = [
    {
        "name": "search_sessions",
        "description": "Full-text search across Claude Code session message content by keyword. Returns matching sessions with context.",
        "cypher": "MATCH (s:Session)-[:HAS_MESSAGE]->(m:Message) WHERE toLower(m.content) CONTAINS toLower($keyword) WITH s, m ORDER BY m.timestamp DESC RETURN s.name AS session, s.branch AS branch, m.role AS role, m.content AS content, m.timestamp AS timestamp LIMIT 15",
        "parameters": [{"name": "keyword", "type": "string", "required": True}],
    },
    {
        "name": "decision_history",
        "description": "Find decisions made during Claude Code sessions related to a file, package, or topic.",
        "cypher": "MATCH (d:Decision) WHERE toLower(d.description) CONTAINS toLower($topic) OPTIONAL MATCH (d)-[:CHOSE]->(chosen:Alternative) OPTIONAL MATCH (d)-[:REJECTED]->(rejected:Alternative) OPTIONAL MATCH (s:Session)-[:MADE_DECISION]->(d) RETURN d.name AS decision, d.description AS description, d.category AS category, d.confidence AS confidence, chosen.description AS chosen_approach, rejected.description AS rejected_approach, s.name AS session ORDER BY d.timestamp DESC LIMIT 10",
        "parameters": [{"name": "topic", "type": "string", "required": True}],
    },
    {
        "name": "file_timeline",
        "description": "Show the complete modification and read history of a specific file across all Claude Code sessions.",
        "cypher": "MATCH (f:File) WHERE f.path CONTAINS $path OPTIONAL MATCH (tc:ToolCall)-[:MODIFIED_FILE]->(f) WITH f, collect(DISTINCT {tool: tc.toolName, time: tc.timestamp, action: 'modified'}) AS modifications OPTIONAL MATCH (tc2:ToolCall)-[:READ_FILE]->(f) RETURN f.path AS file, f.language AS language, f.modificationCount AS total_modifications, modifications, collect(DISTINCT {tool: tc2.toolName, time: tc2.timestamp, action: 'read'}) AS reads LIMIT 5",
        "parameters": [{"name": "path", "type": "string", "required": True}],
    },
    {
        "name": "error_patterns",
        "description": "Find recurring errors encountered during Claude Code sessions and how they were resolved.",
        "cypher": "MATCH (e:Error)<-[:ENCOUNTERED_ERROR]-(tc:ToolCall) OPTIONAL MATCH (d:Decision {category: 'error-fix'})-[:RESULTED_IN]->(fix:ToolCall) WHERE d.description CONTAINS e.message RETURN e.message AS error, tc.toolName AS failed_tool, e.timestamp AS when, fix.toolName AS resolution_tool, d.description AS resolution LIMIT 15",
        "parameters": [],
    },
    {
        "name": "tool_usage_stats",
        "description": "Analytics on tool usage across Claude Code sessions — most used tools, files, and commands.",
        "cypher": "MATCH (tc:ToolCall) RETURN tc.toolName AS tool, count(*) AS usage_count, collect(DISTINCT tc.input)[..3] AS sample_inputs ORDER BY usage_count DESC LIMIT 15",
        "parameters": [],
    },
    {
        "name": "my_preferences",
        "description": "Retrieve extracted developer preferences by category (coding_style, framework_choice, testing_approach, tool_configuration, naming_convention, documentation).",
        "cypher": "MATCH (p:Preference) WHERE $category = '' OR p.category = $category RETURN p.name AS preference, p.value AS value, p.category AS category, p.confidence AS confidence, p.sessionCount AS seen_in_sessions, p.extractedFrom AS source ORDER BY p.confidence DESC LIMIT 20",
        "parameters": [{"name": "category", "type": "string", "required": False, "default": ""}],
    },
    {
        "name": "project_overview",
        "description": "Summary statistics for a Claude Code project — sessions, files touched, decisions made, errors encountered.",
        "cypher": "MATCH (p:Project) WHERE $project_name = '' OR toLower(p.name) CONTAINS toLower($project_name) OPTIONAL MATCH (p)-[:HAS_SESSION]->(s:Session) WITH p, count(DISTINCT s) AS session_count, sum(s.totalInputTokens) AS total_input_tokens, sum(s.totalOutputTokens) AS total_output_tokens OPTIONAL MATCH (p)-[:HAS_SESSION]->(:Session)-[:MADE_DECISION]->(d:Decision) RETURN p.name AS project, session_count, total_input_tokens, total_output_tokens, count(DISTINCT d) AS decision_count LIMIT 10",
        "parameters": [{"name": "project_name", "type": "string", "required": False, "default": ""}],
    },
    {
        "name": "reasoning_trace",
        "description": "Trace the causal chain of tool calls for a specific session — shows the sequence of actions the agent took.",
        "cypher": "MATCH (s:Session {name: $session_name})-[:HAS_MESSAGE]->(m:Message)-[:USED_TOOL]->(tc:ToolCall) RETURN m.role AS role, m.timestamp AS message_time, tc.toolName AS tool, tc.input AS tool_input, tc.isError AS had_error ORDER BY m.timestamp, tc.timestamp LIMIT 50",
        "parameters": [{"name": "session_name", "type": "string", "required": True}],
    },
]

# ---------------------------------------------------------------------------
# Claude Code session connector demo scenarios
# ---------------------------------------------------------------------------

_CLAUDE_CODE_SCENARIOS: list[dict] = [
    {
        "name": "Session Intelligence",
        "prompts": [
            "What files have I modified most frequently?",
            "Show me the decisions made in my recent sessions",
            "What errors have I encountered and how were they resolved?",
        ],
    },
    {
        "name": "Development Patterns",
        "prompts": [
            "What are my coding preferences?",
            "Which tools do I use most frequently?",
            "Give me an overview of my project activity",
        ],
    },
    {
        "name": "Code Archaeology",
        "prompts": [
            "What was I working on in my last session?",
            "Show me the reasoning trace for my most recent session",
            "Which files were involved in fixing the last error?",
        ],
    },
]


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
            "demo_scenarios": self._build_demo_scenarios(),
            "agent_tools": self._build_agent_tools(),
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
            "system_prompt": self._build_system_prompt(),
            "cypher_schema": generate_cypher_schema(self.ontology),
            "pydantic_models": generate_pydantic_models(self.ontology),
            "visualization": generate_visualization_config(self.ontology),
            "saas_connectors": self.config.saas_connectors,
            "connector_credentials": self.config.saas_credentials,
            "with_mcp": self.config.with_mcp,
            "mcp_profile": self.config.mcp_profile,
            "session_strategy": self.config.session_strategy,
            "auto_extract": self.config.auto_extract,
            "auto_preferences": self.config.auto_preferences,
        }

    def _build_system_prompt(self) -> str:
        """Build system prompt, appending connector context if active."""
        prompt = self.ontology.system_prompt
        if "google-workspace" in self.config.saas_connectors:
            prompt += (
                "\n\nYou also have access to Google Workspace decision context. "
                "The knowledge graph contains DecisionThread nodes extracted from "
                "resolved Google Docs comment threads — each represents a decision "
                "with the question, deliberation, resolution, and participants. "
                "Use the find_decisions, decision_context, who_decided, and "
                "open_questions tools to answer questions about why decisions were "
                "made, who was involved, and what is still pending."
            )
        if "claude-code" in self.config.saas_connectors:
            prompt += (
                "\n\nYou also have access to Claude Code session history. "
                "The knowledge graph contains Session, Message, ToolCall, Decision, "
                "Preference, File, and Error nodes extracted from local Claude Code "
                "JSONL session files. Use the search_sessions, decision_history, "
                "file_timeline, error_patterns, tool_usage_stats, my_preferences, "
                "project_overview, and reasoning_trace tools to answer questions about "
                "past coding sessions, decisions made, developer preferences, and "
                "file modification history."
            )
        return prompt

    def _build_demo_scenarios(self) -> list[dict]:
        """Build demo scenarios, replacing with connector-specific ones if active."""
        if "claude-code" in self.config.saas_connectors:
            return _CLAUDE_CODE_SCENARIOS
        return [s.model_dump() for s in self.ontology.demo_scenarios]

    def _build_agent_tools(self) -> list[dict]:
        """Build agent tools list, including connector-specific tools."""
        tools = [t.model_dump() for t in self.ontology.agent_tools]

        # Add Google Workspace decision-trace tools when connector is active
        if "google-workspace" in self.config.saas_connectors:
            tools.extend(_GWS_AGENT_TOOLS)

        # Add Claude Code session intelligence tools when connector is active
        if "claude-code" in self.config.saas_connectors:
            tools.extend(_CLAUDE_CODE_AGENT_TOOLS)

        return tools

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

        # MCP server config (only if --with-mcp)
        if self.config.with_mcp:
            self._render_template(
                "base/mcp/claude_desktop_config.json.j2",
                output_dir / "mcp" / "claude_desktop_config.json",
                ctx,
            )
            self._render_template(
                "base/mcp/README.md.j2",
                output_dir / "mcp" / "README.md",
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
            "backend/shared/memory.py.j2": "app/memory.py",
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
                "google-workspace": "google_workspace_connector",
                "claude-code": "claude_code_connector",
                "local-file": "local_file_connector",
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

        # Copy pre-generated fixtures only when no connectors are selected
        # (connector projects populate fixtures.json via `make import`)
        if not self.config.saas_connectors:
            fixtures_dir = Path(str(files("create_context_graph") / "fixtures"))
            fixture_file = fixtures_dir / f"{self.config.domain}.json"
            if fixture_file.exists():
                shutil.copy2(fixture_file, data_dir / "fixtures.json")
