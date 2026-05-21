# Copyright 2026 Neo4j Labs
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0

"""Unit tests for the generated ``app.memory_adapter`` module.

The adapter is a Jinja2 template, so we render it to a tmp directory and
then load the resulting Python module via importlib. Each adapter function
is exercised against an AsyncMock NAMS client.
"""

from __future__ import annotations

import asyncio
import importlib.util
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from create_context_graph.config import ProjectConfig
from create_context_graph.ontology import load_domain
from create_context_graph.renderer import ProjectRenderer


def _scaffold(tmp_path: Path, *, backend: str = "nams") -> Path:
    """Render a project to tmp_path and return the backend dir."""
    cfg = ProjectConfig(
        project_name="Adapter Test",
        domain="financial-services",
        framework="strands" if backend == "nams" else "pydanticai",
        memory_backend=backend,
        nams_api_key="sk-test" if backend == "nams" else None,
    )
    out = tmp_path / "scaffold"
    out.mkdir(exist_ok=True)
    ProjectRenderer(cfg, load_domain(cfg.domain)).render(out)
    return out / "backend"


def _load_adapter(backend_dir: Path, *, settings_stub):
    """Load the generated ``app.memory_adapter`` module from disk.

    Pre-populates ``sys.modules`` with stubs for ``app.config`` and
    ``app.memory`` so the relative imports resolve without spinning up
    the full backend.
    """
    # Stub app.config — provide a `settings` attribute with what we need
    app_pkg = ModuleType("app")
    app_pkg.__path__ = [str(backend_dir / "app")]
    sys.modules["app"] = app_pkg

    config_mod = ModuleType("app.config")
    config_mod.settings = settings_stub
    sys.modules["app.config"] = config_mod

    memory_mod = ModuleType("app.memory")
    # _client is injected per-test; default to None
    memory_mod._client = None
    memory_mod.get_client = MagicMock(side_effect=lambda: memory_mod._client)
    sys.modules["app.memory"] = memory_mod

    # Load the generated adapter
    adapter_path = backend_dir / "app" / "memory_adapter.py"
    spec = importlib.util.spec_from_file_location("app.memory_adapter", adapter_path)
    adapter = importlib.util.module_from_spec(spec)
    sys.modules["app.memory_adapter"] = adapter
    spec.loader.exec_module(adapter)
    return adapter, memory_mod


@pytest.fixture
def settings_stub():
    return SimpleNamespace(memory_backend="nams", domain_id="financial-services")


@pytest.fixture
def nams_adapter(tmp_path, settings_stub):
    backend_dir = _scaffold(tmp_path, backend="nams")
    return _load_adapter(backend_dir, settings_stub=settings_stub)


@pytest.fixture(autouse=True)
def _isolate_app_modules():
    """Don't leak app.* stubs between tests."""
    yield
    for key in list(sys.modules):
        if key == "app" or key.startswith("app."):
            del sys.modules[key]


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro) if False else asyncio.run(coro)


# ---------------------------------------------------------------------------
# list_documents_nams
# ---------------------------------------------------------------------------


def _make_doc_entity(title: str, content: str = "doc body", entity_type: str = "OBJECT"):
    """Synthesize what NAMS long_term.search_entities returns for a Document.

    The new adapter looks at ``entity_type`` (filters to OBJECT/DOCUMENT) and
    ``description`` (parses out the ccg-edges block + _pole_type marker).
    """
    description = f"{content}\n\n_pole_type: {entity_type}_"
    return SimpleNamespace(name=title, entity_type=entity_type, description=description)


