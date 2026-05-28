# Copyright 2026 Neo4j Labs
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0

"""Integration tests: render a project, mount its FastAPI app, hit routes.

These tests verify the generated ``backend/app/routes.py`` dispatches
correctly between the NAMS adapter and the bolt Cypher path for each
backend-aware endpoint (``/expand``, ``/documents``, ``/traces``,
``/schema/visualization``, ``/entities/{name}``, ``/search``).

We don't run a real Neo4j or NAMS — every external call is mocked.
"""

from __future__ import annotations

import importlib
import importlib.util
import os
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from create_context_graph.config import ProjectConfig
from create_context_graph.ontology import load_domain
from create_context_graph.renderer import ProjectRenderer

# These tests mount the generated FastAPI app via TestClient. They require
# fastapi to be installed in the dev environment — without it (the default
# create-context-graph dev install only has Jinja, pytest, etc.), the whole
# file is skipped. CI environments that install the project's runtime deps
# will exercise these.
pytest.importorskip("fastapi")
pytest.importorskip("pydantic_settings")


# ---------------------------------------------------------------------------
# Project scaffold + module loader
# ---------------------------------------------------------------------------


def _scaffold(tmp_path: Path, *, backend: str) -> Path:
    cfg = ProjectConfig(
        project_name=f"{backend} routes test",
        domain="financial-services",
        framework="strands" if backend == "nams" else "pydanticai",
        memory_backend=backend,
        nams_api_key="sk-test" if backend == "nams" else None,
        neo4j_uri="neo4j://localhost:7687" if backend == "bolt" else "neo4j://localhost:7687",
    )
    out = tmp_path / "scaffold"
    out.mkdir(exist_ok=True)
    ProjectRenderer(cfg, load_domain(cfg.domain)).render(out)
    return out / "backend"


