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

"""Notion connector — imports pages, databases, and users."""

from __future__ import annotations

from typing import Any

from create_context_graph.connectors import (
    BaseConnector,
    NormalizedData,
    register_connector,
)


@register_connector("notion")
class NotionConnector(BaseConnector):
    """Import data from Notion workspaces."""

    service_name = "Notion"
    service_description = "Import pages and databases from a Notion workspace"
    requires_oauth = False

    def __init__(self):
        self._client = None

    def get_credential_prompts(self) -> list[dict[str, Any]]:
        return [
            {
                "name": "token",
                "prompt": "Notion integration token:",
                "secret": True,
                "description": "Internal integration token (Settings > My connections > Develop or manage integrations)",
            },
        ]

    def authenticate(self, credentials: dict[str, str]) -> None:
        try:
            from notion_client import Client
        except ImportError:
            raise ImportError(
                "notion-client is required for the Notion connector. "
                "Install it with: pip install notion-client"
            )

        # notion-client >=2.6 defaults to Notion-Version 2025-09-03 (data sources),
        # which changes the search filter enum and page parent types this
        # connector relies on. Pin the classic API version until the connector
        # is migrated to the data-source model.
        self._client = Client(auth=credentials["token"], notion_version="2022-06-28")

    def _extract_title(self, page: dict) -> str:
        """Extract title from a Notion page properties."""
        props = page.get("properties", {})
        for prop in props.values():
            if prop.get("type") == "title":
                title_parts = prop.get("title", [])
                return "".join(t.get("plain_text", "") for t in title_parts)
        return page.get("id", "Untitled")

    def _extract_text_content(self, blocks: list[dict]) -> str:
        """Extract plain text from Notion blocks."""
        parts = []
        for block in blocks:
            block_type = block.get("type", "")
            block_data = block.get(block_type, {})
            if "rich_text" in block_data:
                text = "".join(
                    t.get("plain_text", "") for t in block_data["rich_text"]
                )
                if text:
                    parts.append(text)
        return "\n".join(parts)

    def fetch(self, **kwargs: Any) -> NormalizedData:
        if not self._client:
            raise RuntimeError("Call authenticate() first")

        limit = kwargs.get("limit", 100)
        entities: dict[str, list[dict]] = {
            "Person": [],
            "Page": [],
            "Database": [],
        }
        relationships: list[dict] = []
        documents: list[dict] = []
        seen_users: set[str] = set()

        def _add_user(user_obj: dict) -> str | None:
            user_id = user_obj.get("id")
            if not user_id or user_id in seen_users:
                return user_id
            seen_users.add(user_id)
            name = user_obj.get("name", user_obj.get("id", "Unknown"))
            entities["Person"].append({
                "name": name,
                "email": user_obj.get("person", {}).get("email", ""),
                "role": user_obj.get("type", "person"),
                "description": f"Notion user: {name}",
            })
            return user_id

        # Search for pages
        results = self._client.search(
            filter={"property": "object", "value": "page"},
            page_size=min(limit, 100),
        )

        for page in results.get("results", []):
            title = self._extract_title(page)
            page_id = page["id"]

            entities["Page"].append({
                "name": title,
                "page_id": page_id,
                "url": page.get("url", ""),
                "created_time": page.get("created_time", ""),
                "last_edited_time": page.get("last_edited_time", ""),
            })

            # Track author
            created_by = page.get("created_by", {})
            if created_by:
                user_id = _add_user(created_by)
                if user_id:
                    relationships.append({
                        "type": "AUTHORED",
                        "source_name": created_by.get("name", user_id),
                        "source_label": "Person",
                        "target_name": title,
                        "target_label": "Page",
                    })

            # Get page content
            try:
                blocks = self._client.blocks.children.list(block_id=page_id)
                content = self._extract_text_content(blocks.get("results", []))
                if content:
                    documents.append({
                        "title": title,
                        "content": content,
                        "type": "notion-page",
                        "metadata": {
                            "page_id": page_id,
                            "url": page.get("url", ""),
                        },
                    })
            except Exception:
                pass  # Some pages may not be accessible

            # Track parent database
            parent = page.get("parent", {})
            if parent.get("type") == "database_id":
                db_id = parent["database_id"]
                relationships.append({
                    "type": "BELONGS_TO",
                    "source_name": title,
                    "source_label": "Page",
                    "target_name": db_id,
                    "target_label": "Database",
                })

        # Search for databases
        db_results = self._client.search(
            filter={"property": "object", "value": "database"},
            page_size=min(limit, 50),
        )

        for db in db_results.get("results", []):
            db_title_parts = db.get("title", [])
            db_title = "".join(t.get("plain_text", "") for t in db_title_parts) or db["id"]

            entities["Database"].append({
                "name": db_title,
                "database_id": db["id"],
                "url": db.get("url", ""),
                "created_time": db.get("created_time", ""),
            })

        return NormalizedData(
            entities=entities,
            relationships=relationships,
            documents=documents,
        )
