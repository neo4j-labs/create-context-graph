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

"""Tests for generated Plotly chart builder specs."""

from __future__ import annotations

import ast
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
def rendered_chart_builder(tmp_path):
    """Render the pure-Python chart builder template."""
    template_path = TEMPLATES_DIR / "backend" / "shared" / "chart_builder.py.j2"
    rendered = Environment().from_string(template_path.read_text()).render()

    module_path = tmp_path / "_chart_builder.py"
    module_path.write_text(rendered)
    return module_path, rendered


@pytest.fixture
def chart_builder_module(rendered_chart_builder):
    """Import the rendered chart builder template as a module."""
    module_path, _rendered = rendered_chart_builder
    spec = importlib.util.spec_from_file_location("_chart_builder", module_path)
    assert spec is not None
    assert spec.loader is not None

    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class TestBuildPlotlySpec:
    """build_plotly_spec returns valid Plotly figures for supported chart types."""

    def test_template_renders_to_valid_python(self, rendered_chart_builder):
        _module_path, rendered = rendered_chart_builder

        ast.parse(rendered)

    def test_bar_chart_uses_requested_fields_and_title(self, chart_builder_module):
        data = [{"team": "Aces", "wins": 12}, {"team": "Bees", "wins": 8}]

        spec = chart_builder_module.build_plotly_spec(
            "bar", "Wins by Team", data, x_field="team", y_field="wins"
        )

        assert spec["data"][0]["type"] == "bar"
        assert spec["data"][0]["x"] == ["Aces", "Bees"]
        assert spec["data"][0]["y"] == [12, 8]
        assert spec["layout"]["title"] == "Wins by Team"

    def test_line_chart_uses_scatter_with_lines_mode(self, chart_builder_module):
        data = [{"day": "Mon", "score": 2}, {"day": "Tue", "score": 5}]

        spec = chart_builder_module.build_plotly_spec(
            "line", "Scores", data, x_field="day", y_field="score"
        )

        assert spec["data"][0]["type"] == "scatter"
        assert spec["data"][0]["mode"] == "lines"

    def test_scatter_chart_uses_marker_mode(self, chart_builder_module):
        data = [{"name": "Ada", "score": 95}, {"name": "Lin", "score": 88}]

        spec = chart_builder_module.build_plotly_spec(
            "scatter", "Scores", data, x_field="name", y_field="score"
        )

        assert spec["data"][0]["type"] == "scatter"
        assert spec["data"][0]["mode"] == "markers"

    def test_pie_chart_uses_labels_and_values(self, chart_builder_module):
        data = [
            {"category": "Open", "count": 4},
            {"category": "Closed", "count": 7},
        ]

        spec = chart_builder_module.build_plotly_spec(
            "pie",
            "Ticket Status",
            data,
            labels_field="category",
            values_field="count",
        )

        assert spec["data"][0]["type"] == "pie"
        assert spec["data"][0]["labels"] == ["Open", "Closed"]
        assert spec["data"][0]["values"] == [4, 7]

    def test_hbar_chart_sets_horizontal_orientation(self, chart_builder_module):
        data = [{"team": "Aces", "wins": 12}, {"team": "Bees", "wins": 8}]

        spec = chart_builder_module.build_plotly_spec(
            "hbar", "Wins by Team", data, x_field="team", y_field="wins"
        )

        assert spec["data"][0]["type"] == "bar"
        assert spec["data"][0]["orientation"] == "h"
        assert spec["data"][0]["x"] == [12, 8]
        assert spec["data"][0]["y"] == ["Aces", "Bees"]

    def test_table_chart_builds_header_and_cells(self, chart_builder_module):
        data = [
            {"team": "Aces", "wins": 12},
            {"team": "Bees", "wins": 8},
        ]

        spec = chart_builder_module.build_plotly_spec("table", "Standings", data)

        trace = spec["data"][0]
        assert trace["type"] == "table"
        assert trace["header"]["values"] == ["team", "wins"]
        assert trace["header"]["fill"]["color"] == "#4C9AFF"
        assert trace["cells"]["values"] == [["Aces", "Bees"], [12, 8]]

    def test_invalid_chart_type_raises_chart_build_error(self, chart_builder_module):
        with pytest.raises(chart_builder_module.ChartBuildError) as exc:
            chart_builder_module.build_plotly_spec(
                "histogram", "Invalid", [{"name": "Ada", "score": 95}]
            )

        assert "Unknown chart type: histogram" in str(exc.value)

    def test_empty_data_raises_chart_build_error(self, chart_builder_module):
        with pytest.raises(chart_builder_module.ChartBuildError) as exc:
            chart_builder_module.build_plotly_spec("bar", "Empty", [])

        assert "Chart data cannot be empty" in str(exc.value)

    def test_auto_detects_first_string_and_numeric_fields(self, chart_builder_module):
        data = [
            {"ignored_number": 1, "name": "Ada", "score": 95},
            {"ignored_number": 2, "name": "Lin", "score": 88},
        ]

        spec = chart_builder_module.build_plotly_spec("bar", "Scores", data)

        assert spec["data"][0]["x"] == ["Ada", "Lin"]
        assert spec["data"][0]["y"] == [1, 2]
        assert spec["layout"]["xaxis"]["title"] == "name"
        assert spec["layout"]["yaxis"]["title"] == "ignored_number"

    def test_flattens_nested_neo4j_node_properties(self, chart_builder_module):
        data = [
            {"n": {"properties": {"name": "Alice", "score": 95}}},
            {"n": {"properties": {"name": "Bob", "score": 82}}},
        ]

        spec = chart_builder_module.build_plotly_spec("bar", "Scores", data)

        assert spec["data"][0]["x"] == ["Alice", "Bob"]
        assert spec["data"][0]["y"] == [95, 82]
