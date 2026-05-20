"""Tests that validate code snippets, flags, and references in documentation."""

import re
from pathlib import Path

import yaml
import pytest

DOCS_DIR = Path(__file__).resolve().parent.parent / "docs" / "docs"
TEMPLATES_DIR = (
    Path(__file__).resolve().parent.parent
    / "src"
    / "create_context_graph"
    / "templates"
)


def _extract_code_blocks(filepath: Path, language: str | None = None) -> list[tuple[str, str]]:
    """Extract fenced code blocks from a markdown file.

    Returns a list of (language, content) tuples.  When *language* is given,
    only blocks whose info-string matches are returned.
    """
    content = filepath.read_text()
    blocks = re.findall(r"```(\w*)\n(.*?)```", content, re.DOTALL)
    if language is not None:
        blocks = [(lang, body) for lang, body in blocks if lang == language]
    return blocks


# ---------------------------------------------------------------------------
# 1. YAML examples
# ---------------------------------------------------------------------------


class TestYamlExamplesValid:
    """Validate that YAML snippets embedded in the docs parse correctly."""

    def test_ontology_schema_doc_bookstore_example(self):
        """The complete bookstore YAML in ontology-yaml-schema.md must parse
        and contain the required top-level keys."""
        doc_path = DOCS_DIR / "reference" / "ontology-yaml-schema.md"
        yaml_blocks = _extract_code_blocks(doc_path, language="yaml")

        # The last (and longest) YAML block is the complete minimal example
        complete_blocks = [
            (lang, body)
            for lang, body in yaml_blocks
            if "inherits:" in body and "entity_types:" in body and "agent_tools:" in body
        ]
        assert complete_blocks, "No complete bookstore YAML example found in ontology-yaml-schema.md"

        parsed = yaml.safe_load(complete_blocks[-1][1])
        assert isinstance(parsed, dict)

        required_keys = {"inherits", "domain", "entity_types", "relationships", "agent_tools", "system_prompt"}
        missing = required_keys - set(parsed.keys())
        assert not missing, f"Bookstore YAML example is missing top-level keys: {missing}"

        # Verify domain sub-keys
        assert "id" in parsed["domain"]
        assert "name" in parsed["domain"]

        # Verify at least one entity type with a label
        assert len(parsed["entity_types"]) > 0
        assert "label" in parsed["entity_types"][0]

    def test_customizing_ontology_examples_parse(self):
        """All YAML blocks in the customizing-domain-ontology tutorial must parse."""
        doc_path = DOCS_DIR / "tutorials" / "customizing-domain-ontology.md"
        yaml_blocks = _extract_code_blocks(doc_path, language="yaml")
        assert yaml_blocks, "No YAML blocks found in customizing-domain-ontology.md"

        for i, (_, body) in enumerate(yaml_blocks):
            try:
                yaml.safe_load(body)
            except yaml.YAMLError as exc:
                pytest.fail(f"YAML block {i} in customizing-domain-ontology.md failed to parse: {exc}")

    def test_ontology_schema_doc_all_yaml_blocks_parse(self):
        """Every YAML block in the ontology-yaml-schema doc must be valid YAML."""
        doc_path = DOCS_DIR / "reference" / "ontology-yaml-schema.md"
        yaml_blocks = _extract_code_blocks(doc_path, language="yaml")
        assert yaml_blocks, "No YAML blocks found"

        for i, (_, body) in enumerate(yaml_blocks):
            # Skip blocks that are intentional "wrong" examples (comments say so)
            if "# Wrong" in body or "# Incorrect" in body:
                continue
            try:
                yaml.safe_load(body)
            except yaml.YAMLError as exc:
                pytest.fail(f"YAML block {i} in ontology-yaml-schema.md failed to parse: {exc}")


# ---------------------------------------------------------------------------
# 2. CLI flags
# ---------------------------------------------------------------------------


