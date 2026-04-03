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

"""Tests for Claude AI and ChatGPT chat history import connectors."""

import json
import zipfile
from datetime import datetime, timezone
from pathlib import Path

import pytest


from create_context_graph.connectors._chat_import.zip_reader import (
    detect_format,
    read_json,
    stream_jsonl,
)
from create_context_graph.connectors._claude_ai.parser import (
    parse_conversations as parse_claude_conversations,
)
from create_context_graph.connectors._chatgpt.parser import (
    parse_conversations as parse_chatgpt_conversations,
)
from create_context_graph.connectors.claude_ai_connector import ClaudeAIConnector
from create_context_graph.connectors.chatgpt_connector import ChatGPTConnector


# ---------------------------------------------------------------------------
# Test fixtures — minimal but realistic export data
# ---------------------------------------------------------------------------

CLAUDE_CONVERSATION_1 = {
    "uuid": "conv-001-claude-ai-test",
    "name": "Help with Python decorators",
    "created_at": "2026-01-15T10:30:00.000000+00:00",
    "updated_at": "2026-01-15T11:45:00.000000+00:00",
    "account": {"uuid": "account-001"},
    "chat_messages": [
        {
            "uuid": "msg-001",
            "text": "How do Python decorators work?",
            "sender": "human",
            "created_at": "2026-01-15T10:30:00.000000+00:00",
            "updated_at": "2026-01-15T10:30:00.000000+00:00",
            "attachments": [],
            "files": [],
            "content": [
                {"type": "text", "text": "How do Python decorators work?"}
            ],
        },
        {
            "uuid": "msg-002",
            "text": "Python decorators are functions that modify other functions.",
            "sender": "assistant",
            "created_at": "2026-01-15T10:30:30.000000+00:00",
            "updated_at": "2026-01-15T10:30:30.000000+00:00",
            "attachments": [],
            "files": [],
            "content": [
                {
                    "type": "text",
                    "text": "Python decorators are functions that modify other functions.",
                }
            ],
        },
    ],
}

CLAUDE_CONVERSATION_2 = {
    "uuid": "conv-002-claude-ai-test",
    "name": "Neo4j Cypher queries",
    "created_at": "2026-02-10T14:00:00.000000+00:00",
    "updated_at": "2026-02-10T15:30:00.000000+00:00",
    "account": {"uuid": "account-001"},
    "chat_messages": [
        {
            "uuid": "msg-003",
            "text": "Show me a MATCH query",
            "sender": "human",
            "created_at": "2026-02-10T14:00:00.000000+00:00",
            "content": [
                {"type": "text", "text": "Show me a MATCH query"}
            ],
        },
    ],
}

CLAUDE_CONVERSATION_WITH_TOOLS = {
    "uuid": "conv-003-tool-test",
    "name": "Tool usage example",
    "created_at": "2026-03-01T09:00:00.000000+00:00",
    "updated_at": "2026-03-01T10:00:00.000000+00:00",
    "account": {"uuid": "account-001"},
    "chat_messages": [
        {
            "uuid": "msg-010",
            "text": "Search for something",
            "sender": "human",
            "created_at": "2026-03-01T09:00:00.000000+00:00",
            "content": [
                {"type": "text", "text": "Search for something"}
            ],
        },
        {
            "uuid": "msg-011",
            "text": "",
            "sender": "assistant",
            "created_at": "2026-03-01T09:00:30.000000+00:00",
            "content": [
                {"type": "thinking", "thinking": "I need to search the web for this."},
                {
                    "type": "tool_use",
                    "id": "tool-001",
                    "name": "web_search",
                    "input": {"query": "something"},
                },
                {
                    "type": "tool_result",
                    "tool_use_id": "tool-001",
                    "content": "Search results here",
                },
                {"type": "text", "text": "Here are the results."},
            ],
        },
    ],
}


CHATGPT_CONVERSATION_1 = {
    "title": "JavaScript async/await",
    "create_time": 1706025600.123,  # 2024-01-23T16:00:00 UTC
    "update_time": 1706029200.456,
    "conversation_id": "conv-001-chatgpt-test",
    "default_model_slug": "gpt-4o",
    "mapping": {
        "root-node": {
            "id": "root-node",
            "parent": None,
            "children": ["sys-node"],
            "message": None,
        },
        "sys-node": {
            "id": "sys-node",
            "parent": "root-node",
            "children": ["user-msg-1"],
            "message": {
                "id": "sys-msg",
                "author": {"role": "system"},
                "create_time": 1706025600.0,
                "content": {"content_type": "text", "parts": ["System prompt"]},
                "metadata": {},
            },
        },
        "user-msg-1": {
            "id": "user-msg-1",
            "parent": "sys-node",
            "children": ["asst-msg-1"],
            "message": {
                "id": "user-msg-1",
                "author": {"role": "user"},
                "create_time": 1706025601.0,
                "content": {
                    "content_type": "text",
                    "parts": ["How does async/await work in JavaScript?"],
                },
                "metadata": {},
            },
        },
        "asst-msg-1": {
            "id": "asst-msg-1",
            "parent": "user-msg-1",
            "children": [],
            "message": {
                "id": "asst-msg-1",
                "author": {"role": "assistant"},
                "create_time": 1706025630.0,
                "content": {
                    "content_type": "text",
                    "parts": [
                        "Async/await is syntactic sugar over Promises in JavaScript."
                    ],
                },
                "metadata": {"model_slug": "gpt-4o"},
            },
        },
    },
}

