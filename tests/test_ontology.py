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

"""Unit tests for the ontology module."""

import re

import pytest

from create_context_graph.ontology import (
    DomainOntology,
    _sanitize_enum_name,
    generate_cypher_schema,
    generate_pydantic_models,
    generate_visualization_config,
    list_available_domains,
    load_domain,
)


class TestListDomains:
    def test_returns_list(self):
        domains = list_available_domains()
        assert isinstance(domains, list)

    def test_has_at_least_22_domains(self):
        domains = list_available_domains()
        assert len(domains) >= 22

    def test_each_domain_has_id_and_name(self):
        domains = list_available_domains()
        for d in domains:
            assert "id" in d
            assert "name" in d
            assert len(d["id"]) > 0
            assert len(d["name"]) > 0

    def test_base_not_in_list(self):
        domains = list_available_domains()
        ids = [d["id"] for d in domains]
        assert "_base" not in ids

    def test_known_domains_present(self):
        domains = list_available_domains()
        ids = [d["id"] for d in domains]
        assert "financial-services" in ids
        assert "healthcare" in ids
        assert "software-engineering" in ids
        assert "wildlife-management" in ids


class TestLoadDomain:
    def test_load_financial_services(self):
        ont = load_domain("financial-services")
        assert isinstance(ont, DomainOntology)
        assert ont.domain.id == "financial-services"
        assert ont.domain.name == "Financial Services"

    def test_load_healthcare(self):
        ont = load_domain("healthcare")
        assert ont.domain.id == "healthcare"

    def test_load_nonexistent_raises(self):
        with pytest.raises(FileNotFoundError):
            load_domain("nonexistent-domain-xyz")

    def test_entity_types_present(self):
        ont = load_domain("financial-services")
        assert len(ont.entity_types) > 0
        labels = [et.label for et in ont.entity_types]
        assert "Account" in labels
        assert "Transaction" in labels

    def test_base_entities_merged(self):
        ont = load_domain("financial-services")
        labels = [et.label for et in ont.entity_types]
        # Base POLE+O entities should be merged in
        assert "Person" in labels
        assert "Organization" in labels
        assert "Location" in labels

    def test_relationships_present(self):
        ont = load_domain("financial-services")
        assert len(ont.relationships) > 0
        rel_types = [r.type for r in ont.relationships]
        assert "OWNS" in rel_types

    def test_base_relationships_merged(self):
        ont = load_domain("financial-services")
        rel_types = [r.type for r in ont.relationships]
        assert "WORKS_FOR" in rel_types  # from base

    def test_document_templates_present(self):
        ont = load_domain("financial-services")
        assert len(ont.document_templates) > 0
        for tmpl in ont.document_templates:
            assert tmpl.id
            assert tmpl.name
            assert tmpl.count > 0

    def test_decision_traces_present(self):
        ont = load_domain("financial-services")
        assert len(ont.decision_traces) > 0
        for trace in ont.decision_traces:
            assert trace.id
            assert trace.task
            assert len(trace.steps) > 0

    def test_demo_scenarios_present(self):
        ont = load_domain("financial-services")
        assert len(ont.demo_scenarios) > 0
        for scenario in ont.demo_scenarios:
            assert scenario.name
            assert len(scenario.prompts) > 0

    def test_agent_tools_present(self):
        ont = load_domain("financial-services")
        assert len(ont.agent_tools) > 0
        for tool in ont.agent_tools:
            assert tool.name
            assert tool.description
            assert tool.cypher

    def test_system_prompt_present(self):
        ont = load_domain("financial-services")
        assert len(ont.system_prompt) > 50

    def test_visualization_config(self):
        ont = load_domain("financial-services")
        assert len(ont.visualization.node_colors) > 0
        assert len(ont.visualization.node_sizes) > 0
        assert ont.visualization.default_cypher


