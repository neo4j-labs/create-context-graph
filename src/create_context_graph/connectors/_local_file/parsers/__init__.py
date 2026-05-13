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

"""Per-format parsers for the Local File document connector.

Each module exposes a ``parse(path) -> ParsedDocument`` function. The
parsers are imported lazily by :func:`create_context_graph.connectors
._local_file.parser.parse_file` so that the connector can run even when
some optional dependencies are missing (each parser checks its own
imports).
"""
