"""Tests for SSE parsing logic and frontend/backend contract validation.

Validates the streaming event protocol between backend (routes.py.j2) and
frontend (ChatInterface.tsx.j2), including SSE format parsing, the thinking/
response split algorithm, and contract consistency between templates.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

TEMPLATES_BASE = Path(__file__).resolve().parent.parent / "src" / "create_context_graph" / "templates"
ROUTES_TEMPLATE = TEMPLATES_BASE / "backend" / "shared" / "routes.py.j2"
CHAT_TEMPLATE = TEMPLATES_BASE / "frontend" / "components" / "ChatInterface.tsx.j2"
GRAPH_VIEW_TEMPLATE = TEMPLATES_BASE / "frontend" / "components" / "ContextGraphView.tsx.j2"
DOC_BROWSER_TEMPLATE = TEMPLATES_BASE / "frontend" / "components" / "DocumentBrowser.tsx.j2"
DECISION_TRACE_TEMPLATE = TEMPLATES_BASE / "frontend" / "components" / "DecisionTracePanel.tsx.j2"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def parse_sse_stream(raw: str) -> list[tuple[str, dict]]:
    """Parse an SSE-formatted string into (event_type, data_dict) tuples.

    Mirrors the frontend parser in ChatInterface.tsx.j2: each SSE message
    consists of ``event: <type>\\ndata: <json>\\n\\n``.  Malformed JSON in the
    data field raises ``json.JSONDecodeError``.
    """
    events: list[tuple[str, dict]] = []
    current_event_type = ""

    for line in raw.split("\n"):
        if line.startswith("event: "):
            current_event_type = line[7:].strip()
        elif line.startswith("data: ") and current_event_type:
            data = json.loads(line[6:])
            events.append((current_event_type, data))
            current_event_type = ""

    return events


# Python port of the TypeScript splitThinkingAndResponse() from ChatInterface.tsx.j2

_THINKING_PATTERNS = [
    re.compile(r"^let me ", re.IGNORECASE),
    re.compile(r"^i'll ", re.IGNORECASE),
    re.compile(r"^i will ", re.IGNORECASE),
    re.compile(r"^first,? i ", re.IGNORECASE),
    re.compile(r"^now let me ", re.IGNORECASE),
    re.compile(r"^let me also ", re.IGNORECASE),
    re.compile(r"^let me try ", re.IGNORECASE),
    re.compile(r"^i need to ", re.IGNORECASE),
    re.compile(r"^i should ", re.IGNORECASE),
    re.compile(r"^let me check ", re.IGNORECASE),
    re.compile(r"^let me look ", re.IGNORECASE),
    re.compile(r"^let me search ", re.IGNORECASE),
    re.compile(r"^let me query ", re.IGNORECASE),
    re.compile(r"^let me find ", re.IGNORECASE),
    re.compile(r"^now i'll ", re.IGNORECASE),
    re.compile(r"^now i need ", re.IGNORECASE),
]

_CONTINUATION_PATTERNS = [
    re.compile(r"^(and |also |then |additionally |next |finally )", re.IGNORECASE),
    re.compile(r"^(this will |this should |this means |that way )", re.IGNORECASE),
    re.compile(r"^(so |because |since |in order to )", re.IGNORECASE),
    re.compile(r"^(after that |once |before )", re.IGNORECASE),
]

_MARKDOWN_LINE = re.compile(r"^(#{1,6} |[-*] |\d+\. |\|)")


def split_thinking_and_response(text: str) -> tuple[str, str]:
    """Python port of ``splitThinkingAndResponse()`` from ChatInterface.tsx.j2.

    Returns ``(thinking, response)`` strings.
    """
    # Don't split if text contains error indicators
    if re.search(r"\berror\b", text, re.IGNORECASE) or re.search(r"\bfailed\b", text, re.IGNORECASE) or re.search(r"\bsyntax error\b", text, re.IGNORECASE):
        return ("", text)

    lines = text.split("\n")
    thinking_lines: list[str] = []
    response_lines: list[str] = []
    found_response = False
    in_thinking_block = False

    for line in lines:
        trimmed = line.strip()
        if not found_response and trimmed and any(p.search(trimmed) for p in _THINKING_PATTERNS):
            thinking_lines.append(line)
            in_thinking_block = True
        elif (
            in_thinking_block
            and not found_response
            and trimmed
            and not _MARKDOWN_LINE.search(trimmed)
            and (any(p.search(trimmed) for p in _CONTINUATION_PATTERNS) or len(trimmed) < 80)
        ):
            thinking_lines.append(line)
        else:
            if trimmed:
                found_response = True
                in_thinking_block = False
            response_lines.append(line)

    response = "\n".join(response_lines).strip()
    thinking = "\n".join(thinking_lines).strip()

    # If response is empty but we have thinking text, show everything as response
    if not response and thinking:
        return ("", text)

    return (thinking, response)


# ---------------------------------------------------------------------------
# 1. TestSSEEventParsing
# ---------------------------------------------------------------------------

class TestSSEEventParsing:
    """Python reimplementation of SSE parser matching frontend logic."""

    def test_parse_valid_session_id(self):
        raw = 'event: session_id\ndata: {"session_id": "abc"}\n\n'
        events = parse_sse_stream(raw)
        assert len(events) == 1
        assert events[0] == ("session_id", {"session_id": "abc"})

    def test_parse_valid_tool_start(self):
        data = {"name": "search_patients", "inputs": {"query": "diabetes"}}
        raw = f"event: tool_start\ndata: {json.dumps(data)}\n\n"
        events = parse_sse_stream(raw)
        assert len(events) == 1
        assert events[0][0] == "tool_start"
        assert events[0][1]["name"] == "search_patients"
        assert events[0][1]["inputs"] == {"query": "diabetes"}

    def test_parse_valid_tool_end(self):
        data = {
            "name": "search_patients",
            "output_preview": "Found 3 patients",
            "graph_data": {"results": [{"name": "John"}]},
        }
        raw = f"event: tool_end\ndata: {json.dumps(data)}\n\n"
        events = parse_sse_stream(raw)
        assert len(events) == 1
        assert events[0][0] == "tool_end"
        assert events[0][1]["output_preview"] == "Found 3 patients"
        assert events[0][1]["graph_data"]["results"] == [{"name": "John"}]

    def test_parse_valid_text_delta(self):
        data = {"text": "Here are the results"}
        raw = f"event: text_delta\ndata: {json.dumps(data)}\n\n"
        events = parse_sse_stream(raw)
        assert len(events) == 1
        assert events[0] == ("text_delta", {"text": "Here are the results"})

    def test_parse_valid_done(self):
        data = {"response": "Full response text", "session_id": "abc-123"}
        raw = f"event: done\ndata: {json.dumps(data)}\n\n"
        events = parse_sse_stream(raw)
        assert len(events) == 1
        assert events[0][0] == "done"
        assert events[0][1]["response"] == "Full response text"
        assert events[0][1]["session_id"] == "abc-123"

    def test_parse_multiple_events(self):
        raw = (
            'event: session_id\ndata: {"session_id": "s1"}\n\n'
            'event: tool_start\ndata: {"name": "query", "inputs": {}}\n\n'
            'event: tool_end\ndata: {"name": "query", "output_preview": "ok", "graph_data": null}\n\n'
            'event: text_delta\ndata: {"text": "Hello"}\n\n'
            'event: done\ndata: {"response": "Hello", "session_id": "s1"}\n\n'
        )
        events = parse_sse_stream(raw)
        assert len(events) == 5
        assert [e[0] for e in events] == [
            "session_id", "tool_start", "tool_end", "text_delta", "done",
        ]

    def test_parse_empty_data(self):
        raw = "event: text_delta\ndata: {}\n\n"
        events = parse_sse_stream(raw)
        assert len(events) == 1
        assert events[0] == ("text_delta", {})

    def test_parse_malformed_json(self):
        raw = "event: text_delta\ndata: {not valid json}\n\n"
        with pytest.raises(json.JSONDecodeError):
            parse_sse_stream(raw)


# ---------------------------------------------------------------------------
# 2. TestThinkingResponseSplit
# ---------------------------------------------------------------------------

class TestThinkingResponseSplit:
    """Python port of splitThinkingAndResponse() tests."""

    def test_no_thinking(self):
        text = "Here are 5 patients with diabetes."
        thinking, response = split_thinking_and_response(text)
        assert thinking == ""
        assert response == text

    def test_all_thinking(self):
        text = "Let me query the database.\nI'll check the results."
        thinking, response = split_thinking_and_response(text)
        # When response would be empty, everything becomes response
        assert thinking == ""
        assert response == text

    def test_thinking_then_response(self):
        text = "Let me check.\n# Results\n- Item 1"
        thinking, response = split_thinking_and_response(text)
        assert thinking == "Let me check."
        assert "# Results" in response
        assert "- Item 1" in response

    def test_continuation_patterns(self):
        text = "I need to look.\nand also check.\n# Answer\nDone."
        thinking, response = split_thinking_and_response(text)
        assert "I need to look." in thinking
        assert "and also check." in thinking
        assert "# Answer" in response
        assert "Done." in response

    def test_markdown_breaks_thinking(self):
        text = "I should check.\n- Found result"
        thinking, response = split_thinking_and_response(text)
        assert thinking == "I should check."
        assert "- Found result" in response

    def test_error_text_not_split(self):
        text = "Let me check.\nThere was an error in the query."
        thinking, response = split_thinking_and_response(text)
        assert thinking == ""
        assert response == text

    def test_failed_text_not_split(self):
        text = "I'll try to query.\nThe request failed."
        thinking, response = split_thinking_and_response(text)
        assert thinking == ""
        assert response == text

    def test_empty_string(self):
        thinking, response = split_thinking_and_response("")
        assert thinking == ""
        assert response == ""

    def test_thinking_at_end(self):
        text = "Here is the answer.\nLet me also note that the data is incomplete."
        thinking, response = split_thinking_and_response(text)
        # "Here is the answer." is the first line and is not a thinking pattern,
        # so foundResponse becomes True immediately. Subsequent thinking lines
        # go to response since foundResponse is already True.
        assert thinking == ""
        assert "Here is the answer." in response
        assert "Let me also note" in response


# ---------------------------------------------------------------------------
# 3. TestSSEContractValidation
# ---------------------------------------------------------------------------

class TestSSEContractValidation:
    """Verify backend and frontend agree on SSE event types and data shapes."""

    @pytest.fixture(autouse=True)
    def _load_templates(self):
        self.routes_src = ROUTES_TEMPLATE.read_text()
        self.chat_src = CHAT_TEMPLATE.read_text()

    def _extract_backend_event_types(self) -> set[str]:
        """Extract event type strings emitted by the backend SSE generator."""
        # Match f-string patterns: event: {event_type}\n  and  event: session_id\n
        # Inline literals like  f"event: session_id\ndata: ..."
        literal_events = set(re.findall(r'f"event: (\w+)\\n', self.routes_src))
        # The generic emitter:  event_type = event["event"]  followed by
        #   f"event: {event_type}\n"  — that covers all queue-based events.
        # Also pick up the docstring listing the canonical event types.
        docstring_events = set(re.findall(r"- (\w+):", self.routes_src))
        # Filter to known event names only
        known = {"session_id", "tool_start", "tool_end", "text_delta", "done", "error",
                 "entities_extracted", "preferences_detected"}
        return (literal_events | docstring_events) & known

    def _extract_frontend_event_types(self) -> set[str]:
        """Extract event types handled by frontend case statements."""
        return set(re.findall(r'case "(\w+)"', self.chat_src))

    def test_backend_event_types_match_frontend_handlers(self):
        backend = self._extract_backend_event_types()
        frontend = self._extract_frontend_event_types()
        # Every backend event type should be handled by the frontend
        missing = backend - frontend
        assert not missing, f"Backend emits events not handled by frontend: {missing}"

    def test_frontend_handles_all_backend_events(self):
        backend = self._extract_backend_event_types()
        frontend = self._extract_frontend_event_types()
        # Frontend should not have case handlers for event types the backend never sends
        extra = frontend - backend
        assert not extra, f"Frontend handles events backend never emits: {extra}"

    def test_sse_event_data_schema_consistent(self):
        """Verify data fields for each event type are consistent between backend and frontend."""
        # Backend: session_id event emits {"session_id": ...}
        assert "'session_id': session_id" in self.routes_src or '"session_id"' in self.routes_src

        # Frontend: session_id handler reads data.session_id
        assert "data.session_id" in self.chat_src

        # tool_start must contain "name" and "inputs"
        assert "data.name" in self.chat_src
        assert "data.inputs" in self.chat_src

        # tool_end must contain "output_preview" and "graph_data"
        assert "data.output_preview" in self.chat_src
        assert "data.graph_data" in self.chat_src

        # text_delta must contain "text"
        assert "data.text" in self.chat_src

        # done must contain "response"
        assert "data.response" in self.chat_src

        # error must contain "detail"
        assert "data.detail" in self.chat_src

        # entities_extracted must contain "entities"
        assert "data.entities" in self.chat_src

        # preferences_detected must contain "preferences"
        assert "data.preferences" in self.chat_src


# ---------------------------------------------------------------------------
# 4. TestGeneratedFrontendStructure
# ---------------------------------------------------------------------------

class TestGeneratedFrontendStructure:
    """Read generated TSX templates and verify structural expectations."""

    def test_chat_interface_has_all_event_handlers(self):
        src = CHAT_TEMPLATE.read_text()
        for event_type in ("session_id", "tool_start", "tool_end", "text_delta",
                           "entities_extracted", "preferences_detected", "done", "error"):
            assert f'case "{event_type}"' in src, f"ChatInterface missing handler for '{event_type}'"

    def test_context_graph_view_has_schema_mode(self):
        src = GRAPH_VIEW_TEMPLATE.read_text()
        assert "schema" in src.lower(), "ContextGraphView does not reference schema view"
        # Check for the schema visualization endpoint call
        assert "schema/visualization" in src, "ContextGraphView does not call schema/visualization endpoint"

    def test_chat_interface_has_abort_controller(self):
        src = CHAT_TEMPLATE.read_text()
        assert "AbortController" in src, "ChatInterface missing AbortController for timeout handling"
        assert "controller.abort" in src or "abort()" in src, "ChatInterface does not call abort()"


class TestStreamingRefAccumulation:
    """v0.12.0 regression test — the ``done`` SSE handler must read the
    streaming entities/preferences from refs, not from useState. The bug
    was that the handler captured ``streamingEntities``/``streamingPreferences``
    via closure on the message-pump async loop, so values accumulated by
    ``setStreamingEntities(prev => ...)`` in earlier events could be one
    render behind when ``done`` fires. Refs read synchronously."""

    def test_done_handler_does_not_read_streaming_state_directly(self):
        """The ``done`` branch must NOT contain bare ``streamingEntities`` /
        ``streamingPreferences`` reads — only ``.current`` reads via refs."""
        src = CHAT_TEMPLATE.read_text()
        # Locate the case "done" block precisely.
        done_idx = src.index('case "done"')
        error_idx = src.index('case "error"', done_idx)
        done_block = src[done_idx:error_idx]

        # No bare reads — must be via refs. Catch the legacy ``streamingEntities.length``
        # / ``[...streamingEntities]`` shapes the v0.12.0 done handler used.
        assert ".length" not in done_block.split("streamingEntities")[1].split("\n")[0] \
            if "streamingEntities" in done_block else True, \
            "done handler appears to read streamingEntities directly — use streamingEntitiesRef.current"

        # Stronger: explicit ref reads should appear.
        assert "streamingEntitiesRef.current" in done_block, (
            "done handler must read accumulated entities from streamingEntitiesRef.current"
        )
        assert "streamingPreferencesRef.current" in done_block, (
            "done handler must read accumulated preferences from streamingPreferencesRef.current"
        )

    def test_refs_are_declared_alongside_state(self):
        src = CHAT_TEMPLATE.read_text()
        assert "streamingEntitiesRef = useRef" in src, (
            "streamingEntitiesRef must be declared with useRef so the done handler "
            "can read synchronously."
        )
        assert "streamingPreferencesRef = useRef" in src, (
            "streamingPreferencesRef must be declared with useRef."
        )

    def test_refs_updated_in_extraction_handlers(self):
        """Each extraction event must push into the ref AND keep the state in
        sync so the display badges still re-render during streaming."""
        src = CHAT_TEMPLATE.read_text()
        # Inside entities_extracted handler, both ref and state should be updated.
        entities_idx = src.index('case "entities_extracted"')
        prefs_idx = src.index('case "preferences_detected"', entities_idx)
        entities_block = src[entities_idx:prefs_idx]
        assert "streamingEntitiesRef.current" in entities_block
        assert "setStreamingEntities" in entities_block

        # Same for preferences.
        text_delta_idx = src.index('case "text_delta"', prefs_idx) if 'case "text_delta"' in src[prefs_idx:] else len(src)
        done_idx = src.index('case "done"', prefs_idx)
        prefs_block = src[prefs_idx:min(text_delta_idx, done_idx)]
        assert "streamingPreferencesRef.current" in prefs_block
        assert "setStreamingPreferences" in prefs_block

    def test_refs_reset_on_done_and_error_and_send(self):
        """Refs must be cleared in: the ``done`` handler (next turn starts
        clean), the error/catch path (cancelled request doesn't leak entities
        into the next message), the start of ``sendMessage`` (defensive),
        and ``startNewConversation`` (full reset)."""
        src = CHAT_TEMPLATE.read_text()
        # Expect at least 4 reset sites for each ref.
        assert src.count("streamingEntitiesRef.current = []") >= 4, (
            "Need ref resets in done, error, sendMessage start, and startNewConversation"
        )
        assert src.count("streamingPreferencesRef.current = []") >= 4

    def test_done_handler_uses_single_setMessages_call(self):
        """The two-step setMessages pattern (append, then re-update with
        entities/preferences) is the smell that produced the closure bug.
        Consolidating into a single setMessages call that pulls from refs
        is the fix."""
        src = CHAT_TEMPLATE.read_text()
        done_idx = src.index('case "done"')
        error_idx = src.index('case "error"', done_idx)
        done_block = src[done_idx:error_idx]
        assert done_block.count("setMessages") == 1, (
            f"done handler should have exactly 1 setMessages call (single-shot "
            f"with refs); found {done_block.count('setMessages')}."
        )

    def test_loading_in_external_input_effect_deps(self):
        """v0.12.0 regression — the externalInput useEffect read `loading`
        but didn't list it as a dep, so clicks landing mid-stream were
        silently dropped. Adding `loading` to the deps fires the effect
        once the stream completes."""
        src = CHAT_TEMPLATE.read_text()
        # The effect block lives between the "externalInput" comment-tag and
        # the next useEffect. Match the deps array of the effect that calls
        # sendMessage(externalInput).
        m = re.search(
            r"if \(externalInput && !loading\)[^}]+\}\s*[^}]*\}\s*,\s*\[([^\]]+)\]",
            src,
        )
        assert m is not None, "Could not locate externalInput useEffect"
        deps = m.group(1)
        assert "externalInput" in deps
        assert "loading" in deps, (
            f"externalInput useEffect must depend on `loading` to re-fire after a "
            f"mid-stream click; current deps: [{deps}]"
        )


class TestCompositeKeyRegressions:
    """v0.13.0 / v0.13.1 — every list rendered from streaming data must use a
    composite key derived from stable item properties. The pre-v0.13.0 bug was
    bare ``key={i}`` (array index), which makes React reuse DOM across reorders
    and stomp on the wrong message's content."""

    def test_chat_interface_entity_badge_key_is_composite(self):
        src = CHAT_TEMPLATE.read_text()
        assert "key={`${e.type}-${e.name}-${i}`}" in src, (
            "entity badge key must be `${e.type}-${e.name}-${i}` — index alone "
            "is unsafe across re-renders"
        )

    def test_chat_interface_preference_badge_key_is_composite(self):
        src = CHAT_TEMPLATE.read_text()
        assert "key={`${p.category}-${p.preference}-${i}`}" in src, (
            "preference badge key must be `${p.category}-${p.preference}-${i}`"
        )

    def test_chat_interface_tool_call_key_is_composite(self):
        src = CHAT_TEMPLATE.read_text()
        assert "key={`${tc.name}-${j}`}" in src, (
            "tool call timeline key must be `${tc.name}-${j}`"
        )

    def test_decision_trace_step_key_is_composite(self):
        src = DECISION_TRACE_TEMPLATE.read_text()
        assert 'key={`step-${i}-${(step.action || "").slice(0, 32)}`}' in src, (
            "trace step key must include the action prefix, not just the index"
        )

    def test_document_browser_entity_key_uses_document_title(self):
        """v0.13.1 fix — the entity badge key in the document detail view used
        to be `${e.name}-${i}`. That collides if the user navigates back to
        the same document repeatedly (React reuses the prior badge nodes).
        The fix scopes the key by the document title so it's unique across
        document switches."""
        src = DOC_BROWSER_TEMPLATE.read_text()
        assert "key={`${selectedDoc.document.title}-${e.name}`}" in src, (
            "DocumentBrowser entity badge key must include the document title"
        )
        # The old, weaker pattern must be gone.
        assert "key={`${e.name}-${i}`}" not in src, (
            "DocumentBrowser still uses the legacy index-tainted key"
        )