class TestLoadAllDomains:
    """Ensure every bundled domain YAML parses without error."""

    def test_all_domains_load(self):
        domains = list_available_domains()
        for d in domains:
            ont = load_domain(d["id"])
            assert ont.domain.id == d["id"]
            assert len(ont.entity_types) >= 4  # base POLE+O + at least 1 domain
            assert len(ont.relationships) >= 3
            assert len(ont.agent_tools) >= 1
            assert ont.system_prompt


    def test_all_domains_default_cypher_has_limit(self):
        domains = list_available_domains()
        for d in domains:
            ont = load_domain(d["id"])
            cypher = ont.visualization.default_cypher.strip().upper()
            assert "LIMIT" in cypher, (
                f"Domain '{d['id']}' default_cypher missing LIMIT clause"
            )

    def test_no_color_collisions_with_base(self):
        """BUG-013: No domain entity should share a color with a base POLE+O entity."""
        from create_context_graph.ontology import load_domain as _load
        base = _load("healthcare")  # any domain to get base types
        # Collect base entity colors (Person, Organization, Location, Event, Object)
        base_labels = {"Person", "Organization", "Location", "Event", "Object"}
        base_colors = {}
        for et in base.entity_types:
            if et.label in base_labels:
                base_colors[et.label] = et.color

        domains = list_available_domains()
        for d in domains:
            ont = load_domain(d["id"])
            for et in ont.entity_types:
                if et.label not in base_labels:
                    for base_label, base_color in base_colors.items():
                        assert et.color != base_color, (
                            f"Domain '{d['id']}': {et.label} color {et.color} "
                            f"collides with base {base_label}"
                        )


class TestGenerateCypherSchema:
    def test_generates_constraints(self, financial_ontology):
        schema = generate_cypher_schema(financial_ontology)
        assert "CREATE CONSTRAINT" in schema
        assert "IF NOT EXISTS" in schema
        assert "account_id" in schema.lower()

    def test_generates_indexes(self, financial_ontology):
        schema = generate_cypher_schema(financial_ontology)
        assert "CREATE INDEX" in schema

    def test_has_header_comment(self, financial_ontology):
        schema = generate_cypher_schema(financial_ontology)
        assert "Financial Services" in schema

    def test_no_empty_statements(self, financial_ontology):
        schema = generate_cypher_schema(financial_ontology)
        for line in schema.strip().split("\n"):
            line = line.strip()
            if line and not line.startswith("//"):
                assert len(line) > 5  # meaningful statement


class TestGeneratePydanticModels:
    def test_generates_valid_python(self, financial_ontology):
        source = generate_pydantic_models(financial_ontology)
        assert "from pydantic import BaseModel" in source
        assert "class Account(BaseModel):" in source
        assert "class Transaction(BaseModel):" in source

    def test_generates_enum_classes(self, financial_ontology):
        source = generate_pydantic_models(financial_ontology)
        # Account has account_type enum
        assert "Enum" in source

    def test_source_compiles(self, financial_ontology):
        source = generate_pydantic_models(financial_ontology)
        # Should be valid Python that compiles
        compile(source, "<test>", "exec")


class TestGenerateVisualizationConfig:
    def test_has_colors_and_sizes(self, financial_ontology):
        config = generate_visualization_config(financial_ontology)
        assert "nodeColors" in config
        assert "nodeSizes" in config
        assert "defaultCypher" in config

    def test_all_entity_types_have_colors(self, financial_ontology):
        config = generate_visualization_config(financial_ontology)
        for et in financial_ontology.entity_types:
            assert et.label in config["nodeColors"]


class TestSanitizeEnumName:
    """Test _sanitize_enum_name handles special characters."""

    def test_plus_sign(self):
        assert _sanitize_enum_name("A+") == "A_PLUS"

    def test_minus_sign(self):
        assert _sanitize_enum_name("A-") == "A_MINUS"

    def test_blood_types(self):
        assert _sanitize_enum_name("AB+") == "AB_PLUS"
        assert _sanitize_enum_name("AB-") == "AB_MINUS"
        assert _sanitize_enum_name("O+") == "O_PLUS"
        assert _sanitize_enum_name("O-") == "O_MINUS"

    def test_leading_digit(self):
        assert _sanitize_enum_name("3d_model") == "_3D_MODEL"

    def test_all_digits(self):
        assert _sanitize_enum_name("123") == "_123"

    def test_normal_value(self):
        assert _sanitize_enum_name("normal_value") == "NORMAL_VALUE"

    def test_spaces(self):
        assert _sanitize_enum_name("with spaces") == "WITH_SPACES"

    def test_hyphens_as_separator(self):
        """Hyphens between words are treated as separators, not minus."""
        assert _sanitize_enum_name("some-value") == "SOME_VALUE"

    def test_trailing_minus(self):
        """Trailing minus is converted to _MINUS."""
        assert _sanitize_enum_name("B-") == "B_MINUS"

    def test_result_is_valid_identifier(self):
        """All sanitized names must be valid Python identifiers."""
        test_values = [
            "A+", "A-", "B+", "B-", "AB+", "AB-", "O+", "O-",
            "3d_model", "normal", "with spaces", "123numeric",
        ]
        for val in test_values:
            result = _sanitize_enum_name(val)
            assert result.isidentifier(), f"'{val}' -> '{result}' is not a valid identifier"


