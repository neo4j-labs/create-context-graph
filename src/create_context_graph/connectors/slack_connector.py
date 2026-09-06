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

"""Slack connector — imports channels, messages, and users."""

from __future__ import annotations

from typing import Any

from create_context_graph.connectors import (
    BaseConnector,
    NormalizedData,
    register_connector,
)


@register_connector("slack")
class SlackConnector(BaseConnector):
    """Import data from Slack workspaces."""

    service_name = "Slack"
    service_description = "Import channel messages and threads from a Slack workspace"
    requires_oauth = False  # Uses bot token

    def __init__(self):
        self._client = None

    def get_credential_prompts(self) -> list[dict[str, Any]]:
        return [
            {
                "name": "token",
                "prompt": "Slack Bot OAuth token (xoxb-...):",
                "secret": True,
                "description": "Bot token from https://api.slack.com/apps — needs channels:read, channels:history, users:read scopes",
            },
            {
                "name": "channels",
                "prompt": "Channel names to import (comma-separated, or 'all'):",
                "secret": False,
                "description": "e.g. general,engineering,product or 'all' for all public channels",
            },
        ]

    def authenticate(self, credentials: dict[str, str]) -> None:
        try:
            from slack_sdk import WebClient
        except ImportError:
            raise ImportError(
                "slack-sdk is required for the Slack connector. "
                "Install it with: pip install slack-sdk"
            )

        retry_handlers = []
        try:
            # Slack's 2025-05-29 tier change rate-limits conversations.history to
            # 1 request/minute for new non-Marketplace apps; retry on 429 instead
            # of silently dropping channels.
            from slack_sdk.http_retry.builtin_handlers import RateLimitErrorRetryHandler
            retry_handlers.append(RateLimitErrorRetryHandler(max_retry_count=3))
        except ImportError:
            pass
        self._client = WebClient(token=credentials["token"], retry_handlers=retry_handlers)
        self._channel_filter = credentials.get("channels", "all")

    def fetch(self, **kwargs: Any) -> NormalizedData:
        if not self._client:
            raise RuntimeError("Call authenticate() first")

        limit = kwargs.get("limit", 200)
        entities: dict[str, list[dict]] = {
            "Person": [],
            "Channel": [],
            "Message": [],
        }
        relationships: list[dict] = []
        documents: list[dict] = []
        seen_users: set[str] = set()

        def _resolve_user(user_id: str) -> str:
            if user_id in seen_users:
                return user_id
            try:
                resp = self._client.users_info(user=user_id)
                user = resp.get("user", {})
                name = user.get("real_name") or user.get("name", user_id)
                seen_users.add(user_id)
                entities["Person"].append({
                    "name": name,
                    "email": user.get("profile", {}).get("email", ""),
                    "role": "slack-user",
                    "description": user.get("profile", {}).get("title", ""),
                })
                return name
            except Exception:
                seen_users.add(user_id)
                return user_id

        # Get channels
        channels_resp = self._client.conversations_list(
            types="public_channel",
            limit=200,
        )
        channels = channels_resp.get("channels", [])

        # Filter channels if specified
        if self._channel_filter and self._channel_filter != "all":
            filter_names = {c.strip() for c in self._channel_filter.split(",")}
            channels = [c for c in channels if c.get("name") in filter_names]

        for channel in channels:
            channel_name = channel.get("name", "")
            channel_id = channel.get("id", "")

            entities["Channel"].append({
                "name": channel_name,
                "channel_id": channel_id,
                "topic": channel.get("topic", {}).get("value", ""),
                "purpose": channel.get("purpose", {}).get("value", ""),
                "member_count": channel.get("num_members", 0),
            })

            # Get messages
            try:
                history = self._client.conversations_history(
                    channel=channel_id,
                    limit=min(limit, 200),
                )
            except Exception:
                continue

            for msg in history.get("messages", []):
                text = msg.get("text", "")
                if not text or msg.get("subtype"):
                    continue  # Skip system messages

                user_id = msg.get("user", "unknown")
                user_name = _resolve_user(user_id)
                ts = msg.get("ts", "")

                entities["Message"].append({
                    "name": text[:80],
                    "text": text,
                    "timestamp": ts,
                    "thread_ts": msg.get("thread_ts", ""),
                    "reply_count": msg.get("reply_count", 0),
                })

                relationships.append({
                    "type": "POSTED_IN",
                    "source_name": text[:80],
                    "source_label": "Message",
                    "target_name": channel_name,
                    "target_label": "Channel",
                })
                relationships.append({
                    "type": "SENT_BY",
                    "source_name": text[:80],
                    "source_label": "Message",
                    "target_name": user_name,
                    "target_label": "Person",
                })

                # Longer messages become documents
                if len(text) > 100:
                    documents.append({
                        "title": f"#{channel_name}: {text[:60]}...",
                        "content": text,
                        "type": "slack-message",
                        "metadata": {
                            "channel": channel_name,
                            "author": user_name,
                            "timestamp": ts,
                        },
                    })

        return NormalizedData(
            entities=entities,
            relationships=relationships,
            documents=documents,
        )
