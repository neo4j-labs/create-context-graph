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

"""Behavioral tests for the generated ``context_graph_client.py`` and
``memory.py`` modules.

Most template coverage in this repo is static (render + assert on source
text). These tests execute the rendered modules against doubles, pinning the
two v0.14.0 runtime behaviors that static checks can't see:

* ``execute_cypher`` dispatches to the NAMS ``client.query.cypher`` API when
  ``MEMORY_BACKEND=nams`` (agent tools were previously dead on NAMS — the
  bolt driver is never connected there), including result-shape coercion and
  tool-event emission (PR #56).
* The bolt path opens sessions against ``settings.neo4j_database`` and
  ``store_message()`` records write failures into the error state that
  ``/health`` reports (PR #60).
"""

from __future__ import annotations

import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from create_context_graph.config import ProjectConfig
from create_context_graph.ontology import load_domain
from create_context_graph.renderer import ProjectRenderer

pytest.importorskip("neo4j")  # generated client imports the driver at module level


# ---------------------------------------------------------------------------
# Scaffolds (rendered once per module — the tests only read the output files)
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def bolt_backend_dir(tmp_path_factory) -> Path:
    cfg = ProjectConfig(
        project_name="bolt client runtime",
        domain="healthcare",
        framework="pydanticai",
        memory_backend="bolt",
        neo4j_uri="neo4j://localhost:7687",
    )
    out = tmp_path_factory.mktemp("bolt-client-scaffold")
    ProjectRenderer(cfg, load_domain(cfg.domain)).render(out)
    return out / "backend"


@pytest.fixture(scope="module")
def nams_backend_dir(tmp_path_factory) -> Path:
    cfg = ProjectConfig(
        project_name="nams client runtime",
        domain="healthcare",
        framework="strands",
        memory_backend="nams",
        nams_api_key="sk-test",
    )
    out = tmp_path_factory.mktemp("nams-client-scaffold")
    ProjectRenderer(cfg, load_domain(cfg.domain)).render(out)
    return out / "backend"


# ---------------------------------------------------------------------------
# Module loader + doubles
# ---------------------------------------------------------------------------


def _make_settings(**overrides) -> SimpleNamespace:
    base = dict(
        memory_backend="bolt",
        memory_api_key="sk-test",
        memory_nams_endpoint="https://memory.neo4jlabs.com/v1",
        memory_llm="",
        memory_embedding="",
        anthropic_api_key=None,
        openai_api_key=None,
        neo4j_uri="neo4j://localhost:7687",
        neo4j_username="neo4j",
        neo4j_password="pw",
        neo4j_database="",
        session_strategy="per_conversation",
        domain_id="healthcare",
    )
    base.update(overrides)
    return SimpleNamespace(**base)


def _install_app_stubs(settings: SimpleNamespace, memory_client=None) -> None:
    """Install ``app``/``app.config``/``app.memory`` stubs into sys.modules."""
    app_mod = ModuleType("app")
    config_mod = ModuleType("app.config")
    config_mod.settings = settings
    memory_mod = ModuleType("app.memory")
    memory_mod.get_client = lambda: memory_client
    memory_mod.connect_memory = AsyncMock()
    memory_mod.close_memory = AsyncMock()
    sys.modules["app"] = app_mod
    sys.modules["app.config"] = config_mod
    sys.modules["app.memory"] = memory_mod


def _load_module(path: Path, name: str) -> ModuleType:
    import importlib.util

    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(autouse=True)
def _cleanup_modules():
    yield
    for key in list(sys.modules):
        if key == "app" or key.startswith("app.") or key.startswith("generated_"):
            del sys.modules[key]
    # Only remove neo4j_agent_memory if it's our stub — never a real install.
    if getattr(sys.modules.get("neo4j_agent_memory"), "__ccg_test_stub__", False):
        del sys.modules["neo4j_agent_memory"]


class _FakeResult:
    """Async-iterable of record doubles, matching ``await session.run(...)``."""

    def __init__(self, records: list[dict]):
        self._records = [SimpleNamespace(items=lambda d=r: d.items()) for r in records]

    def __aiter__(self):
        return self

    async def __anext__(self):
        if not self._records:
            raise StopAsyncIteration
        return self._records.pop(0)


