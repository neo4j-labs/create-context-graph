# Copyright 2026 Neo4j Labs
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0

"""Contract test: the CLI's NAMS ingest path and the scaffolded
``import_data.py`` must emit identical NAMS write sequences.

The two paths live in different files (``src/.../ingest.py`` and the rendered
``templates/.../import_data.py.j2``) on purpose — see the design discussion in
CLAUDE.md / the grill-me transcript for why duplication beats a shared upstream
helper here. The risk that comes with duplication is drift: behavior diverges
in one file but not the other, and we don't notice until a user does.

This test pins both paths to a shared NormalizedData fixture, captures every
NAMS client method call from each, and asserts the sequences match. If you
change one path's behavior, this test breaks and you must mirror the change
in the other.
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock

from create_context_graph.ingest import run_nams_ingest
from create_context_graph.ontology import load_domain


# ---------------------------------------------------------------------------
# Shared canonical fixture — exercises every load-bearing branch:
#   - entity with no body (Patient)
#   - entity with a body field (Note.body) — must trigger add_message
#   - entity with outbound relationships — must trigger ccg-edges encoding
#   - document — must trigger BOTH add_entity AND add_message
#   - decision trace — must trigger reasoning.start_trace + add_step + complete
# ---------------------------------------------------------------------------


CANONICAL_FIXTURE: dict[str, Any] = {
    "entities": {
        "Patient": [
            {"name": "Alice Park", "age": 67, "status": "active"},
            {"name": "Bob Singh", "age": 42, "status": "discharged"},
        ],
        "Note": [
            {
                "name": "Note-001",
                "body": "Patient reports intermittent chest pain over 3 days.",
                "author": "Dr. Lee",
            },
        ],
        "Hospital": [
            {"name": "Mercy General", "city": "Portland"},
        ],
    },
    "relationships": [
        # Alice → Mercy: typed source entity has an outbound edge → ccg-edges
        {
            "source_name": "Alice Park", "source_label": "Patient",
            "target_name": "Mercy General", "target_label": "Hospital",
            "type": "TREATED_AT",
        },
        # Note → Alice: another edge to encode
        {
            "source_name": "Note-001", "source_label": "Note",
            "target_name": "Alice Park", "target_label": "Patient",
            "type": "ABOUT",
        },
    ],
    "documents": [
        {
            "title": "Discharge Note — Bob",
            "content": "Patient discharged today, vitals normal.",
            "template_id": "discharge",
            "template_name": "Discharge Note",
        },
    ],
    "traces": [
        {
            "id": "trace-alpha",
            "task": "Diagnose chest pain",
            "outcome": "Cardiology referral",
            "steps": [
                {"thought": "Rule out MI", "action": "Order ECG", "observation": "Normal sinus"},
            ],
        },
    ],
}

BODY_FIELDS = {"Note": "body"}


# ---------------------------------------------------------------------------
# Recording NAMS client double
# ---------------------------------------------------------------------------


class _RecordingClient:
    """Async-context-manager double that records every long_term /
    short_term / reasoning call as a (method, kwargs) tuple."""

    def __init__(self):
        self.calls: list[tuple[str, dict[str, Any]]] = []
        self.long_term = SimpleNamespace(
            add_entity=AsyncMock(side_effect=self._record("long_term.add_entity")),
        )
        self.short_term = SimpleNamespace(
            add_message=AsyncMock(side_effect=self._record("short_term.add_message")),
        )

        async def _start_trace(**kw):
            self.calls.append(("reasoning.start_trace", _clean(kw)))
            return SimpleNamespace(id=f"trace-{len(self.calls)}")

        self.reasoning = SimpleNamespace(
            start_trace=AsyncMock(side_effect=_start_trace),
            add_step=AsyncMock(side_effect=self._record("reasoning.add_step")),
            complete_trace=AsyncMock(side_effect=self._record("reasoning.complete_trace")),
        )

    def _record(self, name: str):
        async def _inner(**kw):
            self.calls.append((name, _clean(kw)))
            return SimpleNamespace(id=f"id-{len(self.calls)}")
        return _inner

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_):
        return None


def _clean(kw: dict[str, Any]) -> dict[str, Any]:
    """Normalize kwargs so dict comparison is stable across paths.

    The two ingestors use slightly different session_id conventions (the CLI
    keys docs by domain id ``docs-{domain}``; the scaffolded importer uses
    a fixed ``docs-import`` because the running app already knows its
    domain context). We strip session_id from the comparison — it's
    addressing metadata, not semantic graph content.
    """
    return {k: v for k, v in kw.items() if k != "session_id"}


# ---------------------------------------------------------------------------
# Driver — render the scaffolded template, exec it in a sandbox, invoke its
# _ingest_via_nams against the same recording client.
# ---------------------------------------------------------------------------


def _exec_scaffold_template(client: _RecordingClient) -> dict[str, Any]:
    """Render import_data.py.j2 enough to extract its ``_ingest_via_nams``
    function, then return a bound callable that uses ``client``."""
    template_path = (
        Path(__file__).parent.parent
        / "src" / "create_context_graph" / "templates"
        / "backend" / "connectors" / "import_data.py.j2"
    )
    # Strip Jinja blocks — we render with empty connectors so the only thing
    # left is plain Python.
    from jinja2 import Environment, FileSystemLoader

    env = Environment(
        loader=FileSystemLoader(str(template_path.parent)),
        keep_trailing_newline=True,
    )
    rendered = env.get_template("import_data.py.j2").render(saas_connectors=[])

    # Inject stand-ins for the modules the template imports.
    fake_settings = SimpleNamespace(
        memory_api_key="sk-test",
        memory_nams_endpoint="https://test.example/v1",
        memory_backend="nams",
        # Bolt-path settings — _ingest_via_bolt reads these even when the
        # backend is NAMS, because both functions live in the same module.
        neo4j_uri="neo4j://test:7687",
        neo4j_username="neo4j",
        neo4j_password="testpass",
    )
    fake_config_mod = ModuleType("app.config")
    fake_config_mod.settings = fake_settings
    fake_app_mod = ModuleType("app")
    fake_connectors_mod = ModuleType("app.connectors")
    sys.modules["app"] = fake_app_mod
    sys.modules["app.config"] = fake_config_mod
    sys.modules["app.connectors"] = fake_connectors_mod

    # Stub neo4j_agent_memory so the dynamic import inside _ingest_via_nams
    # returns our recording client.
    fake_nam = ModuleType("neo4j_agent_memory")
    fake_nam.MemoryClient = MagicMock(return_value=client)
    fake_nam.MemorySettings = MagicMock()
    fake_nam.NamsConfig = MagicMock()
    sys.modules["neo4j_agent_memory"] = fake_nam

    # Exec the rendered module body in a fresh namespace. The template
    # computes PROJECT_ROOT from __file__, so we set one inside a synthetic
    # tmp directory — the exact value doesn't matter because the test
    # overrides SIDECAR_DIR after exec.
    import tempfile
    synthetic_root = Path(tempfile.gettempdir()) / "ccg_parity_test"
    (synthetic_root / "backend" / "scripts").mkdir(parents=True, exist_ok=True)
    ns: dict[str, Any] = {
        "__name__": "scaffolded_import_data",
        "__file__": str(synthetic_root / "backend" / "scripts" / "import_data.py"),
    }
    exec(compile(rendered, str(template_path), "exec"), ns)
    return ns


def _run_cli_path(client: _RecordingClient) -> list[tuple[str, dict[str, Any]]]:
    ontology = load_domain("healthcare")
    asyncio.run(
        run_nams_ingest(
            client=client,
            fixture_data=CANONICAL_FIXTURE,
            ontology=ontology,
            body_fields=BODY_FIELDS,
        )
    )
    return list(client.calls)


def _run_scaffold_path(client: _RecordingClient) -> list[tuple[str, dict[str, Any]]]:
    prior_modules = {
        name: sys.modules.get(name)
        for name in ("app", "app.config", "app.connectors", "neo4j_agent_memory")
    }
    try:
        ns = _exec_scaffold_template(client)
        ingest_via_nams = ns["_ingest_via_nams"]

        # The scaffolded path also writes failures to a deadletter file; point it
        # at a temp dir so we don't pollute the repo.
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            # The template hard-codes PROJECT_ROOT relative to the script file;
            # we monkeypatch SIDECAR_DIR in the exec'd namespace.
            ns["SIDECAR_DIR"] = Path(tmp)
            ns["DEADLETTER_FILE"] = Path(tmp) / "deadletter.jsonl"
            asyncio.run(ingest_via_nams(CANONICAL_FIXTURE, BODY_FIELDS))
        return list(client.calls)
    finally:
        for name, module in prior_modules.items():
            if module is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = module


# ---------------------------------------------------------------------------
# The actual contract assertion
# ---------------------------------------------------------------------------


def _strip_pole_type(seq: list[tuple[str, dict[str, Any]]]) -> list[tuple[str, dict[str, Any]]]:
    """The CLI path uses the ontology's POLE+O mapping; the scaffolded path
    uses a label-name heuristic. They agree on common labels (Person, etc.)
    but Patient → PERSON on the CLI side and Patient → OBJECT on the
    scaffolded side, because the scaffolded code doesn't know about
    domain ontologies. We compare everything except entity_type so the rest
    of the call sequence parity is enforced.

    This is the deliberate seam between the two paths: CLI knows the domain
    schema; the scaffolded app handles arbitrary connector-emitted labels.
    """
    out: list[tuple[str, dict[str, Any]]] = []
    for name, kw in seq:
        cleaned = {k: v for k, v in kw.items() if k != "entity_type"}
        out.append((name, cleaned))
    return out


def test_cli_and_scaffold_emit_same_nams_call_sequence():
    cli_calls = _strip_pole_type(_run_cli_path(_RecordingClient()))
    scaffold_calls = _strip_pole_type(_run_scaffold_path(_RecordingClient()))

    # Same number of writes per kind.
    def _counts(seq):
        out: dict[str, int] = {}
        for name, _ in seq:
            out[name] = out.get(name, 0) + 1
        return out

    assert _counts(cli_calls) == _counts(scaffold_calls), (
        f"Call counts diverge:\n  CLI:      {_counts(cli_calls)}\n"
        f"  Scaffold: {_counts(scaffold_calls)}"
    )

    # Same set of entity names written in the same order.
    cli_entity_names = [kw.get("name") for n, kw in cli_calls if n == "long_term.add_entity"]
    sc_entity_names = [kw.get("name") for n, kw in scaffold_calls if n == "long_term.add_entity"]
    assert cli_entity_names == sc_entity_names, (
        f"Entity write order diverges:\n  CLI:      {cli_entity_names}\n"
        f"  Scaffold: {sc_entity_names}"
    )

    # The ccg-edges block must be present and identical for the entities
    # that have outbound relationships in the canonical fixture.
    cli_descriptions = {
        kw.get("name"): kw.get("description", "")
        for n, kw in cli_calls if n == "long_term.add_entity"
    }
    sc_descriptions = {
        kw.get("name"): kw.get("description", "")
        for n, kw in scaffold_calls if n == "long_term.add_entity"
    }
    for name in ("Alice Park", "Note-001"):
        assert "```ccg-edges" in cli_descriptions[name], (
            f"CLI: expected ccg-edges block for {name}, got: {cli_descriptions[name]!r}"
        )
        assert "```ccg-edges" in sc_descriptions[name], (
            f"Scaffold: expected ccg-edges block for {name}, got: {sc_descriptions[name]!r}"
        )
        # The block content itself must be identical between the two paths.
        cli_block = cli_descriptions[name].split("```ccg-edges", 1)[1]
        sc_block = sc_descriptions[name].split("```ccg-edges", 1)[1]
        assert cli_block == sc_block, (
            f"ccg-edges block for {name} diverges:\n  CLI: {cli_block!r}\n"
            f"  Scaffold: {sc_block!r}"
        )


def test_document_is_dual_tracked_in_both_paths():
    """Documents must trigger both add_entity (long-term, queryable) AND
    add_message (short-term, extraction fuel) on both paths."""
    cli_calls = _run_cli_path(_RecordingClient())
    scaffold_calls = _run_scaffold_path(_RecordingClient())

    def _doc_entity_present(seq):
        return any(
            n == "long_term.add_entity" and kw.get("name") == "Discharge Note — Bob"
            for n, kw in seq
        )

    def _doc_message_present(seq):
        return any(
            n == "short_term.add_message" and kw.get("role") == "document"
            and (kw.get("metadata") or {}).get("title") == "Discharge Note — Bob"
            for n, kw in seq
        )

    assert _doc_entity_present(cli_calls), "CLI path missing Document long_term entity"
    assert _doc_entity_present(scaffold_calls), "Scaffold path missing Document long_term entity"
    assert _doc_message_present(cli_calls), "CLI path missing Document short_term message"
    assert _doc_message_present(scaffold_calls), "Scaffold path missing Document short_term message"


def test_body_field_entity_emits_message_in_both_paths():
    """An entity declared in BODY_FIELDS (Note.body) must trigger an
    add_message with the body content, on both paths."""
    cli_calls = _run_cli_path(_RecordingClient())
    scaffold_calls = _run_scaffold_path(_RecordingClient())

    def _body_message(seq):
        for n, kw in seq:
            if n == "short_term.add_message" and (kw.get("metadata") or {}).get("entity_name") == "Note-001":
                return kw
        return None

    cli_body = _body_message(cli_calls)
    sc_body = _body_message(scaffold_calls)
    assert cli_body is not None, "CLI path: Note body not sent through add_message"
    assert sc_body is not None, "Scaffold path: Note body not sent through add_message"
    assert cli_body["content"] == sc_body["content"], (
        f"Body content diverges:\n  CLI: {cli_body['content']!r}\n  Scaffold: {sc_body['content']!r}"
    )
    assert "chest pain" in cli_body["content"]


def test_no_relationship_writes_on_nams():
    """NAMS REST has no add_relationship; both paths must avoid calling it."""
    cli_calls = _run_cli_path(_RecordingClient())
    scaffold_calls = _run_scaffold_path(_RecordingClient())
    assert all(n != "long_term.add_relationship" for n, _ in cli_calls)
    assert all(n != "long_term.add_relationship" for n, _ in scaffold_calls)


def test_retry_deadletter_rebuilds_retryable_payloads():
    ns = _exec_scaffold_template(_RecordingClient())
    captured: dict[str, Any] = {}

    async def _fake_ingest(payload, body_fields):
        captured["payload"] = payload
        captured["body_fields"] = body_fields
        return {"failures": 0}

    ns["_ingest_via_nams"] = _fake_ingest

    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        deadletter = Path(tmp) / "deadletter.jsonl"
        ns["DEADLETTER_FILE"] = deadletter
        deadletter.write_text(
            "\n".join(
                json.dumps(record)
                for record in [
                    {"kind": "entity", "label": "Patient", "item": {"name": "Alice"}},
                    {"kind": "entity-batch", "label": "Hospital", "items": [{"name": "Mercy"}]},
                    {
                        "kind": "body",
                        "label": "Note",
                        "item": {"name": "Note-1", "body": "hello"},
                        "body_field": "body",
                    },
                    {"kind": "relationship", "rel": {"type": "ABOUT", "source_name": "Note-1", "target_name": "Alice"}},
                    {"kind": "document", "doc": {"title": "Doc", "content": "body"}},
                    {"kind": "trace", "trace": {"id": "t1", "task": "task", "steps": []}},
                ]
            ) + "\n"
        )

        assert ns["_retry_deadletter"]() == 0

    assert captured["payload"]["entities"]["Patient"] == [{"name": "Alice"}]
    assert captured["payload"]["entities"]["Hospital"] == [{"name": "Mercy"}]
    assert captured["payload"]["entities"]["Note"] == [{"name": "Note-1", "body": "hello"}]
    assert captured["payload"]["relationships"] == [
        {"type": "ABOUT", "source_name": "Note-1", "target_name": "Alice"},
    ]
    assert captured["payload"]["documents"] == [{"title": "Doc", "content": "body"}]
    assert captured["payload"]["traces"] == [{"id": "t1", "task": "task", "steps": []}]
    assert captured["body_fields"] == {"Note": "body"}


# ---------------------------------------------------------------------------
# Bolt path async-shape tests
#
# These were written against the v0.12.0 sync ``_ingest_via_bolt``. v0.13.0
# made the function async and pulled driver construction inside via
# ``AsyncGraphDatabase.driver(...)``. The tests now patch
# ``neo4j.AsyncGraphDatabase`` and run the coroutine through ``asyncio.run``.
# ---------------------------------------------------------------------------


class _AsyncSessionMock:
    def __init__(self):
        self.calls: list[tuple[str, dict]] = []

    async def run(self, cypher, parameters=None, **kwargs):
        params = parameters if parameters is not None else (kwargs or {})
        self.calls.append((cypher, dict(params)))
        return SimpleNamespace(consume=AsyncMock())


class _AsyncDriverMock:
    def __init__(self):
        self.session_obj = _AsyncSessionMock()

    async def verify_connectivity(self):
        return None

    async def close(self):
        return None

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_):
        return None

    def session(self):
        outer = self

        class _Ctx:
            async def __aenter__(self_inner):
                return outer.session_obj

            async def __aexit__(self_inner, *_):
                return None

        return _Ctx()


def _run_bolt_ingest(ns, payload, body_fields):
    """Patch ``neo4j.AsyncGraphDatabase`` and run the async function."""
    driver = _AsyncDriverMock()
    prior = sys.modules.get("neo4j")
    try:
        fake = ModuleType("neo4j")

        class _Factory:
            @staticmethod
            def driver(*_args, **_kwargs):
                return driver

        fake.AsyncGraphDatabase = _Factory
        sys.modules["neo4j"] = fake

        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            ns["SIDECAR_DIR"] = Path(tmp)
            ns["DEADLETTER_FILE"] = Path(tmp) / "deadletter.jsonl"
            counts = asyncio.run(ns["_ingest_via_bolt"](payload, body_fields))
    finally:
        if prior is None:
            sys.modules.pop("neo4j", None)
        else:
            sys.modules["neo4j"] = prior
    return counts, driver.session_obj


def test_bolt_ingest_rejects_unsafe_cypher_identifiers():
    ns = _exec_scaffold_template(_RecordingClient())
    counts, session = _run_bolt_ingest(
        ns,
        {
            "entities": {"Bad Label": [{"name": "Alice"}]},
            "relationships": [{"type": "BAD-TYPE", "source_name": "Alice", "target_name": "Bob"}],
            "documents": [],
            "traces": [],
        },
        {},
    )
    assert counts["failures"] == 2
    assert session.calls == []


def test_bolt_ingest_uses_relationship_labels_when_present():
    ns = _exec_scaffold_template(_RecordingClient())
    counts, session = _run_bolt_ingest(
        ns,
        {
            "entities": {},
            "relationships": [
                {
                    "type": "TREATS",
                    "source_name": "Mercy General",
                    "source_label": "Hospital",
                    "target_name": "Mercy General",
                    "target_label": "Provider",
                }
            ],
            "documents": [],
            "traces": [],
        },
        {},
    )
    assert counts["relationships"] == 1
    assert counts["failures"] == 0
    assert len(session.calls) == 1
    cypher, params = session.calls[0]
    assert "MATCH (a:Hospital {name: $source_name})" in cypher
    assert "MATCH (b:Provider {name: $target_name})" in cypher
    assert "MERGE (a)-[r:TREATS]->(b)" in cypher
    assert params == {"source_name": "Mercy General", "target_name": "Mercy General"}
