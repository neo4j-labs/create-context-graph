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

"""Project configuration model."""

from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel, Field, computed_field


SESSION_STRATEGIES = ["per_conversation", "per_day", "persistent"]
MCP_PROFILES = ["core", "extended"]

SUPPORTED_FRAMEWORKS = [
    "pydanticai",
    "claude-agent-sdk",
    "strands",
    "google-adk",
    "openai-agents",
    "langgraph",
    "crewai",
    "anthropic-tools",
]

# Deprecated aliases — map old keys to current ones
FRAMEWORK_ALIASES = {
    "maf": "anthropic-tools",
}

FRAMEWORK_DISPLAY_NAMES = {
    "pydanticai": "PydanticAI",
    "claude-agent-sdk": "Claude Agent SDK",
    "strands": "Strands",
    "google-adk": "Google ADK",
    "openai-agents": "OpenAI Agents SDK",
    "langgraph": "LangGraph",
    "crewai": "CrewAI",
    "anthropic-tools": "Anthropic Tools (Agentic Loop)",
}

FRAMEWORK_DEPENDENCIES = {
    "pydanticai": ["pydantic-ai>=0.1"],
    "claude-agent-sdk": ["claude-agent-sdk>=0.1", "anthropic>=0.30"],
    "strands": ["strands-agents[anthropic]>=0.1"],
    "google-adk": ["google-adk>=0.1", "nest-asyncio>=1.5"],
    "openai-agents": ["openai-agents>=0.1"],
    "langgraph": ["langgraph>=0.1", "langchain-anthropic>=0.3"],
    "crewai": ["crewai[anthropic]>=0.1"],
    "anthropic-tools": ["anthropic>=0.30"],
}


class ProjectConfig(BaseModel):
    """All configuration collected from the wizard or CLI flags."""

    project_name: str = Field(description="Human-readable project name")
    domain: str = Field(description="Domain ID from ontology YAML")
    framework: str = Field(description="Agent framework key")
    data_source: Literal["demo", "saas", "none"] = Field(default="demo")
    neo4j_uri: str = Field(default="neo4j://localhost:7687")
    neo4j_username: str = Field(default="neo4j")
    neo4j_password: str = Field(default="password")
    neo4j_type: Literal["docker", "existing", "aura", "local"] = Field(default="docker")
    anthropic_api_key: str | None = Field(default=None)
    anthropic_base_url: str | None = Field(default=None)
    openai_api_key: str | None = Field(default=None)
    google_api_key: str | None = Field(default=None)
    generate_data: bool = Field(default=False)
    custom_domain_yaml: str | None = Field(default=None, exclude=True)
    saas_connectors: list[str] = Field(default_factory=list)
    saas_credentials: dict[str, dict[str, str]] = Field(default_factory=dict, exclude=True)

    # Memory enhancement settings (neo4j-agent-memory v0.1.0)
    with_mcp: bool = Field(default=False, description="Generate MCP server config for Claude Desktop")
    mcp_profile: Literal["core", "extended"] = Field(
        default="extended", description="MCP tool profile"
    )
    session_strategy: Literal["per_conversation", "per_day", "persistent"] = Field(
        default="per_conversation", description="Memory session strategy"
    )
    auto_extract: bool = Field(
        default=True, description="Auto-extract entities from messages"
    )
    auto_preferences: bool = Field(
        default=True, description="Auto-detect user preferences from messages"
    )

    @computed_field
    @property
    def project_slug(self) -> str:
        """Kebab-case slug derived from project name."""
        slug = self.project_name.lower().strip()
        slug = re.sub(r"[^a-z0-9]+", "-", slug)
        return slug.strip("-")

    @property
    def resolved_framework(self) -> str:
        """Resolve deprecated framework aliases to current keys."""
        return FRAMEWORK_ALIASES.get(self.framework, self.framework)

    @property
    def framework_display_name(self) -> str:
        return FRAMEWORK_DISPLAY_NAMES.get(self.resolved_framework, self.framework)

    @property
    def framework_deps(self) -> list[str]:
        return FRAMEWORK_DEPENDENCIES.get(self.resolved_framework, [])