class _FakeSession:
    def __init__(self, records: list[dict]):
        self._records = records
        self.queries: list[tuple[str, dict, Any]] = []

    async def run(self, query, parameters=None, timeout=None, **kw):
        self.queries.append((query, dict(parameters or {}), timeout))
        return _FakeResult(self._records)


class _FakeDriver:
    def __init__(self, records: list[dict] | None = None):
        self.session_obj = _FakeSession(records or [])
        self.session_kwargs: list[dict] = []

    def session(self, **kwargs):
        self.session_kwargs.append(dict(kwargs))
        outer = self

        class _Ctx:
            async def __aenter__(self_inner):
                return outer.session_obj

            async def __aexit__(self_inner, *_):
                return None

        return _Ctx()


def _fake_nams_client(cypher_result=None) -> MagicMock:
    client = MagicMock()
    client.query.cypher = AsyncMock(return_value=cypher_result)
    return client


# ---------------------------------------------------------------------------
# NAMS dispatch (PR #56)
# ---------------------------------------------------------------------------


class TestExecuteCypherOnNams:
    def _load(self, nams_backend_dir, client):
        settings = _make_settings(memory_backend="nams")
        _install_app_stubs(settings, memory_client=client)
        return _load_module(
            nams_backend_dir / "app" / "context_graph_client.py",
            "generated_cgc_nams",
        )

    async def test_dispatches_to_nams_query_api(self, nams_backend_dir):
        client = _fake_nams_client([{"name": "Alice"}])
        cgc = self._load(nams_backend_dir, client)

        records = await cgc.execute_cypher("MATCH (n) RETURN n", {"x": 1})

        client.query.cypher.assert_awaited_once_with("MATCH (n) RETURN n", {"x": 1})
        assert records == [{"name": "Alice"}]

    async def test_raises_when_client_not_connected(self, nams_backend_dir):
        cgc = self._load(nams_backend_dir, client=None)

        with pytest.raises(RuntimeError, match="NAMS client not connected"):
            await cgc.execute_cypher("MATCH (n) RETURN n")

    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            (None, []),
            ([{"a": 1}], [{"a": 1}]),
            ({"results": [{"a": 1}]}, [{"a": 1}]),
            ({"data": [{"b": 2}]}, [{"b": 2}]),
            ({"rows": [{"c": 3}]}, [{"c": 3}]),
            ({"count": 7}, [{"count": 7}]),  # bare row object wraps
            (({"a": 1},), [{"a": 1}]),  # tuple normalizes to list
            (42, [42]),  # scalar wraps
        ],
    )
    async def test_result_shape_coercion(self, nams_backend_dir, raw, expected):
        client = _fake_nams_client(raw)
        cgc = self._load(nams_backend_dir, client)

        assert await cgc.execute_cypher("RETURN 1") == expected

    async def test_tool_events_are_collected(self, nams_backend_dir):
        client = _fake_nams_client([{"name": "Alice"}])
        cgc = self._load(nams_backend_dir, client)
        collector = cgc.get_collector()
        collector.drain()
        collector.drain_tool_calls()

        await cgc.execute_cypher(
            "MATCH (n) RETURN n", {"q": "alice"}, tool_name="search_patients"
        )

        assert collector.drain() == [{"name": "Alice"}]
        calls = collector.drain_tool_calls()
        assert len(calls) == 1
        assert calls[0]["name"] == "search_patients"
        assert calls[0]["inputs"] == {"q": "alice"}

    async def test_collect_false_skips_collector(self, nams_backend_dir):
        client = _fake_nams_client([{"name": "Alice"}])
        cgc = self._load(nams_backend_dir, client)
        collector = cgc.get_collector()
        collector.drain()
        collector.drain_tool_calls()

        await cgc.execute_cypher("MATCH (n) RETURN n", collect=False, tool_name="t")

        assert collector.drain() == []
        assert collector.drain_tool_calls() == []

    async def test_bolt_driver_never_touched_on_nams(self, nams_backend_dir):
        """The pre-PR-#56 failure mode: agent tools hit get_driver() on NAMS
        and died with "Neo4j not connected". The NAMS branch must return
        before any driver access."""
        client = _fake_nams_client([])
        cgc = self._load(nams_backend_dir, client)
        assert cgc._driver is None  # never connected

        await cgc.execute_cypher("MATCH (n) RETURN n")  # must not raise