def _import_app(backend_dir: Path, *, backend: str, fake_client):
    """Wire up the generated backend as importable Python.

    Stubs every external dep (neo4j driver, neo4j_agent_memory, agent module,
    framework SDKs) and mounts the FastAPI app via TestClient.
    """
    # Make `app` package importable from the generated directory
    app_pkg_path = str(backend_dir / "app")
    if app_pkg_path not in sys.path:
        sys.path.insert(0, app_pkg_path)

    # Set placeholder API keys before any agent import
    os.environ.setdefault("ANTHROPIC_API_KEY", "sk-test")
    os.environ.setdefault("OPENAI_API_KEY", "sk-test")
    os.environ.setdefault("GOOGLE_API_KEY", "sk-test")
    os.environ["MEMORY_BACKEND"] = backend
    # Set ONLY the credentials matching the requested backend and clear the
    # opposite ones — the generated Settings class auto-corrects a mismatch
    # (e.g. MEMORY_BACKEND=bolt but only MEMORY_API_KEY set → flips to nams).
    # Without this, env leakage from a previous nams test poisons bolt cases.
    if backend == "nams":
        os.environ["MEMORY_API_KEY"] = "sk-test"
        os.environ.pop("NEO4J_URI", None)
        os.environ.pop("NEO4J_USERNAME", None)
        os.environ.pop("NEO4J_PASSWORD", None)
    else:  # bolt
        os.environ["NEO4J_URI"] = "neo4j://localhost:7687"
        os.environ["NEO4J_USERNAME"] = "neo4j"
        os.environ["NEO4J_PASSWORD"] = "test-pw"
        os.environ.pop("MEMORY_API_KEY", None)

    # Stub neo4j_agent_memory before anything imports it
    fake_nam = ModuleType("neo4j_agent_memory")
    fake_nam.MemoryClient = MagicMock(return_value=fake_client)
    fake_nam.MemorySettings = MagicMock()
    fake_nam.MemoryIntegration = MagicMock()
    fake_nam.NamsConfig = MagicMock()

    class _SessionStrategy:
        PER_CONVERSATION = "per_conversation"
        PER_DAY = "per_day"
        PERSISTENT = "persistent"

    fake_nam.SessionStrategy = _SessionStrategy

    class _NotSupportedError(Exception):
        pass
    fake_nam.NotSupportedError = _NotSupportedError
    sys.modules["neo4j_agent_memory"] = fake_nam

    # Stub the agent module (each framework SDK adds heavy deps; skip them)
    agent_mod = ModuleType("app.agent")
    agent_mod.handle_message = AsyncMock(
        return_value={"response": "stub", "session_id": "s-1", "graph_data": None}
    )
    sys.modules["app.agent"] = agent_mod

    # Now do the real import
    # First load `app` as a namespace package pointing at the scaffold
    app_init = backend_dir / "app" / "__init__.py"
    spec = importlib.util.spec_from_file_location(
        "app", app_init, submodule_search_locations=[str(backend_dir / "app")]
    )
    app_pkg = importlib.util.module_from_spec(spec)
    sys.modules["app"] = app_pkg
    spec.loader.exec_module(app_pkg)

    # Load app.config
    spec = importlib.util.spec_from_file_location(
        "app.config", backend_dir / "app" / "config.py"
    )
    config_mod = importlib.util.module_from_spec(spec)
    sys.modules["app.config"] = config_mod
    spec.loader.exec_module(config_mod)

    # Load app.memory and override connect/close to bypass the real lifecycle.
    # We inject the fake client directly so route handlers see it.
    spec = importlib.util.spec_from_file_location(
        "app.memory", backend_dir / "app" / "memory.py"
    )
    memory_mod = importlib.util.module_from_spec(spec)
    sys.modules["app.memory"] = memory_mod
    spec.loader.exec_module(memory_mod)
    memory_mod._client = fake_client
    memory_mod._memory = MagicMock()

    async def _fake_connect():
        memory_mod._client = fake_client

    async def _fake_close():
        memory_mod._client = None

    memory_mod.connect_memory = _fake_connect
    memory_mod.close_memory = _fake_close
    memory_mod.get_client = lambda: memory_mod._client

    # Load app.memory_adapter
    spec = importlib.util.spec_from_file_location(
        "app.memory_adapter", backend_dir / "app" / "memory_adapter.py"
    )
    adapter_mod = importlib.util.module_from_spec(spec)
    sys.modules["app.memory_adapter"] = adapter_mod
    spec.loader.exec_module(adapter_mod)

    # Stub app.context_graph_client (bolt side)
    cgc_mod = ModuleType("app.context_graph_client")
    cgc_mod.execute_cypher = AsyncMock(return_value=[])
    cgc_mod.search_entities = AsyncMock(return_value=[])
    cgc_mod.get_entity_graph = AsyncMock(return_value={"nodes": [], "relationships": []})
    cgc_mod.get_schema = AsyncMock(return_value={"labels": [], "relationship_types": []})
    cgc_mod.get_schema_visualization = AsyncMock(return_value={"nodes": [], "relationships": []})
    cgc_mod.expand_node = AsyncMock(return_value={"nodes": [], "relationships": []})
    cgc_mod.is_connected = MagicMock(return_value=True)
    cgc_mod.connect_neo4j = AsyncMock()
    cgc_mod.close_neo4j = AsyncMock()

    class _Collector:
        def drain(self): return []
        def drain_tool_calls(self): return []
        def set_event_queue(self, q): pass
        def clear_event_queue(self): pass
        def emit_text_delta(self, t): pass
        def emit_done(self, t, s): pass
        def emit_entities_extracted(self, e): pass
        def emit_preferences_detected(self, p): pass

    cgc_mod.get_collector = MagicMock(return_value=_Collector())
    sys.modules["app.context_graph_client"] = cgc_mod

    # Stub app.gds_client
    gds_mod = ModuleType("app.gds_client")
    gds_mod.check_gds_available = AsyncMock(return_value=False)
    gds_mod.run_community_detection = AsyncMock(return_value=[])
    gds_mod.run_pagerank = AsyncMock(return_value=[])
    sys.modules["app.gds_client"] = gds_mod

    # Stub app.vector_client
    vc_mod = ModuleType("app.vector_client")
    vc_mod.create_vector_index = AsyncMock()
    sys.modules["app.vector_client"] = vc_mod

    # Stub app.models (routes may import from it; render a minimal stub)
    if "app.models" not in sys.modules:
        try:
            spec = importlib.util.spec_from_file_location(
                "app.models", backend_dir / "app" / "models.py"
            )
            models_mod = importlib.util.module_from_spec(spec)
            sys.modules["app.models"] = models_mod
            spec.loader.exec_module(models_mod)
        except Exception:
            sys.modules["app.models"] = ModuleType("app.models")

    # Load app.routes
    spec = importlib.util.spec_from_file_location(
        "app.routes", backend_dir / "app" / "routes.py"
    )
    routes_mod = importlib.util.module_from_spec(spec)
    sys.modules["app.routes"] = routes_mod
    spec.loader.exec_module(routes_mod)

    # Load app.main (the FastAPI app)
    spec = importlib.util.spec_from_file_location(
        "app.main", backend_dir / "app" / "main.py"
    )
    main_mod = importlib.util.module_from_spec(spec)
    sys.modules["app.main"] = main_mod
    spec.loader.exec_module(main_mod)

    return main_mod.app, memory_mod, cgc_mod


