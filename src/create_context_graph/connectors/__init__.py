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

"""SaaS data connectors for importing external data into context graphs.

Each connector fetches data from a SaaS service, normalizes it to the
common fixture schema (entities, relationships, documents), and returns
it for ingestion into Neo4j.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Normalized data model — matches the fixture schema used by ingest.py
# ---------------------------------------------------------------------------


class NormalizedData(BaseModel):
    """Normalized data format matching the fixture schema.

    This format is directly consumable by the existing ingestion pipeline.
    """

    entities: dict[str, list[dict[str, Any]]] = Field(
        default_factory=dict,
        description="Entity data keyed by label, e.g. {'Person': [{...}, ...]}",
    )
    relationships: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Relationship data as list of dicts with type, source, target",
    )
    documents: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Document data as list of dicts with title, content, metadata",
    )

    def merge(self, other: NormalizedData) -> NormalizedData:
        """Merge another NormalizedData into this one, returning a new instance."""
        merged_entities: dict[str, list[dict[str, Any]]] = {}
        for label, items in self.entities.items():
            merged_entities[label] = list(items)
        for label, items in other.entities.items():
            merged_entities.setdefault(label, []).extend(items)

        return NormalizedData(
            entities=merged_entities,
            relationships=list(self.relationships) + list(other.relationships),
            documents=list(self.documents) + list(other.documents),
        )


# ---------------------------------------------------------------------------
# Base connector
# ---------------------------------------------------------------------------


class BaseConnector(ABC):
    """Abstract base class for all SaaS connectors."""

    service_name: str = ""
    service_description: str = ""
    requires_oauth: bool = False

    @abstractmethod
    def authenticate(self, credentials: dict[str, str]) -> None:
        """Authenticate with the service using provided credentials."""
        ...

    @abstractmethod
    def fetch(self, **kwargs: Any) -> NormalizedData:
        """Fetch data from the service and return normalized data."""
        ...

    @abstractmethod
    def get_credential_prompts(self) -> list[dict[str, Any]]:
        """Return credential prompts for the wizard.

        Each dict has: name, prompt, secret (bool), description
        """
        ...


# ---------------------------------------------------------------------------
# Connector registry
# ---------------------------------------------------------------------------

CONNECTOR_REGISTRY: dict[str, type[BaseConnector]] = {}


def register_connector(name: str):
    """Decorator to register a connector class."""
    def decorator(cls: type[BaseConnector]):
        CONNECTOR_REGISTRY[name] = cls
        return cls
    return decorator


def get_connector(name: str) -> BaseConnector:
    """Get an instance of a registered connector by name."""
    if name not in CONNECTOR_REGISTRY:
        available = ", ".join(sorted(CONNECTOR_REGISTRY.keys()))
        raise ValueError(f"Unknown connector: {name}. Available: {available}")
    return CONNECTOR_REGISTRY[name]()


def list_connectors() -> list[dict[str, str]]:
    """List available connectors with their descriptions."""
    results = []
    for name, cls in sorted(CONNECTOR_REGISTRY.items()):
        results.append({
            "id": name,
            "name": cls.service_name,
            "description": cls.service_description,
        })
    return results


def merge_connector_results(results: list[NormalizedData]) -> NormalizedData:
    """Merge multiple connector results into one."""
    if not results:
        return NormalizedData()
    merged = results[0]
    for r in results[1:]:
        merged = merged.merge(r)
    return merged


# ---------------------------------------------------------------------------
# Import all connectors to register them
# ---------------------------------------------------------------------------

from create_context_graph.connectors.github_connector import GitHubConnector  # noqa: E402, F401
from create_context_graph.connectors.notion_connector import NotionConnector  # noqa: E402, F401
from create_context_graph.connectors.jira_connector import JiraConnector  # noqa: E402, F401
from create_context_graph.connectors.slack_connector import SlackConnector  # noqa: E402, F401
from create_context_graph.connectors.gmail_connector import GmailConnector  # noqa: E402, F401
from create_context_graph.connectors.gcal_connector import GCalConnector  # noqa: E402, F401
from create_context_graph.connectors.salesforce_connector import SalesforceConnector  # noqa: E402, F401
from create_context_graph.connectors.linear_connector import LinearConnector  # noqa: E402, F401
