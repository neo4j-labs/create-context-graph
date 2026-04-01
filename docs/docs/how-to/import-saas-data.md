---
sidebar_position: 1
title: Import Data from SaaS Services
---

# Import Data from SaaS Services

Create Context Graph can pull data from SaaS services and map it into your Neo4j knowledge graph. This guide covers how to configure connectors during project scaffolding and how to re-import data afterward.

## Available Connectors

| Service | What It Imports | Auth Method |
|---------|----------------|-------------|
| **GitHub** | Repositories, issues, pull requests, commits, users, code reviews | Personal access token (PAT) |
| **Notion** | Pages, databases, blocks, users, comments | Internal integration token |
| **Jira** | Projects, issues, sprints, users, comments, worklogs | API token + Atlassian email |
| **Slack** | Channels, messages, threads, users, reactions | Bot token (OAuth) |
| **Gmail** | Emails, threads, contacts, labels, attachments (metadata) | Google OAuth 2.0 / service account |
| **Google Calendar** | Events, attendees, calendars, recurring series | Google OAuth 2.0 / service account |
| **Salesforce** | Accounts, contacts, opportunities, leads, cases, activities | OAuth 2.0 connected app |
| **Linear** | Issues, projects, cycles, teams, users, labels, workflow states | Personal API key |

## Selecting Connectors in the Interactive Wizard

When you run `create-context-graph my-app`, the wizard includes a step to connect SaaS services:

1. Select **"Connect to SaaS services"** when prompted for your data source.
2. Pick one or more connectors from the checklist.
3. Enter the required credentials for each selected connector (tokens, keys, etc.).
4. The scaffolded project will include connector configuration in `.env` and an import pipeline in `backend/scripts/`.

## Non-Interactive CLI Usage

Pass `--connector` flags to skip the wizard:

```bash
create-context-graph my-app \
  --domain software-development \
  --framework pydanticai \
  --connector github \
  --connector slack
```

You can combine `--connector` with any domain and framework flags. Each connector will prompt for its credentials unless they are already set as environment variables.

### Linear example

Import your Linear workspace data into a context graph:

```bash
create-context-graph my-project \
  --domain software-engineering \
  --framework pydanticai \
  --connector linear \
  --linear-api-key lin_api_xxxxx \
  --linear-team ENG
```

The `--linear-team` flag is optional. If omitted, all teams in the workspace are imported.

## Gmail and Google Calendar Setup

Gmail and Google Calendar connectors use the **Google Workspace CLI (gws)** for OAuth flows. When you select either connector, the wizard checks whether `gws` is installed:

- If found, it uses `gws` to handle the OAuth consent flow and token refresh.
- If not found, the wizard offers to install it automatically (`pip install gws`).
- You can skip the install and provide a service account JSON key file instead.

Both connectors share the same Google Cloud project credentials, so configuring one makes the other available with no extra setup.

## Re-Importing Data in a Generated Project

After scaffolding, the generated project includes Makefile targets for data import:

```bash
# Import data from all configured connectors
make import

# Import data and seed the graph with demo scenarios
make import-and-seed
```

These targets read credentials from the `.env` file in the project root.

## Connector Credential Setup

### GitHub

1. Go to **Settings > Developer settings > Personal access tokens > Tokens (classic)**.
2. Generate a token with `repo`, `read:org`, and `read:user` scopes.
3. Set `GITHUB_TOKEN` in `.env`.

### Notion

1. Go to [notion.so/my-integrations](https://www.notion.so/my-integrations) and create an internal integration.
2. Copy the **Internal Integration Secret**.
3. Share the target pages/databases with your integration.
4. Set `NOTION_TOKEN` in `.env`.

### Jira

1. Go to [id.atlassian.com/manage-profile/security/api-tokens](https://id.atlassian.com/manage-profile/security/api-tokens) and create an API token.
2. Set `JIRA_EMAIL`, `JIRA_API_TOKEN`, and `JIRA_BASE_URL` (e.g., `https://yourorg.atlassian.net`) in `.env`.

### Slack

1. Create a Slack app at [api.slack.com/apps](https://api.slack.com/apps).
2. Add bot token scopes: `channels:history`, `channels:read`, `users:read`, `reactions:read`.
3. Install the app to your workspace and copy the **Bot User OAuth Token**.
4. Set `SLACK_BOT_TOKEN` in `.env`.

### Gmail / Google Calendar

1. Create a project in [Google Cloud Console](https://console.cloud.google.com/).
2. Enable the Gmail API and/or Google Calendar API.
3. Create OAuth 2.0 credentials (Desktop app type) and download the JSON file.
4. Set `GOOGLE_CREDENTIALS_FILE` in `.env` pointing to the downloaded JSON.

### Salesforce

1. In Salesforce Setup, go to **App Manager** and create a new Connected App.
2. Enable OAuth and select scopes: `api`, `refresh_token`, `offline_access`.
3. Set `SALESFORCE_CLIENT_ID`, `SALESFORCE_CLIENT_SECRET`, `SALESFORCE_USERNAME`, `SALESFORCE_PASSWORD`, and `SALESFORCE_SECURITY_TOKEN` in `.env`.

### Linear

1. Open **Linear Settings > Security & Access > API** (or navigate to `linear.app/settings/api`).
2. Click **Create key** to generate a personal API key.
3. Set `LINEAR_API_KEY` in `.env`.
4. Optionally set `LINEAR_TEAM` to a team URL key (e.g., `ENG`) to limit the import to a single team.

The Linear connector imports issues, projects, cycles, teams, users, labels, and workflow states. Issue descriptions are also imported as documents for semantic search. No external Python package is required — the connector uses Python's built-in `urllib`.