@pytest.fixture(autouse=True)
def _cleanup_modules():
    yield
    for key in list(sys.modules):
        if key == "app" or key.startswith("app.") or key == "neo4j_agent_memory":
            del sys.modules[key]
    # Remove scaffold path entries
    sys.path[:] = [p for p in sys.path if "scaffold" not in p]


def _fake_client():
    """A MagicMock NAMS client with the methods routes need."""
    client = MagicMock()
    client.short_term.get_conversation = AsyncMock(
        return_value=SimpleNamespace(messages=[])
    )
    client.long_term.search_entities = AsyncMock(return_value=[])
    client.long_term.get_entity_by_name = AsyncMock(return_value=None)
    client.long_term.get_entity = AsyncMock()
    client.reasoning.list_traces = AsyncMock(return_value=[])
    return client


# ---------------------------------------------------------------------------
# NAMS backend route dispatch
# ---------------------------------------------------------------------------


class TestNamsRoutes:
    def test_health_reports_nams_backend(self, tmp_path):
        from fastapi.testclient import TestClient

        backend_dir = _scaffold(tmp_path, backend="nams")
        client = _fake_client()
        app, _, _ = _import_app(backend_dir, backend="nams", fake_client=client)

        with TestClient(app) as tc:
            r = tc.get("/health")
            assert r.status_code == 200
            body = r.json()
            assert body["memory_backend"] == "nams"
            assert "nams" in body
            assert "neo4j" not in body  # bolt-only field

    def test_documents_uses_long_term_entities(self, tmp_path):
        """Documents are now dual-tracked on NAMS — the /documents endpoint
        reads from the long_term Document entity (queryable, matches bolt
        graph shape) rather than short_term messages (which are extraction
        fuel, not the source of truth)."""
        from fastapi.testclient import TestClient

        backend_dir = _scaffold(tmp_path, backend="nams")
        client = _fake_client()
        # The new adapter calls long_term.search_entities and filters to
        # OBJECT-typed records whose description has a body.
        client.long_term.search_entities = AsyncMock(
            return_value=[
                SimpleNamespace(
                    name="Discharge Note",
                    entity_type="OBJECT",
                    description="Discharge content\n\n_pole_type: OBJECT_",
                ),
            ]
        )
        app, _, _ = _import_app(backend_dir, backend="nams", fake_client=client)

        with TestClient(app) as tc:
            r = tc.get("/api/documents")
            assert r.status_code == 200
            body = r.json()
            assert "documents" in body
            assert len(body["documents"]) == 1
            assert body["documents"][0]["title"] == "Discharge Note"

    def test_documents_rejects_template_filter_on_nams(self, tmp_path):
        from fastapi.testclient import TestClient

        backend_dir = _scaffold(tmp_path, backend="nams")
        client = _fake_client()
        app, _, _ = _import_app(backend_dir, backend="nams", fake_client=client)

        with TestClient(app) as tc:
            r = tc.get("/api/documents?template_id=discharge")
            assert r.status_code == 501
            assert "not supported" in r.json()["detail"]

    def test_search_uses_long_term_search(self, tmp_path):
        from fastapi.testclient import TestClient

        backend_dir = _scaffold(tmp_path, backend="nams")
        client = _fake_client()
        client.long_term.search_entities = AsyncMock(
            return_value=[
                SimpleNamespace(id="e-1", name="Alice", type="Patient", description="..."),
            ]
        )
        app, _, _ = _import_app(backend_dir, backend="nams", fake_client=client)

        with TestClient(app) as tc:
            r = tc.post("/api/search", json={"query": "Alice", "limit": 20})
            assert r.status_code == 200
            body = r.json()
            assert body["results"][0]["name"] == "Alice"

    def test_schema_visualization_synthesizes_view(self, tmp_path):
        from fastapi.testclient import TestClient

        backend_dir = _scaffold(tmp_path, backend="nams")
        client = _fake_client()
        client.long_term.search_entities = AsyncMock(
            return_value=[
                SimpleNamespace(type="Patient"),
                SimpleNamespace(type="Patient"),
                SimpleNamespace(type="Hospital"),
            ]
        )
        app, _, _ = _import_app(backend_dir, backend="nams", fake_client=client)

        with TestClient(app) as tc:
            r = tc.get("/api/schema/visualization")
            assert r.status_code == 200
            body = r.json()
            assert body["relationships"] == []   # NAMS has no edges
            names = {n["name"]: n["count"] for n in body["nodes"]}
            assert names["Patient"] == 2
            assert names["Hospital"] == 1

    def test_expand_uses_inlined_relationships(self, tmp_path):
        from fastapi.testclient import TestClient

        backend_dir = _scaffold(tmp_path, backend="nams")
        client = _fake_client()
        center = SimpleNamespace(
            id="alice", name="Alice", type="Patient", description="...",
            relationships=[SimpleNamespace(target_id="mercy", type="TREATED_AT")],
        )
        target = SimpleNamespace(
            id="mercy", name="Mercy", type="Hospital", description="...",
        )
        client.long_term.get_entity = AsyncMock(side_effect=[center, target])
        app, _, _ = _import_app(backend_dir, backend="nams", fake_client=client)

        with TestClient(app) as tc:
            r = tc.post("/api/expand", json={"element_id": "alice"})
            assert r.status_code == 200
            body = r.json()
            assert len(body["nodes"]) == 2
            assert len(body["relationships"]) == 1

    def test_traces_uses_reasoning_api(self, tmp_path):
        from fastapi.testclient import TestClient

        backend_dir = _scaffold(tmp_path, backend="nams")
        client = _fake_client()
        client.reasoning.list_traces = AsyncMock(
            return_value=[SimpleNamespace(id="t-1")]
        )
        client.reasoning.get_trace_with_steps = AsyncMock(
            return_value=SimpleNamespace(
                task="task", outcome="outcome",
                steps=[SimpleNamespace(thought="t", action="a", observation="o")],
            )
        )
        app, _, _ = _import_app(backend_dir, backend="nams", fake_client=client)

        with TestClient(app) as tc:
            r = tc.get("/api/traces")
            assert r.status_code == 200
            body = r.json()
            assert len(body["traces"]) == 1
            assert body["traces"][0]["task"] == "task"
            assert len(body["traces"][0]["steps"]) == 1

    def test_gds_endpoints_return_501_on_nams(self, tmp_path):
        from fastapi.testclient import TestClient

        backend_dir = _scaffold(tmp_path, backend="nams")
        client = _fake_client()
        app, _, _ = _import_app(backend_dir, backend="nams", fake_client=client)

        with TestClient(app) as tc:
            r = tc.get("/api/gds/communities")
            assert r.status_code == 501
            r = tc.get("/api/gds/pagerank")
            assert r.status_code == 501
            r = tc.get("/api/gds/status")
            assert r.status_code == 200
            assert r.json()["gds_available"] is False


