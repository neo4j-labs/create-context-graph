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

"""Unit tests for custom domain generation."""

from unittest.mock import MagicMock, patch

import pytest
from pydantic import ValidationError

from create_context_graph.custom_domain import (
    _ONTOLOGY_MAX_TOKENS,
    _build_domain_generation_prompt,
    _build_retry_prompt,
    _strip_yaml_fences,
    _validate_ontology_completeness,
    display_ontology_summary,
    generate_custom_domain,
    save_custom_domain,
)
from create_context_graph.ontology import (
    DomainOntology,
    list_available_domains,
    load_domain_from_yaml_string,
)

# ---------------------------------------------------------------------------
# Minimal valid domain YAML for testing
# ---------------------------------------------------------------------------

VALID_DOMAIN_YAML = """\
inherits: _base

domain:
  id: test-domain
  name: Test Domain
  description: A test domain for unit testing
  tagline: "Testing is fun"
  emoji: "\\U0001F9EA"

entity_types:
  - label: Widget
    pole_type: OBJECT
    color: "#16a34a"
    icon: box
    properties:
      - name: widget_id
        type: string
        required: true
        unique: true
      - name: name
        type: string
        required: true

  - label: Factory
    pole_type: ORGANIZATION
    color: "#3b82f6"
    icon: building
    properties:
      - name: factory_id
        type: string
        required: true
        unique: true
      - name: name
        type: string
        required: true
      - name: capacity
        type: integer

  - label: Inspection
    pole_type: EVENT
    color: "#f97316"
    icon: clipboard
    properties:
      - name: inspection_id
        type: string
        required: true
        unique: true
      - name: date
        type: datetime
        required: true
      - name: result
        type: string
        enum: ["pass", "fail", "pending"]

relationships:
  - type: MANUFACTURED_BY
    source: Widget
    target: Factory
  - type: INSPECTED_IN
    source: Widget
    target: Inspection
  - type: CONDUCTED_AT
    source: Inspection
    target: Factory

document_templates:
  - id: inspection-report
    name: Inspection Report
    description: Quality inspection report
    count: 3
    prompt_template: "Generate an inspection report"
    required_entities: [Widget, Inspection]
  - id: production-log
    name: Production Log
    description: Daily production log
    count: 3
    prompt_template: "Generate a production log"
    required_entities: [Factory]

decision_traces:
  - id: quality-decision
    task: Determine if widget passes quality check
    steps:
      - thought: Review inspection data
        action: Query inspection results
        observation: Found 3 recent inspections

demo_scenarios:
  - name: Quality Check
    prompts:
      - "What widgets failed inspection last week?"
      - "Show me the production stats for Factory A"
  - name: Production Overview
    prompts:
      - "Which factory has the highest capacity?"

agent_tools:
  - name: search_widgets
    description: Search for widgets by name
    cypher: "MATCH (w:Widget) WHERE w.name CONTAINS $query RETURN w"
    parameters:
      - name: query
        type: string
        description: Search term
  - name: get_inspections
    description: Get recent inspections
    cypher: "MATCH (i:Inspection) RETURN i ORDER BY i.date DESC LIMIT $limit"
    parameters:
      - name: limit
        type: integer
        description: Number of results
  - name: factory_stats
    description: Get factory production stats
    cypher: "MATCH (f:Factory)<-[:MANUFACTURED_BY]-(w:Widget) RETURN f.name, count(w)"

system_prompt: |
  You are a quality management assistant for widget manufacturing.

visualization:
  node_colors:
    Widget: "#16a34a"
    Factory: "#3b82f6"
    Inspection: "#f97316"
  node_sizes:
    Widget: 20
    Factory: 25
    Inspection: 20
  default_cypher: "MATCH (n)-[r]->(m) RETURN n, r, m LIMIT 100"
"""

INVALID_DOMAIN_YAML = """\
domain:
  id: bad
  name: Bad
entity_types: "not a list"
"""

INVALID_YAML_SYNTAX = """\
domain:
  id: bad
  name: [unmatched bracket
"""


# ---------------------------------------------------------------------------
# Tests for load_domain_from_yaml_string
# ---------------------------------------------------------------------------


