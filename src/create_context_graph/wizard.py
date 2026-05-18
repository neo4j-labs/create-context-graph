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

"""Interactive CLI wizard using Questionary and Rich.

Wizard shape (locked v0.11):
  1. Project name
  2. Industry domain (autocomplete; "Custom..." for LLM-generated)
  3. Agent framework (default: Strands)
  4. NAMS API key  (skipped if self_hosted=True; in that case asks Neo4j connection)
  5. Session strategy
  6. Data source (demo / SaaS) + per-connector creds
  7. Customize advanced settings? [y/N]
       -> MCP toggle (+ profile), auto_extract, auto_preferences (hidden on NAMS),
          Anthropic key, OpenAI key, Google key
  8. Confirm

The default scaffold = NAMS-backed memory + empty graph + Strands agent.
Self-hosted (`--self-hosted`) preserves the legacy bolt-Neo4j path.
"""

from __future__ import annotations

import questionary
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from create_context_graph.config import (
    DEFAULT_FRAMEWORK,
    DEFAULT_NAMS_ENDPOINT,
    FRAMEWORK_DISPLAY_NAMES,
    NAMS_SIGNUP_URL,
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


def _ask_or_abort(prompt_result, what: str = "input"):
    """Helper — ``None`` means the user hit ctrl-c on a questionary prompt."""
    if prompt_result is None:
        raise SystemExit("Aborted.")
    return prompt_result


def _prompt_project_name() -> str:
    return _ask_or_abort(
        questionary.text("Project name?", default="my-context-graph").ask(),
        "project name",
    )


def _prompt_domain() -> tuple[str, str | None, str | None]:
    """Returns (domain_id, custom_domain_yaml, anthropic_api_key_for_custom).

    The Anthropic key in the third slot is only set when a custom domain was
    generated — we keep it so the LLM-data-generation step can reuse the key.
    """
    domains = list_available_domains()
    choices = [d["name"] for d in domains] + ["Custom (describe your domain)"]
    label_to_id = {d["name"]: d["id"] for d in domains}
    label_to_id["Custom (describe your domain)"] = "__custom__"

    selection = _ask_or_abort(
        questionary.autocomplete(
            "Industry domain? (start typing to filter)",
            choices=choices,
            match_middle=True,
            ignore_case=True,
        ).ask(),
        "domain",
    )

    if selection not in label_to_id:
        console.print(
            f"[red]Error:[/red] '{selection}' is not a valid domain. "
            "Pick one from the list or 'Custom (describe your domain)'."
        )
        raise SystemExit(1)

    domain_id = label_to_id[selection]
    if domain_id != "__custom__":
        return domain_id, None, None

    return _run_custom_domain_flow()


def _run_custom_domain_flow() -> tuple[str, str, str]:
    """Generate a custom domain via LLM. Returns (domain_id, yaml, anthropic_key)."""
    description = _ask_or_abort(
        questionary.text(
            "Describe your domain (industry, key concepts, what the agent should help with):",
        ).ask(),
        "description",
    )

    api_key = _ask_or_abort(
        questionary.password(
            "Anthropic API key (required for custom domain generation):",
        ).ask(),
        "API key",
    )
    if not api_key:
        console.print("[red]An API key is required for custom domain generation.[/red]")
        raise SystemExit("API key required.")

    from create_context_graph.custom_domain import (
        display_ontology_summary,
        generate_custom_domain,
        save_custom_domain,
    )

    while True:
        with console.status("[bold cyan]Generating custom domain ontology..."):
            try:
                custom_ontology, custom_domain_yaml = generate_custom_domain(
                    description, api_key
                )
            except ValueError as e:
                console.print(f"[red]Generation failed: {e}[/red]")
                raise SystemExit("Custom domain generation failed.")

        display_ontology_summary(custom_ontology, console)

        action = _ask_or_abort(
            questionary.select(
                "How would you like to proceed?",
                choices=[
                    questionary.Choice("Accept this ontology", value="accept"),
                    questionary.Choice("Regenerate with same description", value="regenerate"),
                    questionary.Choice("Edit description and regenerate", value="edit"),
                    questionary.Choice("Cancel", value="cancel"),
                ],
            ).ask(),
            "action",
        )

        if action == "accept":
            break
        if action == "cancel":
            raise SystemExit("Aborted.")
        if action == "edit":
            description = _ask_or_abort(
                questionary.text("Updated domain description:", default=description).ask(),
                "description",
            )

    if questionary.confirm("Save this domain for future use?", default=True).ask():
        save_custom_domain(custom_ontology, custom_domain_yaml)

    return custom_ontology.domain.id, custom_domain_yaml, api_key


def _prompt_framework() -> str:
    # Build choices with DEFAULT_FRAMEWORK first so its row is highlighted on entry.
    # ``questionary.select`` highlights the first choice by default; passing a
    # ``default=`` argument requires it to match a choice's ``Choice.title`` (a
    # FormattedText / str) — not the internal ``value``. We rely on row order
    # rather than ``default=`` to avoid that fragile coupling.
    ordered = [DEFAULT_FRAMEWORK] + [
        fw for fw in SUPPORTED_FRAMEWORKS if fw != DEFAULT_FRAMEWORK
    ]
    choices = [
        questionary.Choice(FRAMEWORK_DISPLAY_NAMES[fw], value=fw) for fw in ordered
    ]
    return _ask_or_abort(
        questionary.select(
            "Agent framework?",
            choices=choices,
        ).ask(),
        "framework",
    )


def _prompt_nams_api_key() -> str:
    console.print(
        Panel(
            "[bold]Neo4j Agent Memory Service (NAMS)[/bold] is the default "
            "hosted memory backend. Your project will read and write memory "
            "through it.\n\n"
            f"1. Sign up at [cyan]{NAMS_SIGNUP_URL}[/cyan]\n"
            "2. Provision an API key from your dashboard\n"
            "3. Paste it below\n\n"
            "[dim]Prefer self-hosted Neo4j? Cancel and re-run with "
            "[bold]--self-hosted[/bold].[/dim]",
            border_style="cyan",
            title="Setup",
        )
    )
    key = _ask_or_abort(
        questionary.password("NAMS API key?").ask(),
        "NAMS API key",
    )
    if not key:
        console.print("[red]A NAMS API key is required. Re-run with --self-hosted to skip.[/red]")
        raise SystemExit(1)
    return key


def _prompt_self_hosted_neo4j() -> tuple[str, str, str, str]:
    """Returns (uri, username, password, neo4j_type) for the bolt path."""
    neo4j_type = _ask_or_abort(
        questionary.select(
            "How would you like to connect to Neo4j?",
            choices=[
                questionary.Choice("Neo4j Aura (cloud — free tier available)", value="aura"),
                questionary.Choice("Local Neo4j via neo4j-local (no Docker required)", value="local"),
                questionary.Choice("Local Neo4j via Docker", value="docker"),
                questionary.Choice("Existing Neo4j instance", value="existing"),
            ],
        ).ask(),
        "neo4j type",
    )

    if neo4j_type == "aura":
        console.print(
            Panel(
                "[bold]Neo4j Aura — Free Cloud Database[/bold]\n\n"
                "1. Sign up at [cyan]https://console.neo4j.io[/cyan]\n"
                "2. Create a free AuraDB instance\n"
                "3. Download the [bold].env[/bold] file with your credentials\n"
                "4. Provide the path to the downloaded file below",
                border_style="cyan",
                title="Setup",
            )
        )
        aura_env_path = _ask_or_abort(
            questionary.path("Path to Neo4j Aura .env file:").ask(),
            "Aura .env",
        )
        uri, username, password = _parse_aura_env(aura_env_path)
    elif neo4j_type == "local":
        uri, username, password = "neo4j://localhost:7687", "neo4j", "password"
        console.print(
            "[dim]Will use [bold]@johnymontana/neo4j-local[/bold] — "
            "run [bold]make neo4j-start[/bold] to launch Neo4j (requires Node.js)[/dim]"
        )
    elif neo4j_type == "docker":
        uri, username, password = "neo4j://localhost:7687", "neo4j", "password"
    else:
        uri = _ask_or_abort(
            questionary.text("Neo4j URI:", default="neo4j+s://xxxx.databases.neo4j.io").ask(),
            "neo4j uri",
        )
        username = _ask_or_abort(
            questionary.text("Neo4j Username:", default="neo4j").ask(),
            "neo4j username",
        )
        password = _ask_or_abort(questionary.password("Neo4j Password:").ask(), "neo4j password")

    return uri, username, password, neo4j_type


def _prompt_session_strategy() -> str:
    return _ask_or_abort(
        questionary.select(
            "Session strategy?",
            choices=[
                questionary.Choice("Per conversation (default — each session is separate)", value="per_conversation"),
                questionary.Choice("Per day (sessions reset daily)", value="per_day"),
                questionary.Choice("Persistent (single continuous session)", value="persistent"),
            ],
        ).ask(),
        "session strategy",
    )


def _prompt_data_source() -> tuple[str, list[str], dict[str, dict[str, str]]]:
    """Returns (data_source, connector_ids, credentials_by_connector)."""
    data_source = _ask_or_abort(
        questionary.select(
            "How would you like to populate your context graph?",
            choices=[
                questionary.Choice("Generate demo data (synthetic documents & entities)", value="demo"),
                questionary.Choice("Connect to SaaS services (Gmail, Slack, Jira, etc.)", value="saas"),
            ],
        ).ask(),
        "data source",
    )

    if data_source != "saas":
        return data_source, [], {}

    from create_context_graph.connectors import list_connectors, get_connector
    from create_context_graph.connectors.oauth import check_gws_cli, install_gws_cli

    available = list_connectors()
    connector_choices = [
        questionary.Choice(f"{c['name']} — {c['description']}", value=c["id"])
        for c in available
    ]

    selected = _ask_or_abort(
        questionary.checkbox("Select services to connect:", choices=connector_choices).ask(),
        "connectors",
    )
    if not selected:
        console.print("[red]Select at least one connector.[/red]")
        raise SystemExit(1)

    if {"gmail", "gcal"} & set(selected) and not check_gws_cli():
        console.print("[yellow]Google Workspace CLI (gws) not found.[/yellow]")
        if questionary.confirm(
            "Install it via npm? (recommended for Gmail/Calendar)", default=True
        ).ask():
            with console.status("[bold cyan]Installing @googleworkspace/cli..."):
                if install_gws_cli():
                    console.print("[green]Google Workspace CLI installed successfully.[/green]")
                else:
                    console.print("[yellow]Installation failed. Will use Python OAuth2 fallback.[/yellow]")

    credentials: dict[str, dict[str, str]] = {}
    for conn_id in selected:
        connector = get_connector(conn_id)
        prompts = connector.get_credential_prompts()
        if not prompts:
            continue

        console.print(f"\n[bold]{connector.service_name} credentials:[/bold]")
        creds: dict[str, str] = {}
        for p in prompts:
            value = (
                questionary.password(p["prompt"]).ask()
                if p.get("secret")
                else questionary.text(p["prompt"]).ask()
            )
            if value is None:
                raise SystemExit("Aborted.")
            if not value and not p.get("optional"):
                raise SystemExit("Aborted.")
            if value:
                creds[p["name"]] = value
        credentials[conn_id] = creds

    return data_source, selected, credentials


def _prompt_advanced(*, is_nams: bool, framework: str) -> dict:
    """Returns a dict of advanced settings to splat into ProjectConfig.

    Only collects settings the user actually has decisions about — MCP, the
    extraction toggles, and any extra API keys not collected elsewhere.
    """
    customize = _ask_or_abort(
        questionary.confirm("Customize advanced settings?", default=False).ask(),
        "customize advanced",
    )

    defaults = {
        "with_mcp": False,
        "mcp_profile": "core" if is_nams else "extended",
        "auto_extract": True,
        "auto_preferences": False if is_nams else True,
        "anthropic_api_key": None,
        "openai_api_key": None,
        "google_api_key": None,
    }

    if not customize:
        return defaults

    with_mcp = _ask_or_abort(
        questionary.confirm(
            "Generate MCP server config for Claude Desktop integration?",
            default=False,
        ).ask(),
        "mcp",
    )
    mcp_profile = "core" if is_nams else "extended"
    if with_mcp and not is_nams:
        mcp_profile = _ask_or_abort(
            questionary.select(
                "MCP tool profile?",
                choices=[
                    questionary.Choice("Extended (16 tools — full memory access)", value="extended"),
                    questionary.Choice("Core (6 tools — basic memory)", value="core"),
                ],
            ).ask(),
            "mcp profile",
        )

    auto_extract = _ask_or_abort(
        questionary.confirm("Auto-extract entities from messages?", default=True).ask(),
        "auto_extract",
    )

    if is_nams:
        # NAMS doesn't expose preference endpoints; suppress this prompt.
        auto_preferences = False
    else:
        auto_preferences = _ask_or_abort(
            questionary.confirm("Auto-detect user preferences from messages?", default=True).ask(),
            "auto_preferences",
        )

    anthropic_api_key = questionary.password(
        "Anthropic API key (recommended — required for most agent frameworks):",
        default="",
    ).ask()

    openai_api_key = None
    if framework == "openai-agents":
        openai_api_key = questionary.password(
            "OpenAI API key (required for OpenAI Agents SDK):",
            default="",
        ).ask()
    else:
        openai_api_key = questionary.password(
            "OpenAI API key (optional — for OpenAI embeddings):",
            default="",
        ).ask()

    google_api_key = None
    if framework == "google-adk":
        google_api_key = questionary.password(
            "Google/Gemini API key (required for Google ADK framework):",
            default="",
        ).ask()

    return {
        "with_mcp": bool(with_mcp),
        "mcp_profile": mcp_profile,
        "auto_extract": bool(auto_extract),
        "auto_preferences": bool(auto_preferences),
        "anthropic_api_key": anthropic_api_key or None,
        "openai_api_key": openai_api_key or None,
        "google_api_key": google_api_key or None,
    }


def run_wizard(*, self_hosted: bool = False) -> ProjectConfig:
    """Run the interactive wizard and return a ProjectConfig.

    Args:
        self_hosted: when True, skip the NAMS API-key prompt and ask for Neo4j
            connection details instead. Maps to ``memory_backend="bolt"``.
    """
    _banner()

    project_name = _prompt_project_name()
    domain_id, custom_domain_yaml, custom_anthropic_key = _prompt_domain()
    framework = _prompt_framework()

    nams_api_key: str | None = None
    neo4j_uri = "neo4j://localhost:7687"
    neo4j_username = "neo4j"
    neo4j_password = "password"
    neo4j_type = "docker"
    if self_hosted:
        neo4j_uri, neo4j_username, neo4j_password, neo4j_type = (
            _prompt_self_hosted_neo4j()
        )
    else:
        nams_api_key = _prompt_nams_api_key()

    session_strategy = _prompt_session_strategy()
    data_source, connectors, credentials = _prompt_data_source()

    is_nams = not self_hosted
    advanced = _prompt_advanced(is_nams=is_nams, framework=framework)

    config = ProjectConfig(
        project_name=project_name,
        domain=domain_id,
        framework=framework,
        data_source=data_source,
        memory_backend="nams" if is_nams else "bolt",
        nams_api_key=nams_api_key,
        nams_endpoint=DEFAULT_NAMS_ENDPOINT,
        neo4j_uri=neo4j_uri,
        neo4j_username=neo4j_username,
        neo4j_password=neo4j_password,
        neo4j_type=neo4j_type,
        anthropic_api_key=advanced["anthropic_api_key"] or custom_anthropic_key,
        openai_api_key=advanced["openai_api_key"],
        google_api_key=advanced["google_api_key"],
        generate_data=data_source == "demo",
        custom_domain_yaml=custom_domain_yaml,
        saas_connectors=connectors,
        saas_credentials=credentials,
        with_mcp=advanced["with_mcp"],
        mcp_profile=advanced["mcp_profile"],
        session_strategy=session_strategy,
        auto_extract=advanced["auto_extract"],
        auto_preferences=advanced["auto_preferences"],
    )

    _show_summary(config)
    if not questionary.confirm("Proceed with these settings?", default=True).ask():
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
    if config.is_nams:
        table.add_row("Memory", f"NAMS ({config.nams_endpoint})")
    else:
        table.add_row("Memory", f"Self-hosted Neo4j — {config.neo4j_type} ({config.neo4j_uri})")
    table.add_row("Data source", config.data_source)
    if config.saas_connectors:
        table.add_row("Connectors", ", ".join(config.saas_connectors))
    table.add_row("Session strategy", config.session_strategy)
    table.add_row("Entity extraction", "enabled" if config.auto_extract else "disabled")
    table.add_row(
        "Preference detection",
        "n/a on NAMS"
        if config.is_nams
        else ("enabled" if config.auto_preferences else "disabled"),
    )
    if config.with_mcp:
        table.add_row("MCP server", f"enabled (profile: {config.effective_mcp_profile})")
    table.add_row("NAMS key" if config.is_nams else "—", "***" if config.nams_api_key else "(not set)")
    table.add_row("Anthropic key", "***" if config.anthropic_api_key else "(not set — set in .env later)")
    table.add_row("OpenAI key", "***" if config.openai_api_key else "(not set)")
    if config.google_api_key or config.resolved_framework == "google-adk":
        table.add_row("Google key", "***" if config.google_api_key else "(not set)")

    console.print()
    console.print(table)
    console.print()