class TestListDocuments:
    def test_returns_documents_from_long_term_entities(self, nams_adapter):
        adapter, memory_mod = nams_adapter
        entities = [
            _make_doc_entity("Discharge — Alice", "Discharge note content..."),
            _make_doc_entity("Labs — Bob", "Lab results page 1..."),
        ]
        client = MagicMock()
        client.long_term.search_entities = AsyncMock(return_value=entities)
        memory_mod._client = client

        result = _run(adapter.list_documents_nams(0, 50))
        assert len(result) == 2
        titles = {d["title"] for d in result}
        assert titles == {"Discharge — Alice", "Labs — Bob"}
        for d in result:
            assert len(d["preview"]) <= 200

    def test_skips_typed_non_document_entities(self, nams_adapter):
        """Person/Organization/etc. entities returned by the search should be
        filtered out — only OBJECT-typed records are treated as documents."""
        adapter, memory_mod = nams_adapter
        entities = [
            _make_doc_entity("DocA", entity_type="OBJECT"),
            _make_doc_entity("Dr. Smith", entity_type="PERSON"),
            _make_doc_entity("Mercy General", entity_type="ORGANIZATION"),
        ]
        client = MagicMock()
        client.long_term.search_entities = AsyncMock(return_value=entities)
        memory_mod._client = client

        result = _run(adapter.list_documents_nams(0, 50))
        assert {d["title"] for d in result} == {"DocA"}

    def test_returns_empty_when_client_is_none(self, nams_adapter):
        adapter, memory_mod = nams_adapter
        memory_mod._client = None
        result = _run(adapter.list_documents_nams(0, 50))
        assert result == []

    def test_returns_empty_when_client_errors(self, nams_adapter):
        adapter, memory_mod = nams_adapter
        client = MagicMock()
        client.long_term.search_entities = AsyncMock(side_effect=RuntimeError("oops"))
        memory_mod._client = client
        result = _run(adapter.list_documents_nams(0, 50))
        assert result == []

    def test_pagination_skip_and_limit(self, nams_adapter):
        adapter, memory_mod = nams_adapter
        entities = [_make_doc_entity(f"Doc-{i:02d}", content=str(i)) for i in range(10)]
        client = MagicMock()
        client.long_term.search_entities = AsyncMock(return_value=entities)
        memory_mod._client = client

        page = _run(adapter.list_documents_nams(skip=3, limit=4))
        assert len(page) == 4
        assert [d["title"] for d in page] == ["Doc-03", "Doc-04", "Doc-05", "Doc-06"]

    def test_strips_ccg_edges_block_from_preview(self, nams_adapter):
        """The ccg-edges YAML block is an implementation detail; previews
        shown in the document browser must not include it."""
        adapter, memory_mod = nams_adapter
        description = (
            "Real document body about chest pain workup.\n\n"
            "```ccg-edges\n- type: MENTIONS\n  target: Alice Park\n```\n\n"
            "_pole_type: OBJECT_"
        )
        entity = SimpleNamespace(
            name="ClinicalNote-1", entity_type="OBJECT", description=description,
        )
        client = MagicMock()
        client.long_term.search_entities = AsyncMock(return_value=[entity])
        memory_mod._client = client

        result = _run(adapter.list_documents_nams(0, 50))
        assert len(result) == 1
        assert "ccg-edges" not in result[0]["preview"]
        assert "_pole_type" not in result[0]["preview"]
        assert "chest pain" in result[0]["preview"]

    def test_skips_blank_description_after_stripping_metadata(self, nams_adapter):
        adapter, memory_mod = nams_adapter
        entity = SimpleNamespace(
            name="EmptyDoc",
            entity_type="OBJECT",
            description="```ccg-edges\n- type: MENTIONS\n  target: Alice\n```\n\n_pole_type: OBJECT_",
        )
        client = MagicMock()
        client.long_term.search_entities = AsyncMock(return_value=[entity])
        memory_mod._client = client

        assert _run(adapter.list_documents_nams(0, 50)) == []


# ---------------------------------------------------------------------------
# get_document_nams
# ---------------------------------------------------------------------------


class TestGetDocument:
    def test_returns_full_content_by_title(self, nams_adapter):
        adapter, memory_mod = nams_adapter
        entities = [
            _make_doc_entity("DocA", content="content-A"),
            _make_doc_entity("DocB", content="content-B"),
        ]
        client = MagicMock()
        client.long_term.search_entities = AsyncMock(return_value=entities)
        memory_mod._client = client

        result = _run(adapter.get_document_nams("DocB"))
        assert result is not None
        assert result["document"]["title"] == "DocB"
        assert result["document"]["content"] == "content-B"

    def test_returns_none_when_not_found(self, nams_adapter):
        adapter, memory_mod = nams_adapter
        client = MagicMock()
        client.long_term.search_entities = AsyncMock(return_value=[])
        memory_mod._client = client
        assert _run(adapter.get_document_nams("missing")) is None

    def test_returns_none_when_content_is_blank_after_stripping_metadata(self, nams_adapter):
        adapter, memory_mod = nams_adapter
        entity = _make_doc_entity("DocB", content="")
        client = MagicMock()
        client.long_term.search_entities = AsyncMock(return_value=[entity])
        memory_mod._client = client

        assert _run(adapter.get_document_nams("DocB")) is None