# ---------------------------------------------------------------------------
# Bolt database threading (PR #60)
# ---------------------------------------------------------------------------


class TestExecuteCypherOnBolt:
    def _load(self, bolt_backend_dir, *, database: str, records=None):
        settings = _make_settings(memory_backend="bolt", neo4j_database=database)
        _install_app_stubs(settings)
        cgc = _load_module(
            bolt_backend_dir / "app" / "context_graph_client.py",
            "generated_cgc_bolt",
        )
        driver = _FakeDriver(records or [])
        cgc._driver = driver
        return cgc, driver

    async def test_session_uses_configured_database(self, bolt_backend_dir):
        cgc, driver = self._load(bolt_backend_dir, database="clinical-db")

        await cgc.execute_cypher("RETURN 1")

        assert driver.session_kwargs == [{"database": "clinical-db"}]

    async def test_blank_database_defers_to_server_default(self, bolt_backend_dir):
        cgc, driver = self._load(bolt_backend_dir, database="")

        await cgc.execute_cypher("RETURN 1")

        assert driver.session_kwargs == [{"database": None}]

    async def test_records_serialized_from_session(self, bolt_backend_dir):
        cgc, driver = self._load(
            bolt_backend_dir, database="", records=[{"n": 1}, {"n": 2}]
        )

        records = await cgc.execute_cypher("MATCH (n) RETURN n", {"k": "v"})

        assert records == [{"n": 1}, {"n": 2}]
        query, params, timeout = driver.session_obj.queries[0]
        assert params == {"k": "v"}
        assert timeout == 30.0

    async def test_nams_client_never_touched_on_bolt(self, bolt_backend_dir):
        cgc, driver = self._load(bolt_backend_dir, database="")
        # app.memory.get_client would raise if consulted — replace to detect
        sentinel = MagicMock(side_effect=AssertionError("NAMS path taken on bolt"))
        sys.modules["app.memory"].get_client = sentinel

        await cgc.execute_cypher("RETURN 1")

        sentinel.assert_not_called()


# ---------------------------------------------------------------------------
# Generated memory.py — database pass-through + store failure surfacing
# ---------------------------------------------------------------------------


def _install_memory_lib_stub() -> ModuleType:
    """Stub neo4j_agent_memory with capture-friendly doubles."""
    fake = ModuleType("neo4j_agent_memory")
    fake.__ccg_test_stub__ = True
    fake.MemorySettings = MagicMock(name="MemorySettings")
    fake.NamsConfig = MagicMock(name="NamsConfig")
    fake.MemoryClient = MagicMock(name="MemoryClient")
    fake.MemoryIntegration = MagicMock(name="MemoryIntegration")

    class _SessionStrategy:
        PER_CONVERSATION = "per_conversation"
        PER_DAY = "per_day"
        PERSISTENT = "persistent"

    fake.SessionStrategy = _SessionStrategy

    class _NotSupportedError(Exception):
        pass

    fake.NotSupportedError = _NotSupportedError
    sys.modules["neo4j_agent_memory"] = fake
    return fake


class TestGeneratedMemorySettings:
    def _load(self, bolt_backend_dir, *, database: str):
        settings = _make_settings(memory_backend="bolt", neo4j_database=database)
        _install_app_stubs(settings)
        lib = _install_memory_lib_stub()
        mem = _load_module(
            bolt_backend_dir / "app" / "memory.py", "generated_memory"
        )
        return mem, lib

    def test_database_passed_to_memory_settings(self, bolt_backend_dir):
        mem, lib = self._load(bolt_backend_dir, database="clinical-db")

        mem._build_memory_settings()

        neo4j_config = lib.MemorySettings.call_args.kwargs["neo4j"]
        assert neo4j_config["database"] == "clinical-db"
        assert neo4j_config["uri"] == "neo4j://localhost:7687"

    def test_blank_database_omitted_from_memory_settings(self, bolt_backend_dir):
        """Omitting the key (rather than passing "") defers to
        neo4j-agent-memory's own default of "neo4j"."""
        mem, lib = self._load(bolt_backend_dir, database="")

        mem._build_memory_settings()

        neo4j_config = lib.MemorySettings.call_args.kwargs["neo4j"]
        assert "database" not in neo4j_config


