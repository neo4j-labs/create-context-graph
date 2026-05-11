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

"""CLI entry point for create-context-graph."""

from __future__ import annotations

import logging
import os
from pathlib import Path

import click
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn

from create_context_graph.config import SUPPORTED_FRAMEWORKS, FRAMEWORK_ALIASES, ProjectConfig
from create_context_graph.ontology import list_available_domains, load_domain
from create_context_graph.renderer import ProjectRenderer

console = Console()


@click.command()
@click.argument("project_name", required=False)
@click.option(
    "--domain",
    type=str,
    help="Domain ID (e.g., financial-services, healthcare, software-engineering)",
)
@click.option(
    "--framework",
    type=click.Choice(SUPPORTED_FRAMEWORKS + list(FRAMEWORK_ALIASES.keys()), case_sensitive=False),
    help="Agent framework to use",
)
@click.option("--demo-data", is_flag=True, help="Generate synthetic demo data")
@click.option("--ingest", is_flag=True, help="Ingest generated data into Neo4j")
@click.option("--neo4j-uri", envvar="NEO4J_URI", help="Neo4j connection URI")
@click.option("--neo4j-username", envvar="NEO4J_USERNAME", default="neo4j")
@click.option("--neo4j-password", envvar="NEO4J_PASSWORD", default="password")
@click.option("--neo4j-aura-env", type=click.Path(exists=True), help="Path to Neo4j Aura .env file with credentials")
@click.option("--neo4j-local", is_flag=True, help="Use @johnymontana/neo4j-local for local Neo4j (no Docker)")
@click.option("--anthropic-api-key", envvar="ANTHROPIC_API_KEY", help="Anthropic API key for LLM generation")
@click.option("--openai-api-key", envvar="OPENAI_API_KEY", help="OpenAI API key for LLM generation")
@click.option("--google-api-key", envvar="GOOGLE_API_KEY", help="Google/Gemini API key (required for google-adk framework)")
@click.option("--custom-domain", type=str, help="Natural language description for custom domain generation (requires --anthropic-api-key)")
@click.option("--connector", multiple=True, help="SaaS connector to enable (github, slack, jira, notion, gmail, gcal, salesforce, linear, google-workspace, claude-code, claude-ai, chatgpt, local-file)")
@click.option("--linear-api-key", envvar="LINEAR_API_KEY", help="Linear API key (required for --connector linear)")
@click.option("--linear-team", envvar="LINEAR_TEAM", help="Linear team key to filter import (e.g., ENG)")
@click.option("--claude-code-scope", type=click.Choice(["current", "all"]), default="current", help="Import sessions from current project (default) or all projects")
@click.option("--claude-code-project", help="Explicit project path to import Claude Code sessions for")
@click.option("--claude-code-since", help="Import Claude Code sessions since date (ISO format)")
@click.option("--claude-code-max-sessions", type=int, default=0, help="Maximum number of Claude Code sessions to import (0=all)")
@click.option("--claude-code-content", type=click.Choice(["truncated", "full", "none"]), default="truncated", help="Content storage mode for Claude Code messages")
@click.option("--local-file-path", "local_file_path", multiple=True, type=click.Path(), help="Path to a file or directory to ingest with --connector local-file (repeatable)")
@click.option("--local-file-pattern", default="**/*", help="Glob pattern filter for local-file ingest")
@click.option("--local-file-recursive/--local-file-no-recursive", default=True, help="Recurse into subdirectories during local-file ingest")
@click.option("--local-file-follow-links", is_flag=True, default=False, help="Follow symlinks during local-file ingest")
@click.option("--local-file-exclude", "local_file_exclude", multiple=True, help="Glob pattern to exclude from local-file ingest (repeatable)")
@click.option("--gws-folder-id", envvar="GWS_FOLDER_ID", help="Google Drive folder ID to scope import")
@click.option("--gws-include-comments/--gws-no-comments", default=True, help="Import comment threads from Docs/Sheets/Slides")
@click.option("--gws-include-revisions/--gws-no-revisions", default=True, help="Import revision history metadata")
@click.option("--gws-include-activity/--gws-no-activity", default=True, help="Import Drive Activity events")
@click.option("--gws-include-calendar", is_flag=True, default=False, help="Import Calendar events")
@click.option("--gws-include-gmail", is_flag=True, default=False, help="Import Gmail thread metadata")
@click.option("--gws-since", help="Import data since date (ISO format, default 90 days ago)")
@click.option("--gws-mime-types", default="docs,sheets,slides", help="Comma-separated MIME types (docs,sheets,slides,pdf,all)")
@click.option("--gws-max-files", type=int, default=500, help="Maximum files to import (safety limit)")
@click.option("--import-type", "import_type", type=click.Choice(["claude-ai", "chatgpt"]), help="Chat history import type (claude-ai or chatgpt)")
@click.option("--import-file", type=click.Path(), help="Path to chat export file (.zip, .json, .jsonl)")
@click.option("--import-depth", type=click.Choice(["fast", "deep"]), default="fast", help="Import extraction depth (fast=messages only, deep=full)")
@click.option("--import-filter-after", type=str, help="Only import conversations after this date (ISO 8601)")
@click.option("--import-filter-before", type=str, help="Only import conversations before this date (ISO 8601)")
@click.option("--import-filter-title", type=str, help="Only import conversations matching this title pattern (regex)")
@click.option("--import-max-conversations", type=int, default=0, help="Maximum conversations to import (0=all)")
@click.option("--with-mcp", is_flag=True, default=False, help="Generate MCP server configuration for Claude Desktop")
@click.option("--mcp-profile", type=click.Choice(["core", "extended"], case_sensitive=False), default="extended", help="MCP tool profile (core=6 tools, extended=16 tools)")
@click.option("--session-strategy", type=click.Choice(["per_conversation", "per_day", "persistent"], case_sensitive=False), default="per_conversation", help="Memory session strategy")
@click.option("--auto-extract/--no-auto-extract", default=True, help="Auto-extract entities from conversation messages")
@click.option("--auto-preferences/--no-auto-preferences", default=True, help="Auto-detect user preferences from conversation messages")
@click.option("--output-dir", type=click.Path(), help="Output directory (default: ./<project-name>)")
@click.option("--demo", is_flag=True, help="Shortcut for --reset-database --demo-data --ingest")
@click.option("--dry-run", is_flag=True, help="Preview what would be generated without creating files")
@click.option("--reset-database", is_flag=True, help="Clear all Neo4j data before ingesting")
@click.option("--verbose", is_flag=True, help="Enable verbose debug output")
@click.option("--list-domains", is_flag=True, help="List available domains and exit")
@click.version_option(package_name="create-context-graph")
def main(
    project_name: str | None,
    domain: str | None,
    framework: str | None,
    demo_data: bool,
    ingest: bool,
    neo4j_uri: str | None,
    neo4j_username: str,
    neo4j_password: str,
    neo4j_aura_env: str | None,
    neo4j_local: bool,
    anthropic_api_key: str | None,
    openai_api_key: str | None,
    google_api_key: str | None,
    custom_domain: str | None,
    connector: tuple[str, ...],
    linear_api_key: str | None,
    linear_team: str | None,
    gws_folder_id: str | None,
    gws_include_comments: bool,
    gws_include_revisions: bool,
    gws_include_activity: bool,
    gws_include_calendar: bool,
    gws_include_gmail: bool,
    gws_since: str | None,
    gws_mime_types: str,
    gws_max_files: int,
    claude_code_scope: str,
    claude_code_project: str | None,
    claude_code_since: str | None,
    claude_code_max_sessions: int,
    claude_code_content: str,
    local_file_path: tuple[str, ...],
    local_file_pattern: str,
    local_file_recursive: bool,
    local_file_follow_links: bool,
    local_file_exclude: tuple[str, ...],
    import_type: str | None,
    import_file: str | None,
    import_depth: str,
    import_filter_after: str | None,
    import_filter_before: str | None,
    import_filter_title: str | None,
    import_max_conversations: int,
    with_mcp: bool,
    mcp_profile: str,
    session_strategy: str,
    auto_extract: bool,
    auto_preferences: bool,
    output_dir: str | None,
    demo: bool,
    dry_run: bool,
    reset_database: bool,
    verbose: bool,
    list_domains: bool,
) -> None:
    """Create a domain-specific context graph application.

    Generates a full-stack application with a FastAPI backend,
    Next.js frontend, Neo4j knowledge graph, and AI agent—
    all customized for your industry domain.
    """
    # Verbose logging
    if verbose:
        logging.basicConfig(level=logging.DEBUG, format="%(name)s %(levelname)s: %(message)s")

    # --demo is a shortcut for --reset-database --demo-data --ingest
    if demo:
        reset_database = True
        demo_data = True
        ingest = True

    # Validate --import-type / --import-file co-dependency
    if import_type and not import_file:
        console.print("[red]Error:[/red] --import-file is required when --import-type is specified.")
        raise SystemExit(1)
    if import_file and not import_type:
        console.print("[red]Error:[/red] --import-type is required when --import-file is specified.")
        raise SystemExit(1)

    # Auto-add chat import connector when --import-type is provided
    if import_type:
        connector = tuple(list(connector) + [import_type])

    # List domains mode
    if list_domains:
        domains = list_available_domains()
        console.print("\n[bold]Available domains:[/bold]\n")
        for d in domains:
            console.print(f"  {d['id']:30s} {d['name']}")
        console.print()
        return

    # Handle custom domain generation (non-interactive)
    custom_domain_yaml = None
    custom_ontology = None
    if custom_domain:
        if not anthropic_api_key:
            console.print("[red]Error:[/red] --anthropic-api-key is required for custom domain generation.")
            raise SystemExit(1)
        from create_context_graph.custom_domain import (
            display_ontology_summary,
            generate_custom_domain,
        )

        console.print("[bold]Generating custom domain ontology...[/bold]")
        try:
            custom_ontology, custom_domain_yaml = generate_custom_domain(
                custom_domain, anthropic_api_key
            )
        except ValueError as e:
            console.print(f"[red]Error:[/red] {e}")
            raise SystemExit(1)

        display_ontology_summary(custom_ontology, console)
        domain = custom_ontology.domain.id

    # Resolve deprecated framework aliases
    if framework:
        framework = FRAMEWORK_ALIASES.get(framework, framework)

    # Handle Neo4j Aura .env import
    if neo4j_aura_env:
        from create_context_graph.wizard import _parse_aura_env
        neo4j_uri, neo4j_username, neo4j_password = _parse_aura_env(neo4j_aura_env)

    # Determine neo4j_type from flags
    if neo4j_aura_env:
        neo4j_type_resolved = "aura"
    elif neo4j_local:
        neo4j_type_resolved = "local"
    elif neo4j_uri and "aura" in (neo4j_uri or ""):
        neo4j_type_resolved = "aura"
    else:
        neo4j_type_resolved = "docker"

    # Validate empty project name in non-interactive mode
    if project_name is not None and not project_name.strip():
        console.print("[red]Error:[/red] Project name cannot be empty.")
        raise SystemExit(1)

    # Auto-generate project name when all required flags are provided but no positional arg
    if not project_name and (domain or custom_domain) and framework:
        domain_part = domain or "custom"
        project_name = f"{domain_part}-{framework}-app"

    # Non-TTY detection: give a helpful error when wizard would be required but stdin isn't interactive
    import sys
    if not project_name and not sys.stdin.isatty():
        missing = []
        if not domain and not custom_domain:
            missing.append("--domain")
        if not framework:
            missing.append("--framework")
        console.print(f"[red]Error:[/red] Non-interactive mode requires: {', '.join(missing or ['--domain and --framework'])}")
        console.print("Tip: Provide all required flags, e.g.:")
        console.print("  create-context-graph --domain healthcare --framework pydanticai --demo-data")
        raise SystemExit(1)

    # If all required args are provided, skip wizard
    if project_name and (domain or custom_domain) and framework:
        config = ProjectConfig(
            project_name=project_name,
            domain=domain or "custom",
            framework=framework,
            data_source="saas" if connector else ("demo" if demo_data else "none"),
            neo4j_uri=neo4j_uri or "neo4j://localhost:7687",
            neo4j_username=neo4j_username,
            neo4j_password=neo4j_password,
            neo4j_type=neo4j_type_resolved,
            anthropic_api_key=anthropic_api_key,
            openai_api_key=openai_api_key,
            google_api_key=google_api_key,
            generate_data=demo_data,
            custom_domain_yaml=custom_domain_yaml,
            saas_connectors=list(connector),
            with_mcp=with_mcp,
            mcp_profile=mcp_profile,
            session_strategy=session_strategy,
            auto_extract=auto_extract,
            auto_preferences=auto_preferences,
        )
        # Populate SaaS credentials from CLI flags
        if "linear" in connector:
            creds = {}
            if linear_api_key:
                creds["api_key"] = linear_api_key
            if linear_team:
                creds["team_key"] = linear_team
            config.saas_credentials["linear"] = creds
            if not linear_api_key:
                console.print(
                    "[yellow]Warning:[/yellow] --connector linear requires a Linear API key. "
                    "Set LINEAR_API_KEY in your .env or pass --linear-api-key."
                )
        if "google-workspace" in connector:
            creds = {
                "folder_id": gws_folder_id or "",
                "include_comments": str(gws_include_comments).lower(),
                "include_revisions": str(gws_include_revisions).lower(),
                "include_activity": str(gws_include_activity).lower(),
                "include_calendar": str(gws_include_calendar).lower(),
                "include_gmail": str(gws_include_gmail).lower(),
                "since": gws_since or "",
                "mime_types": gws_mime_types or "",
                "max_files": str(gws_max_files),
            }
            config.saas_credentials["google-workspace"] = creds
        if "claude-code" in connector:
            creds = {
                "scope": claude_code_scope,
                "project_filter": claude_code_project or "",
                "since": claude_code_since or "",
                "max_sessions": str(claude_code_max_sessions),
                "content_mode": claude_code_content,
            }
            config.saas_credentials["claude-code"] = creds
        if "local-file" in connector:
            if not local_file_path:
                console.print(
                    "[red]Error:[/red] --connector local-file requires at least one "
                    "--local-file-path."
                )
                raise SystemExit(1)
            # ProjectConfig.saas_credentials values are typed as
            # ``dict[str, str]`` — list-valued fields are stored joined by
            # os.pathsep here and split back in LocalFileConnector.authenticate.
            # os.pathsep (':' on POSIX, ';' on Windows) cannot appear in a
            # well-formed filesystem path, so this is safe for all platforms.
            config.saas_credentials["local-file"] = {
                "paths": os.pathsep.join(local_file_path),
                "pattern": local_file_pattern,
                "recursive": str(local_file_recursive).lower(),
                "follow_links": str(local_file_follow_links).lower(),
                "exclude": os.pathsep.join(local_file_exclude),
            }
        if import_type and import_file:
            creds = {
                "file_path": str(Path(import_file).resolve()),
                "depth": import_depth,
                "filter_after": import_filter_after or "",
                "filter_before": import_filter_before or "",
                "filter_title": import_filter_title or "",
                "max_conversations": str(import_max_conversations),
            }
            config.saas_credentials[import_type] = creds
        # Warn if google-adk is selected without a Google API key
        if config.resolved_framework == "google-adk" and not google_api_key:
            console.print(
                "[yellow]Warning:[/yellow] google-adk framework requires a Google/Gemini API key. "
                "Set GOOGLE_API_KEY in your .env or pass --google-api-key."
            )
        # Warn if openai-agents is selected without an OpenAI API key
        if config.resolved_framework == "openai-agents" and not openai_api_key:
            console.print(
                "[yellow]Warning:[/yellow] openai-agents framework requires an OpenAI API key. "
                "Set OPENAI_API_KEY in your .env or pass --openai-api-key."
            )
    else:
        # Launch interactive wizard
        from create_context_graph.wizard import run_wizard

        config = run_wizard()

    # Resolve output directory
    out = Path(output_dir) if output_dir else Path.cwd() / config.project_slug

    # Dry run: show what would be generated and exit
    if dry_run:
        console.print("\n[bold]Dry run — no files will be created[/bold]\n")
        console.print(f"  Project:    {config.project_name}")
        console.print(f"  Slug:       {config.project_slug}")
        console.print(f"  Domain:     {config.domain}")
        console.print(f"  Framework:  {config.framework}")
        console.print(f"  Neo4j:      {config.neo4j_type} ({config.neo4j_uri})")
        console.print(f"  Data:       {config.data_source}")
        if config.saas_connectors:
            console.print(f"  Connectors: {', '.join(config.saas_connectors)}")
        console.print(f"  Memory:     strategy={config.session_strategy}, extract={config.auto_extract}, preferences={config.auto_preferences}")
        if config.with_mcp:
            console.print(f"  MCP:        profile={config.mcp_profile}")
        console.print(f"  Output:     {out}")
        console.print()
        return
    if out.exists() and any(out.iterdir()):
        console.print(f"[red]Error:[/red] Directory {out} already exists and is not empty.")
        raise SystemExit(1)

    # Load domain ontology
    if custom_ontology:
        ontology = custom_ontology
    elif config.custom_domain_yaml:
        from create_context_graph.ontology import load_domain_from_yaml_string
        ontology = load_domain_from_yaml_string(config.custom_domain_yaml)
    else:
        try:
            ontology = load_domain(config.domain)
        except FileNotFoundError:
            console.print(f"[red]Error:[/red] Domain '{config.domain}' not found.")
            available = list_available_domains()
            console.print("Available domains: " + ", ".join(d["id"] for d in available))
            raise SystemExit(1)

    # Generate project
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        task = progress.add_task("Creating project scaffold...", total=None)

        renderer = ProjectRenderer(config, ontology)
        renderer.render(out)

        progress.update(task, description="Project generated!")

    # Generate demo data if requested
    fixture_path = out / "data" / "fixtures.json"
    if config.generate_data or demo_data:
        console.print("\n[bold]Generating demo data...[/bold]")
        from create_context_graph.generator import generate_fixture_data

        generate_fixture_data(
            ontology,
            fixture_path,
            api_key=config.anthropic_api_key or anthropic_api_key,
        )

    # Import data from SaaS connectors if configured
    if config.saas_connectors:
        import json

        from create_context_graph.connectors import get_connector, merge_connector_results, NormalizedData

        console.print("\n[bold]Importing data from connected services...[/bold]")
        results: list[NormalizedData] = []
        for conn_id in config.saas_connectors:
            try:
                conn = get_connector(conn_id)
                creds = config.saas_credentials.get(conn_id, {})
                console.print(f"  Connecting to {conn.service_name}...")
                conn.authenticate(creds)
                console.print(f"  Fetching data from {conn.service_name}...")
                data = conn.fetch()
                results.append(data)
                entity_count = sum(len(v) for v in data.entities.values())
                console.print(f"  [green]✓[/green] {conn.service_name}: {entity_count} entities, {len(data.documents)} documents")
            except Exception as e:
                console.print(f"  [yellow]⚠[/yellow] {conn_id}: {e}")

        if results:
            merged = merge_connector_results(results)
            fixture_path.parent.mkdir(parents=True, exist_ok=True)
            fixture_path.write_text(json.dumps(merged.model_dump(), indent=2, default=str))
            console.print(f"\n[green]Imported data written to {fixture_path}[/green]")

    # Reset Neo4j database if requested
    if reset_database:
        console.print("\n[bold]Resetting Neo4j database...[/bold]")
        from create_context_graph.ingest import reset_neo4j

        try:
            reset_neo4j(
                config.neo4j_uri,
                config.neo4j_username,
                config.neo4j_password,
            )
            console.print("  [green]Database cleared[/green]")
        except Exception as e:
            console.print(f"  [red]Failed to reset database:[/red] {e}")

    # Ingest into Neo4j if requested
    if ingest and fixture_path.exists():
        console.print("\n[bold]Ingesting data into Neo4j...[/bold]")
        from create_context_graph.ingest import ingest_data

        ingest_data(
            fixture_path,
            ontology,
            config.neo4j_uri,
            config.neo4j_username,
            config.neo4j_password,
        )
        console.print("  [dim]Tip: Use --reset-database if you previously ingested a different domain into this Neo4j instance.[/dim]")

    # Success message
    console.print()
    console.print(f"[bold green]Done![/bold green] Your {ontology.domain.name} context graph app is ready.")
    console.print()
    try:
        display_path = out.relative_to(Path.cwd())
    except ValueError:
        display_path = out
    def _step(cmd: str, comment: str) -> None:
        console.print(f"  [bold]{cmd}[/bold]{' ' * (18 - len(cmd))}# {comment}")

    console.print(f"  [bold]cd {display_path}[/bold]")
    _step("make install",     "Install dependencies")
    if config.neo4j_type == "docker":
        _step("make docker-up",   "Start Neo4j")
    elif config.neo4j_type == "local":
        _step("make neo4j-start", "Start Neo4j (requires Node.js)")
    if config.saas_connectors:
        _step("make import",      "Fetch real data from connected services")
        _step("make seed",        "Apply schema + ingest data into Neo4j")
    elif ingest:
        _step("make seed",        "Re-seed sample data (already ingested)")
    else:
        _step("make seed",        "Apply schema + seed sample data")
    if config.with_mcp:
        _step("make mcp-server",  "Start MCP server for Claude Desktop")
    _step("make start",       "Start backend + frontend")
    console.print()
    console.print("  Backend:  http://localhost:8000")
    console.print("  Frontend: http://localhost:3000")
    console.print()