class TestLoadDomainFromYamlString:
    def test_valid_yaml_parses(self):
        ontology = load_domain_from_yaml_string(VALID_DOMAIN_YAML)
        assert isinstance(ontology, DomainOntology)
        assert ontology.domain.id == "test-domain"
        assert ontology.domain.name == "Test Domain"

    def test_base_merge_adds_base_entities(self):
        ontology = load_domain_from_yaml_string(VALID_DOMAIN_YAML)
        labels = [et.label for et in ontology.entity_types]
        # Base entities should be merged in
        assert "Person" in labels
        assert "Organization" in labels
        assert "Location" in labels
        assert "Event" in labels
        assert "Object" in labels
        # Domain entities too
        assert "Widget" in labels
        assert "Factory" in labels
        assert "Inspection" in labels

    def test_invalid_yaml_raises(self):
        with pytest.raises((ValidationError, ValueError)):
            load_domain_from_yaml_string(INVALID_DOMAIN_YAML)

    def test_empty_yaml_raises(self):
        with pytest.raises(ValueError, match="Invalid YAML"):
            load_domain_from_yaml_string("")

    def test_yaml_without_inherits(self):
        """YAML without inherits: _base should still validate if it has all base types."""
        yaml_no_inherit = VALID_DOMAIN_YAML.replace("inherits: _base\n\n", "")
        ontology = load_domain_from_yaml_string(yaml_no_inherit)
        assert ontology.domain.id == "test-domain"
        # Without inherits, base types are NOT merged
        labels = [et.label for et in ontology.entity_types]
        assert "Person" not in labels


# ---------------------------------------------------------------------------
# Tests for prompt construction
# ---------------------------------------------------------------------------


class TestPromptConstruction:
    def test_build_domain_generation_prompt(self):
        prompt = _build_domain_generation_prompt(
            "veterinary clinic management",
            "base yaml content",
            ["example1 yaml", "example2 yaml"],
        )
        assert "veterinary clinic management" in prompt
        assert "base yaml content" in prompt
        assert "example1 yaml" in prompt
        assert "example2 yaml" in prompt
        assert "entity_types" in prompt  # schema spec included
        assert "inherits: _base" in prompt

    def test_build_retry_prompt(self):
        prompt = _build_retry_prompt(
            "veterinary clinic", "bad yaml here", "ValidationError: missing field"
        )
        assert "veterinary clinic" in prompt
        assert "bad yaml here" in prompt
        assert "ValidationError" in prompt


# ---------------------------------------------------------------------------
# Tests for YAML fence stripping
# ---------------------------------------------------------------------------


class TestStripYamlFences:
    def test_strips_yaml_fences(self):
        text = "```yaml\nsome: yaml\n```"
        assert _strip_yaml_fences(text) == "some: yaml"

    def test_strips_plain_fences(self):
        text = "```\nsome: yaml\n```"
        assert _strip_yaml_fences(text) == "some: yaml"

    def test_no_fences_unchanged(self):
        text = "some: yaml"
        assert _strip_yaml_fences(text) == "some: yaml"


# ---------------------------------------------------------------------------
# Tests for generate_custom_domain (mocked LLM)
# ---------------------------------------------------------------------------


