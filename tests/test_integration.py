"""Neo4j database integration tests.

These tests require a running Neo4j instance. Configure via environment variables:
    NEO4J_URI      (default: neo4j://localhost:7687)
    NEO4J_USERNAME (default: neo4j)
    NEO4J_PASSWORD (default: password)

Run with:
    pytest tests/test_integration.py -v -m integration
"""

from __future__ import annotations

import json
import os
import tempfile
from copy import deepcopy
from pathlib import Path

import pytest

from create_context_graph.ontology import (
    DomainOntology,
    generate_cypher_schema,
    load_domain,
    split_cypher_statements,
)
from create_context_graph.ingest import ingest_data

try:
    from neo4j import GraphDatabase

    NEO4J_AVAILABLE = True
except ImportError:
    NEO4J_AVAILABLE = False

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(not NEO4J_AVAILABLE, reason="neo4j driver not installed"),
]

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

NEO4J_URI = os.environ.get("NEO4J_URI", "neo4j://localhost:7687")
NEO4J_USERNAME = os.environ.get("NEO4J_USERNAME", "neo4j")
NEO4J_PASSWORD = os.environ.get("NEO4J_PASSWORD", "password")

FIXTURES_DIR = Path(__file__).resolve().parent.parent / "src" / "create_context_graph" / "fixtures"


def _load_fixture(domain_id: str) -> dict:
    """Load a fixture JSON file and return parsed data."""
    path = FIXTURES_DIR / f"{domain_id}.json"
    return json.loads(path.read_text())


def _rewrite_fixture_domain(fixture_data: dict, new_domain: str) -> Path:
    """Write fixture data to a temp file with the domain field overridden.

    Returns the path to the temporary fixture file.
    """
    data = deepcopy(fixture_data)
    data["domain"] = new_domain
    tmp = tempfile.NamedTemporaryFile(
        mode="w", suffix=".json", delete=False, prefix="test_fixture_"
    )
    json.dump(data, tmp)
    tmp.close()
    return Path(tmp.name)


def _override_ontology_domain(ontology: DomainOntology, new_domain_id: str) -> DomainOntology:
    """Return a copy of the ontology with domain.id replaced."""
    data = ontology.model_dump()
    data["domain"]["id"] = new_domain_id
    return DomainOntology.model_validate(data)


def _seed_domain(domain_id: str, test_domain: str) -> DomainOntology:
    """Load a domain, override its id, ingest its fixtures, return the ontology."""
    ontology = _override_ontology_domain(load_domain(domain_id), test_domain)
    fixture_data = _load_fixture(domain_id)
    fixture_path = _rewrite_fixture_domain(fixture_data, test_domain)
    try:
        ingest_data(fixture_path, ontology, NEO4J_URI, NEO4J_USERNAME, NEO4J_PASSWORD)
    finally:
        fixture_path.unlink(missing_ok=True)
    return ontology


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def neo4j_driver():
    """Connect to Neo4j, yield driver, clean up test data on teardown."""
    if not NEO4J_AVAILABLE:
        pytest.skip("neo4j driver not installed")

    driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USERNAME, NEO4J_PASSWORD))

    # Verify connectivity before yielding
    try:
        driver.verify_connectivity()
    except Exception as exc:
        driver.close()
        pytest.skip(f"Cannot connect to Neo4j at {NEO4J_URI}: {exc}")

    yield driver

    # Cleanup: remove all nodes whose domain starts with "test-"
    with driver.session() as session:
        session.run("MATCH (n) WHERE n.domain STARTS WITH 'test-' DETACH DELETE n")

    driver.close()


@pytest.fixture()
def neo4j_session(neo4j_driver):
    """Yield a Neo4j session from the module-scoped driver."""
    with neo4j_driver.session() as session:
        yield session


# ---------------------------------------------------------------------------
# TestSchemaCreation
# ---------------------------------------------------------------------------


class TestSchemaCreation:
    """Verify that generated Cypher DDL applies cleanly to Neo4j."""

    def test_schema_constraints_apply(self, neo4j_session):
        """Load financial-services ontology, apply schema, verify constraints exist."""
        ontology = load_domain("financial-services")
        schema_ddl = generate_cypher_schema(ontology)

        # Execute each statement — should not raise
        for stmt in split_cypher_statements(schema_ddl):
            try:
                neo4j_session.run(stmt)
            except Exception as exc:
                if "already exists" not in str(exc).lower():
                    raise

        result = neo4j_session.run("SHOW CONSTRAINTS")
        constraints = list(result)
        assert len(constraints) > 0, "Expected at least one constraint after schema application"

    def test_schema_indexes_apply(self, neo4j_session):
        """Load financial-services ontology, apply schema, verify indexes exist."""
        ontology = load_domain("financial-services")
        schema_ddl = generate_cypher_schema(ontology)

        for stmt in split_cypher_statements(schema_ddl):
            try:
                neo4j_session.run(stmt)
            except Exception as exc:
                if "already exists" not in str(exc).lower():
                    raise

        result = neo4j_session.run("SHOW INDEXES")
        index_names = {record["name"] for record in result}
        assert len(index_names) > 0, "Expected at least one index after schema application"
        # These four sat behind comment headers, so the old naive splitter
        # silently skipped them (v0.14.0 regression guard).
        for expected in ("person_name", "document_title", "document_domain"):
            assert expected in index_names, f"index {expected} was not created"


