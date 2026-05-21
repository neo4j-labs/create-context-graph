---
sidebar_position: 5
title: Domain Catalog
---

# Domain Catalog

create-context-graph ships with **27 built-in domains**. Each domain includes a complete ontology with entity types, relationships, agent tools, demo scenarios, and pre-generated fixture data.

## All Domains

| Domain | Name | Focus | Entity Types | Agent Tools |
|--------|------|-------|-------------|-------------|
| `agent-memory` | 🧠 Agent Memory | AI agent conversation and memory management | 11 | 7 |
| `conservation` | 🌿 Conservation | Environmental conservation programs and endangered species | 11 | 8 |
| `cybersecurity` | 🛡️ Cybersecurity | Assets, vulnerabilities, alerts, incidents, threat actors, and controls | 12 | 7 |
| `data-journalism` | 📰 Data Journalism | Investigative reporting, sources, and story threads | 11 | 8 |
| `digital-twin` | 🏭 Digital Twin | IoT sensor networks and industrial simulation | 11 | 8 |
| `education` | 🎓 Education | Students, instructors, courses, enrollments, assessments, and outcomes | 12 | 7 |
| `financial-services` | 💰 Financial Services | Banking, accounts, transactions, and compliance | 10 | 7 |
| `gaming` | 🎮 Gaming | Game worlds, players, quests, and item economies | 11 | 9 |
| `genai-llm-ops` | 🤖 GenAI & LLM Ops | LLM deployment, prompts, evaluations, and model versioning | 11 | 8 |
| `gis-cartography` | 🗺 GIS & Cartography | Geospatial features, map layers, and spatial analysis | 11 | 8 |
| `golf-sports` | ⛳ Golf Sports | Golf courses, tournaments, player stats, and handicaps | 11 | 8 |
| `government` | 🏛️ Government | Agencies, programs, policies, regulations, services, and budgets | 13 | 7 |
| `healthcare` | 🏥 Healthcare | Patients, providers, diagnoses, and treatment plans | 12 | 6 |
| `hospitality` | 🏨 Hospitality | Hotel operations, guest management, and room inventory | 11 | 8 |
| `legal` | ⚖️ Legal | Cases, matters, contracts, filings, hearings, and counsel | 12 | 7 |
| `manufacturing` | 🏭 Manufacturing | Production lines, quality control, and supply chain | 11 | 7 |
| `oil-gas` | 🛢️ Oil & Gas | Wells, pipelines, production sites, and inspections | 10 | 6 |
| `options-intelligence` | 📈 Options Intelligence | Options markets, exposure levels, regimes, and dealer positioning | 13 | 8 |
| `personal-knowledge` | 📝 Personal Knowledge | Personal notes, contacts, projects, and learning | 10 | 8 |
| `product-management` | 📋 Product Management | Features, roadmaps, user feedback, and sprint planning | 12 | 7 |
| `real-estate` | 🏠 Real Estate | Properties, listings, agents, and transactions | 10 | 8 |
| `retail-ecommerce` | 🛒 Retail & E-Commerce | Products, orders, customers, and inventory | 11 | 6 |
| `scientific-research` | 🔬 Scientific Research | Papers, experiments, datasets, and citations | 11 | 6 |
| `software-engineering` | 💻 Software Engineering | Repositories, PRs, incidents, deployments, and services | 11 | 7 |
| `trip-planning` | 🌍 Trip Planning | Itinerary assembly, destinations, and travel logistics | 10 | 7 |
| `vacation-industry` | 🏖 Vacation Industry | Tour operators, packages, OTA supply chain, and bookings | 10 | 6 |
| `wildlife-management` | 🐻 Wildlife Management | Animal tracking, habitats, populations, and rangers | 11 | 6 |

## Domain Details

### 🧠 Agent Memory

**ID:** `agent-memory` | **Tagline:** AI-powered Agent Intelligence

**Entity types:** `Person`, `Organization`, `Location`, `Event`, `Object`, `Agent`, `Conversation`, `Entity`, `Memory`, `ToolCall`, `Session`

**Sample question:** "What does agent Alpha remember about the user's project preferences?"