CHATGPT_CONVERSATION_BRANCHING = {
    "title": "Branching conversation",
    "create_time": 1706100000.0,
    "update_time": 1706103600.0,
    "conversation_id": "conv-002-chatgpt-branch",
    "mapping": {
        "root": {
            "id": "root",
            "parent": None,
            "children": ["user-1"],
            "message": None,
        },
        "user-1": {
            "id": "user-1",
            "parent": "root",
            "children": ["asst-branch-a", "asst-branch-b"],
            "message": {
                "id": "user-1",
                "author": {"role": "user"},
                "create_time": 1706100001.0,
                "content": {"content_type": "text", "parts": ["Tell me a joke"]},
                "metadata": {},
            },
        },
        "asst-branch-a": {
            "id": "asst-branch-a",
            "parent": "user-1",
            "children": [],
            "message": {
                "id": "asst-branch-a",
                "author": {"role": "assistant"},
                "create_time": 1706100010.0,
                "content": {"content_type": "text", "parts": ["First branch answer"]},
                "metadata": {},
            },
        },
        "asst-branch-b": {
            "id": "asst-branch-b",
            "parent": "user-1",
            "children": [],
            "message": {
                "id": "asst-branch-b",
                "author": {"role": "assistant"},
                "create_time": 1706100020.0,
                "content": {"content_type": "text", "parts": ["Second branch answer (latest)"]},
                "metadata": {},
            },
        },
    },
}

CHATGPT_CONVERSATION_HIDDEN = {
    "title": "Hidden message test",
    "create_time": 1706200000.0,
    "update_time": 1706203600.0,
    "conversation_id": "conv-003-chatgpt-hidden",
    "mapping": {
        "root": {
            "id": "root",
            "parent": None,
            "children": ["user-1"],
            "message": None,
        },
        "user-1": {
            "id": "user-1",
            "parent": "root",
            "children": ["hidden-msg"],
            "message": {
                "id": "user-1",
                "author": {"role": "user"},
                "create_time": 1706200001.0,
                "content": {"content_type": "text", "parts": ["Hello"]},
                "metadata": {},
            },
        },
        "hidden-msg": {
            "id": "hidden-msg",
            "parent": "user-1",
            "children": ["asst-1"],
            "message": {
                "id": "hidden-msg",
                "author": {"role": "assistant"},
                "create_time": 1706200002.0,
                "content": {"content_type": "text", "parts": ["This is hidden"]},
                "metadata": {"is_visually_hidden_from_conversation": True},
            },
        },
        "asst-1": {
            "id": "asst-1",
            "parent": "hidden-msg",
            "children": [],
            "message": {
                "id": "asst-1",
                "author": {"role": "assistant"},
                "create_time": 1706200010.0,
                "content": {"content_type": "text", "parts": ["Visible response"]},
                "metadata": {},
            },
        },
    },
}

