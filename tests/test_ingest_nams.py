# Copyright 2026 Neo4j Labs
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0

"""Unit tests for the NAMS branch of ingest.py.

We don't run a real NAMS service; instead, we patch the MemoryClient context
manager and assert the right high-level method calls are made for entities,
documents, traces, and the relationship-skip warning.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from create_context_graph.config import ProjectConfig
from create_context_graph.ingest import (
    _get_pole_type,
    _serialize_entity_to_description,
    ingest_data,
    reset_memory_store,
)
from create_context_graph.ontology import load_domain


# ---------------------------------------------------------------------------
# Helpers — a fake MemoryClient that records every call.
# ---------------------------------------------------------------------------


class _FakeNamsClient:
    """Minimal recording double for ``neo4j_agent_memory.MemoryClient``.

    Implements an async context manager protocol plus the long_term / short_term /
    reasoning accessors the NAMS ingest path uses.
    """

    def __init__(self):
        self.long_term = SimpleNamespace(
            add_entity=AsyncMock(return_value=SimpleNamespace(id="entity-1")),
            search_entities=AsyncMock(return_value=[]),
            delete_entity=AsyncMock(return_value=None),
        )
        self.short_term = SimpleNamespace(
            add_message=AsyncMock(return_value=SimpleNamespace(id="msg-1")),
        )
        self.reasoning = SimpleNamespace(
            start_trace=AsyncMock(return_value=SimpleNamespace(id="trace-1")),
            add_step=AsyncMock(return_value=SimpleNamespace(id="step-1")),
            complete_trace=AsyncMock(return_value=None),
        )

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return None


@pytest.fixture
def fake_client():
    return _FakeNamsClient()


class _SecretStr:
    def __init__(self, v):
        self.v = v

    def get_secret_value(self):
        return self.v


@pytest.fixture
def fake_nams_module(fake_client, monkeypatch):
    """Install a fake ``neo4j_agent_memory`` module into sys.modules.

    The dev environment doesn't install neo4j-agent-memory by default; this
    fixture lets the lazy ``import neo4j_agent_memory`` inside ``ingest.py``
    succeed against a recording stub.
    """
    mod = ModuleType("neo4j_agent_memory")
    mod.MemoryClient = MagicMock(return_value=fake_client)
    mod.MemorySettings = MagicMock()
    mod.NamsConfig = MagicMock()
    monkeypatch.setitem(sys.modules, "neo4j_agent_memory", mod)

    # Also stub pydantic.SecretStr if pydantic isn't around (it is, but defensive).
    yield mod


@pytest.fixture
def healthcare_ontology():
    return load_domain("healthcare")


def _make_fixture_file(tmp_path: Path) -> Path:
    """A minimal but realistic fixture matching the on-disk schema."""
    data = {
        "entities": {
            "Patient": [
                {"name": "Alice Park", "age": 67, "status": "active", "blood_type": "O+"},
                {"name": "Bob Singh", "age": 42, "status": "discharged"},
            ],
            "Hospital": [
                {"name": "Mercy General", "city": "Portland"},
            ],
        },
        "relationships": [
            {"source_name": "Alice Park", "source_label": "Patient",
             "target_name": "Mercy General", "target_label": "Hospital",
             "type": "TREATED_AT"},
        ],
        "documents": [
            {"title": "Discharge Note — Bob Singh", "content": "Patient discharged today.",
             "template_id": "discharge", "template_name": "Discharge Note"},
        ],
        "traces": [
            {
                "id": "trace-alpha",
                "task": "Diagnose chest pain",
                "outcome": "Referral to cardiology",
                "steps": [
                    {"thought": "Rule out MI", "action": "Order ECG", "observation": "Normal sinus rhythm"},
                    {"thought": "Check labs", "action": "Order troponin", "observation": "Within range"},
                ],
            },
        ],
    }
    f = tmp_path / "fixtures.json"
    f.write_text(json.dumps(data))
    return f


# ---------------------------------------------------------------------------
# Pure helpers
# ---------------------------------------------------------------------------


class TestGetPoleType:
    def test_known_label_returns_pole_type(self, healthcare_ontology):
        pole = _get_pole_type("Patient", healthcare_ontology)
        # All healthcare entity types should map to a POLE+O value
        assert pole in {"PERSON", "ORGANIZATION", "LOCATION", "EVENT", "OBJECT"}

    def test_unknown_label_defaults_to_object(self, healthcare_ontology):
        assert _get_pole_type("ZZZ_DoesNotExist", healthcare_ontology) == "OBJECT"


class TestSerializeEntityToDescription:
    def test_includes_pole_type_marker(self):
        desc = _serialize_entity_to_description(
            {"name": "X", "alpha": 1}, label="Foo", pole_type="OBJECT"
        )
        assert "_pole_type: OBJECT_" in desc

    def test_jsonifies_nested_values(self):
        desc = _serialize_entity_to_description(
            {"name": "X", "tags": ["a", "b"], "meta": {"k": 1}},
            label="Foo",
            pole_type="OBJECT",
        )
        assert "**Tags**" in desc
        assert "**Meta**" in desc
        # Lists/dicts get json-serialized into the value
        assert "[\"a\", \"b\"]" in desc or "[\"a\",\"b\"]" in desc

    def test_falsy_values_skipped(self):
        desc = _serialize_entity_to_description(
            {"name": "X", "empty_str": "", "none_value": None, "zero": 0},
            label="Foo",
            pole_type="OBJECT",
        )
        # zero is NOT treated as "skip" — only None and "" are skipped
        assert "**Zero**" in desc
        assert "**Empty str**" not in desc
        assert "**None value**" not in desc


# ---------------------------------------------------------------------------
# _ingest_with_nams (via the ingest_data entry point with patched client)
# ---------------------------------------------------------------------------


class TestIngestDataDispatch:
    def test_nams_path_invokes_add_entity_for_each_entity(
        self, tmp_path, healthcare_ontology, fake_client, fake_nams_module
    ):
        fixture = _make_fixture_file(tmp_path)
        cfg = ProjectConfig(
            project_name="x",
            domain="healthcare",
            framework="strands",
            nams_api_key="sk-test",
        )
        ingest_data(fixture, healthcare_ontology, cfg)

        # 3 entities total in the fixture (2 patients + 1 hospital)
        assert fake_client.long_term.add_entity.await_count == 3
        first_kwargs = fake_client.long_term.add_entity.await_args_list[0].kwargs
        assert first_kwargs["name"] == "Alice Park"
        assert first_kwargs["entity_type"] in {"PERSON", "ORGANIZATION", "LOCATION", "EVENT", "OBJECT"}
        assert "_pole_type:" in first_kwargs["description"]

    def test_nams_path_skips_relationships(
        self, tmp_path, healthcare_ontology, fake_client, fake_nams_module, capsys
    ):
        fixture = _make_fixture_file(tmp_path)
        cfg = ProjectConfig(
            project_name="x",
            domain="healthcare",
            framework="strands",
            nams_api_key="sk-test",
        )
        ingest_data(fixture, healthcare_ontology, cfg)
        captured = capsys.readouterr()
        assert "relationships not persisted" in captured.out

    def test_nams_path_stores_documents_as_messages(
        self, tmp_path, healthcare_ontology, fake_client, fake_nams_module
    ):
        fixture = _make_fixture_file(tmp_path)
        cfg = ProjectConfig(
            project_name="x",
            domain="healthcare",
            framework="strands",
            nams_api_key="sk-test",
        )
        ingest_data(fixture, healthcare_ontology, cfg)

        assert fake_client.short_term.add_message.await_count == 1
        kwargs = fake_client.short_term.add_message.await_args.kwargs
        assert kwargs["role"] == "document"
        assert kwargs["session_id"].startswith("docs-")
        assert kwargs["metadata"]["title"] == "Discharge Note — Bob Singh"

    def test_nams_path_creates_traces_via_reasoning_api(
        self, tmp_path, healthcare_ontology, fake_client, fake_nams_module
    ):
        fixture = _make_fixture_file(tmp_path)
        cfg = ProjectConfig(
            project_name="x",
            domain="healthcare",
            framework="strands",
            nams_api_key="sk-test",
        )
        ingest_data(fixture, healthcare_ontology, cfg)

        assert fake_client.reasoning.start_trace.await_count == 1
        assert fake_client.reasoning.add_step.await_count == 2
        assert fake_client.reasoning.complete_trace.await_count == 1

        complete_kwargs = fake_client.reasoning.complete_trace.await_args.kwargs
        assert complete_kwargs["outcome"] == "Referral to cardiology"
        assert complete_kwargs["success"] is True

    def test_nams_path_without_api_key_errors_clearly(
        self, tmp_path, healthcare_ontology, capsys
    ):
        fixture = _make_fixture_file(tmp_path)
        cfg = ProjectConfig(
            project_name="x",
            domain="healthcare",
            framework="strands",
            # NO nams_api_key
        )
        ingest_data(fixture, healthcare_ontology, cfg)
        captured = capsys.readouterr()
        assert "no API key" in captured.out

    def test_nams_path_handles_missing_fixture_file(
        self, tmp_path, healthcare_ontology, capsys
    ):
        nonexistent = tmp_path / "no-such-file.json"
        cfg = ProjectConfig(
            project_name="x",
            domain="healthcare",
            framework="strands",
            nams_api_key="sk-test",
        )
        ingest_data(nonexistent, healthcare_ontology, cfg)
        captured = capsys.readouterr()
        assert "Fixture file not found" in captured.out

    def test_bolt_path_calls_neo4j_via_memory_client(
        self, tmp_path, healthcare_ontology, monkeypatch
    ):
        """Bolt path delegates to the existing _ingest_with_memory_client path."""
        fixture = _make_fixture_file(tmp_path)
        cfg = ProjectConfig(
            project_name="x",
            domain="healthcare",
            framework="pydanticai",
            memory_backend="bolt",
            neo4j_uri="neo4j://localhost:7687",
        )

        bolt_client = _FakeNamsClient()
        bolt_client.graph = SimpleNamespace(execute_write=AsyncMock(return_value=None))

        mod = ModuleType("neo4j_agent_memory")
        mod.MemoryClient = MagicMock(return_value=bolt_client)
        mod.MemorySettings = MagicMock()
        mod.NamsConfig = MagicMock()
        monkeypatch.setitem(sys.modules, "neo4j_agent_memory", mod)

        ingest_data(fixture, healthcare_ontology, cfg)

        # Should NOT have hit the NAMS-shaped reasoning API on this path
        assert bolt_client.reasoning.start_trace.await_count == 0
        # SHOULD have hit graph.execute_write (schema + rels + docs + traces)
        assert bolt_client.graph.execute_write.await_count > 0


# ---------------------------------------------------------------------------
# reset_memory_store dispatch
# ---------------------------------------------------------------------------


class TestResetMemoryStoreDispatch:
    def test_nams_reset_calls_delete_entity_for_each(self, fake_client, fake_nams_module):
        fake_client.long_term.search_entities = AsyncMock(
            return_value=[
                SimpleNamespace(id="e1"),
                SimpleNamespace(id="e2"),
                SimpleNamespace(id="e3"),
            ]
        )
        cfg = ProjectConfig(
            project_name="x",
            domain="healthcare",
            framework="strands",
            nams_api_key="sk-test",
        )
        reset_memory_store(cfg)
        assert fake_client.long_term.delete_entity.await_count == 3

    def test_nams_reset_without_api_key_warns(self, capsys):
        cfg = ProjectConfig(
            project_name="x",
            domain="healthcare",
            framework="strands",
        )  # no nams_api_key
        reset_memory_store(cfg)
        captured = capsys.readouterr()
        assert "No NAMS API key" in captured.out

    def test_bolt_reset_uses_neo4j_driver(self):
        cfg = ProjectConfig(
            project_name="x",
            domain="healthcare",
            framework="pydanticai",
            memory_backend="bolt",
        )
        with patch("create_context_graph.ingest.reset_neo4j") as mock_reset:
            reset_memory_store(cfg)
            mock_reset.assert_called_once_with(
                cfg.neo4j_uri, cfg.neo4j_username, cfg.neo4j_password
            )