```bash
uvx create-context-graph --domain agent-memory --framework pydanticai --demo
```

---

### 🌿 Conservation

**ID:** `conservation` | **Tagline:** AI-powered Conservation Intelligence

**Entity types:** `Person`, `Organization`, `Location`, `Event`, `Object`, `Site`, `Species`, `Program`, `Funding`, `Stakeholder`, `Monitoring`

**Sample question:** "Which programs are funded by stakeholders working on endangered species recovery?"

```bash
uvx create-context-graph --domain conservation --framework pydanticai --demo
```

---

### 🛡️ Cybersecurity

**ID:** `cybersecurity` | **Tagline:** AI-powered Security Intelligence

**Entity types:** `Person`, `Organization`, `Location`, `Event`, `Object`, `Asset`, `Vulnerability`, `Alert`, `Incident`, `ThreatActor`, `Control`, `User`

**Sample question:** "Which production assets are affected by critical CVEs used by active threat actors?"

```bash
uvx create-context-graph --domain cybersecurity --framework anthropic-tools --demo
```

---

### 📰 Data Journalism

**ID:** `data-journalism` | **Tagline:** AI-powered Investigative Intelligence

**Entity types:** `Person`, `Organization`, `Location`, `Event`, `Object`, `Source`, `Story`, `Dataset`, `Claim`, `Correction`, `Investigation`

**Sample question:** "Show me all active investigations and their current status"

```bash
uvx create-context-graph --domain data-journalism --framework pydanticai --demo
```

---

### 🏭 Digital Twin

**ID:** `digital-twin` | **Tagline:** AI-powered Digital Twin Intelligence

**Entity types:** `Person`, `Organization`, `Location`, `Event`, `Object`, `Asset`, `Sensor`, `Reading`, `Alert`, `MaintenanceRecord`, `System`

**Sample question:** "Show me all assets currently in degraded status"

```bash
uvx create-context-graph --domain digital-twin --framework pydanticai --demo
```

---

### 🎓 Education

**ID:** `education` | **Tagline:** AI-powered Learning Intelligence

**Entity types:** `Person`, `Organization`, `Location`, `Event`, `Object`, `Student`, `Instructor`, `Course`, `Term`, `Enrollment`, `Assessment`, `Submission`

**Sample question:** "Which students are at risk of failing this term?"

```bash
uvx create-context-graph --domain education --framework strands --demo
```

---

### 💰 Financial Services

**ID:** `financial-services` | **Tagline:** AI-powered Financial Intelligence

**Entity types:** `Person`, `Organization`, `Location`, `Event`, `Object`, `Account`, `Transaction`, `Decision`, `Policy`, `Security`

**Sample question:** "Show me a summary of all client accounts and their current balances"

```bash
uvx create-context-graph --domain financial-services --framework pydanticai --demo
```

---

### 🎮 Gaming

**ID:** `gaming` | **Tagline:** AI-powered Game Intelligence

**Entity types:** `Person`, `Organization`, `Location`, `Event`, `Object`, `Player`, `Character`, `Item`, `Quest`, `Guild`, `Achievement`

**Sample question:** "Show me the most active players in the NA region by play time"

```bash
uvx create-context-graph --domain gaming --framework pydanticai --demo
```

---

### 🤖 GenAI & LLM Ops

**ID:** `genai-llm-ops` | **Tagline:** AI-powered ML Operations Intelligence

**Entity types:** `Person`, `Organization`, `Location`, `Event`, `Object`, `Model`, `Experiment`, `Dataset`, `Prompt`, `Evaluation`, `Deployment`

**Sample question:** "Show me all models currently in production and their evaluation scores"

```bash
uvx create-context-graph --domain genai-llm-ops --framework pydanticai --demo
```

---

### 🗺 GIS & Cartography

**ID:** `gis-cartography` | **Tagline:** AI-powered Geospatial Intelligence

**Entity types:** `Person`, `Organization`, `Location`, `Event`, `Object`, `Feature`, `Layer`, `Survey`, `Coordinate`, `Boundary`, `MapProject`

