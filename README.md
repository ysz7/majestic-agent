# Majestic

Universal AI agent framework. Low-resource, self-contained, multi-agent.

```
pip install -e .
majestic setup
majestic
```

---

## What it does

- Runs AI agents in **foreground** (interactive CLI) or **background** (HTTP server)
- Multiple isolated **profiles** — each with its own persona, models, keys, memory
- **Multi-agent**: background agents accept tasks from other agents via HTTP
- Searches the web, fetches pages, writes and runs Python/Node scripts
- Parses PDF, DOCX, CSV, TXT, MD → indexes to memory → answers from content
- Learns from every task (reflection + lessons learned)
- Costs controlled: token/USD budget per task, warn at 80%, stop at 100%
- ~100–150 MB RAM per agent in Docker

---

## Install

**Linux / Mac**
```bash
curl -fsSL https://raw.githubusercontent.com/ysz7/majestic-agent/main/scripts/install.sh | bash
```

**Windows**
```powershell
irm https://raw.githubusercontent.com/ysz7/majestic-agent/main/scripts/install.ps1 | iex
```

**Docker**
```bash
curl -fsSL https://raw.githubusercontent.com/ysz7/majestic-agent/main/scripts/install_docker.sh | bash
```

**From source**
```bash
git clone https://github.com/ysz7/majestic-agent
cd majestic-agent
pip install -e .
```

---

## Setup

```
majestic setup
```

Asks for:
- OpenRouter key (primary LLM provider)
- Anthropic / OpenAI keys (optional fallbacks)
- Brave Search API key (optional, uses DuckDuckGo if missing)
- Agent name, language, models per step type, optional budget limits

Creates `profiles/default/` with `.env` and `persona.yaml`.

---

## CLI commands

```
majestic setup          interactive first-time setup wizard
majestic new <name>     create new profile
majestic list           list available profiles
majestic rm <name>      delete profile (confirmation required)
majestic <profile>      run in foreground (interactive CLI)
majestic run <profile>  run in background (HTTP server)
majestic ps             list running background agents
majestic stop <profile> stop a background agent
majestic                run default profile in foreground
```

---

## Profiles

Each profile is a fully isolated agent:

```
profiles/
└── my_agent/
    ├── .env            OPENROUTER_API_KEY, AGENT_PORT, ...
    ├── persona.yaml    name, role, tone, model routing, limits
    ├── skills/         YAML skill files (hot-reloaded)
    ├── workspace/      files, scripts, .venv, node_modules
    └── data/           all SQLite databases
```

Create a new profile:
```
majestic new sales_agent
```

---

## Persona

`profiles/my_agent/persona.yaml`:

```yaml
name: "Alex"
role: "Sales Manager"
tone: "friendly, persuasive"
language: "en"
restrictions:
  - "do not discuss competitors"
context: |
  You work at Company X. You sell a SaaS platform for HR departments.

model_routing:
  reason:     "anthropic/claude-sonnet-4-5"
  simple:     "meta-llama/llama-3.1-8b-instruct:free"
  code:       "qwen/qwen-2.5-coder-32b-instruct"
  reflection: "meta-llama/llama-3.1-8b-instruct:free"

limits:
  max_tokens_per_task: 50000   # 0 = unlimited
  max_cost_per_task: 0.10      # 0 = unlimited
```

---

## LLM providers

Primary: **OpenRouter** (access to 100+ models via one key)
Fallback 1: **Anthropic**
Fallback 2: **OpenAI**

Per-step model routing:
```
REASON step     → reason model   (smart, complex)
SIMPLE actions  → simple model   (fast, cheap/free)
CODE generation → code model     (specialized)
REFLECTION      → simple model   (always cheapest)
```

---

## Tools

Built into every agent:

```
web_search      Brave Search API → DuckDuckGo fallback
web_fetch       fetch URL → clean readable text (trafilatura)
http            GET / POST requests to any API
files           read / write / list workspace files
python_exec     write + run .py scripts in .venv (timeout 30s)
node_exec       write + run .js scripts in node_modules (timeout 30s)
file_parser     PDF / DOCX / CSV / TXT / MD → text → memory index
agent_client    delegate tasks to running background agents
```

Web search + fetch workflow:
```
1. web_search("query") → [{title, url, snippet}]
2. web_fetch(url)      → clean page content
3. synthesize answer   → return with source URLs
```

Add a new simple tool: one file in `majestic/tools/`.
Add a new complex tool: one folder in `majestic/tools/`.

---

## Memory

Six types, all SQLite:

```
Working         current session (in-memory)
Episodic        task history + reflections (FTS5)
Semantic        knowledge base + indexed files (sqlite-vec / FTS5)
Procedural      YAML skills per profile (hot-reload)
Lessons Learned principles from experience (FTS5)
User Profile    preferences and patterns
```

Attach a file in chat → auto-detected → parsed → indexed to semantic memory → agent answers from it.

---

## Skills

Add a YAML file to `profiles/<name>/skills/` — picked up on next task, no restart needed:

```yaml
name: "research"
description: "Research a topic using web search and synthesis"
triggers: ["research", "find information", "look up"]
steps:
  - "Search the web for the topic"
  - "Fetch top 2-3 results for details"
  - "Synthesize findings into a clear summary"
  - "Include source URLs"
```

---

## Multi-agent

Run agents in background, let them delegate to each other:

```bash
majestic run default        # port 8000
majestic run sales_agent    # port 8001
majestic ps                 # see both running
```

Any agent can call `agent_client` tool to delegate to another running agent.
Registry is in `data/registry.json`.

Agent HTTP API (background mode):
```
POST /task      receive a delegated task
GET  /status    health check
POST /message   future channels (Telegram, webhook)
```

---

## Docker

```bash
docker compose up -d
docker exec -it majestic majestic setup
docker exec -it majestic majestic
```

Single container, ~100–150 MB RAM per agent.
Volumes: `./profiles`, `./data`.

---

## MCP

Add an MCP server in `majestic/mcp/registry.yaml` — auto-installed and available as tools:

```yaml
servers:
  git:
    runtime: python
    package: "mcp-server-git"
    description: "git repository operations"
```

---

## Architecture

```
Layer 7  CLI                 setup · new · list · rm · run · ps · stop
Layer 6  Channels            CLI (foreground) · HTTP Server (background)
Layer 5  Gateway             normalize · session · persona · file detection
Layer 4  Planner             classify · decompose · cron · HITL · delegation
Layer 3  Agent Runtime       ReAct loop · tools · budget · compaction · retry
Layer 2  Tools + MCP         http · files · web_search · web_fetch · exec · MCP
Layer 1  Memory + LLM        6 memory types · LLM Router (3 providers)
```
