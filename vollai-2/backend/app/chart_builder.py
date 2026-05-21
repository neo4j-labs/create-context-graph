"""Build Plotly-compatible chart specifications from query results."""

from __future__ import annotations

from numbers import Number
from typing import Any


VALID_CHART_TYPES = {"bar", "line", "scatter", "pie", "hbar", "table"}


class ChartBuildError(Exception):
    """Raised when a chart specification cannot be built."""


def _flatten_records(data: list[Any]) -> list[Any]:
    """Flatten Neo4j node property wrappers into row dictionaries."""
    flattened: list[Any] = []

    for record in data:
        if not isinstance(record, dict):
            flattened.append(record)
            continue

        row: dict[str, Any] = {}
        for key, value in record.items():
            if isinstance(value, dict) and isinstance(value.get("properties"), dict):
                row.update(value["properties"])
            elif key == "properties" and isinstance(value, dict):
                row.update(value)
            else:
                row[key] = value
        flattened.append(row)

    return flattened


def _auto_detect_fields(
    data: list[Any], prefer_x: str = "", prefer_y: str = ""
) -> tuple[str, str]:
    """Detect x/y fields from the first row when explicit fields are missing."""
    x_field = prefer_x
    y_field = prefer_y

    first_row = data[0]
    if not isinstance(first_row, dict):
        raise ChartBuildError("Chart data rows must be dictionaries")

    if not x_field:
        for field, value in first_row.items():
            if isinstance(value, str):
                x_field = field
                break

    if not y_field:
        for field, value in first_row.items():
            if isinstance(value, Number) and not isinstance(value, bool):
                y_field = field
                break

    if not x_field or not y_field:
        raise ChartBuildError("Could not determine x and y fields for chart")

    return x_field, y_field


def _extract_values(data: list[Any], field: str) -> list[Any]:
    values: list[Any] = []
    for row in data:
        if not isinstance(row, dict):
            raise ChartBuildError("Chart data rows must be dictionaries")
        if field not in row:
            raise ChartBuildError(f"Field '{field}' not found in chart data")
        values.append(row[field])
    return values


def _table_headers(data: list[Any]) -> list[str]:
    headers: list[str] = []
    for row in data:
        if not isinstance(row, dict):
            raise ChartBuildError("Table chart data rows must be dictionaries")
        for field in row:
            if field not in headers:
                headers.append(field)
    return headers


def _extract_table_values(data: list[Any], field: str) -> list[Any]:
    values: list[Any] = []
    for row in data:
        if not isinstance(row, dict):
            raise ChartBuildError("Table chart data rows must be dictionaries")
        values.append(row.get(field))
    return values


def build_plotly_spec(
    chart_type: str,
    title: str,
    data: list[Any],
    x_field: str = "",
    y_field: str = "",
    labels_field: str = "",
    values_field: str = "",
) -> dict[str, Any]:
    """Build a Plotly figure dictionary with data and layout keys."""
    if chart_type not in VALID_CHART_TYPES:
        raise ChartBuildError(f"Unknown chart type: {chart_type}")

    if not data:
        raise ChartBuildError("Chart data cannot be empty")

    rows = _flatten_records(data)

    if chart_type == "table":
        headers = _table_headers(rows)
        cells = [_extract_table_values(rows, header) for header in headers]
        return {
            "data": [
                {
                    "type": "table",
                    "header": {
                        "values": headers,
                        "fill": {"color": "#4C9AFF"},
                        "font": {"color": "white"},
                    },
                    "cells": {"values": cells},
                }
            ],
            "layout": {"title": title},
        }

    if chart_type == "pie":
        labels_field = labels_field or x_field
        values_field = values_field or y_field
        labels_field, values_field = _auto_detect_fields(
            rows, labels_field, values_field
        )
        return {
            "data": [
                {
                    "type": "pie",
                    "labels": _extract_values(rows, labels_field),
                    "values": _extract_values(rows, values_field),
                }
            ],
            "layout": {"title": title},
        }

    x_field, y_field = _auto_detect_fields(rows, x_field, y_field)
    x_values = _extract_values(rows, x_field)
    y_values = _extract_values(rows, y_field)

    if chart_type == "hbar":
        trace: dict[str, Any] = {
            "type": "bar",
            "orientation": "h",
            "x": y_values,
            "y": x_values,
        }
        layout = {
            "title": title,
            "xaxis": {"title": y_field},
            "yaxis": {"title": x_field},
        }
    else:
        trace = {
            "type": chart_type,
            "x": x_values,
            "y": y_values,
        }
        if chart_type == "scatter":
            trace["mode"] = "markers"
        layout = {
            "title": title,
            "xaxis": {"title": x_field},
            "yaxis": {"title": y_field},
        }

    return {"data": [trace], "layout": layout}