# ---------------------------------------------------------------------------
# list_traces_nams
# ---------------------------------------------------------------------------


class TestListTraces:
    def test_assembles_trace_with_steps(self, nams_adapter):
        adapter, memory_mod = nams_adapter
        trace_summary = SimpleNamespace(id="t-1")
        full_trace = SimpleNamespace(
            task="Diagnose chest pain",
            outcome="Refer to cardiology",
            steps=[
                SimpleNamespace(thought="rule out MI", action="order ECG", observation="normal"),
                SimpleNamespace(thought="check labs", action="troponin", observation="normal"),
            ],
        )
        client = MagicMock()
        client.reasoning.list_traces = AsyncMock(return_value=[trace_summary])
        client.reasoning.get_trace_with_steps = AsyncMock(return_value=full_trace)
        memory_mod._client = client

        results = _run(adapter.list_traces_nams())
        assert len(results) == 1
        assert results[0]["task"] == "Diagnose chest pain"
        assert len(results[0]["steps"]) == 2
        assert results[0]["steps"][0]["step_number"] == 1

    def test_skips_traces_with_no_id(self, nams_adapter):
        adapter, memory_mod = nams_adapter
        bad_trace = SimpleNamespace()  # no id attr
        client = MagicMock()
        client.reasoning.list_traces = AsyncMock(return_value=[bad_trace])
        client.reasoning.get_trace_with_steps = AsyncMock()
        memory_mod._client = client

        results = _run(adapter.list_traces_nams())
        assert results == []


# ---------------------------------------------------------------------------
# expand_node_nams
# ---------------------------------------------------------------------------


class TestExpandNode:
    def test_returns_node_and_inlined_neighbors(self, nams_adapter):
        adapter, memory_mod = nams_adapter
        center = SimpleNamespace(
            id="alice",
            type="Patient",
            name="Alice Park",
            description="Patient details",
            relationships=[
                SimpleNamespace(target_id="mercy", type="TREATED_AT", id="rel-1"),
            ],
        )
        target = SimpleNamespace(
            id="mercy",
            type="Hospital",
            name="Mercy General",
            description="Hospital",
        )
        client = MagicMock()
        client.long_term.get_entity = AsyncMock(side_effect=[center, target])
        memory_mod._client = client

        result = _run(adapter.expand_node_nams("alice"))
        assert len(result["nodes"]) == 2
        node_names = [n["name"] for n in result["nodes"]]
        assert "Alice Park" in node_names
        assert "Mercy General" in node_names
        assert len(result["relationships"]) == 1
        assert result["relationships"][0]["type"] == "TREATED_AT"

    def test_returns_empty_when_entity_missing(self, nams_adapter):
        adapter, memory_mod = nams_adapter
        client = MagicMock()
        client.long_term.get_entity = AsyncMock(side_effect=RuntimeError("404"))
        memory_mod._client = client
        result = _run(adapter.expand_node_nams("does-not-exist"))
        assert result == {"nodes": [], "relationships": []}


# ---------------------------------------------------------------------------
# schema_visualization_nams
# ---------------------------------------------------------------------------


class TestSchemaVisualization:
    def test_groups_entities_by_type(self, nams_adapter):
        adapter, memory_mod = nams_adapter
        entities = [
            SimpleNamespace(type="Patient"),
            SimpleNamespace(type="Patient"),
            SimpleNamespace(type="Hospital"),
        ]
        client = MagicMock()
        client.long_term.search_entities = AsyncMock(return_value=entities)
        memory_mod._client = client

        result = _run(adapter.schema_visualization_nams())
        types = {n["name"]: n["count"] for n in result["nodes"]}
        assert types["Patient"] == 2
        assert types["Hospital"] == 1
        # NAMS view has no edges
        assert result["relationships"] == []

    def test_falls_back_on_error(self, nams_adapter):
        adapter, memory_mod = nams_adapter
        client = MagicMock()
        client.long_term.search_entities = AsyncMock(side_effect=RuntimeError("oops"))
        memory_mod._client = client
        result = _run(adapter.schema_visualization_nams())
        assert result == {"nodes": [], "relationships": []}


# ---------------------------------------------------------------------------
# get_entity_detail_nams
# ---------------------------------------------------------------------------