**Sample question:** "Show me all surveys conducted in the Cedar Creek watershed"

```bash
uvx create-context-graph --domain gis-cartography --framework pydanticai --demo
```

---

### ⛳ Golf Sports

**ID:** `golf-sports` | **Tagline:** AI-powered Golf Intelligence

**Entity types:** `Person`, `Organization`, `Location`, `Event`, `Object`, `Course`, `Player`, `Round`, `Tournament`, `Handicap`, `Hole`

**Sample question:** "Show me all rounds played by Tiger Woods this season"

```bash
uvx create-context-graph --domain golf-sports --framework pydanticai --demo
```

---

### 🏛️ Government

**ID:** `government` | **Tagline:** AI-powered Public Sector Intelligence

**Entity types:** `Person`, `Organization`, `Location`, `Event`, `Object`, `Agency`, `Program`, `Policy`, `Regulation`, `Service`, `Citizen`, `Official`, `Budget`

**Sample question:** "Which programs are overspending against appropriated budget?"

```bash
uvx create-context-graph --domain government --framework claude-agent-sdk --demo
```

---

### 🏥 Healthcare

**ID:** `healthcare` | **Tagline:** AI-powered Clinical Intelligence

**Entity types:** `Person`, `Organization`, `Location`, `Event`, `Object`, `Patient`, `Provider`, `Diagnosis`, `Treatment`, `Encounter`, `Facility`, `Medication`

**Sample question:** "Show me all patients with a chronic diagnosis"

```bash
uvx create-context-graph --domain healthcare --framework pydanticai --demo
```

---

### 🏨 Hospitality

**ID:** `hospitality` | **Tagline:** AI-powered Hospitality Intelligence

**Entity types:** `Person`, `Organization`, `Location`, `Event`, `Object`, `Hotel`, `Room`, `Reservation`, `Guest`, `Service`, `Staff`

**Sample question:** "Show me all platinum guests arriving this week"

```bash
uvx create-context-graph --domain hospitality --framework pydanticai --demo
```

---

### ⚖️ Legal

**ID:** `legal` | **Tagline:** AI-powered Legal Intelligence

**Entity types:** `Person`, `Organization`, `Location`, `Event`, `Object`, `Case`, `Matter`, `Contract`, `Filing`, `Hearing`, `Counsel`, `Statute`

**Sample question:** "What past cases cite the same statute as our current trade-secret case?"

```bash
uvx create-context-graph --domain legal --framework pydanticai --demo
```

---

### 🏭 Manufacturing

**ID:** `manufacturing` | **Tagline:** AI-powered Manufacturing Intelligence

**Entity types:** `Person`, `Organization`, `Location`, `Event`, `Object`, `Machine`, `Part`, `WorkOrder`, `Supplier`, `QualityReport`, `ProductionLine`

**Sample question:** "Show me all active work orders sorted by priority"

```bash
uvx create-context-graph --domain manufacturing --framework pydanticai --demo
```

---

### 🛢️ Oil & Gas

**ID:** `oil-gas` | **Tagline:** AI-powered Energy Intelligence

**Entity types:** `Person`, `Organization`, `Location`, `Event`, `Object`, `Well`, `Reservoir`, `Equipment`, `Inspection`, `Permit`, `Formation`

**Sample question:** "Show me all producing wells sorted by daily production rate"

```bash
uvx create-context-graph --domain oil-gas --framework pydanticai --demo
```

---

### 📈 Options Intelligence

**ID:** `options-intelligence` | **Tagline:** AI-powered Options Market Intelligence

**Entity types:** `Person`, `Organization`, `Location`, `Event`, `Object`, `Underlying`, `OptionsContract`, `ExposureLevel`, `Regime`, `KeyLevel`, `Trade`, `MarketEvent`, `Strategy`

**Sample question:** "Which underlyings are currently in a gamma-positive regime with elevated dealer exposure?"

```bash
uvx create-context-graph --domain options-intelligence --framework pydanticai --demo
```

---

### 📝 Personal Knowledge

**ID:** `personal-knowledge` | **Tagline:** AI-powered Personal Knowledge Graph