CHATGPT_CONVERSATION_TOOL = {
    "title": "Code interpreter test",
    "create_time": 1706300000.0,
    "update_time": 1706303600.0,
    "conversation_id": "conv-004-chatgpt-tool",
    "mapping": {
        "root": {
            "id": "root",
            "parent": None,
            "children": ["user-1"],
            "message": None,
        },
        "user-1": {
            "id": "user-1",
            "parent": "root",
            "children": ["tool-msg"],
            "message": {
                "id": "user-1",
                "author": {"role": "user"},
                "create_time": 1706300001.0,
                "content": {"content_type": "text", "parts": ["Run some code"]},
                "metadata": {},
            },
        },
        "tool-msg": {
            "id": "tool-msg",
            "parent": "user-1",
            "children": ["asst-1"],
            "message": {
                "id": "tool-msg",
                "author": {"role": "tool"},
                "create_time": 1706300010.0,
                "content": {
                    "content_type": "execution_output",
                    "parts": ["42"],
                },
                "metadata": {},
            },
        },
        "asst-1": {
            "id": "asst-1",
            "parent": "tool-msg",
            "children": [],
            "message": {
                "id": "asst-1",
                "author": {"role": "assistant"},
                "create_time": 1706300020.0,
                "content": {"content_type": "text", "parts": ["The answer is 42."]},
                "metadata": {},
            },
        },
    },
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_claude_zip(tmp_path: Path, conversations: list[dict]) -> Path:
    """Create a Claude AI export zip in tmp_path."""
    jsonl_lines = "\n".join(json.dumps(c) for c in conversations)
    zip_path = tmp_path / "claude-export.zip"
    with zipfile.ZipFile(zip_path, "w") as zf:
        zf.writestr("conversations.jsonl", jsonl_lines)
    return zip_path


def _make_claude_jsonl(tmp_path: Path, conversations: list[dict]) -> Path:
    """Create a raw Claude AI JSONL file in tmp_path."""
    jsonl_path = tmp_path / "conversations.jsonl"
    jsonl_path.write_text("\n".join(json.dumps(c) for c in conversations))
    return jsonl_path


def _make_chatgpt_zip(tmp_path: Path, conversations: list[dict]) -> Path:
    """Create a ChatGPT export zip in tmp_path."""
    zip_path = tmp_path / "chatgpt-export.zip"
    with zipfile.ZipFile(zip_path, "w") as zf:
        zf.writestr("conversations.json", json.dumps(conversations))
    return zip_path


def _make_chatgpt_json(tmp_path: Path, conversations: list[dict]) -> Path:
    """Create a raw ChatGPT JSON file in tmp_path."""
    json_path = tmp_path / "conversations.json"
    json_path.write_text(json.dumps(conversations))
    return json_path


# ---------------------------------------------------------------------------
# Zip reader tests
# ---------------------------------------------------------------------------


class TestZipReader:
    def test_detect_claude_ai_from_zip(self, tmp_path):
        path = _make_claude_zip(tmp_path, [CLAUDE_CONVERSATION_1])
        assert detect_format(path) == "claude-ai"

    def test_detect_chatgpt_from_zip(self, tmp_path):
        path = _make_chatgpt_zip(tmp_path, [CHATGPT_CONVERSATION_1])
        assert detect_format(path) == "chatgpt"

    def test_detect_claude_ai_from_jsonl(self, tmp_path):
        path = _make_claude_jsonl(tmp_path, [CLAUDE_CONVERSATION_1])
        assert detect_format(path) == "claude-ai"

    def test_detect_chatgpt_from_json(self, tmp_path):
        path = _make_chatgpt_json(tmp_path, [CHATGPT_CONVERSATION_1])
        assert detect_format(path) == "chatgpt"

    def test_detect_unknown_extension(self, tmp_path):
        path = tmp_path / "data.csv"
        path.write_text("a,b,c")
        with pytest.raises(ValueError, match="Unsupported file type"):
            detect_format(path)

    def test_detect_zip_without_known_files(self, tmp_path):
        path = tmp_path / "unknown.zip"
        with zipfile.ZipFile(path, "w") as zf:
            zf.writestr("random.txt", "hello")
        with pytest.raises(ValueError, match="does not contain"):
            detect_format(path)

    def test_stream_jsonl_from_zip(self, tmp_path):
        path = _make_claude_zip(tmp_path, [CLAUDE_CONVERSATION_1, CLAUDE_CONVERSATION_2])
        results = list(stream_jsonl(path))
        assert len(results) == 2
        assert results[0]["uuid"] == "conv-001-claude-ai-test"
        assert results[1]["uuid"] == "conv-002-claude-ai-test"

    def test_stream_jsonl_from_raw_file(self, tmp_path):
        path = _make_claude_jsonl(tmp_path, [CLAUDE_CONVERSATION_1])
        results = list(stream_jsonl(path))
        assert len(results) == 1
        assert results[0]["uuid"] == "conv-001-claude-ai-test"

    def test_stream_jsonl_skips_malformed(self, tmp_path):
        path = tmp_path / "bad.jsonl"
        path.write_text('{"uuid":"good"}\n{INVALID JSON}\n{"uuid":"good2"}')
        results = list(stream_jsonl(path))
        assert len(results) == 2

    def test_stream_jsonl_skips_empty_lines(self, tmp_path):
        path = tmp_path / "sparse.jsonl"
        path.write_text('{"a":1}\n\n\n{"b":2}\n')
        results = list(stream_jsonl(path))
        assert len(results) == 2

    def test_read_json_from_zip(self, tmp_path):
        path = _make_chatgpt_zip(tmp_path, [CHATGPT_CONVERSATION_1])
        results = read_json(path)
        assert len(results) == 1
        assert results[0]["conversation_id"] == "conv-001-chatgpt-test"

    def test_read_json_from_raw_file(self, tmp_path):
        path = _make_chatgpt_json(tmp_path, [CHATGPT_CONVERSATION_1])
        results = read_json(path)
        assert len(results) == 1

    def test_read_json_rejects_non_array(self, tmp_path):
        path = tmp_path / "obj.json"
        path.write_text('{"not": "an array"}')
        with pytest.raises(ValueError, match="Expected a JSON array"):
            read_json(path)

    def test_stream_jsonl_missing_file_in_zip(self, tmp_path):
        path = tmp_path / "no-jsonl.zip"
        with zipfile.ZipFile(path, "w") as zf:
            zf.writestr("other.txt", "hello")
        with pytest.raises(ValueError, match="conversations.jsonl"):
            list(stream_jsonl(path))

    def test_read_json_missing_file_in_zip(self, tmp_path):
        path = tmp_path / "no-json.zip"
        with zipfile.ZipFile(path, "w") as zf:
            zf.writestr("other.txt", "hello")
        with pytest.raises(ValueError, match="conversations.json"):
            read_json(path)


# ---------------------------------------------------------------------------
# Claude AI parser tests
# ---------------------------------------------------------------------------


class TestClaudeAIParser:
    def test_single_conversation(self, tmp_path):
        path = _make_claude_jsonl(tmp_path, [CLAUDE_CONVERSATION_1])
        convs = parse_claude_conversations(path)
        assert len(convs) == 1
        assert convs[0].source == "claude-ai"
        assert convs[0].conversation_id == "conv-001-claude-ai-test"
        assert convs[0].title == "Help with Python decorators"

    def test_multi_conversation(self, tmp_path):
        path = _make_claude_jsonl(tmp_path, [CLAUDE_CONVERSATION_1, CLAUDE_CONVERSATION_2])
        convs = parse_claude_conversations(path)
        assert len(convs) == 2

    def test_from_zip(self, tmp_path):
        path = _make_claude_zip(tmp_path, [CLAUDE_CONVERSATION_1])
        convs = parse_claude_conversations(path)
        assert len(convs) == 1
        assert convs[0].title == "Help with Python decorators"

    def test_message_parsing(self, tmp_path):
        path = _make_claude_jsonl(tmp_path, [CLAUDE_CONVERSATION_1])
        convs = parse_claude_conversations(path)
        msgs = convs[0].messages
        assert len(msgs) == 2
        assert msgs[0].role == "user"
        assert msgs[0].content == "How do Python decorators work?"
        assert msgs[1].role == "assistant"

    def test_sender_normalization(self, tmp_path):
        path = _make_claude_jsonl(tmp_path, [CLAUDE_CONVERSATION_1])
        convs = parse_claude_conversations(path)
        # "human" -> "user", "assistant" -> "assistant"
        assert convs[0].messages[0].role == "user"
        assert convs[0].messages[1].role == "assistant"

    def test_content_block_extraction(self, tmp_path):
        path = _make_claude_jsonl(tmp_path, [CLAUDE_CONVERSATION_WITH_TOOLS])
        convs = parse_claude_conversations(path)
        msgs = convs[0].messages
        # Second message has tool_use, tool_result, thinking, and text
        asst_msg = msgs[1]
        assert asst_msg.content == "Here are the results."
        assert len(asst_msg.tool_calls) == 1
        assert asst_msg.tool_calls[0]["name"] == "web_search"
        assert len(asst_msg.tool_results) == 1
        assert asst_msg.thinking == "I need to search the web for this."

    def test_timestamp_parsing(self, tmp_path):
        path = _make_claude_jsonl(tmp_path, [CLAUDE_CONVERSATION_1])
        convs = parse_claude_conversations(path)
        assert convs[0].created_at.year == 2026
        assert convs[0].created_at.month == 1
        assert convs[0].created_at.day == 15

    def test_filter_after(self, tmp_path):
        path = _make_claude_jsonl(tmp_path, [CLAUDE_CONVERSATION_1, CLAUDE_CONVERSATION_2])
        after = datetime(2026, 2, 1, tzinfo=timezone.utc)
        convs = parse_claude_conversations(path, filter_after=after)
        assert len(convs) == 1
        assert convs[0].title == "Neo4j Cypher queries"

    def test_filter_before(self, tmp_path):
        path = _make_claude_jsonl(tmp_path, [CLAUDE_CONVERSATION_1, CLAUDE_CONVERSATION_2])
        before = datetime(2026, 2, 1, tzinfo=timezone.utc)
        convs = parse_claude_conversations(path, filter_before=before)
        assert len(convs) == 1
        assert convs[0].title == "Help with Python decorators"

    def test_filter_title(self, tmp_path):
        path = _make_claude_jsonl(tmp_path, [CLAUDE_CONVERSATION_1, CLAUDE_CONVERSATION_2])
        convs = parse_claude_conversations(path, filter_title="cypher")
        assert len(convs) == 1
        assert convs[0].title == "Neo4j Cypher queries"

    def test_max_conversations(self, tmp_path):
        path = _make_claude_jsonl(tmp_path, [CLAUDE_CONVERSATION_1, CLAUDE_CONVERSATION_2])
        convs = parse_claude_conversations(path, max_conversations=1)
        assert len(convs) == 1

    def test_malformed_conversation_skipped(self, tmp_path):
        """Conversations missing required fields are skipped."""
        bad_conv = {"name": "Missing uuid"}
        path = _make_claude_jsonl(tmp_path, [bad_conv, CLAUDE_CONVERSATION_1])
        convs = parse_claude_conversations(path)
        assert len(convs) == 1
        assert convs[0].title == "Help with Python decorators"

    def test_empty_conversations(self, tmp_path):
        conv = {
            "uuid": "conv-empty",
            "name": "Empty",
            "created_at": "2026-01-01T00:00:00+00:00",
            "updated_at": "2026-01-01T00:00:00+00:00",
            "chat_messages": [],
        }
        path = _make_claude_jsonl(tmp_path, [conv])
        convs = parse_claude_conversations(path)
        assert len(convs) == 1
        assert len(convs[0].messages) == 0

    def test_text_fallback_when_no_content_blocks(self, tmp_path):
        """When content blocks are missing, fall back to the text field."""
        conv = {
            "uuid": "conv-text-fallback",
            "name": "Text fallback",
            "created_at": "2026-01-01T00:00:00+00:00",
            "updated_at": "2026-01-01T00:00:00+00:00",
            "chat_messages": [
                {
                    "uuid": "msg-fb",
                    "text": "Fallback text content",
                    "sender": "human",
                    "created_at": "2026-01-01T00:00:00+00:00",
                    "content": [],
                },
            ],
        }
        path = _make_claude_jsonl(tmp_path, [conv])
        convs = parse_claude_conversations(path)
        assert convs[0].messages[0].content == "Fallback text content"

    def test_metadata_account_uuid(self, tmp_path):
        path = _make_claude_jsonl(tmp_path, [CLAUDE_CONVERSATION_1])
        convs = parse_claude_conversations(path)
        assert convs[0].metadata.get("account_uuid") == "account-001"


# ---------------------------------------------------------------------------
# ChatGPT parser tests
# ---------------------------------------------------------------------------


class TestChatGPTParser:
    def test_single_conversation(self, tmp_path):
        path = _make_chatgpt_json(tmp_path, [CHATGPT_CONVERSATION_1])
        convs = parse_chatgpt_conversations(path)
        assert len(convs) == 1
        assert convs[0].source == "chatgpt"
        assert convs[0].conversation_id == "conv-001-chatgpt-test"
        assert convs[0].title == "JavaScript async/await"

    def test_from_zip(self, tmp_path):
        path = _make_chatgpt_zip(tmp_path, [CHATGPT_CONVERSATION_1])
        convs = parse_chatgpt_conversations(path)
        assert len(convs) == 1

    def test_system_messages_filtered(self, tmp_path):
        path = _make_chatgpt_json(tmp_path, [CHATGPT_CONVERSATION_1])
        convs = parse_chatgpt_conversations(path)
        msgs = convs[0].messages
        # Only user + assistant messages, system is filtered
        assert len(msgs) == 2
        roles = [m.role for m in msgs]
        assert "system" not in roles

    def test_message_content(self, tmp_path):
        path = _make_chatgpt_json(tmp_path, [CHATGPT_CONVERSATION_1])
        convs = parse_chatgpt_conversations(path)
        msgs = convs[0].messages
        assert msgs[0].content == "How does async/await work in JavaScript?"
        assert "syntactic sugar" in msgs[1].content

    def test_unix_timestamp_conversion(self, tmp_path):
        path = _make_chatgpt_json(tmp_path, [CHATGPT_CONVERSATION_1])
        convs = parse_chatgpt_conversations(path)
        # create_time=1706025600.123 -> 2024-01-23
        assert convs[0].created_at.year == 2024
        assert convs[0].created_at.month == 1

    def test_branching_follows_last_child(self, tmp_path):
        """At branch points, the parser follows the last child."""
        path = _make_chatgpt_json(tmp_path, [CHATGPT_CONVERSATION_BRANCHING])
        convs = parse_chatgpt_conversations(path)
        msgs = convs[0].messages
        assert len(msgs) == 2  # user + last branch
        assert msgs[0].content == "Tell me a joke"
        assert "latest" in msgs[1].content

    def test_hidden_messages_filtered(self, tmp_path):
        path = _make_chatgpt_json(tmp_path, [CHATGPT_CONVERSATION_HIDDEN])
        convs = parse_chatgpt_conversations(path)
        msgs = convs[0].messages
        # Hidden message should be filtered out
        contents = [m.content for m in msgs]
        assert "This is hidden" not in contents
        assert "Hello" in contents
        assert "Visible response" in contents

    def test_tool_role_messages(self, tmp_path):
        path = _make_chatgpt_json(tmp_path, [CHATGPT_CONVERSATION_TOOL])
        convs = parse_chatgpt_conversations(path)
        msgs = convs[0].messages
        # Should include user, tool, assistant
        assert len(msgs) == 3
        tool_msg = [m for m in msgs if m.role == "tool"]
        assert len(tool_msg) == 1
        assert tool_msg[0].tool_results[0]["content"] == "42"

    def test_filter_after(self, tmp_path):
        path = _make_chatgpt_json(
            tmp_path, [CHATGPT_CONVERSATION_1, CHATGPT_CONVERSATION_BRANCHING]
        )
        after = datetime(2024, 1, 24, tzinfo=timezone.utc)
        convs = parse_chatgpt_conversations(path, filter_after=after)
        assert len(convs) == 1
        assert convs[0].title == "Branching conversation"

    def test_filter_title(self, tmp_path):
        path = _make_chatgpt_json(
            tmp_path, [CHATGPT_CONVERSATION_1, CHATGPT_CONVERSATION_BRANCHING]
        )
        convs = parse_chatgpt_conversations(path, filter_title="async")
        assert len(convs) == 1
        assert convs[0].title == "JavaScript async/await"

    def test_max_conversations(self, tmp_path):
        path = _make_chatgpt_json(
            tmp_path, [CHATGPT_CONVERSATION_1, CHATGPT_CONVERSATION_BRANCHING]
        )
        convs = parse_chatgpt_conversations(path, max_conversations=1)
        assert len(convs) == 1

    def test_null_message_nodes(self, tmp_path):
        """Nodes with message=None (like root) are handled gracefully."""
        path = _make_chatgpt_json(tmp_path, [CHATGPT_CONVERSATION_1])
        convs = parse_chatgpt_conversations(path)
        # Root node has message=None — should not appear in output
        assert all(m.content for m in convs[0].messages)

    def test_empty_mapping(self, tmp_path):
        conv = {
            "conversation_id": "empty-map",
            "title": "Empty",
            "create_time": 1706025600.0,
            "update_time": 1706025600.0,
            "mapping": {},
        }
        path = _make_chatgpt_json(tmp_path, [conv])
        convs = parse_chatgpt_conversations(path)
        assert len(convs) == 1
        assert len(convs[0].messages) == 0

    def test_model_slug_metadata(self, tmp_path):
        path = _make_chatgpt_json(tmp_path, [CHATGPT_CONVERSATION_1])
        convs = parse_chatgpt_conversations(path)
        assert convs[0].metadata.get("model_slug") == "gpt-4o"

    def test_malformed_conversation_skipped(self, tmp_path):
        bad_conv = {"title": "Missing conversation_id"}
        path = _make_chatgpt_json(
            tmp_path, [bad_conv, CHATGPT_CONVERSATION_1]
        )
        convs = parse_chatgpt_conversations(path)
        assert len(convs) == 1
        assert convs[0].title == "JavaScript async/await"


# ---------------------------------------------------------------------------
# Claude AI connector tests
# ---------------------------------------------------------------------------


class TestClaudeAIConnector:
    def test_registration(self):
        from create_context_graph.connectors import get_connector
        conn = get_connector("claude-ai")
        assert isinstance(conn, ClaudeAIConnector)

    def test_service_name(self):
        conn = ClaudeAIConnector()
        assert conn.service_name == "Claude AI"

    def test_credential_prompts_empty(self):
        conn = ClaudeAIConnector()
        assert conn.get_credential_prompts() == []

    def test_authenticate_with_file_path(self, tmp_path):
        path = _make_claude_zip(tmp_path, [CLAUDE_CONVERSATION_1])
        conn = ClaudeAIConnector()
        conn.authenticate({"file_path": str(path)})
        assert conn._file_path == str(path)

    def test_authenticate_file_not_found(self, tmp_path):
        conn = ClaudeAIConnector()
        with pytest.raises(FileNotFoundError):
            conn.authenticate({"file_path": str(tmp_path / "missing.zip")})

    def test_authenticate_wrong_extension(self, tmp_path):
        path = tmp_path / "data.csv"
        path.write_text("a,b,c")
        conn = ClaudeAIConnector()
        with pytest.raises(ValueError, match="Expected .zip or .jsonl"):
            conn.authenticate({"file_path": str(path)})

    def test_fetch_returns_normalized_data(self, tmp_path):
        path = _make_claude_zip(tmp_path, [CLAUDE_CONVERSATION_1])
        conn = ClaudeAIConnector()
        conn.authenticate({"file_path": str(path)})
        data = conn.fetch()
        assert "Conversation" in data.entities
        assert "Message" in data.entities
        assert len(data.entities["Conversation"]) == 1
        assert len(data.entities["Message"]) == 2

    def test_fetch_entity_properties(self, tmp_path):
        path = _make_claude_zip(tmp_path, [CLAUDE_CONVERSATION_1])
        conn = ClaudeAIConnector()
        conn.authenticate({"file_path": str(path)})
        data = conn.fetch()
        conv = data.entities["Conversation"][0]
        assert conv["name"] == "conv-conv-001-claude-ai-test"
        assert conv["title"] == "Help with Python decorators"
        assert conv["source"] == "claude-ai"
        assert conv["message_count"] == 2

    def test_fetch_relationships(self, tmp_path):
        path = _make_claude_zip(tmp_path, [CLAUDE_CONVERSATION_1])
        conn = ClaudeAIConnector()
        conn.authenticate({"file_path": str(path)})
        data = conn.fetch()
        has_msg_rels = [r for r in data.relationships if r["type"] == "HAS_MESSAGE"]
        next_rels = [r for r in data.relationships if r["type"] == "NEXT"]
        assert len(has_msg_rels) == 2
        assert len(next_rels) == 1

    def test_fetch_documents(self, tmp_path):
        path = _make_claude_zip(tmp_path, [CLAUDE_CONVERSATION_1])
        conn = ClaudeAIConnector()
        conn.authenticate({"file_path": str(path)})
        data = conn.fetch()
        assert len(data.documents) == 1
        assert "Claude AI" in data.documents[0]["title"]
        assert data.documents[0]["source"] == "claude-ai"

    def test_fetch_empty_file(self):
        conn = ClaudeAIConnector()
        conn.authenticate({})  # No file path
        data = conn.fetch()
        assert data.entities == {}

    def test_fetch_multiple_conversations(self, tmp_path):
        path = _make_claude_zip(
            tmp_path, [CLAUDE_CONVERSATION_1, CLAUDE_CONVERSATION_2]
        )
        conn = ClaudeAIConnector()
        conn.authenticate({"file_path": str(path)})
        data = conn.fetch()
        assert len(data.entities["Conversation"]) == 2

    def test_fetch_with_filters(self, tmp_path):
        path = _make_claude_zip(
            tmp_path, [CLAUDE_CONVERSATION_1, CLAUDE_CONVERSATION_2]
        )
        conn = ClaudeAIConnector()
        conn.authenticate({
            "file_path": str(path),
            "filter_after": "2026-02-01",
        })
        data = conn.fetch()
        assert len(data.entities["Conversation"]) == 1

    def test_fetch_deep_mode_traces(self, tmp_path):
        path = _make_claude_zip(tmp_path, [CLAUDE_CONVERSATION_WITH_TOOLS])
        conn = ClaudeAIConnector()
        conn.authenticate({"file_path": str(path), "depth": "deep"})
        data = conn.fetch()
        assert len(data.traces) == 1
        assert data.traces[0]["id"].startswith("claude-ai-trace-")

    def test_fetch_fast_mode_no_traces(self, tmp_path):
        path = _make_claude_zip(tmp_path, [CLAUDE_CONVERSATION_WITH_TOOLS])
        conn = ClaudeAIConnector()
        conn.authenticate({"file_path": str(path), "depth": "fast"})
        data = conn.fetch()
        assert len(data.traces) == 0


# ---------------------------------------------------------------------------
# ChatGPT connector tests
# ---------------------------------------------------------------------------


class TestChatGPTConnector:
    def test_registration(self):
        from create_context_graph.connectors import get_connector
        conn = get_connector("chatgpt")
        assert isinstance(conn, ChatGPTConnector)

    def test_service_name(self):
        conn = ChatGPTConnector()
        assert conn.service_name == "ChatGPT"

    def test_credential_prompts_empty(self):
        conn = ChatGPTConnector()
        assert conn.get_credential_prompts() == []

    def test_authenticate_with_file_path(self, tmp_path):
        path = _make_chatgpt_zip(tmp_path, [CHATGPT_CONVERSATION_1])
        conn = ChatGPTConnector()
        conn.authenticate({"file_path": str(path)})
        assert conn._file_path == str(path)

    def test_authenticate_file_not_found(self, tmp_path):
        conn = ChatGPTConnector()
        with pytest.raises(FileNotFoundError):
            conn.authenticate({"file_path": str(tmp_path / "missing.zip")})

    def test_authenticate_wrong_extension(self, tmp_path):
        path = tmp_path / "data.csv"
        path.write_text("a,b,c")
        conn = ChatGPTConnector()
        with pytest.raises(ValueError, match="Expected .zip or .json"):
            conn.authenticate({"file_path": str(path)})

    def test_fetch_returns_normalized_data(self, tmp_path):
        path = _make_chatgpt_zip(tmp_path, [CHATGPT_CONVERSATION_1])
        conn = ChatGPTConnector()
        conn.authenticate({"file_path": str(path)})
        data = conn.fetch()
        assert "Conversation" in data.entities
        assert "Message" in data.entities
        assert len(data.entities["Conversation"]) == 1
        # 2 messages: user + assistant (system filtered)
        assert len(data.entities["Message"]) == 2

    def test_fetch_entity_properties(self, tmp_path):
        path = _make_chatgpt_zip(tmp_path, [CHATGPT_CONVERSATION_1])
        conn = ChatGPTConnector()
        conn.authenticate({"file_path": str(path)})
        data = conn.fetch()
        conv = data.entities["Conversation"][0]
        assert conv["name"] == "conv-conv-001-chatgpt-test"
        assert conv["title"] == "JavaScript async/await"
        assert conv["source"] == "chatgpt"
        assert conv["model_slug"] == "gpt-4o"

    def test_fetch_relationships(self, tmp_path):
        path = _make_chatgpt_zip(tmp_path, [CHATGPT_CONVERSATION_1])
        conn = ChatGPTConnector()
        conn.authenticate({"file_path": str(path)})
        data = conn.fetch()
        has_msg_rels = [r for r in data.relationships if r["type"] == "HAS_MESSAGE"]
        next_rels = [r for r in data.relationships if r["type"] == "NEXT"]
        assert len(has_msg_rels) == 2
        assert len(next_rels) == 1

    def test_fetch_documents(self, tmp_path):
        path = _make_chatgpt_zip(tmp_path, [CHATGPT_CONVERSATION_1])
        conn = ChatGPTConnector()
        conn.authenticate({"file_path": str(path)})
        data = conn.fetch()
        assert len(data.documents) == 1
        assert "ChatGPT" in data.documents[0]["title"]

    def test_fetch_empty_file(self):
        conn = ChatGPTConnector()
        conn.authenticate({})
        data = conn.fetch()
        assert data.entities == {}

    def test_fetch_branching_conversation(self, tmp_path):
        path = _make_chatgpt_zip(tmp_path, [CHATGPT_CONVERSATION_BRANCHING])
        conn = ChatGPTConnector()
        conn.authenticate({"file_path": str(path)})
        data = conn.fetch()
        # Should have 2 messages (user + last branch)
        assert len(data.entities["Message"]) == 2

    def test_fetch_hidden_messages_excluded(self, tmp_path):
        path = _make_chatgpt_zip(tmp_path, [CHATGPT_CONVERSATION_HIDDEN])
        conn = ChatGPTConnector()
        conn.authenticate({"file_path": str(path)})
        data = conn.fetch()
        msg_contents = [m["content"] for m in data.entities["Message"]]
        assert "This is hidden" not in msg_contents

    def test_fetch_with_tool_messages(self, tmp_path):
        path = _make_chatgpt_zip(tmp_path, [CHATGPT_CONVERSATION_TOOL])
        conn = ChatGPTConnector()
        conn.authenticate({"file_path": str(path)})
        data = conn.fetch()
        # user + tool + assistant = 3 messages
        assert len(data.entities["Message"]) == 3

    def test_fetch_with_filters(self, tmp_path):
        path = _make_chatgpt_zip(
            tmp_path,
            [CHATGPT_CONVERSATION_1, CHATGPT_CONVERSATION_BRANCHING],
        )
        conn = ChatGPTConnector()
        conn.authenticate({
            "file_path": str(path),
            "filter_title": "async",
        })
        data = conn.fetch()
        assert len(data.entities["Conversation"]) == 1

    def test_fetch_deep_mode_traces(self, tmp_path):
        path = _make_chatgpt_zip(tmp_path, [CHATGPT_CONVERSATION_TOOL])
        conn = ChatGPTConnector()
        conn.authenticate({"file_path": str(path), "depth": "deep"})
        data = conn.fetch()
        assert len(data.traces) == 1
        assert data.traces[0]["id"].startswith("chatgpt-trace-")

    def test_fetch_fast_mode_no_traces(self, tmp_path):
        path = _make_chatgpt_zip(tmp_path, [CHATGPT_CONVERSATION_TOOL])
        conn = ChatGPTConnector()
        conn.authenticate({"file_path": str(path), "depth": "fast"})
        data = conn.fetch()
        assert len(data.traces) == 0


# ---------------------------------------------------------------------------
# CLI flag tests
# ---------------------------------------------------------------------------


class TestChatImportCLI:
    def test_import_type_without_file_fails(self):
        from click.testing import CliRunner
        from create_context_graph.cli import main

        runner = CliRunner()
        result = runner.invoke(main, [
            "test-app", "--domain", "healthcare", "--framework", "pydanticai",
            "--import-type", "claude-ai",
        ])
        assert result.exit_code != 0
        assert "import-file" in result.output.lower() or result.exit_code == 1

    def test_import_file_without_type_fails(self, tmp_path):
        from click.testing import CliRunner
        from create_context_graph.cli import main

        dummy = tmp_path / "export.zip"
        dummy.write_bytes(b"")

        runner = CliRunner()
        result = runner.invoke(main, [
            "test-app", "--domain", "healthcare", "--framework", "pydanticai",
            "--import-file", str(dummy),
        ])
        assert result.exit_code != 0

    def test_import_flags_dry_run(self, tmp_path):
        from click.testing import CliRunner
        from create_context_graph.cli import main

        path = _make_claude_zip(tmp_path, [CLAUDE_CONVERSATION_1])
        runner = CliRunner()
        result = runner.invoke(main, [
            "test-app", "--domain", "healthcare", "--framework", "pydanticai",
            "--import-type", "claude-ai", "--import-file", str(path),
            "--dry-run",
        ])
        assert result.exit_code == 0
        assert "claude-ai" in result.output.lower()
