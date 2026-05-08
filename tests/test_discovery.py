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

"""Unit tests for Neo4j schema discovery and ontology construction."""

from unittest.mock import MagicMock, patch

from neo4j.exceptions import AuthError, ServiceUnavailable

from create_context_graph.discovery import (
    _classify_pole_type,
    _map_neo4j_type,
    build_ontology_from_discovery,
    discover_ontology_from_database,
)


def _sample_discovery() -> dict:
    return {
        "labels": ["Match", "Player", "Team", "Venue"],
        "relationship_types": ["PLAYED_AT", "PLAYS_FOR"],
        "properties": {
            "Match": [
                {"name": "match_id", "types": ["String"], "mandatory": True},
                {"name": "match_date", "types": ["Date"], "mandatory": False},
            ],
            "Player": [
                {"name": "player_id", "types": ["String"], "mandatory": True},
                {"name": "name", "types": ["String"], "mandatory": True},
                {"name": "height", "types": ["Double"], "mandatory": False},
            ],
            "Team": [
                {"name": "team_id", "types": ["String"], "mandatory": True},
                {"name": "founded", "types": ["Long"], "mandatory": False},
            ],
            "Venue": [
                {"name": "venue_id", "types": ["String"], "mandatory": False},
                {"name": "name", "types": ["String"], "mandatory": True},
            ],
        },
        "rel_properties": {},
        "constraints": [
            {
                "entityType": "NODE",
                "labelsOrTypes": ["Player"],
                "properties": ["player_id"],
            }
        ],
        "indexes": [],
        "schema_graph": [
            {
                "start_label": "Player",
                "rel_type": "PLAYS_FOR",
                "end_label": "Team",
            },
            {
                "start_label": "Match",
                "rel_type": "PLAYED_AT",
                "end_label": "Venue",
            },
        ],
        "sample_counts": {
            "Match": 12,
            "Player": 48,
            "Team": 8,
            "Venue": 4,
        },
    }


def _entity_by_label(ontology, label):
    return next(entity for entity in ontology.entity_types if entity.label == label)


def _property_by_name(entity, name):
    return next(prop for prop in entity.properties if prop.name == name)


def _mock_driver_with_session(session):
    driver = MagicMock()
    driver.session.return_value.__enter__.return_value = session
    return driver


def _assert_raises_connection_error(callable_, text):
    try:
        callable_()
    except ConnectionError as exc:
        assert text in str(exc)
    else:
        raise AssertionError("Expected ConnectionError")


class TestClassifyPoleType:
    def test_player_is_person(self):
        assert _classify_pole_type("Player") == "PERSON"

    def test_coach_is_person(self):
        assert _classify_pole_type("Coach") == "PERSON"

    def test_head_coach_is_person(self):
        assert _classify_pole_type("HeadCoach") == "PERSON"

    def test_team_is_organization(self):
        assert _classify_pole_type("Team") == "ORGANIZATION"

    def test_league_is_organization(self):
        assert _classify_pole_type("League") == "ORGANIZATION"

    def test_club_is_organization(self):
        assert _classify_pole_type("Club") == "ORGANIZATION"

    def test_venue_is_location(self):
        assert _classify_pole_type("Venue") == "LOCATION"

    def test_stadium_is_location(self):
        assert _classify_pole_type("Stadium") == "LOCATION"

    def test_arena_is_location(self):
        assert _classify_pole_type("Arena") == "LOCATION"

    def test_match_is_event(self):
        assert _classify_pole_type("Match") == "EVENT"

    def test_game_is_event(self):
        assert _classify_pole_type("Game") == "EVENT"

    def test_tournament_is_event(self):
        assert _classify_pole_type("Tournament") == "EVENT"

    def test_stat_falls_back_to_object(self):
        assert _classify_pole_type("Stat") == "OBJECT"

    def test_skill_falls_back_to_object(self):
        assert _classify_pole_type("Skill") == "OBJECT"

    def test_formation_falls_back_to_object(self):
        assert _classify_pole_type("Formation") == "OBJECT"