**Entity types:** `Person`, `Organization`, `Location`, `Event`, `Object`, `Note`, `Contact`, `Project`, `Topic`, `Bookmark`, `JournalEntry`

**Sample question:** "What notes have I written about machine learning this month?"

```bash
uvx create-context-graph --domain personal-knowledge --framework pydanticai --demo
```

---

### 📋 Product Management

**ID:** `product-management` | **Tagline:** AI-powered Product Intelligence

**Entity types:** `Person`, `Organization`, `Location`, `Event`, `Object`, `Feature`, `Epic`, `UserPersona`, `Metric`, `Release`, `Feedback`, `Objective`

**Sample question:** "Show me all features planned for the Q2 release"

```bash
uvx create-context-graph --domain product-management --framework pydanticai --demo
```

---

### 🏠 Real Estate

**ID:** `real-estate` | **Tagline:** AI-powered Real Estate Intelligence

**Entity types:** `Person`, `Organization`, `Location`, `Event`, `Object`, `Property`, `Listing`, `Agent`, `Transaction`, `Inspection`, `Neighborhood`

**Sample question:** "Find all active listings in the Downtown neighborhood under $500,000"

```bash
uvx create-context-graph --domain real-estate --framework pydanticai --demo
```

---

### 🛒 Retail & E-Commerce

**ID:** `retail-ecommerce` | **Tagline:** AI-powered Retail Intelligence

**Entity types:** `Person`, `Organization`, `Location`, `Event`, `Object`, `Customer`, `Product`, `Order`, `Review`, `Campaign`, `Category`

**Sample question:** "Show me the top 10 VIP customers by lifetime value"

```bash
uvx create-context-graph --domain retail-ecommerce --framework pydanticai --demo
```

---

### 🔬 Scientific Research

**ID:** `scientific-research` | **Tagline:** AI-powered Research Intelligence

**Entity types:** `Person`, `Organization`, `Location`, `Event`, `Object`, `Researcher`, `Paper`, `Dataset`, `Experiment`, `Grant`, `Institution`

**Sample question:** "Find the most cited papers in computational biology from the last 3 years"

```bash
uvx create-context-graph --domain scientific-research --framework pydanticai --demo
```

---

### 💻 Software Engineering

**ID:** `software-engineering` | **Tagline:** AI-powered Software Intelligence

**Entity types:** `Person`, `Organization`, `Location`, `Event`, `Object`, `Repository`, `Issue`, `PullRequest`, `Deployment`, `Service`, `Incident`

**Sample question:** "Show me all open pull requests across our repositories"

```bash
uvx create-context-graph --domain software-engineering --framework pydanticai --demo
```

---

### 🌍 Trip Planning

**ID:** `trip-planning` | **Tagline:** AI-powered Travel Intelligence

**Entity types:** `Person`, `Organization`, `Location`, `Event`, `Object`, `Destination`, `Hotel`, `Activity`, `Restaurant`, `Itinerary`, `Review`

**Sample question:** "Help me plan a 7-day trip to Japan for two people in spring"

```bash
uvx create-context-graph --domain trip-planning --framework pydanticai --demo
```

---

### 🏖 Vacation Industry

**ID:** `vacation-industry` | **Tagline:** AI-powered Vacation Intelligence

**Entity types:** `Person`, `Organization`, `Location`, `Event`, `Object`, `Resort`, `Booking`, `Guest`, `Activity`, `Season`, `Package`

**Sample question:** "Show me all bookings for the upcoming holiday season"

```bash
uvx create-context-graph --domain vacation-industry --framework pydanticai --demo
```

---

### 🐻 Wildlife Management

**ID:** `wildlife-management` | **Tagline:** AI-powered Conservation Intelligence

**Entity types:** `Person`, `Organization`, `Location`, `Event`, `Object`, `Species`, `Individual`, `Sighting`, `Habitat`, `Camera`, `Threat`

**Sample question:** "Show me all recent sightings of endangered species in the Serengeti habitat"

```bash
uvx create-context-graph --domain wildlife-management --framework pydanticai --demo
```

---

