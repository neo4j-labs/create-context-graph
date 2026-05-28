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

"""Performance tests — scaffold generation must complete within time limits."""

from __future__ import annotations

import time

import pytest

from create_context_graph.cli import main
from create_context_graph.ontology import list_available_domains

# ``runner`` fixture is provided by tests/conftest.py and auto-injects
# ``--self-hosted`` so these performance tests exercise the bolt path
# without each test needing to pass the flag explicitly.


def _all_domain_ids():
    return [d["id"] for d in list_available_domains()]


@pytest.mark.slow
class TestGenerationPerformance:
    """Each domain must scaffold in under 120 seconds."""

    @pytest.mark.parametrize("domain_id", _all_domain_ids())
    def test_generation_under_two_minutes(self, runner, tmp_path, domain_id):
        out = tmp_path / f"perf-{domain_id}"
        start = time.monotonic()
        result = runner.invoke(main, [
            f"perf-{domain_id}",
            "--domain", domain_id,
            "--framework", "pydanticai",
            "--output-dir", str(out),
        ])
        elapsed = time.monotonic() - start

        assert result.exit_code == 0, (
            f"{domain_id} failed (exit {result.exit_code}): {result.output[-300:]}"
        )
        assert elapsed < 120, (
            f"{domain_id} took {elapsed:.1f}s (limit: 120s)"
        )
