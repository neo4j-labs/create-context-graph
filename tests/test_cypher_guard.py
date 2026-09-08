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

"""Tests for generated Cypher query safety guards."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest
from jinja2 import Environment


TEMPLATES_DIR = (
    Path(__file__).resolve().parent.parent
    / "src"
    / "create_context_graph"
    / "templates"
)


@pytest.fixture
def cypher_guard_module(tmp_path):
    """Render the pure-Python guard template and import it as a module."""
    template_path = TEMPLATES_DIR / "backend" / "shared" / "cypher_guard.py.j2"
    rendered = Environment().from_string(template_path.read_text()).render()

    module_path = tmp_path / "_cypher_guard.py"
    module_path.write_text(rendered)

    spec = importlib.util.spec_from_file_location("_cypher_guard", module_path)
    assert spec is not None
    assert spec.loader is not None

    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class TestValidateReadOnly:
    """validate_read_only allows read queries and blocks writes."""

    @pytest.mark.parametrize(
        "query",
        [
            "MATCH (n) RETURN n",
            "MATCH (p:Person) WITH p WHERE p.name IS NOT NULL RETURN p.name",
            "MATCH (n) RETURN n ORDER BY n.name LIMIT 10 SKIP 5",
            "UNWIND $items AS item RETURN item",
            "CALL db.labels() YIELD label RETURN label",
            "CALL db.schema.visualization()",
        ],
    )
    def test_allows_read_only_queries(self, cypher_guard_module, query):
        cypher_guard_module.validate_read_only(query)

    @pytest.mark.parametrize(
        "query,keyword",
        [
            ("CREATE (:Person {name: 'Ada'})", "CREATE"),
            ("MERGE (p:Person {id: 1}) RETURN p", "MERGE"),
            ("MATCH (p:Person) SET p.name = 'Ada'", "SET"),
            ("MATCH (p:Person) DELETE p", "DELETE"),
            ("MATCH (p:Person) DETACH DELETE p", "DETACH"),
            ("MATCH (p:Person) REMOVE p.name", "REMOVE"),
            ("DROP CONSTRAINT person_id IF EXISTS", "DROP CONSTRAINT"),
            ("DROP INDEX person_name IF EXISTS", "DROP INDEX"),
        ],
    )
    def test_blocks_write_operations(self, cypher_guard_module, query, keyword):
        with pytest.raises(cypher_guard_module.CypherGuardError) as exc:
            cypher_guard_module.validate_read_only(query)

        assert keyword in str(exc.value)

    def test_blocks_write_operations_case_insensitively(self, cypher_guard_module):
        with pytest.raises(cypher_guard_module.CypherGuardError) as exc:
            cypher_guard_module.validate_read_only("match (n) detach delete n")

        assert "DETACH" in str(exc.value)


class TestEnforceRowLimit:
    """enforce_row_limit adds or caps LIMIT clauses."""

    def test_appends_default_limit_when_missing(self, cypher_guard_module):
        query = "MATCH (n) RETURN n"

        assert cypher_guard_module.enforce_row_limit(query) == (
            "MATCH (n) RETURN n\nLIMIT 100"
        )

    def test_preserves_existing_numeric_limit(self, cypher_guard_module):
        query = "MATCH (n) RETURN n LIMIT 25"

        assert cypher_guard_module.enforce_row_limit(query) == query

    def test_caps_large_numeric_limit(self, cypher_guard_module):
        query = "MATCH (n) RETURN n LIMIT 99999"

        assert cypher_guard_module.enforce_row_limit(query) == (
            "MATCH (n) RETURN n LIMIT 500"
        )

    def test_preserves_parameterized_limit(self, cypher_guard_module):
        query = "MATCH (n) RETURN n LIMIT $limit"

        assert cypher_guard_module.enforce_row_limit(query) == query

    def test_uses_custom_default_limit(self, cypher_guard_module):
        query = "MATCH (n) RETURN n"

        assert cypher_guard_module.enforce_row_limit(query, default_limit=50) == (
            "MATCH (n) RETURN n\nLIMIT 50"
        )

    def test_strips_trailing_semicolons_before_appending(self, cypher_guard_module):
        query = "MATCH (n) RETURN n;  "

        assert cypher_guard_module.enforce_row_limit(query) == (
            "MATCH (n) RETURN n\nLIMIT 100"
        )