class TestStoreMessageErrorSurfacing:
    """PR #60: store_message() failures must reach get_error_category() —
    previously a bad database name meant every write failed with only a log
    line while /health kept reporting "ok"."""

    def _load(self, bolt_backend_dir):
        settings = _make_settings(memory_backend="bolt")
        _install_app_stubs(settings)
        _install_memory_lib_stub()
        return _load_module(
            bolt_backend_dir / "app" / "memory.py", "generated_memory_store"
        )

    async def test_write_failure_records_error_state(self, bolt_backend_dir):
        mem = self._load(bolt_backend_dir)
        mem._memory = SimpleNamespace(
            store_message=AsyncMock(side_effect=ConnectionError("db gone"))
        )

        result = await mem.store_message("s-1", "user", "hello")

        assert result is None
        assert mem.get_error_category() == "network"
        assert mem.get_error_detail() == "ConnectionError"
        assert mem.get_error_message() is not None

    async def test_successful_write_clears_error_state(self, bolt_backend_dir):
        mem = self._load(bolt_backend_dir)
        mem._memory = SimpleNamespace(
            store_message=AsyncMock(side_effect=ConnectionError("boom"))
        )
        await mem.store_message("s-1", "user", "hello")
        assert mem.get_error_category() == "network"

        mem._memory = SimpleNamespace(
            store_message=AsyncMock(return_value={"entities": []})
        )
        result = await mem.store_message("s-1", "user", "hello again")

        assert result == {"entities": []}
        assert mem.get_error_category() is None
        assert mem.get_error_detail() is None

    async def test_not_supported_error_does_not_degrade(self, bolt_backend_dir):
        """NotSupportedError is expected partial behavior on NAMS — it must
        not flip /health to degraded."""
        mem = self._load(bolt_backend_dir)
        lib = sys.modules["neo4j_agent_memory"]
        mem._memory = SimpleNamespace(
            store_message=AsyncMock(side_effect=lib.NotSupportedError("no prefs"))
        )

        result = await mem.store_message("s-1", "user", "hello")

        assert result is None
        assert mem.get_error_category() is None

    async def test_no_memory_preserves_startup_error(self, bolt_backend_dir):
        """When connect failed at startup, store_message must not clobber the
        recorded startup error with fresher state."""
        mem = self._load(bolt_backend_dir)
        mem._memory = None
        mem._error_category = "auth"
        mem._error_detail = "HTTP 401"

        result = await mem.store_message("s-1", "user", "hello")

        assert result is None
        assert mem.get_error_category() == "auth"


class TestClassifyMemoryError:
    """Pin the error classifier buckets the /health endpoint reports."""

    @pytest.fixture()
    def classify(self, bolt_backend_dir):
        settings = _make_settings(memory_backend="bolt")
        _install_app_stubs(settings)
        _install_memory_lib_stub()
        mem = _load_module(
            bolt_backend_dir / "app" / "memory.py", "generated_memory_classify"
        )
        return mem._classify_memory_error

    def test_http_status_buckets(self, classify):
        class _Http(Exception):
            def __init__(self, status):
                self.status_code = status

        assert classify(_Http(401))[0] == "auth"
        assert classify(_Http(403))[0] == "auth"
        assert classify(_Http(429))[0] == "rate_limit"
        assert classify(_Http(503))[0] == "network"

    def test_network_exception_types(self, classify):
        assert classify(ConnectionError("x"))[0] == "network"
        assert classify(TimeoutError("x"))[0] == "network"
        assert classify(OSError("x"))[0] == "network"

    def test_message_scan_buckets(self, classify):
        assert classify(Exception("401 unauthorized"))[0] == "auth"
        assert classify(Exception("rate limit exceeded"))[0] == "rate_limit"
        assert classify(Exception("connection refused"))[0] == "network"
        assert classify(Exception("MEMORY_API_KEY missing"))[0] == "config"
        assert classify(Exception("something odd"))[0] == "unknown"