# ---------------------------------------------------------------------------
# TestFixtureIngestion
# ---------------------------------------------------------------------------


class TestFixtureIngestion:
    """Verify that fixture data can be ingested into Neo4j."""

    TEST_DOMAIN = "test-financial"

    @pytest.fixture(autouse=True)
    def _seed_and_cleanup(self, neo4j_driver):
        """Seed financial-services data before tests, clean up after."""
        self.ontology = _seed_domain("financial-services", self.TEST_DOMAIN)
        yield
        with neo4j_driver.session() as session:
            session.run(
                "MATCH (n) WHERE n.domain = $domain DETACH DELETE n",
                {"domain": self.TEST_DOMAIN},
            )

    def test_ingest_financial_services(self, neo4j_session):
        """Verify entities were created with the test domain."""
        result = neo4j_session.run(
            "MATCH (n) WHERE n.domain = $domain AND NOT n:Document "
            "AND NOT n:DecisionTrace AND NOT n:TraceStep RETURN count(n) AS cnt",
            {"domain": self.TEST_DOMAIN},
        )
        count = result.single()["cnt"]
        assert count > 0, f"Expected entities for domain '{self.TEST_DOMAIN}', got {count}"

    def test_ingest_creates_documents(self, neo4j_session):
        """Verify Document nodes were created."""
        result = neo4j_session.run(
            "MATCH (d:Document) WHERE d.domain = $domain RETURN count(d) AS cnt",
            {"domain": self.TEST_DOMAIN},
        )
        count = result.single()["cnt"]
        assert count > 0, f"Expected Document nodes for domain '{self.TEST_DOMAIN}', got {count}"

    def test_ingest_creates_relationships(self, neo4j_session):
        """Verify relationships exist between entities in the test domain."""
        result = neo4j_session.run(
            "MATCH (a)-[r]->(b) WHERE a.domain = $domain RETURN count(r) AS cnt",
            {"domain": self.TEST_DOMAIN},
        )
        count = result.single()["cnt"]
        assert count > 0, f"Expected relationships for domain '{self.TEST_DOMAIN}', got {count}"


# ---------------------------------------------------------------------------
# TestAgentToolQueriesExecute
# ---------------------------------------------------------------------------


class TestAgentToolQueriesExecute:
    """Verify that agent tool Cypher queries execute without errors."""

    TEST_DOMAIN = "test-agent-tools"

    @pytest.fixture(autouse=True, scope="class")
    def _seed_data(self, neo4j_driver):
        """Seed financial-services data once for all tool query tests."""
        _seed_domain("financial-services", self.TEST_DOMAIN)
        yield
        with neo4j_driver.session() as session:
            session.run(
                "MATCH (n) WHERE n.domain = $domain DETACH DELETE n",
                {"domain": self.TEST_DOMAIN},
            )

    @pytest.fixture()
    def agent_tools(self):
        """Return the first 3 agent tools from financial-services ontology."""
        ontology = load_domain("financial-services")
        return ontology.agent_tools[:3]

    def test_agent_tool_queries_return_results(self, neo4j_session, agent_tools):
        """Each agent tool Cypher query should execute without exceptions."""
        for tool in agent_tools:
            # Build dummy parameters: use sensible defaults for common param names
            params = {}
            for param in tool.parameters:
                name = param.name
                if name == "domain":
                    params[name] = self.TEST_DOMAIN
                elif name == "limit":
                    params[name] = 5
                elif name == "name":
                    params[name] = "test"
                elif param.type in ("integer", "float"):
                    params[name] = 0
                else:
                    params[name] = "test"

            # Ensure domain param is always present (many queries filter by domain)
            if "domain" not in params:
                params["domain"] = self.TEST_DOMAIN

            try:
                result = neo4j_session.run(tool.cypher, params)
                # Consume the result to ensure the query completes
                list(result)
            except Exception as exc:
                pytest.fail(
                    f"Agent tool '{tool.name}' query failed: {exc}\n"
                    f"Cypher: {tool.cypher}\n"
                    f"Params: {params}"
                )


