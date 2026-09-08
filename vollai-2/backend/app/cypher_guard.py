"""Safety guards for generated Cypher queries."""

from __future__ import annotations

import re


DEFAULT_ROW_LIMIT = 100
MAX_ROW_LIMIT = 500

_DDL_PATTERNS = (
    "CREATE CONSTRAINT",
    "DROP CONSTRAINT",
    "CREATE INDEX",
    "DROP INDEX",
)
_WRITE_KEYWORDS = {
    "CREATE",
    "MERGE",
    "SET",
    "DELETE",
    "DETACH",
    "REMOVE",
    "DROP",
}
_LIMIT_RE = re.compile(r"\bLIMIT\b", re.IGNORECASE)
_NUMERIC_LIMIT_RE = re.compile(r"(\bLIMIT\s+)(\d+)\b", re.IGNORECASE)


class CypherGuardError(Exception):
    """Raised when a Cypher query violates safety guards."""


def validate_read_only(query: str) -> None:
    """Validate that a Cypher query does not contain write operations."""
    query_upper = query.upper()

    for pattern in _DDL_PATTERNS:
        if pattern in query_upper:
            raise CypherGuardError(f"Write operation is not allowed: {pattern}")

    for raw_token in re.split(r"[\s()]+", query_upper):
        token = raw_token.strip(";,.(){}")
        if token in _WRITE_KEYWORDS:
            raise CypherGuardError(f"Write operation is not allowed: {token}")


def enforce_row_limit(query: str, default_limit: int = DEFAULT_ROW_LIMIT) -> str:
    """Ensure a Cypher query has a bounded LIMIT clause."""
    if _LIMIT_RE.search(query):

        def cap_limit(match: re.Match[str]) -> str:
            limit_value = int(match.group(2))
            if limit_value > MAX_ROW_LIMIT:
                return f"{match.group(1)}{MAX_ROW_LIMIT}"
            return match.group(0)

        return _NUMERIC_LIMIT_RE.sub(cap_limit, query)

    stripped_query = query.rstrip().rstrip(";").rstrip()
    return f"{stripped_query}\nLIMIT {default_limit}"
