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

"""Interactive CLI wizard using Questionary and Rich."""

from __future__ import annotations

import questionary
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from create_context_graph.config import (
    FRAMEWORK_DISPLAY_NAMES,
    SUPPORTED_FRAMEWORKS,
    ProjectConfig,
)
from create_context_graph.ontology import list_available_domains

console = Console()


def _parse_aura_env(env_path: str) -> tuple[str, str, str]:
    """Parse a Neo4j Aura .env file and return (uri, username, password)."""
    from pathlib import Path

    path = Path(env_path).expanduser()
    if not path.exists():
        console.print(f"[red]Error:[/red] File not found: {path}")
        raise SystemExit(1)

    values: dict[str, str] = {}
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" in line:
            key, _, value = line.partition("=")
            values[key.strip()] = value.strip().strip('"').strip("'")

    uri = values.get("NEO4J_URI", "")
    username = values.get("NEO4J_USERNAME", "neo4j")
    password = values.get("NEO4J_PASSWORD", "")

    if not uri:
        console.print("[red]Error:[/red] NEO4J_URI not found in .env file")
        raise SystemExit(1)
    if not password:
        console.print("[red]Error:[/red] NEO4J_PASSWORD not found in .env file")
        raise SystemExit(1)

    console.print(f"  [green]✓[/green] Loaded credentials for {uri}")
    return uri, username, password


def _banner() -> None:
    console.print(
        Panel(
            "[bold cyan]Create Context Graph[/bold cyan]\n"
            "[dim]Interactive scaffolding for domain-specific context graph applications[/dim]",
            border_style="cyan",
        )
    )