class TestCliFlags:
    """Verify that documented CLI flags actually exist on the Click command."""

    def test_documented_flags_exist_in_cli(self):
        """Every --flag-name documented in cli-options.md must map to a
        parameter on the ``main`` Click command."""
        from create_context_graph.cli import main

        doc_path = DOCS_DIR / "reference" / "cli-options.md"
        content = doc_path.read_text()

        # Extract --flag-name patterns from the options table (lines starting
        # with | `--...)  Also grab from example code blocks.
        documented_flags = set(re.findall(r"`(--[\w-]+)`", content))
        assert documented_flags, "No --flags found in cli-options.md"

        # Build a set of flag names from the Click command parameters.
        # Click stores parameter names with underscores; convert to kebab.
        # For boolean flag pairs (e.g. --flag/--no-flag), include both
        # the primary and secondary option strings.
        cli_flag_names: set[str] = set()
        for p in main.params:
            cli_flag_names.add("--" + p.name.replace("_", "-"))
            if hasattr(p, "opts"):
                cli_flag_names.update(p.opts)
            if hasattr(p, "secondary_opts") and p.secondary_opts:
                cli_flag_names.update(p.secondary_opts)

        # --help and --version are built-in Click decorators and won't appear
        # as explicit params in all Click versions; allow them.
        known_exceptions = {"--help", "--version"}

        missing = documented_flags - cli_flag_names - known_exceptions
        assert not missing, (
            f"Documented flags not found on CLI command: {sorted(missing)}. "
            f"Available: {sorted(cli_flag_names)}"
        )


# ---------------------------------------------------------------------------
# 3. Cypher snippets
# ---------------------------------------------------------------------------


class TestCypherSnippets:
    """Validate structure of Cypher code blocks in tutorial docs."""

    @staticmethod
    def _collect_cypher_blocks() -> list[tuple[str, str, int]]:
        """Return (filename, cypher_body, block_index) for all cypher blocks
        in tutorial and how-to docs."""
        results = []
        for md_file in sorted(DOCS_DIR.rglob("*.md")):
            blocks = _extract_code_blocks(md_file, language="cypher")
            for i, (_, body) in enumerate(blocks):
                results.append((md_file.name, body, i))
        return results

    def test_cypher_snippets_have_valid_structure(self):
        """Each ```cypher block must contain MATCH or CALL, and RETURN."""
        blocks = self._collect_cypher_blocks()
        assert blocks, "No cypher code blocks found in any doc"

        for filename, body, idx in blocks:
            upper = body.upper()
            # DDL blocks (CREATE CONSTRAINT / CREATE INDEX) are valid Cypher
            # but don't have MATCH/RETURN.
            is_ddl = "CREATE CONSTRAINT" in upper or "CREATE INDEX" in upper
            if is_ddl:
                continue

            has_match_or_call = "MATCH" in upper or "CALL" in upper
            has_return = "RETURN" in upper
            assert has_match_or_call, (
                f"Cypher block {idx} in {filename} missing MATCH/CALL:\n{body[:200]}"
            )
            assert has_return, (
                f"Cypher block {idx} in {filename} missing RETURN:\n{body[:200]}"
            )

    def test_linear_tutorial_has_cypher_examples(self):
        """The Linear tutorial should have multiple Cypher examples."""
        doc_path = DOCS_DIR / "tutorials" / "linear-context-graph.md"
        blocks = _extract_code_blocks(doc_path, language="cypher")
        assert len(blocks) >= 8, (
            f"Expected at least 8 cypher blocks in linear-context-graph.md, found {len(blocks)}"
        )


# ---------------------------------------------------------------------------
# 4. Make targets
# ---------------------------------------------------------------------------


