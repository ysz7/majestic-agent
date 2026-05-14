# Majestic

<p align="center">
  <a href="https://github.com/ysz7/majestic-agent/blob/main/LICENSE"><img src="https://img.shields.io/badge/License-MIT-green?style=for-the-badge" alt="License: MIT"></a>
  <a href="https://github.com/ysz7/majestic-agent"><img src="https://img.shields.io/badge/Python-3.11+-blue?style=for-the-badge&logo=python&logoColor=white" alt="Python 3.11+"></a>
  <a href="https://github.com/ysz7/majestic-agent"><img src="https://img.shields.io/badge/Providers-Anthropic%20%7C%20OpenAI%20%7C%20OpenRouter%20%7C%20Ollama-blueviolet?style=for-the-badge" alt="Providers"></a>
</p>

**Universal AI agent framework. Low-resource, self-contained, multi-agent.** Run fully isolated agents from the terminal — plain CLI or split-screen TUI — or as background HTTP daemons that delegate tasks to each other. One model, one command, zero boilerplate.

<table>
<tr><td><b>Foreground + background modes</b></td><td>Plain CLI, split-screen TUI (<code>--tui</code>), or background HTTP daemon. Same agent, same memory, different channel.</td></tr>
<tr><td><b>Profile system</b></td><td>Each agent is a fully isolated profile — its own persona, model, keys, memory, skills, and workspace. Unlimited agents, each on its own port.</td></tr>
<tr><td><b>Multi-agent</b></td><td>Background agents register in a shared registry. Any agent can delegate tasks to any other via HTTP using the <code>agent_client</code> tool.</td></tr>
<tr><td><b>8 built-in tools</b></td><td>web_search (Brave → DDG fallback), web_fetch, http, files, python_exec, node_exec, file_parser, agent_client. Add tools with one file in <code>tools/</code>.</td></tr>
<tr><td><b>Self-improving</b></td><td>After complex tasks the agent writes YAML skill files from experience. Skills are hot-reloaded — no restart needed. Gets smarter over time, zero effort.</td></tr>
<tr><td><b>6 memory types</b></td><td>Working, Episodic, Semantic (sqlite-vec), Procedural (skills), Lessons Learned, User Profile — all SQLite, all local.</td></tr>
<tr><td><b>Cost control</b></td><td>Token and USD budgets per task. Warns at 80%, stops at 100%. Budget bar visible in the TUI.</td></tr>
<tr><td><b>~100–150 MB RAM per agent</b></td><td>Runs comfortably in Docker, a VPS, or a Raspberry Pi.</td></tr>
</table>

---

## Install

**Linux / macOS**
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

## Quick Start

```bash
majestic setup     # first-time wizard — provider, API key, model, agent name
majestic           # start the default agent (plain CLI)
majestic --tui     # start with split-screen TUI
```

The setup wizard asks for your LLM provider, API key, model (fetched live for OpenRouter; curated list for others), Brave Search key (optional), and agent name. Creates `profiles/default/` and writes keys to root `.env`.

---

## CLI Reference

| Command | Description |
|---------|-------------|
| `majestic setup` | Interactive first-time setup wizard |
| `majestic` | Run default profile — plain CLI |
| `majestic --tui` | Run default profile — split-screen TUI |
| `majestic <name>` | Run named profile — plain CLI |
| `majestic <name> --tui` | Run named profile — split-screen TUI |
| `majestic new <name>` | Create a new profile |
| `majestic list` | List all profiles |
| `majestic config [name]` | Edit agent configuration interactively |
| `majestic rm <name>` | Delete a profile (confirmation required) |
| `majestic run <name>` | Run as background HTTP daemon |
| `majestic ps` | List running background agents |
| `majestic stop <name>` | Stop a background agent |

**Slash commands** (available in both plain CLI and TUI):

| Command | Description |
|---------|-------------|
| `/help` | Show available commands |
| `/skills` | List loaded skills |
| `/agents` | Show running background agents |
| `/memory` | Memory stats |
| `/budget` | Token / cost usage |
| `/new` | Clear chat and reset session |
| `/quit` | Exit |

---

## Profiles

