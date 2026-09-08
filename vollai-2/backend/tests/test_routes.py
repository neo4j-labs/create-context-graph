"""Tests for Discovered Database Context Graph API."""

import os
import pytest
from unittest.mock import AsyncMock, patch
from fastapi.testclient import TestClient

# Set placeholder keys before importing app modules so framework agents that
# validate API keys at module-level (e.g. PydanticAI) don't raise on import.
# These are never used — no real LLM calls happen in unit tests.
os.environ.setdefault("ANTHROPIC_API_KEY", "test-placeholder")
os.environ.setdefault("OPENAI_API_KEY", "test-placeholder")
os.environ.setdefault("GOOGLE_API_KEY", "test-placeholder")

from app.main import app


@pytest.fixture(autouse=True)
def mock_neo4j():
    """Mock Neo4j connection for all tests."""
    with patch("app.context_graph_client.connect_neo4j", new_callable=AsyncMock), \
         patch("app.context_graph_client.close_neo4j", new_callable=AsyncMock), \
         patch("app.main.is_connected", return_value=True), \
         patch("app.vector_client.create_vector_index", new_callable=AsyncMock):
        yield


client = TestClient(app)


def test_health():
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["domain"] == "discovered-database"



def test_scenarios():
    response = client.get("/api/scenarios")
    assert response.status_code == 200
    data = response.json()
    assert "domain" in data
    assert "scenarios" in data
    assert isinstance(data["scenarios"], list)