class TestGenerateCustomDomain:
    # generate_custom_domain now calls _llm_generate with return_stop_reason=True,
    # so all mocks must return ``(text, stop_reason)``. ``stop_reason="end_turn"``
    # is the normal-completion value for Anthropic (OpenAI's equivalent is
    # ``"stop"``); ``"max_tokens"`` / ``"length"`` signal truncation.
    @patch("create_context_graph.custom_domain._llm_generate")
    @patch("create_context_graph.custom_domain._get_llm_client")
    def test_success(self, mock_get_client, mock_generate):
        mock_get_client.return_value = (MagicMock(), "anthropic")
        mock_generate.return_value = (VALID_DOMAIN_YAML, "end_turn")

        ontology, raw_yaml = generate_custom_domain("test domain", "fake-key")
        assert isinstance(ontology, DomainOntology)
        assert ontology.domain.id == "test-domain"
        assert raw_yaml == VALID_DOMAIN_YAML.strip()

    @patch("create_context_graph.custom_domain._llm_generate")
    @patch("create_context_graph.custom_domain._get_llm_client")
    def test_retry_on_validation_error(self, mock_get_client, mock_generate):
        mock_get_client.return_value = (MagicMock(), "anthropic")
        # First call returns invalid, second returns valid
        mock_generate.side_effect = [
            (INVALID_DOMAIN_YAML, "end_turn"),
            (VALID_DOMAIN_YAML, "end_turn"),
        ]

        ontology, raw_yaml = generate_custom_domain("test domain", "fake-key")
        assert isinstance(ontology, DomainOntology)
        assert mock_generate.call_count == 2

    @patch("create_context_graph.custom_domain._llm_generate")
    @patch("create_context_graph.custom_domain._get_llm_client")
    def test_max_retries_exceeded(self, mock_get_client, mock_generate):
        mock_get_client.return_value = (MagicMock(), "anthropic")
        mock_generate.return_value = (INVALID_DOMAIN_YAML, "end_turn")

        with pytest.raises(ValueError, match="Failed to generate valid domain"):
            generate_custom_domain("test domain", "fake-key", max_retries=2)

    def test_no_client_raises(self):
        with patch("create_context_graph.custom_domain._get_llm_client", return_value=(None, None)):
            with pytest.raises(ValueError, match="Could not initialize LLM client"):
                generate_custom_domain("test", "fake")

    def test_no_client_error_message_is_actionable(self):
        """When anthropic/openai isn't installed (common uvx footgun), the
        error must tell the user exactly how to fix it.
        """
        with patch(
            "create_context_graph.custom_domain._get_llm_client",
            return_value=(None, None),
        ):
            with pytest.raises(ValueError) as excinfo:
                generate_custom_domain("test", "fake")
        msg = str(excinfo.value)
        # Must mention both the pip-install and uvx-invocation paths.
        assert "pip install" in msg
        assert "create-context-graph[generate]" in msg
        assert "uvx --with anthropic" in msg

    @patch("create_context_graph.custom_domain._llm_generate")
    @patch("create_context_graph.custom_domain._get_llm_client")
    def test_uses_large_max_tokens(self, mock_get_client, mock_generate):
        """The generator-wide 4096 default truncated 20KB+ ontology YAMLs.
        Custom-domain generation must request a large output budget.
        """
        mock_get_client.return_value = (MagicMock(), "anthropic")
        mock_generate.return_value = (VALID_DOMAIN_YAML, "end_turn")

        generate_custom_domain("test domain", "fake-key")
        # Inspect what _llm_generate was actually called with.
        call_kwargs = mock_generate.call_args.kwargs
        assert call_kwargs["max_tokens"] >= 16000, (
            f"max_tokens must be large enough for full ontologies "
            f"(~5–8k tokens of YAML); got {call_kwargs['max_tokens']}"
        )
        assert call_kwargs["return_stop_reason"] is True

    @patch("create_context_graph.custom_domain._llm_generate")
    @patch("create_context_graph.custom_domain._get_llm_client")
    def test_truncation_triggers_retry(self, mock_get_client, mock_generate):
        """When the LLM hits max_tokens, the partial output must be retried."""
        mock_get_client.return_value = (MagicMock(), "anthropic")
        # First call: truncated (parses OK-ish but should be rejected by
        # stop_reason check). Second call: complete.
        mock_generate.side_effect = [
            (VALID_DOMAIN_YAML, "max_tokens"),  # would otherwise succeed
            (VALID_DOMAIN_YAML, "end_turn"),
        ]
        ontology, _ = generate_custom_domain("test", "fake-key")
        assert isinstance(ontology, DomainOntology)
        assert mock_generate.call_count == 2

    @patch("create_context_graph.custom_domain._llm_generate")
    @patch("create_context_graph.custom_domain._get_llm_client")
    def test_persistent_truncation_raises(self, mock_get_client, mock_generate):
        mock_get_client.return_value = (MagicMock(), "anthropic")
        mock_generate.return_value = (VALID_DOMAIN_YAML, "max_tokens")
        with pytest.raises(ValueError, match="Failed to generate valid domain"):
            generate_custom_domain("test", "fake-key", max_retries=2)

    @patch("create_context_graph.custom_domain._llm_generate")
    @patch("create_context_graph.custom_domain._get_llm_client")
    def test_incomplete_ontology_triggers_retry(self, mock_get_client, mock_generate):
        """A YAML missing system_prompt parses successfully (Pydantic defaults
        to empty) but is unusable — must be caught by the completeness check.
        """
        mock_get_client.return_value = (MagicMock(), "anthropic")
        # Strip system_prompt and visualization sections — the YAML still parses
        # but produces a skeletal ontology with empty defaults.
        truncated_yaml = VALID_DOMAIN_YAML.split("system_prompt:")[0]
        mock_generate.side_effect = [
            (truncated_yaml, "end_turn"),  # parses, but incomplete
            (VALID_DOMAIN_YAML, "end_turn"),
        ]
        ontology, _ = generate_custom_domain("test", "fake-key")
        assert isinstance(ontology, DomainOntology)
        assert ontology.system_prompt  # second attempt had it
        assert mock_generate.call_count == 2