Each profile is a fully isolated agent:

```
profiles/
└── my_agent/
    ├── persona.yaml    name, role, tone, model, limits, port
    ├── .env            API keys for this agent
    ├── skills/         YAML skill files (hot-reloaded)
    ├── workspace/      files, scripts, .venv, node_modules
    └── data/           all SQLite databases
```

```bash
majestic new sales_agent
majestic config sales_agent
```

`profiles/my_agent/persona.yaml`:

```yaml
name: "Alex"
role: "Sales Manager"
tone: "friendly, persuasive"
language: "en"
port: 8001
restrictions:
  - "do not discuss competitors"
context: |
  You work at Company X. You sell a SaaS platform for HR departments.
limits:
  max_tokens_per_task: 50000   # 0 = unlimited
  max_cost_per_task: 0.10      # 0 = unlimited
```

---

## LLM Providers

One model is used for all tasks — set during `majestic setup` or via `.env`:

```bash
MAJESTIC_MODEL_REASON=anthropic/claude-sonnet-4-6
```

| Provider | Env var | Notes |
|----------|---------|-------|
| OpenRouter | `OPENROUTER_API_KEY` | 200+ models via one key — recommended |
| Anthropic | `ANTHROPIC_API_KEY` | Claude family |
| OpenAI | `OPENAI_API_KEY` | GPT family |
| Ollama | `OLLAMA_BASE_URL` | Local, no key needed |

---

## Tools

| Tool | Description |
|------|-------------|
| `web_search` | Brave Search API → DuckDuckGo fallback |
| `web_fetch` | Fetch URL → clean readable text |
| `http` | GET / POST to any REST API |
| `files` | Read / write / list workspace files |
| `python_exec` | Write + run `.py` scripts in isolated `.venv` |
| `node_exec` | Write + run `.js` scripts in isolated `node_modules` |
| `file_parser` | PDF / DOCX / CSV / TXT / MD → text → memory index |
| `agent_client` | Delegate tasks to running background agents |

Add a new tool: drop one `.py` file in `majestic/tools/` — auto-registered.

---

## Memory

Six types, all SQLite, all local:

| Type | Purpose |
|------|---------|
| Working | Current session (in-memory) |
| Episodic | Task history + reflections (FTS5) |
| Semantic | Knowledge base + indexed files (sqlite-vec / FTS5) |
| Procedural | YAML skills per profile (hot-reload) |
| Lessons Learned | Principles extracted from experience (FTS5) |
| User Profile | Preferences and interaction patterns |

Attach a file in chat → auto-detected → parsed → indexed to semantic memory → agent answers from it.

---

## Skills

Add a YAML file to `profiles/<name>/skills/` — picked up on next task, no restart:

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

```bash
majestic run default       # port 8000
majestic run sales_agent   # port 8001
majestic ps                # see both running
```

Any agent can delegate to another via `agent_client`. Registry lives in `data/registry.json`.

**Background agent HTTP API:**

| Endpoint | Description |
|----------|-------------|
| `POST /task` | Submit a delegated task |
| `GET /status/{id}` | Check task status |
| `POST /message/{id}` | Send a message to a running task |

---

## Docker

```bash
docker compose up -d
docker exec -it majestic majestic setup
docker exec -it majestic majestic
```

Single container, ~100–150 MB RAM per agent. Volumes: `./profiles`, `./data`.

---

## Architecture

```
Layer 7  CLI          setup · new · list · config · rm · run · ps · stop
Layer 6  Channels     CLI (foreground) · HTTP Server (background)
Layer 5  Gateway      normalize · session · persona · file detection
Layer 4  Planner      classify · decompose · cron · HITL · delegation
Layer 3  Runtime      ReAct loop · tools · budget · compaction · retry
Layer 2  Tools + MCP  http · files · web_search · web_fetch · exec · MCP
Layer 1  Memory + LLM 6 memory types · LLM Router (4 providers)
```

---

## Contributing

```bash
git clone https://github.com/ysz7/majestic-agent
cd majestic-agent
pip install -e .
pip install pytest pytest-asyncio
pytest tests/
```

Issues and PRs welcome.

---

## License

MIT