class TestNamsConversationTranslation:
    """v0.14.0 live-service fixes: the NAMS service only accepts messages
    addressed to conversation ids IT minted — client-chosen session ids 404
    ("conversation not found") and neo4j-agent-memory <=0.5.0 posts them
    straight through, so every chat memory write silently failed."""

    def _load(self, nams_backend_dir):
        settings = _make_settings(memory_backend="nams")
        _install_app_stubs(settings)
        _install_memory_lib_stub()
        mem = _load_module(
            nams_backend_dir / "app" / "memory.py", "generated_memory_nams"
        )
        client = MagicMock()
        client.short_term.create_conversation = AsyncMock(
            return_value=SimpleNamespace(id="conv-uuid-1")
        )
        mem._client = client
        mem._memory = SimpleNamespace(
            store_message=AsyncMock(return_value={"entities": []}),
            get_context=AsyncMock(
                return_value={"messages": [], "entities": [], "preferences": [], "traces": []}
            ),
        )
        return mem, client

    async def test_store_message_targets_server_conversation_id(self, nams_backend_dir):
        mem, client = self._load(nams_backend_dir)

        await mem.store_message("app-session-1", "user", "hello")

        client.short_term.create_conversation.assert_awaited_once_with(
            session_id="app-session-1"
        )
        kwargs = mem._memory.store_message.await_args.kwargs
        assert kwargs["session_id"] == "conv-uuid-1"

    async def test_conversation_created_once_per_session(self, nams_backend_dir):
        mem, client = self._load(nams_backend_dir)

        await mem.store_message("app-session-1", "user", "one")
        await mem.store_message("app-session-1", "assistant", "two")
        await mem.get_context("app-session-1", query="x")

        assert client.short_term.create_conversation.await_count == 1
        ctx_kwargs = mem._memory.get_context.await_args.kwargs
        assert ctx_kwargs["session_id"] == "conv-uuid-1"

    async def test_create_failure_falls_back_to_raw_session(self, nams_backend_dir):
        mem, client = self._load(nams_backend_dir)
        client.short_term.create_conversation = AsyncMock(
            side_effect=ConnectionError("service down")
        )

        await mem.store_message("app-session-2", "user", "hello")

        kwargs = mem._memory.store_message.await_args.kwargs
        assert kwargs["session_id"] == "app-session-2"

    async def test_bolt_backend_skips_translation(self, bolt_backend_dir):
        settings = _make_settings(memory_backend="bolt")
        _install_app_stubs(settings)
        _install_memory_lib_stub()
        mem = _load_module(
            bolt_backend_dir / "app" / "memory.py", "generated_memory_bolt_skip"
        )
        sentinel = MagicMock()
        sentinel.short_term.create_conversation = AsyncMock()
        mem._client = sentinel
        mem._memory = SimpleNamespace(
            store_message=AsyncMock(return_value={"entities": []})
        )

        await mem.store_message("bolt-session", "user", "hello")

        sentinel.short_term.create_conversation.assert_not_awaited()
        assert mem._memory.store_message.await_args.kwargs["session_id"] == "bolt-session"


class TestStoreMessageSwallowedErrors:
    """MemoryIntegration swallows failures into {'error': ...} return values
    (observed live) — store_message must treat those as failures, not clear
    the error state and report success."""

    async def test_error_dict_return_records_error_state(self, bolt_backend_dir):
        settings = _make_settings(memory_backend="bolt")
        _install_app_stubs(settings)
        _install_memory_lib_stub()
        mem = _load_module(
            bolt_backend_dir / "app" / "memory.py", "generated_memory_errdict"
        )
        mem._memory = SimpleNamespace(
            store_message=AsyncMock(
                return_value={"error": "NAMS POST /conversations/x/messages → 404: conversation not found"}
            )
        )

        result = await mem.store_message("s-1", "user", "hello")

        assert result is None
        assert mem.get_error_category() is not None
        assert mem.get_error_detail() is not None
