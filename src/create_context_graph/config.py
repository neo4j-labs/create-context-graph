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
MEMORY_BACKENDS = ["nams", "bolt"]
DEFAULT_FRAMEWORK = "strands"
DEFAULT_MEMORY_BACKEND = "nams"
DEFAULT_NAMS_ENDPOINT = "https://memory.neo4jlabs.com/v1"
NAMS_SIGNUP_URL = "https://memory.neo4jlabs.com"

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
    framework: str = Field(default=DEFAULT_FRAMEWORK, description="Agent framework key")
    data_source: Literal["demo", "saas", "none"] = Field(default="demo")

    # Memory backend: NAMS hosted service (default) or self-hosted Bolt Neo4j
    memory_backend: Literal["nams", "bolt"] = Field(
        default=DEFAULT_MEMORY_BACKEND,
        description="Memory backend: 'nams' (hosted) or 'bolt' (self-hosted Neo4j)",
    )
    nams_api_key: str | None = Field(default=None, exclude=True)
    nams_endpoint: str = Field(default=DEFAULT_NAMS_ENDPOINT)

    # Self-hosted Neo4j (only meaningful when memory_backend == "bolt")
    neo4j_uri: str = Field(default="neo4j://localhost:7687")
    neo4j_username: str = Field(default="neo4j")
    neo4j_password: str = Field(default="password")
    neo4j_type: Literal["docker", "existing", "aura", "local"] = Field(default="docker")

    anthropic_api_key: str | None = Field(default=None)
    openai_api_key: str | None = Field(default=None)
    google_api_key: str | None = Field(default=None)

    # LiteLLM provider strings for memory layer (optional — defaults applied at runtime)
    memory_llm: str | None = Field(
        default=None,
        description="LiteLLM-style provider/model for memory entity extraction",
    )
    memory_embedding: str | None = Field(
        default=None,
        description="LiteLLM-style provider/model for memory embeddings",
    )

    generate_data: bool = Field(default=False)
    custom_domain_yaml: str | None = Field(default=None, exclude=True)
    saas_connectors: list[str] = Field(default_factory=list)
    saas_credentials: dict[str, dict[str, str]] = Field(default_factory=dict, exclude=True)

    # Memory enhancement settings (neo4j-agent-memory)
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

    @property
    def is_nams(self) -> bool:
        return self.memory_backend == "nams"

    @property
    def is_self_hosted(self) -> bool:
        return self.memory_backend == "bolt"

    @property
    def effective_mcp_profile(self) -> str:
        """NAMS forces ``core`` profile — extended-profile tools (preferences/facts) are unsupported."""
        if self.is_nams:
            return "core"
        return self.mcp_profile

    @property
    def effective_auto_preferences(self) -> bool:
        """NAMS does not expose preference endpoints — force off when backend=nams."""
        if self.is_nams:
            return False
        return self.auto_preferences

    @computed_field
    @property
    def project_slug(self) -> str:
        """Kebab-case slug derived from project name."""
        slug = self.project_name.lower().strip()
        slug = re.sub(r"[^a-z0-9]+", "-", slug)
        return slug.strip("-")

    @property
    def framework_display_name(self) -> str:
        return FRAMEWORK_DISPLAY_NAMES.get(self.framework, self.framework)

    @property
    def framework_deps(self) -> list[str]:
        return FRAMEWORK_DEPENDENCIES.get(self.framework, [])