class TestGetEntityDetail:
    def test_returns_entity_with_connections(self, nams_adapter):
        adapter, memory_mod = nams_adapter
        entity = SimpleNamespace(
            id="alice",
            name="Alice Park",
            type="Patient",
            description="...",
            relationships=[
                SimpleNamespace(target_id="mercy", type="TREATED_AT"),
            ],
        )
        target = SimpleNamespace(
            id="mercy",
            name="Mercy General",
            type="Hospital",
            description="...",
        )
        client = MagicMock()
        client.long_term.get_entity_by_name = AsyncMock(return_value=entity)
        client.long_term.get_entity = AsyncMock(return_value=target)
        memory_mod._client = client

        result = _run(adapter.get_entity_detail_nams("Alice Park"))
        assert result["entity"]["name"] == "Alice Park"
        assert len(result["connections"]) == 1
        assert result["connections"][0]["name"] == "Mercy General"
        assert result["connections"][0]["relationship"] == "TREATED_AT"

    def test_returns_none_when_not_found(self, nams_adapter):
        adapter, memory_mod = nams_adapter
        client = MagicMock()
        client.long_term.get_entity_by_name = AsyncMock(return_value=None)
        memory_mod._client = client
        assert _run(adapter.get_entity_detail_nams("missing")) is None


# ---------------------------------------------------------------------------
# search_entities_nams
# ---------------------------------------------------------------------------


class TestSearchEntities:
    def test_returns_serialized_entities(self, nams_adapter):
        adapter, memory_mod = nams_adapter
        entities = [
            SimpleNamespace(id="e-1", name="Alice", type="Patient", description="..."),
            SimpleNamespace(id="e-2", name="Bob", type="Patient", description="..."),
        ]
        client = MagicMock()
        client.long_term.search_entities = AsyncMock(return_value=entities)
        memory_mod._client = client

        results = _run(adapter.search_entities_nams("patient", "Patient", 20))
        assert len(results) == 2
        assert results[0]["name"] == "Alice"
        assert results[0]["labels"] == ["Patient"]


# ---------------------------------------------------------------------------
# ingest_fixtures_nams
# ---------------------------------------------------------------------------


class TestIngestFixturesNams:
    def test_full_fixture_ingest(self, nams_adapter, capsys):
        adapter, memory_mod = nams_adapter
        client = MagicMock()
        client.long_term.add_entity = AsyncMock(return_value=SimpleNamespace(id="e"))
        client.short_term.add_message = AsyncMock(return_value=SimpleNamespace(id="m"))
        client.reasoning.start_trace = AsyncMock(return_value=SimpleNamespace(id="t"))
        client.reasoning.add_step = AsyncMock(return_value=SimpleNamespace(id="s"))
        client.reasoning.complete_trace = AsyncMock(return_value=None)
        memory_mod._client = client

        fixture = {
            "entities": {
                "Patient": [{"name": "Alice", "age": 30}],
                "Hospital": [{"name": "Mercy"}],
            },
            "relationships": [
                {"source_name": "Alice", "target_name": "Mercy", "type": "TREATED_AT"},
            ],
            "documents": [
                {"title": "Doc1", "content": "..."},
            ],
            "traces": [
                {"id": "t1", "task": "task", "outcome": "done", "steps": [
                    {"thought": "...", "action": "...", "observation": "..."},
                ]},
            ],
        }
        _run(adapter.ingest_fixtures_nams(fixture, "healthcare"))

        # 2 typed entities + 1 dual-tracked Document entity = 3 add_entity calls
        assert client.long_term.add_entity.await_count == 3
        # 1 document → 1 short-term message (no body fields in this fixture)
        assert client.short_term.add_message.await_count == 1
        # 1 trace with 1 step
        assert client.reasoning.start_trace.await_count == 1
        assert client.reasoning.add_step.await_count == 1
        assert client.reasoning.complete_trace.await_count == 1

        # Alice's outbound TREATED_AT edge must be encoded into her description
        # as a ccg-edges block (NAMS REST has no add_relationship yet).
        alice_call = next(
            c for c in client.long_term.add_entity.await_args_list
            if c.kwargs.get("name") == "Alice"
        )
        assert "```ccg-edges" in alice_call.kwargs["description"]
        assert "TREATED_AT" in alice_call.kwargs["description"]

    def test_handles_missing_client_gracefully(self, nams_adapter, capsys):
        adapter, memory_mod = nams_adapter
        memory_mod._client = None
        _run(adapter.ingest_fixtures_nams({"entities": {}}, "healthcare"))
        captured = capsys.readouterr()
        assert "NAMS client not connected" in captured.out
