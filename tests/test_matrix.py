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

"""Full domain x framework matrix test.

Tests all 184 combinations (23 domains x 8 frameworks) to ensure
every scaffold generates successfully. Marked as slow — run with --slow.
"""

from __future__ import annotations

import pytest

from create_context_graph.cli import main
from create_context_graph.config import SUPPORTED_FRAMEWORKS
from create_context_graph.ontology import list_available_domains

# ``runner`` fixture comes from tests/conftest.py and auto-injects
# ``--self-hosted`` so the matrix exercises the bolt path uniformly.


def _all_domain_ids():
    return [d["id"] for d in list_available_domains()]


def _all_combos():
    """Generate all domain x framework combinations."""
    domains = _all_domain_ids()
    return [(d, f) for d in domains for f in SUPPORTED_FRAMEWORKS]


@pytest.mark.slow
class TestFullMatrix:
    """Scaffold every domain x framework combination."""

    @pytest.mark.parametrize("domain_id,framework", _all_combos())
    def test_scaffold(self, runner, tmp_path, domain_id, framework):
        slug = f"{domain_id[:12]}-{framework[:8]}"
        out = tmp_path / slug
        result = runner.invoke(main, [
            slug,
            "--domain", domain_id,
            "--framework", framework,
            "--output-dir", str(out),
        ])
        assert result.exit_code == 0, (
            f"{domain_id}/{framework} failed (exit {result.exit_code}):\n{result.output[-500:]}"
        )

        # Key files exist
        agent_path = out / "backend" / "app" / "agent.py"
        assert agent_path.exists(), f"No agent.py for {domain_id}/{framework}"

        assert (out / "data" / "fixtures.json").exists(), (
            f"No fixtures.json for {domain_id}/{framework}"
        )
        assert (out / "cypher" / "schema.cypher").exists(), (
            f"No schema.cypher for {domain_id}/{framework}"
        )

        # Agent compiles
        source = agent_path.read_text()
        try:
            compile(source, str(agent_path), "exec")
        except SyntaxError as e:
            pytest.fail(
                f"agent.py for {domain_id}/{framework} has syntax error: {e}"
            )