class TestEnumModelsCompileAllDomains:
    """Ensure models.py compiles for all domains (catches enum bugs)."""

    ALL_DOMAINS = [d["id"] for d in list_available_domains()]

    @pytest.mark.parametrize("domain_id", ALL_DOMAINS)
    def test_models_compile(self, domain_id):
        ontology = load_domain(domain_id)
        source = generate_pydantic_models(ontology)
        try:
            compile(source, f"{domain_id}/models.py", "exec")
        except SyntaxError as e:
            pytest.fail(f"models.py syntax error for {domain_id}: {e}")


class TestCypherQueryValidation:
    """Validate that agent_tools Cypher queries reference valid schema elements."""

    ALL_DOMAINS = [d["id"] for d in list_available_domains()]

    @staticmethod
    def _extract_labels(cypher: str) -> set[str]:
        """Extract node labels from Cypher patterns like (n:Label) or (n:Label {})."""
        return set(re.findall(r"\(\w*:(\w+)", cypher))

    @staticmethod
    def _extract_rel_types(cypher: str) -> set[str]:
        """Extract relationship types from Cypher patterns like -[:TYPE]- or -[r:TYPE]-."""
        # Match :TYPE in relationship patterns, handling pipe-separated alternatives
        raw = re.findall(r"\[[\w*]*:([A-Z_|]+)\]", cypher)
        types = set()
        for match in raw:
            for t in match.split("|"):
                t = t.strip().lstrip(":")
                if t:
                    types.add(t)
        return types

    @pytest.mark.parametrize("domain_id", ALL_DOMAINS)
    def test_cypher_labels_exist_in_schema(self, domain_id):
        """All node labels in agent_tools Cypher must exist in entity_types."""
        ontology = load_domain(domain_id)
        valid_labels = {et.label for et in ontology.entity_types}
        # Add common Neo4j built-in labels
        valid_labels.update({"Document", "DecisionTrace", "TraceStep", "Message"})

        for tool in ontology.agent_tools:
            labels = self._extract_labels(tool.cypher)
            unknown = labels - valid_labels
            if unknown:
                pytest.fail(
                    f"Domain '{domain_id}', tool '{tool.name}': "
                    f"Cypher references unknown labels {unknown}. "
                    f"Valid labels: {sorted(valid_labels)}"
                )

    @pytest.mark.parametrize("domain_id", ALL_DOMAINS)
    def test_cypher_rel_types_exist_in_schema(self, domain_id):
        """All relationship types in agent_tools Cypher must exist in relationships."""
        ontology = load_domain(domain_id)
        valid_rels = {r.type for r in ontology.relationships}
        # Add common relationship types used by neo4j-agent-memory and built-in
        valid_rels.update({"MENTIONS", "HAS_STEP", "HAS_DOCUMENT"})

        for tool in ontology.agent_tools:
            rel_types = self._extract_rel_types(tool.cypher)
            unknown = rel_types - valid_rels
            if unknown:
                pytest.fail(
                    f"Domain '{domain_id}', tool '{tool.name}': "
                    f"Cypher references unknown relationship types {unknown}. "
                    f"Valid types: {sorted(valid_rels)}"
                )

    @pytest.mark.parametrize("domain_id", ALL_DOMAINS)
    def test_no_deprecated_colon_syntax_in_rel_patterns(self, domain_id):
        """Check for deprecated :TYPE1|:TYPE2 syntax (should be TYPE1|TYPE2)."""
        ontology = load_domain(domain_id)
        for tool in ontology.agent_tools:
            if re.search(r"\|:", tool.cypher):
                pytest.fail(
                    f"Domain '{domain_id}', tool '{tool.name}': "
                    f"Uses deprecated colon syntax in pipe-separated relationship "
                    f"pattern (e.g., ':TYPE1|:TYPE2'). Use 'TYPE1|TYPE2' instead."
                )


