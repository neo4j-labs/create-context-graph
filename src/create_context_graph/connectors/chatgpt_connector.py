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

"""ChatGPT conversation export connector.

Imports conversation data from the official ChatGPT data export
(Settings > Data Controls > Export Data).  The export is a ``.zip``
containing ``conversations.json`` — a JSON array of conversations with
a tree-structured ``mapping`` field.

This connector requires no API key or authentication; it reads a local
file provided by the user.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from create_context_graph.connectors import (
    BaseConnector,
    NormalizedData,
    register_connector,
)
from create_context_graph.connectors._chatgpt.parser import parse_conversations

logger = logging.getLogger(__name__)

# Maximum characters to store per message entity.
MAX_CONTENT_LEN = 2000
# Maximum characters to store in a conversation document (for search/RAG).
MAX_DOC_LEN = 10_000
# Number of characters to use from IDs when building composite entity names.
_ID_PREFIX_LEN = 12


@register_connector("chatgpt")
class ChatGPTConnector(BaseConnector):
    """Import conversations from a ChatGPT data export."""

    service_name = "ChatGPT"
    service_description = (
        "Import conversations from a ChatGPT data export "
        "(.zip or .json from Settings > Data Controls > Export Data)"
    )
    requires_oauth = False

    def __init__(self) -> None:
        self._file_path: str = ""
        self._depth: str = "fast"
        self._filter_after: datetime | None = None
        self._filter_before: datetime | None = None
        self._filter_title: str | None = None
        self._max_conversations: int = 0

    # ------------------------------------------------------------------
    # BaseConnector interface
    # ------------------------------------------------------------------

    def get_credential_prompts(self) -> list[dict[str, Any]]:
        """No interactive prompts — file path comes from CLI flags."""
        return []

    def authenticate(self, credentials: dict[str, str]) -> None:
        """Parse configuration from credentials dict.

        The CLI wires ``--import-*`` flags into the credentials dict
        so that configuration flows through the standard connector pipeline.
        """
        self._file_path = credentials.get("file_path", "")
        self._depth = credentials.get("depth", "fast")
        self._max_conversations = int(credentials.get("max_conversations", "0"))
        self._filter_title = credentials.get("filter_title") or None

        after = credentials.get("filter_after", "")
        if after:
            self._filter_after = datetime.fromisoformat(after)
            if self._filter_after.tzinfo is None:
                self._filter_after = self._filter_after.replace(tzinfo=timezone.utc)

        before = credentials.get("filter_before", "")
        if before:
            self._filter_before = datetime.fromisoformat(before)
            if self._filter_before.tzinfo is None:
                self._filter_before = self._filter_before.replace(tzinfo=timezone.utc)

        if self._file_path:
            p = Path(self._file_path)
            if not p.exists():
                raise FileNotFoundError(f"Import file not found: {p}")
            if p.suffix not in (".zip", ".json"):
                raise ValueError(
                    f"Expected .zip or .json file, got: {p.suffix}"
                )

    def fetch(self, **kwargs: Any) -> NormalizedData:
        """Parse ChatGPT conversations and return normalised graph data."""
        if not self._file_path:
            logger.warning("No import file specified — returning empty data.")
            return NormalizedData()

        conversations = parse_conversations(
            self._file_path,
            filter_after=self._filter_after,
            filter_before=self._filter_before,
            filter_title=self._filter_title,
            max_conversations=self._max_conversations,
        )

        logger.info(
            "Parsed %d ChatGPT conversations from %s",
            len(conversations),
            Path(self._file_path).name,
        )

        entities: dict[str, list[dict[str, Any]]] = {}
        relationships: list[dict[str, Any]] = []
        documents: list[dict[str, Any]] = []
        traces: list[dict[str, Any]] = []

        conversation_entities: list[dict[str, Any]] = []
        message_entities: list[dict[str, Any]] = []

        for conv in conversations:
            conv_name = f"conv-{conv.conversation_id}"

            conversation_entities.append({
                "name": conv_name,
                "title": conv.title,
                "conversation_id": conv.conversation_id,
                "source": "chatgpt",
                "created_at": conv.created_at.isoformat(),
                "updated_at": conv.updated_at.isoformat(),
                "message_count": len(conv.messages),
                "model_slug": conv.metadata.get("model_slug", ""),
            })

            doc_parts: list[str] = []
            prev_msg_name: str | None = None

            for i, msg in enumerate(conv.messages):
                if msg.message_id:
                    msg_name = f"{conv.conversation_id[:_ID_PREFIX_LEN]}-{msg.message_id[:_ID_PREFIX_LEN]}"
                else:
                    msg_name = f"{conv.conversation_id[:_ID_PREFIX_LEN]}-msg-{i}"
                content = msg.content or ""

                truncated = content[:MAX_CONTENT_LEN] if len(content) > MAX_CONTENT_LEN else content

                message_entities.append({
                    "name": msg_name,
                    "role": msg.role,
                    "content": truncated,
                    "created_at": msg.created_at.isoformat() if msg.created_at else "",
                    "conversation_id": conv.conversation_id,
                    "has_tool_results": bool(msg.tool_results),
                    "model_slug": msg.metadata.get("model_slug", ""),
                })

                relationships.append({
                    "type": "HAS_MESSAGE",
                    "source_name": conv_name,
                    "source_label": "Conversation",
                    "target_name": msg_name,
                    "target_label": "Message",
                })

                if prev_msg_name:
                    relationships.append({
                        "type": "NEXT",
                        "source_name": prev_msg_name,
                        "source_label": "Message",
                        "target_name": msg_name,
                        "target_label": "Message",
                    })

                prev_msg_name = msg_name

                role_label = msg.role.capitalize()
                if content:
                    doc_parts.append(f"**{role_label}**: {content}")

            if doc_parts:
                doc_content = "\n\n".join(doc_parts)
                documents.append({
                    "title": f"ChatGPT: {conv.title} [{conv.conversation_id[:_ID_PREFIX_LEN]}]",
                    "content": doc_content[:MAX_DOC_LEN],
                    "template_id": "chat-import",
                    "template_name": "ChatGPT Conversation",
                    "conversation_id": conv.conversation_id,
                    "source": "chatgpt",
                    "created_at": conv.created_at.isoformat(),
                })

            # Deep mode: extract tool/code interpreter traces
            if self._depth == "deep":
                trace = self._extract_tool_trace(conv)
                if trace:
                    traces.append(trace)

        if conversation_entities:
            entities["Conversation"] = conversation_entities
        if message_entities:
            entities["Message"] = message_entities

        return NormalizedData(
            entities=entities,
            relationships=relationships,
            documents=documents,
            traces=traces,
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _extract_tool_trace(self, conv: Any) -> dict[str, Any] | None:
        """Extract tool/code interpreter results as a decision trace."""
        steps: list[dict[str, str]] = []
        for msg in conv.messages:
            for tr in msg.tool_results:
                steps.append({
                    "thought": "Code execution in conversation",
                    "action": f"tool_result: {tr.get('type', 'unknown')}",
                    "observation": str(tr.get("content", ""))[:500],
                })

        if not steps:
            return None

        return {
            "id": f"chatgpt-trace-{conv.conversation_id[:12]}",
            "task": f"Tool usage in: {conv.title}",
            "outcome": f"{len(steps)} tool results across conversation",
            "steps": steps,
        }