def run_wizard(
    project_name: str | None = None,
    domain: str | None = None,
    framework: str | None = None,
    anthropic_api_key: str | None = None,
    anthropic_base_url: str | None = None,
    openai_api_key: str | None = None,
    connector: tuple[str, ...] = (),
    demo_data: bool = False,
    neo4j_uri: str | None = None,
    neo4j_username: str | None = None,
    neo4j_password: str | None = None,
    neo4j_local: bool = False,
    neo4j_aura_env: str | None = None,
) -> ProjectConfig:
    """Run the interactive wizard and return a ProjectConfig."""
    _banner()

    # Step 1: Project name
    if project_name:
        # Use provided project name
        pass
    else:
        project_name = questionary.text(
            "What is your project name?",
            default="my-context-graph",
        ).ask()
        if not project_name:
            raise SystemExit("Aborted.")

    # Step 2: Data source
    if demo_data or connector:
        # Use provided data source
        data_source = "saas" if connector else ("demo" if demo_data else "none")
    else:
        data_source = questionary.select(
            "How would you like to populate your context graph?",
            choices=[
                questionary.Choice("Generate demo data (synthetic documents & entities)", value="demo"),
                questionary.Choice("Connect to SaaS services (Gmail, Slack, Jira, etc.)", value="saas"),
            ],
        ).ask()
        if not data_source:
            raise SystemExit("Aborted.")

    # Step 2b: SaaS connector selection (if SaaS data source)
    selected_connectors: list[str] = []
    saas_credentials: dict[str, dict[str, str]] = {}
    if data_source == "saas":
        if connector:
            # Use provided connectors
            selected_connectors = list(connector)
        else:
            from create_context_graph.connectors import list_connectors, get_connector
            from create_context_graph.connectors.oauth import check_gws_cli, install_gws_cli

            available = list_connectors()
            connector_choices = [
                questionary.Choice(f"{c['name']} — {c['description']}", value=c["id"])
                for c in available
            ]

            selected_connectors = questionary.checkbox(
                "Select services to connect:",
                choices=connector_choices,
            ).ask()
            if not selected_connectors:
                raise SystemExit("Aborted. Select at least one connector.")

        # Check for Google Workspace CLI for Gmail/GCal
        google_connectors = {"gmail", "gcal"}
        if google_connectors & set(selected_connectors):
            if not check_gws_cli():
                console.print("[yellow]Google Workspace CLI (gws) not found.[/yellow]")
                install = questionary.confirm(
                    "Install it via npm? (recommended for Gmail/Calendar)", default=True
                ).ask()
                if install:
                    with console.status("[bold cyan]Installing @googleworkspace/cli..."):
                        if install_gws_cli():
                            console.print("[green]Google Workspace CLI installed successfully.[/green]")
                        else:
                            console.print("[yellow]Installation failed. Will use Python OAuth2 fallback.[/yellow]")

        # Collect credentials for each connector
        for conn_id in selected_connectors:
            connector = get_connector(conn_id)
            prompts = connector.get_credential_prompts()
            if not prompts:
                continue  # e.g. gws handles auth itself

            console.print(f"\n[bold]{connector.service_name} credentials:[/bold]")
            creds: dict[str, str] = {}
            for p in prompts:
                if p.get("secret"):
                    value = questionary.password(p["prompt"]).ask()
                else:
                    value = questionary.text(p["prompt"]).ask()
                if value is None:
                    raise SystemExit("Aborted.")
                if not value and not p.get("optional"):
                    raise SystemExit("Aborted.")
                if value:
                    creds[p["name"]] = value
            saas_credentials[conn_id] = creds

    # Step 3: Domain selection
    if domain:
        # Use provided domain
        pass
    else:
        domains = list_available_domains()
        domain_choices = [
            questionary.Choice(d["name"], value=d["id"]) for d in domains
        ]
        domain_choices.append(questionary.Choice("Custom (describe your domain)", value="custom"))

        domain = questionary.select(
            "Select your industry domain:",
            choices=domain_choices,
        ).ask()
        if not domain:
            raise SystemExit("Aborted.")

    custom_domain_yaml = None
    custom_ontology = None
    if domain == "custom":
        # Collect domain description
        domain_description = questionary.text(
            "Describe your domain (industry, key concepts, what the agent should help with):",
        ).ask()
        if not domain_description:
            raise SystemExit("Aborted.")

        # Need an API key for LLM generation
        if anthropic_api_key:
            # Use provided API key
            custom_api_key = anthropic_api_key
        else:
            custom_api_key = questionary.password(
                "Anthropic API key (required for custom domain generation):",
            ).ask()
            if not custom_api_key:
                console.print("[red]An API key is required for custom domain generation.[/red]")
                raise SystemExit("API key required.")

        # Ask for custom base URL
        if anthropic_base_url:
            # Use provided base URL
            custom_base_url = anthropic_base_url
        else:
            custom_base_url = questionary.text(
                "Anthropic-compatible API base URL (Enter to use default):",
                default="",
            ).ask()

        # Generate the domain
        from create_context_graph.custom_domain import (
            display_ontology_summary,
            generate_custom_domain,
            save_custom_domain,
        )

        while True:
            with console.status("[bold cyan]Generating custom domain ontology..."):
                try:
                    custom_ontology, custom_domain_yaml = generate_custom_domain(
                        domain_description, custom_api_key, base_url=custom_base_url
                    )
                except ValueError as e:
                    console.print(f"[red]Generation failed: {e}[/red]")
                    raise SystemExit("Custom domain generation failed.")

            display_ontology_summary(custom_ontology, console)

            action = questionary.select(
                "How would you like to proceed?",
                choices=[
                    questionary.Choice("Accept this ontology", value="accept"),
                    questionary.Choice("Regenerate with same description", value="regenerate"),
                    questionary.Choice("Edit description and regenerate", value="edit"),
                    questionary.Choice("Cancel", value="cancel"),
                ],
            ).ask()

            if action == "accept":
                break
            elif action == "regenerate":
                continue
            elif action == "edit":
                domain_description = questionary.text(
                    "Updated domain description:",
                    default=domain_description,
                ).ask()
                if not domain_description:
                    raise SystemExit("Aborted.")
                continue
            else:
                raise SystemExit("Aborted.")

        domain = custom_ontology.domain.id

        # Offer to save for future use
        save = questionary.confirm("Save this domain for future use?", default=True).ask()
        if save:
            save_custom_domain(custom_ontology, custom_domain_yaml)

        # Store the API key and base URL for later use
        anthropic_api_key = custom_api_key
        anthropic_base_url = custom_base_url

    # Step 4: Agent framework
    if framework:
        # Use provided framework
        pass
    else:
        framework_choices = [
            questionary.Choice(FRAMEWORK_DISPLAY_NAMES[fw], value=fw)
            for fw in SUPPORTED_FRAMEWORKS
        ]
        framework = questionary.select(
            "Select your agent framework:",
            choices=framework_choices,
        ).ask()
        if not framework:
            raise SystemExit("Aborted.")

    # Step 5: Neo4j connection
    if neo4j_aura_env:
        neo4j_type = "aura"
    elif neo4j_local:
        neo4j_type = "local"
    elif neo4j_uri and "aura" in (neo4j_uri or ""):
        neo4j_type = "aura"
    elif neo4j_uri:
        neo4j_type = "existing"
    else:
        neo4j_type = questionary.select(
            "How would you like to connect to Neo4j?",
            choices=[
                questionary.Choice("Neo4j Aura (cloud — free tier available)", value="aura"),
                questionary.Choice("Local Neo4j via neo4j-local (no Docker required)", value="local"),
                questionary.Choice("Local Neo4j via Docker", value="docker"),
                questionary.Choice("Existing Neo4j instance", value="existing"),
            ],
        ).ask()
        if not neo4j_type:
            raise SystemExit("Aborted.")

    if neo4j_type == "aura":
        if neo4j_aura_env:
            # Use provided Aura env file
            neo4j_uri, neo4j_username, neo4j_password = _parse_aura_env(neo4j_aura_env)
        else:
            console.print(Panel(
                "[bold]Neo4j Aura — Free Cloud Database[/bold]\n\n"
                "1. Sign up at [cyan]https://console.neo4j.io[/cyan]\n"
                "2. Create a free AuraDB instance\n"
                "3. Download the [bold].env[/bold] file with your credentials\n"
                "4. Provide the path to the downloaded file below",
                border_style="cyan",
                title="Setup",
            ))
            aura_env_path = questionary.path(
                "Path to Neo4j Aura .env file:",
            ).ask()
            if not aura_env_path:
                raise SystemExit("Aborted.")
            neo4j_uri, neo4j_username, neo4j_password = _parse_aura_env(aura_env_path)
    elif neo4j_type == "local":
        neo4j_uri = neo4j_uri or "neo4j://localhost:7687"
        neo4j_username = neo4j_username or "neo4j"
        neo4j_password = neo4j_password or "password"
        console.print(
            "[dim]Will use [bold]@johnymontana/neo4j-local[/bold] — "
            "run [bold]make neo4j-start[/bold] to launch Neo4j (requires Node.js)[/dim]"
        )
    elif neo4j_type == "docker":
        neo4j_uri = neo4j_uri or "neo4j://localhost:7687"
        neo4j_username = neo4j_username or "neo4j"
        neo4j_password = neo4j_password or "password"
    else:  # existing
        if neo4j_uri and neo4j_username and neo4j_password:
            # Use provided values
            pass
        else:
            neo4j_uri = questionary.text(
                "Neo4j URI:",
                default=neo4j_uri or "neo4j+s://xxxx.databases.neo4j.io",
            ).ask()
            neo4j_username = questionary.text(
                "Neo4j Username:",
                default=neo4j_username or "neo4j",
            ).ask()
            neo4j_password = questionary.password("Neo4j Password:").ask()

    if not neo4j_uri:
        raise SystemExit("Aborted.")

    # Step 5b: Memory enhancement options
    enhance_memory = questionary.confirm(
        "Enable memory enhancements? (entity extraction + preference detection from conversations)",
        default=True,
    ).ask()
    if enhance_memory is None:
        raise SystemExit("Aborted.")

    auto_extract = enhance_memory
    auto_preferences = enhance_memory

    if enhance_memory:
        session_strategy = questionary.select(
            "Session strategy for conversation memory:",
            choices=[
                questionary.Choice("Per conversation (default — each session is separate)", value="per_conversation"),
                questionary.Choice("Per day (sessions reset daily)", value="per_day"),
                questionary.Choice("Persistent (single continuous session)", value="persistent"),
            ],
        ).ask()
        if not session_strategy:
            raise SystemExit("Aborted.")
    else:
        session_strategy = "per_conversation"

    with_mcp = questionary.confirm(
        "Generate MCP server config for Claude Desktop integration?",
        default=False,
    ).ask()
    if with_mcp is None:
        raise SystemExit("Aborted.")

    mcp_profile = "extended"
    if with_mcp:
        mcp_profile = questionary.select(
            "MCP tool profile:",
            choices=[
                questionary.Choice("Extended (16 tools — full memory access)", value="extended"),
                questionary.Choice("Core (6 tools — basic memory)", value="core"),
            ],
        ).ask() or "extended"

    # Step 6: API Keys (skip Anthropic if already collected for custom domain)
    if custom_domain_yaml is None:
        if anthropic_api_key:
            # Use provided API key
            pass
        else:
            anthropic_api_key = questionary.password(
                "Anthropic API key (for AI agent):",
                default="",
            ).ask()
    # anthropic_api_key already set from custom domain flow otherwise

    if openai_api_key:
        # Use provided OpenAI API key
        pass
    else:
        openai_api_key = questionary.password(
            "OpenAI API key (for embeddings, or Enter to skip):",
            default="",
        ).ask()

    if anthropic_base_url:
        # Use provided base URL
        pass
    else:
        anthropic_base_url = questionary.text(
            "Anthropic-compatible API base URL (Enter to use default):",
            default="",
        ).ask()

    if framework == "openai-agents":
        openai_api_key = questionary.password(
            "OpenAI API key (required for OpenAI Agents SDK):",
            default="",
        ).ask()
        if not openai_api_key:
            console.print("[yellow]Warning:[/yellow] OpenAI Agents SDK requires OPENAI_API_KEY. Set it in your .env file.")
    else:
        openai_api_key = questionary.password(
            "OpenAI API key (optional — for OpenAI embeddings, or Enter to skip):",
            default="",
        ).ask()

    google_api_key = None
    if framework == "google-adk":
        google_api_key = questionary.password(
            "Google/Gemini API key (required for Google ADK framework):",
            default="",
        ).ask()
        if not google_api_key:
            console.print("[yellow]Warning:[/yellow] Google ADK requires a Google API key. Set GOOGLE_API_KEY in your .env file.")

    # Step 7: Confirmation
    config = ProjectConfig(
        project_name=project_name,
        domain=domain,
        framework=framework,
        data_source=data_source,
        neo4j_uri=neo4j_uri,
        neo4j_username=neo4j_username,
        neo4j_password=neo4j_password or "password",
        neo4j_type=neo4j_type,
        anthropic_api_key=anthropic_api_key or None,
        anthropic_base_url=anthropic_base_url or None,
        openai_api_key=openai_api_key or None,
        google_api_key=google_api_key or None,
        generate_data=data_source == "demo",
        custom_domain_yaml=custom_domain_yaml,
        saas_connectors=selected_connectors,
        saas_credentials=saas_credentials,
        with_mcp=with_mcp,
        mcp_profile=mcp_profile,
        session_strategy=session_strategy,
        auto_extract=auto_extract,
        auto_preferences=auto_preferences,
    )

    _show_summary(config)

    confirm = questionary.confirm("Proceed with these settings?", default=True).ask()
    if not confirm:
        raise SystemExit("Aborted.")

    return config