# ---------------------------------------------------------------------------
# Bolt backend route dispatch — confirm the NAMS adapters DON'T run
# ---------------------------------------------------------------------------


class TestBoltRoutes:
    def test_health_reports_bolt_backend(self, tmp_path):
        from fastapi.testclient import TestClient

        backend_dir = _scaffold(tmp_path, backend="bolt")
        client = _fake_client()
        app, _, _ = _import_app(backend_dir, backend="bolt", fake_client=client)

        with TestClient(app) as tc:
            r = tc.get("/health")
            assert r.status_code == 200
            body = r.json()
            assert body["memory_backend"] == "bolt"
            assert "neo4j" in body

    def test_documents_uses_cypher_path_on_bolt(self, tmp_path):
        from fastapi.testclient import TestClient

        backend_dir = _scaffold(tmp_path, backend="bolt")
        client = _fake_client()
        app, _, cgc = _import_app(backend_dir, backend="bolt", fake_client=client)

        # Stub the Cypher execute call to return a fake document
        cgc.execute_cypher = AsyncMock(return_value=[
            {"title": "BoltDoc", "template_id": "x", "template_name": "y",
             "preview": "preview...", "mentioned_entities": []}
        ])
        # The route already captured the original; patch in the module too
        sys.modules["app.context_graph_client"].execute_cypher = cgc.execute_cypher
        # Refresh routes module bindings (it imported the names at top)
        import app.routes as routes_mod
        routes_mod.execute_cypher = cgc.execute_cypher

        with TestClient(app) as tc:
            r = tc.get("/api/documents")
            assert r.status_code == 200
            assert r.json()["documents"][0]["title"] == "BoltDoc"

        # NAMS short_term should NOT have been touched
        assert client.short_term.get_conversation.await_count == 0

    def test_gds_communities_works_on_bolt(self, tmp_path):
        from fastapi.testclient import TestClient

        backend_dir = _scaffold(tmp_path, backend="bolt")
        client = _fake_client()
        app, _, _ = _import_app(backend_dir, backend="bolt", fake_client=client)

        with TestClient(app) as tc:
            r = tc.get("/api/gds/communities")
            # Returns 200 with an empty list from our mocked GDS
            assert r.status_code == 200
            assert "communities" in r.json()