# ---------------------------------------------------------------------------
# TestDomainScoping
# ---------------------------------------------------------------------------


class TestDomainScoping:
    """Verify that domain filtering isolates data correctly."""

    DOMAIN_A = "test-domain-a"
    DOMAIN_B = "test-domain-b"

    @pytest.fixture(autouse=True)
    def _seed_both_domains(self, neo4j_driver):
        """Seed two different domains and clean up after."""
        _seed_domain("financial-services", self.DOMAIN_A)
        _seed_domain("healthcare", self.DOMAIN_B)
        yield
        with neo4j_driver.session() as session:
            session.run(
                "MATCH (n) WHERE n.domain IN $domains DETACH DELETE n",
                {"domains": [self.DOMAIN_A, self.DOMAIN_B]},
            )

    def test_domain_filter_isolates_data(self, neo4j_session):
        """Querying domain A should not return healthcare-specific entity labels."""
        healthcare_ontology = load_domain("healthcare")
        # Collect labels unique to healthcare (not in financial-services)
        financial_ontology = load_domain("financial-services")
        financial_labels = {et.label for et in financial_ontology.entity_types}
        healthcare_only_labels = {
            et.label
            for et in healthcare_ontology.entity_types
            if et.label not in financial_labels
        }

        if not healthcare_only_labels:
            pytest.skip("No healthcare-only labels to test isolation with")

        # Query domain A for any healthcare-only labels
        for label in healthcare_only_labels:
            result = neo4j_session.run(
                f"MATCH (n:{label}) WHERE n.domain = $domain RETURN count(n) AS cnt",
                {"domain": self.DOMAIN_A},
            )
            count = result.single()["cnt"]
            assert count == 0, (
                f"Found {count} nodes with label '{label}' in domain '{self.DOMAIN_A}' "
                f"— expected 0 (label is healthcare-only)"
            )


# ---------------------------------------------------------------------------
# TestNeo4jDatabaseThreading (v0.14.0)
# ---------------------------------------------------------------------------


class TestNeo4jDatabaseThreading:
    """v0.14.0: an explicitly-named database must be honored end-to-end.

    We resolve the server's default database name and pass it EXPLICITLY —
    equivalent routing, but it exercises the ``neo4j_database`` parameter
    through ``ProjectConfig`` → ``ingest_data`` → session, on any edition
    (community has a single database, so an explicit name is the only
    portable way to test the threading).
    """

    TEST_DOMAIN = "test-dbthread"

    @pytest.fixture()
    def default_db_name(self, neo4j_driver) -> str:
        with neo4j_driver.session() as session:
            record = session.run("CALL db.info() YIELD name RETURN name").single()
        return record["name"]

    @pytest.fixture(autouse=True)
    def _cleanup(self, neo4j_driver):
        yield
        with neo4j_driver.session() as session:
            session.run(
                "MATCH (n) WHERE n.domain = $domain DETACH DELETE n",
                {"domain": self.TEST_DOMAIN},
            )

    def test_ingest_honors_explicit_database(self, neo4j_driver, default_db_name):
        from create_context_graph.config import ProjectConfig

        ontology = _override_ontology_domain(
            load_domain("financial-services"), self.TEST_DOMAIN
        )
        fixture_path = _rewrite_fixture_domain(
            _load_fixture("financial-services"), self.TEST_DOMAIN
        )
        config = ProjectConfig(
            project_name="db threading test",
            domain=self.TEST_DOMAIN,
            memory_backend="bolt",
            neo4j_uri=NEO4J_URI,
            neo4j_username=NEO4J_USERNAME,
            neo4j_password=NEO4J_PASSWORD,
            neo4j_database=default_db_name,
        )
        try:
            ingest_data(fixture_path, ontology, config)
        finally:
            fixture_path.unlink(missing_ok=True)

        with neo4j_driver.session(database=default_db_name) as session:
            count = session.run(
                "MATCH (n) WHERE n.domain = $domain RETURN count(n) AS cnt",
                {"domain": self.TEST_DOMAIN},
            ).single()["cnt"]
        assert count > 0, "explicit-database ingest wrote no nodes"

    def test_validate_connection_with_database(self, default_db_name):
        from create_context_graph.neo4j_validator import validate_connection

        ok, message = validate_connection(
            NEO4J_URI, NEO4J_USERNAME, NEO4J_PASSWORD, database=default_db_name
        )
        assert ok, message

    def test_validate_connection_rejects_unknown_database(self):
        from create_context_graph.neo4j_validator import validate_connection

        ok, _ = validate_connection(
            NEO4J_URI, NEO4J_USERNAME, NEO4J_PASSWORD,
            database="ccg-no-such-database",
        )
        assert not ok
