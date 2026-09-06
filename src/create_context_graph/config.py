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

# Every entry has a floor create-context-graph verified against and a cap at
# the next major (0.x packages that ship behaviour changes in minors are capped
# at the next minor). See DEPENDENCY_UPGRADE_PLAN.md §4.4 for the per-framework
# rationale and the upstream pins that constrain these choices:
# - strands-agents[anthropic] pins anthropic<1 and crewai[anthropic] pins
#   anthropic~=0.73, so no framework-wide anthropic floor is possible.
# - pydantic-ai-slim[anthropic] instead of the ``pydantic-ai`` meta-package:
#   76 fewer distributions and no openai>=3 pin (which forces a litellm downgrade).
# - claude-agent-sdk was declared but never imported (the template uses the
#   Anthropic SDK directly); it added a 190 MB bundled CLI to every scaffold.
# - nest-asyncio is unnecessary for google-adk (FunctionTool awaits async tools)
#   and is archived upstream / incompatible with Python 3.14 semantics.
# - langchain>=1 ships ``langchain.agents.create_agent``, the replacement for
#   ``langgraph.prebuilt.create_react_agent`` (removed in LangGraph 2.0).
FRAMEWORK_DEPENDENCIES = {
    "pydanticai": ["pydantic-ai-slim[anthropic]>=2.30,<3"],
    "claude-agent-sdk": ["anthropic>=1.0,<2"],
    "strands": ["strands-agents[anthropic]>=1.53,<2.0"],
    "google-adk": ["google-adk>=2.2,<3"],
    "openai-agents": ["openai-agents>=0.21,<0.23"],
    "langgraph": ["langchain>=1.4,<2", "langchain-anthropic>=1.7,<2"],
    "crewai": ["crewai[anthropic]>=1.15,<2"],
    "anthropic-tools": ["anthropic>=1.0,<2"],
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
    # "" defers to neo4j-agent-memory's own default ("neo4j"). Must be set
    # explicitly for Aura instances whose database isn't named "neo4j" (e.g.
    # ones provisioned via the Aura API/CLI, which commonly name it after
    # the instance id).
    neo4j_database: str = Field(default="")
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
