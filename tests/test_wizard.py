# Copyright 2026 Neo4j Labs
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0

"""Unit tests for the interactive wizard.

Questionary's text/select/password/confirm/autocomplete/checkbox functions
all return objects with an .ask() method. We patch each of those at the
module level to drive scripted answers through the wizard end-to-end.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from create_context_graph.wizard import run_wizard


def _scripted(*answers):
    """Build a callable that returns successive scripted answers from `answers`.

    Wraps the answer in an object with an ``.ask()`` method (matching
    Questionary's return shape).
    """
    answers_iter = iter(answers)

    def _factory(*_args, **_kwargs):
        nxt = next(answers_iter)
        # Return an object whose .ask() returns the scripted value.
        return MagicMock(ask=MagicMock(return_value=nxt))

    return _factory


class _Scripted:
    """Bundle a script of answers and a per-prompt-type counter.

    Each questionary function (text, select, password, confirm, autocomplete,
    checkbox) gets its own queue. Tests express the wizard flow as a sequence
    of expected prompts.
    """

    def __init__(
        self,
        text: list = None,
        select: list = None,
        password: list = None,
        confirm: list = None,
        autocomplete: list = None,
        checkbox: list = None,
        path: list = None,
    ):
        self.text = iter(text or [])
        self.select = iter(select or [])
        self.password = iter(password or [])
        self.confirm = iter(confirm or [])
        self.autocomplete = iter(autocomplete or [])
        self.checkbox = iter(checkbox or [])
        self.path = iter(path or [])

    def _pop(self, name):
        try:
            value = next(getattr(self, name))
        except StopIteration:
            raise AssertionError(
                f"wizard asked one too many {name} questions; check the test script"
            )
        return MagicMock(ask=MagicMock(return_value=value))

    def install(self, mp):
        mp.setattr("create_context_graph.wizard.questionary.text",
                   lambda *a, **k: self._pop("text"))
        mp.setattr("create_context_graph.wizard.questionary.select",
                   lambda *a, **k: self._pop("select"))
        mp.setattr("create_context_graph.wizard.questionary.password",
                   lambda *a, **k: self._pop("password"))
        mp.setattr("create_context_graph.wizard.questionary.confirm",
                   lambda *a, **k: self._pop("confirm"))
        mp.setattr("create_context_graph.wizard.questionary.autocomplete",
                   lambda *a, **k: self._pop("autocomplete"))
        mp.setattr("create_context_graph.wizard.questionary.checkbox",
                   lambda *a, **k: self._pop("checkbox"))
        mp.setattr("create_context_graph.wizard.questionary.path",
                   lambda *a, **k: self._pop("path"))


class TestNamsHappyPath:
    """The default NAMS flow with no advanced customization."""

    def test_minimal_nams_scaffold(self, monkeypatch):
        script = _Scripted(
            text=["my-app"],                  # 1. project name
            autocomplete=["Healthcare"],      # 2. domain (display name)
            select=[
                "strands",                    # 3. framework (Choice .value)
                "per_conversation",           # 5. session strategy
                "demo",                       # 6. data source
            ],
            password=["sk-nams-fake"],        # 4. NAMS API key
            confirm=[
                False,                        # 7. customize advanced? → no
                True,                         # 8. proceed?
            ],
        )
        script.install(monkeypatch)

        cfg = run_wizard(self_hosted=False)

        assert cfg.project_name == "my-app"
        assert cfg.domain == "healthcare"
        assert cfg.framework == "strands"
        assert cfg.memory_backend == "nams"
        assert cfg.nams_api_key == "sk-nams-fake"
        assert cfg.session_strategy == "per_conversation"
        assert cfg.data_source == "demo"
        assert cfg.with_mcp is False
        assert cfg.auto_extract is True
        # NAMS forces preferences off
        assert cfg.effective_auto_preferences is False

    def test_nams_advanced_path_enables_mcp(self, monkeypatch):
        script = _Scripted(
            text=["my-app"],
            autocomplete=["Healthcare"],
            select=[
                "strands",
                "per_day",
                "demo",
            ],
            password=[
                "sk-nams-fake",     # NAMS key
                "",                 # Anthropic (advanced) — leave blank
                "sk-openai-fake",   # OpenAI (advanced)
            ],
            confirm=[
                True,    # customize advanced?
                True,    # with MCP?
                True,    # auto_extract?
                True,    # proceed?
            ],
        )
        script.install(monkeypatch)

        cfg = run_wizard(self_hosted=False)

        assert cfg.with_mcp is True
        # NAMS forces core profile regardless of what user wanted
        assert cfg.effective_mcp_profile == "core"
        assert cfg.openai_api_key == "sk-openai-fake"
        # auto_preferences hidden on NAMS — should remain False
        assert cfg.effective_auto_preferences is False


class TestSelfHostedPath:
    """The --self-hosted bolt flow."""

    def test_self_hosted_docker_scaffold(self, monkeypatch):
        script = _Scripted(
            text=["bolt-app"],
            autocomplete=["Financial Services"],
            select=[
                "pydanticai",       # framework
                "docker",           # neo4j type
                "per_conversation", # session strategy
                "demo",             # data source
            ],
            confirm=[
                False,   # customize advanced?
                True,    # proceed?
            ],
        )
        script.install(monkeypatch)

        cfg = run_wizard(self_hosted=True)

        assert cfg.memory_backend == "bolt"
        assert cfg.neo4j_type == "docker"
        assert cfg.neo4j_uri == "neo4j://localhost:7687"
        assert cfg.nams_api_key is None
        # On bolt, preferences default ON
        assert cfg.effective_auto_preferences is True

    def test_self_hosted_existing_neo4j(self, monkeypatch):
        script = _Scripted(
            text=[
                "x",                          # project name
                "neo4j+s://abc.databases.neo4j.io",  # neo4j uri
                "myuser",                     # username
            ],
            autocomplete=["Software Engineering"],
            select=[
                "pydanticai",
                "existing",                   # neo4j type
                "per_conversation",
                "demo",
            ],
            password=["secret123"],
            confirm=[
                False,
                True,
            ],
        )
        script.install(monkeypatch)

        cfg = run_wizard(self_hosted=True)
        assert cfg.neo4j_type == "existing"
        assert cfg.neo4j_uri == "neo4j+s://abc.databases.neo4j.io"
        assert cfg.neo4j_username == "myuser"
        assert cfg.neo4j_password == "secret123"


class TestQuestionaryConstruction:
    """Regression tests that exercise the real questionary.select construction.

    These guard against bugs where a ``default=`` argument doesn't match any
    choice's ``Choice.title`` (or value, depending on questionary version) — a
    failure mode the heavily-mocked wizard tests above can't catch because they
    replace ``questionary.select`` entirely.
    """

    def test_framework_prompt_constructs_cleanly(self, monkeypatch):
        """Building ``questionary.select`` for the framework picker must not
        raise on default-value validation."""
        import questionary

        from create_context_graph.wizard import _prompt_framework

        # Capture the call but let the real questionary build the object.
        # If a default value is wrong, the .select() constructor raises here
        # before .ask() is ever called.
        called_with = {}
        real_select = questionary.select

        def capturing_select(*args, **kwargs):
            called_with["args"] = args
            called_with["kwargs"] = kwargs
            obj = real_select(*args, **kwargs)
            obj.ask = MagicMock(return_value="strands")
            return obj

        monkeypatch.setattr(
            "create_context_graph.wizard.questionary.select", capturing_select
        )

        result = _prompt_framework()
        assert result == "strands"
        # The first choice should be the default framework so the row is highlighted
        # on entry without needing a fragile ``default=`` lookup.
        choices = called_with["kwargs"]["choices"]
        assert choices[0].value == "strands"

    def test_session_strategy_prompt_constructs_cleanly(self, monkeypatch):
        import questionary

        from create_context_graph.wizard import _prompt_session_strategy

        real_select = questionary.select

        def capturing_select(*args, **kwargs):
            obj = real_select(*args, **kwargs)
            obj.ask = MagicMock(return_value="per_conversation")
            return obj

        monkeypatch.setattr(
            "create_context_graph.wizard.questionary.select", capturing_select
        )

        # If session-strategy ever gets a broken default=, this raises.
        assert _prompt_session_strategy() == "per_conversation"


class TestEdgeCases:
    def test_aborts_when_user_cancels_proceed(self, monkeypatch):
        script = _Scripted(
            text=["x"],
            autocomplete=["Healthcare"],
            select=["strands", "per_conversation", "demo"],
            password=["sk-nams-fake"],
            confirm=[
                False,   # advanced
                False,   # proceed? → user cancels
            ],
        )
        script.install(monkeypatch)

        with pytest.raises(SystemExit):
            run_wizard(self_hosted=False)

    def test_invalid_domain_aborts(self, monkeypatch):
        script = _Scripted(
            text=["x"],
            autocomplete=["NotARealDomain"],  # user typed garbage
        )
        script.install(monkeypatch)

        with pytest.raises(SystemExit):
            run_wizard(self_hosted=False)

    def test_empty_nams_key_aborts(self, monkeypatch):
        script = _Scripted(
            text=["x"],
            autocomplete=["Healthcare"],
            select=["strands"],
            password=[""],   # empty NAMS key
        )
        script.install(monkeypatch)

        with pytest.raises(SystemExit):
            run_wizard(self_hosted=False)