class TestValidateOntologyCompleteness:
    """Direct tests for _validate_ontology_completeness."""

    def test_full_ontology_is_complete(self):
        ontology = load_domain_from_yaml_string(VALID_DOMAIN_YAML)
        assert _validate_ontology_completeness(ontology) == []

    def test_missing_system_prompt_flagged(self):
        ontology = load_domain_from_yaml_string(VALID_DOMAIN_YAML)
        ontology.system_prompt = ""
        problems = _validate_ontology_completeness(ontology)
        assert any("system_prompt" in p for p in problems)

    def test_empty_visualization_flagged(self):
        ontology = load_domain_from_yaml_string(VALID_DOMAIN_YAML)
        ontology.visualization.node_colors = {}
        problems = _validate_ontology_completeness(ontology)
        assert any("visualization.node_colors" in p for p in problems)

    def test_too_few_agent_tools_flagged(self):
        ontology = load_domain_from_yaml_string(VALID_DOMAIN_YAML)
        ontology.agent_tools = ontology.agent_tools[:2]
        problems = _validate_ontology_completeness(ontology)
        assert any("agent_tools" in p for p in problems)

    def test_too_few_entity_types_flagged(self):
        ontology = load_domain_from_yaml_string(VALID_DOMAIN_YAML)
        # Schema spec requires "at least 3 domain-specific entity types"
        ontology.entity_types = ontology.entity_types[:2]
        problems = _validate_ontology_completeness(ontology)
        assert any("entity_types" in p for p in problems)

    def test_ontology_max_tokens_is_sane(self):
        # Healthcare YAML is 20,793 bytes ≈ 5–7k tokens. The cap needs to
        # be comfortably above that to leave room for richer ontologies.
        assert _ONTOLOGY_MAX_TOKENS >= 16000


# ---------------------------------------------------------------------------
# Tests for display and save
# ---------------------------------------------------------------------------


class TestDisplayAndSave:
    def test_display_ontology_summary(self):
        ontology = load_domain_from_yaml_string(VALID_DOMAIN_YAML)
        from rich.console import Console

        c = Console(file=None, force_terminal=False)
        # Should not raise
        display_ontology_summary(ontology, c)

    def test_save_custom_domain(self, tmp_path):
        ontology = load_domain_from_yaml_string(VALID_DOMAIN_YAML)

        with patch(
            "create_context_graph.custom_domain._get_custom_domains_path",
            return_value=tmp_path / "custom-domains",
        ):
            path = save_custom_domain(ontology, VALID_DOMAIN_YAML)

        assert path.exists()
        assert path.name == "test-domain.yaml"
        assert path.read_text() == VALID_DOMAIN_YAML

    def test_list_includes_saved_custom(self, tmp_path):
        """Custom domains dir is scanned by list_available_domains."""
        custom_dir = tmp_path / "custom-domains"
        custom_dir.mkdir()
        (custom_dir / "my-custom.yaml").write_text(VALID_DOMAIN_YAML)

        with patch(
            "create_context_graph.ontology._get_custom_domains_path",
            return_value=custom_dir,
        ):
            domains = list_available_domains()
            ids = [d["id"] for d in domains]
            assert "test-domain" in ids