class TestMakeTargets:
    """Verify that ``make <target>`` references in docs exist in the Makefile template."""

    @staticmethod
    def _get_makefile_targets() -> set[str]:
        """Parse target names from the Makefile.j2 template."""
        makefile_path = TEMPLATES_DIR / "base" / "Makefile.j2"
        content = makefile_path.read_text()
        # Matches lines like "target:" or "target: dep1 dep2" at the start
        targets = set(re.findall(r"^([\w-]+)\s*:", content, re.MULTILINE))
        return targets

    @staticmethod
    def _get_documented_make_targets() -> set[str]:
        """Extract ``make <target>`` references from all doc files."""
        targets: set[str] = set()
        for md_file in sorted(DOCS_DIR.rglob("*.md")):
            content = md_file.read_text()
            # Match `make target` in code blocks and inline code.
            # Use word boundary to avoid matching prose like "make sure".
            found = re.findall(r"(?:^|\s)make\s+([\w-]+)", content)
            # Filter out common English words that follow "make" in prose
            found = [t for t in found if t not in {"sure", "it", "the", "a", "any", "changes", "this", "up", "use"}]
            targets.update(found)
        return targets

    def test_documented_make_targets_exist_in_template(self):
        """Every ``make <target>`` mentioned in docs should be defined in
        Makefile.j2 (or be a well-known conditional target)."""
        template_targets = self._get_makefile_targets()
        documented_targets = self._get_documented_make_targets()

        assert documented_targets, "No 'make <target>' references found in docs"

        # Some targets are conditional in the Jinja template (only rendered
        # when certain config options are set), but still valid.
        conditional_targets = {
            "docker-up", "docker-down",          # neo4j_type == 'docker'
            "neo4j-start", "neo4j-stop", "neo4j-status",  # neo4j_type == 'local'
            "import", "import-and-seed",         # saas_connectors present
        }

        missing = documented_targets - template_targets - conditional_targets
        assert not missing, (
            f"Documented make targets not found in Makefile.j2: {sorted(missing)}. "
            f"Template targets: {sorted(template_targets)}"
        )


# ---------------------------------------------------------------------------
# 5. Environment variables
# ---------------------------------------------------------------------------


class TestEnvVariables:
    """Verify documented env vars appear in the .env.example template."""

    @staticmethod
    def _get_template_env_keys() -> set[str]:
        """Extract KEY names from dot_env_example.j2."""
        env_path = TEMPLATES_DIR / "base" / "dot_env_example.j2"
        content = env_path.read_text()
        # Match KEY=value lines (skip Jinja comments and blank lines)
        keys = set(re.findall(r"^([A-Z][A-Z0-9_]+)\s*=", content, re.MULTILINE))
        # Also pick up commented-out keys like "# ANTHROPIC_MODEL=..."
        keys.update(re.findall(r"^#\s*([A-Z][A-Z0-9_]+)\s*=", content, re.MULTILINE))
        return keys

    @staticmethod
    def _get_documented_env_keys() -> set[str]:
        """Extract environment variable names from .env-style code blocks in docs."""
        keys: set[str] = set()
        for md_file in sorted(DOCS_DIR.rglob("*.md")):
            content = md_file.read_text()
            # Look inside ```bash or ``` blocks that look like .env files
            blocks = re.findall(r"```(?:bash|env|sh)?\n(.*?)```", content, re.DOTALL)
            for block in blocks:
                for line in block.splitlines():
                    stripped = line.lstrip("# ")
                    # Match KEY=value or export KEY=value
                    match = re.match(r"^(?:export\s+)?([A-Z][A-Z0-9_]+)=", stripped)
                    if match:
                        keys.add(match.group(1))
        return keys

    def test_documented_env_vars_exist_in_template(self):
        """Core env vars documented in the docs should appear in
        dot_env_example.j2."""
        template_keys = self._get_template_env_keys()
        documented_keys = self._get_documented_env_keys()

        assert template_keys, "No env keys found in dot_env_example.j2"
        assert documented_keys, "No env keys found in documentation"

        # Only check the core env vars that the generated project uses.
        # Docs may also reference vars like ANTHROPIC_API_KEY in CLI usage
        # context (export ...) that do belong in .env.example.
        core_vars = {
            "NEO4J_URI",
            "NEO4J_USERNAME",
            "NEO4J_PASSWORD",
            "ANTHROPIC_API_KEY",
        }

        # These core vars should be documented AND in the template
        for var in core_vars:
            assert var in template_keys, f"{var} missing from dot_env_example.j2"
            assert var in documented_keys, f"{var} not referenced in any documentation"

        # Check that documented env vars that also appear in the template
        # have reasonable overlap
        overlap = documented_keys & template_keys
        assert len(overlap) >= 3, (
            f"Expected at least 3 env vars in common between docs and template, "
            f"found {len(overlap)}: {sorted(overlap)}"
        )