class TestMapNeo4jType:
    def test_string_maps_to_string(self):
        assert _map_neo4j_type(["String"]) == "string"

    def test_long_maps_to_integer(self):
        assert _map_neo4j_type(["Long"]) == "integer"

    def test_integer_maps_to_integer(self):
        assert _map_neo4j_type(["Integer"]) == "integer"

    def test_double_maps_to_float(self):
        assert _map_neo4j_type(["Double"]) == "float"

    def test_boolean_maps_to_boolean(self):
        assert _map_neo4j_type(["Boolean"]) == "boolean"

    def test_date_maps_to_date(self):
        assert _map_neo4j_type(["Date"]) == "date"

    def test_datetime_maps_to_datetime(self):
        assert _map_neo4j_type(["DateTime"]) == "datetime"

    def test_empty_list_maps_to_string(self):
        assert _map_neo4j_type([]) == "string"

    def test_unknown_type_maps_to_string(self):
        assert _map_neo4j_type(["Vector"]) == "string"


class TestDiscoverOntologyFromDatabase:
    def test_discovers_labels_correctly(self):
        session = MagicMock()

        def run(query):
            if "db.labels" in query:
                return [{"label": "Team"}, {"label": "Player"}]
            if "db.relationshipTypes" in query:
                return [{"relationshipType": "PLAYS_FOR"}]
            if "db.schema.nodeTypeProperties" in query:
                return [
                    {
                        "nodeLabels": ["Player"],
                        "propertyName": "name",
                        "propertyTypes": ["String"],
                        "mandatory": True,
                    }
                ]
            if "db.schema.relTypeProperties" in query:
                return []
            if "db.schema.visualization" in query:
                return [
                    {
                        "relationships": [
                            {
                                "type": "PLAYS_FOR",
                                "start": "Player",
                                "end": "Team",
                            }
                        ]
                    }
                ]
            if "SHOW CONSTRAINTS" in query or "SHOW INDEXES" in query:
                return []
            if "count(n)" in query:
                return [{"count": 3}]
            return []

        session.run.side_effect = run
        driver = _mock_driver_with_session(session)

        with patch("create_context_graph.discovery.GraphDatabase.driver") as mock_driver:
            mock_driver.return_value = driver
            discovered = discover_ontology_from_database(
                "neo4j://localhost:7687",
                "neo4j",
                "password",
            )

        assert discovered["labels"] == ["Player", "Team"]
        assert discovered["relationship_types"] == ["PLAYS_FOR"]
        assert discovered["properties"]["Player"][0]["name"] == "name"
        assert discovered["schema_graph"] == [
            {
                "start_label": "Player",
                "rel_type": "PLAYS_FOR",
                "end_label": "Team",
            }
        ]
        assert discovered["sample_counts"] == {"Player": 3, "Team": 3}
        assert set(discovered) == {
            "labels",
            "relationship_types",
            "properties",
            "rel_properties",
            "constraints",
            "indexes",
            "schema_graph",
            "sample_counts",
        }

    def test_auth_error_raises_connection_error(self):
        driver = MagicMock()
        driver.verify_connectivity.side_effect = AuthError("bad auth")

        with patch("create_context_graph.discovery.GraphDatabase.driver") as mock_driver:
            mock_driver.return_value = driver
            _assert_raises_connection_error(
                lambda: discover_ontology_from_database(
                    "neo4j://localhost:7687",
                    "neo4j",
                    "bad-password",
                ),
                "Authentication failed",
            )

    def test_service_unavailable_raises_connection_error(self):
        driver = MagicMock()
        driver.verify_connectivity.side_effect = ServiceUnavailable("offline")

        with patch("create_context_graph.discovery.GraphDatabase.driver") as mock_driver:
            mock_driver.return_value = driver
            _assert_raises_connection_error(
                lambda: discover_ontology_from_database(
                    "neo4j://localhost:7687",
                    "neo4j",
                    "password",
                ),
                "Cannot connect",
            )