def _show_summary(config: ProjectConfig) -> None:
    """Display a summary table of the configuration."""
    table = Table(title="Project Configuration", show_header=False)
    table.add_column("Setting", style="bold")
    table.add_column("Value")

    table.add_row("Project", config.project_name)
    table.add_row("Domain", config.domain)
    table.add_row("Framework", config.framework_display_name)
    table.add_row("Data Source", config.data_source)
    if config.saas_connectors:
        table.add_row("Connectors", ", ".join(config.saas_connectors))
    table.add_row("Neo4j", f"{config.neo4j_type} ({config.neo4j_uri})")
    table.add_row("Session Strategy", config.session_strategy)
    table.add_row("Entity Extraction", "enabled" if config.auto_extract else "disabled")
    table.add_row("Preference Detection", "enabled" if config.auto_preferences else "disabled")
    if config.with_mcp:
        table.add_row("MCP Server", f"enabled (profile: {config.mcp_profile})")
    table.add_row("Anthropic Key", "***" if config.anthropic_api_key else "(not set)")
    table.add_row("Anthropic Base URL", config.anthropic_base_url or "(default)")
    table.add_row("OpenAI Key", "***" if config.openai_api_key else "(not set)")
    if config.google_api_key or config.resolved_framework == "google-adk":
        table.add_row("Google Key", "***" if config.google_api_key else "(not set)")

    console.print()
    console.print(table)
    console.print()
