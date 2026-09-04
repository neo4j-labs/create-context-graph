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

"""Neo4j connection validation."""

from __future__ import annotations

from neo4j import GraphDatabase
from neo4j.exceptions import ServiceUnavailable, AuthError


def validate_connection(
    uri: str, username: str, password: str, database: str = ""
) -> tuple[bool, str]:
    """Test Neo4j connection and return (success, message).

    ``database`` of ``""`` runs the test query against the server default
    database; pass a name to validate a specific database (e.g. Aura
    instances whose database isn't named "neo4j").
    """
    try:
        driver = GraphDatabase.driver(uri, auth=(username, password))
        driver.verify_connectivity()
        # Quick test query
        with driver.session(database=database or None) as session:
            result = session.run("RETURN 1 AS n")
            result.single()
        driver.close()
        return True, "Connected successfully"
    except AuthError:
        return False, "Authentication failed. Check username and password."
    except ServiceUnavailable:
        return False, f"Cannot connect to Neo4j at {uri}. Is it running?"
    except Exception as e:
        return False, f"Connection error: {e}"