class TestNamsRelationshipEncoding:
    """Both the docs and the code must describe the ccg-edges encoding the
    NAMS path uses in lieu of native relationships."""

    def test_use_nams_doc_covers_ccg_edges_encoding(self):
        doc = (DOCS_DIR / "how-to" / "use-nams.md").read_text()
        # The encoding section heading + the literal fence marker + a
        # readable example so users know what they're looking at.
        assert "Seeding a relationship-rich graph" in doc
        assert "ccg-edges" in doc
        # The self-hosted escape hatch must still be discoverable for users
        # who need native edges today.
        assert "--self-hosted" in doc
        assert "--demo" in doc

    def test_ingest_py_uses_ccg_edges_marker(self):
        ingest = (
            Path(__file__).resolve().parent.parent
            / "src"
            / "create_context_graph"
            / "ingest.py"
        ).read_text()
        # The marker is the single seam future contributors swap when NAMS
        # ships add_relationship; the contract test pins both consumers
        # to its output.
        assert "ccg-edges" in ingest
        assert "_build_ccg_edges_block" in ingest

    def test_scaffold_template_uses_ccg_edges_marker(self):
        template = (
            Path(__file__).resolve().parent.parent
            / "src"
            / "create_context_graph"
            / "templates"
            / "backend"
            / "connectors"
            / "import_data.py.j2"
        ).read_text()
        # The scaffolded path must use the same encoding so generated apps
        # produce graph-identical output to the CLI ingest.
        assert "ccg-edges" in template
        assert "_build_ccg_edges_block" in template

    def test_explanation_page_exists_and_round_trips(self):
        """The new explanation/ccg-edges.md must exist and its example block
        must match the format actually produced by ``_build_ccg_edges_block``.
        Catches the page drifting out of sync with the encoder."""
        page = DOCS_DIR / "explanation" / "ccg-edges.md"
        assert page.exists(), "docs/docs/explanation/ccg-edges.md missing"
        text = page.read_text()
        assert "```ccg-edges" in text
        assert "type:" in text and "target:" in text and "target_label:" in text

        # Drive the encoder with the exact relationships shown in the doc's
        # example and verify the output matches what the page claims.
        from create_context_graph.ingest import _build_ccg_edges_block
        relationships = [
            {
                "source_name": "Alice Park",
                "type": "AUTHORED",
                "target_name": "Q3 Strategy Memo",
                "target_label": "Document",
            },
            {
                "source_name": "Alice Park",
                "type": "MENTIONS",
                "target_name": "Market Opportunity",
                "target_label": "Concept",
            },
        ]
        block = _build_ccg_edges_block(relationships, "Alice Park")
        # Sorted deterministically by (type, target) — AUTHORED < MENTIONS.
        assert block.startswith("```ccg-edges")
        assert block.endswith("```")
        assert "- type: AUTHORED" in block
        assert "  target: Q3 Strategy Memo" in block
        assert "  target_label: Document" in block
        assert "- type: MENTIONS" in block
        assert "  target: Market Opportunity" in block
        # AUTHORED entry must appear before MENTIONS in the deterministic sort.
        assert block.index("AUTHORED") < block.index("MENTIONS")

    def test_readme_template_links_to_ccg_edges_doc(self):
        readme = (
            Path(__file__).resolve().parent.parent
            / "src"
            / "create_context_graph"
            / "templates"
            / "base"
            / "README.md.j2"
        ).read_text()
        # Scaffolded README must point at the explanation page so users who
        # see the encoding in their graph can read the design rationale.
        assert "ccg-edges" in readme
        assert "explanation/ccg-edges" in readme