class TestSplitCypherStatements:
    """v0.14.0: the shared DDL splitter must survive comments — the naive
    ``split(";")`` + ``startswith("//")`` pattern silently skipped real
    statements behind comment headers and executed comment tails as Cypher."""

    def test_semicolon_inside_comment_does_not_split(self):
        from create_context_graph.ontology import split_cypher_statements

        script = (
            "// Create after embeddings are generated; dimensions must match.\n"
            "CREATE INDEX a IF NOT EXISTS FOR (n:A) ON (n.name);\n"
        )
        statements = split_cypher_statements(script)
        assert statements == ["CREATE INDEX a IF NOT EXISTS FOR (n:A) ON (n.name)"]

    def test_statement_behind_comment_header_is_kept(self):
        from create_context_graph.ontology import split_cypher_statements

        script = (
            "CREATE INDEX a IF NOT EXISTS FOR (n:A) ON (n.name);\n"
            "\n"
            "// Section header comment\n"
            "CREATE INDEX b IF NOT EXISTS FOR (n:B) ON (n.name);\n"
        )
        statements = split_cypher_statements(script)
        assert len(statements) == 2
        assert statements[1].startswith("CREATE INDEX b")

    def test_commented_out_ddl_is_dropped(self):
        from create_context_graph.ontology import split_cypher_statements

        script = (
            "// CREATE VECTOR INDEX v IF NOT EXISTS\n"
            "// OPTIONS { indexConfig: { `vector.dimensions`: 1536 } };\n"
            "CREATE INDEX real_one IF NOT EXISTS FOR (n:A) ON (n.name);\n"
        )
        statements = split_cypher_statements(script)
        assert statements == [
            "CREATE INDEX real_one IF NOT EXISTS FOR (n:A) ON (n.name)"
        ]

    @pytest.mark.parametrize("domain_id", ["financial-services", "healthcare", "software-engineering"])
    def test_generated_schema_yields_only_executable_statements(self, domain_id):
        from create_context_graph.ontology import (
            generate_cypher_schema,
            split_cypher_statements,
        )

        schema = generate_cypher_schema(load_domain(domain_id))
        statements = split_cypher_statements(schema)
        assert statements, "schema produced no statements"
        for stmt in statements:
            first_word = stmt.split(None, 1)[0].upper()
            assert first_word in {"CREATE", "DROP", "CALL", "SHOW", "MATCH", "MERGE"}, (
                f"non-executable fragment leaked through: {stmt[:80]!r}"
            )

    def test_previously_skipped_statements_are_recovered(self):
        """The old pattern dropped person_name/document_title/document_domain
        and the fulltext index for every domain. Pin their recovery."""
        from create_context_graph.ontology import (
            generate_cypher_schema,
            split_cypher_statements,
        )

        schema = generate_cypher_schema(load_domain("financial-services"))
        statements = split_cypher_statements(schema)
        joined = "\n".join(statements)
        for name in ("person_name", "document_title", "document_domain",
                     "document_name_unique", "local_file_fulltext"):
            assert name in joined, f"{name} missing from split statements"

        # And prove the OLD pattern really did drop statements (regression doc)
        old_style = [
            s.strip() for s in schema.split(";")
            if s.strip() and not s.strip().startswith("//")
        ]
        old_joined = "\n".join(old_style)
        assert "person_name" not in old_joined


class TestCustomDomainIsolation:
    """The autouse conftest fixture must keep tests hermetic against
    ~/.create-context-graph/custom-domains/ — a contributor's saved custom
    domains previously leaked into every domain-iterating test (the
    "football-intelligence" failure reports against v0.13.x)."""

    def test_custom_domains_path_is_isolated_from_home(self):
        from pathlib import Path

        from create_context_graph import custom_domain as custom_domain_mod
        from create_context_graph import ontology as ontology_mod

        home = Path.home()
        for resolver in (
            ontology_mod._get_custom_domains_path,
            custom_domain_mod._get_custom_domains_path,
        ):
            resolved = resolver()
            assert not resolved.is_relative_to(home), (
                f"tests are reading the real user directory: {resolved}"
            )

    def test_listed_domains_are_exactly_the_bundled_set(self):
        """With isolation active, only bundled domains appear."""
        from create_context_graph.ontology import _get_domains_path

        bundled = {
            p.stem for p in _get_domains_path().glob("*.yaml")
            if not p.stem.startswith("_")
        }
        listed = {d["id"] for d in list_available_domains()}
        assert listed == bundled