class TestBuildOntologyFromDiscovery:
    def test_builds_valid_ontology(self):
        ontology = build_ontology_from_discovery(
            _sample_discovery(),
            "volleyball",
            domain_name="Volleyball",
        )

        assert ontology.domain.id == "volleyball"
        assert ontology.domain.name == "Volleyball"
        assert len(ontology.entity_types) == 4
        assert len(ontology.relationships) == 2

    def test_pole_classification_matches_expected_types(self):
        ontology = build_ontology_from_discovery(_sample_discovery(), "volleyball")

        pole_types = {
            entity.label: entity.pole_type
            for entity in ontology.entity_types
        }
        assert pole_types == {
            "Match": "EVENT",
            "Player": "PERSON",
            "Team": "ORGANIZATION",
            "Venue": "LOCATION",
        }

    def test_property_types_are_mapped_correctly(self):
        ontology = build_ontology_from_discovery(_sample_discovery(), "volleyball")

        match = _entity_by_label(ontology, "Match")
        player = _entity_by_label(ontology, "Player")
        team = _entity_by_label(ontology, "Team")
        assert _property_by_name(match, "match_date").type == "date"
        assert _property_by_name(player, "height").type == "float"
        assert _property_by_name(team, "founded").type == "integer"

    def test_unique_property_detection_from_constraints(self):
        ontology = build_ontology_from_discovery(_sample_discovery(), "volleyball")

        player = _entity_by_label(ontology, "Player")
        assert _property_by_name(player, "player_id").unique is True

    def test_unique_property_heuristic_fallback(self):
        ontology = build_ontology_from_discovery(_sample_discovery(), "volleyball")

        team = _entity_by_label(ontology, "Team")
        assert _property_by_name(team, "team_id").unique is True

    def test_relationships_built_from_schema_graph(self):
        ontology = build_ontology_from_discovery(_sample_discovery(), "volleyball")

        relationships = {
            (rel.source, rel.type, rel.target)
            for rel in ontology.relationships
        }
        assert relationships == {
            ("Player", "PLAYS_FOR", "Team"),
            ("Match", "PLAYED_AT", "Venue"),
        }

    def test_auto_generated_prompt_mentions_labels_and_run_cypher(self):
        ontology = build_ontology_from_discovery(_sample_discovery(), "volleyball")

        assert "Match" in ontology.system_prompt
        assert "Player" in ontology.system_prompt
        assert "run_cypher" in ontology.system_prompt

    def test_custom_system_prompt_overrides_generated_prompt(self):
        ontology = build_ontology_from_discovery(
            _sample_discovery(),
            "volleyball",
            system_prompt="Use volleyball scouting language.",
        )

        assert ontology.system_prompt == "Use volleyball scouting language."

    def test_demo_scenarios_reference_labels(self):
        ontology = build_ontology_from_discovery(_sample_discovery(), "volleyball")

        prompts = ontology.demo_scenarios[0].prompts
        assert any("Match" in prompt for prompt in prompts)
        assert any("Player" in prompt for prompt in prompts)

    def test_visualization_colors_are_assigned_and_distinct(self):
        ontology = build_ontology_from_discovery(_sample_discovery(), "volleyball")

        colors = ontology.visualization.node_colors
        assert set(colors) == {"Match", "Player", "Team", "Venue"}
        assert len(set(colors.values())) == 4

    def test_empty_database_produces_valid_ontology(self):
        ontology = build_ontology_from_discovery(
            {
                "labels": [],
                "relationship_types": [],
                "properties": {},
                "rel_properties": {},
                "constraints": [],
                "indexes": [],
                "schema_graph": [],
                "sample_counts": {},
            },
            "empty",
        )

        assert ontology.domain.id == "empty"
        assert ontology.entity_types == []
        assert ontology.relationships == []
