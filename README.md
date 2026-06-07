<p align="center">
  <img src="docs/assets/majestic-cli-logo.png" alt="Majestic" width="85%">
</p>

<p align="center">
  <a href="https://github.com/ysz7/majestic-agent/blob/main/LICENSE"><img src="https://img.shields.io/badge/License-MIT-green?style=for-the-badge" alt="License: MIT"></a>
  <a href="https://github.com/ysz7/majestic-agent"><img src="https://img.shields.io/badge/Python-3.11+-blue?style=for-the-badge&logo=python&logoColor=white" alt="Python 3.11+"></a>
  <a href="https://github.com/ysz7/majestic-agent"><img src="https://img.shields.io/badge/Providers-Anthropic%20%7C%20OpenAI%20%7C%20OpenRouter%20%7C%20Ollama-blueviolet?style=for-the-badge" alt="Providers"></a>
</p>

# Majestic

**Deploy a fleet of AI agents. Each with its own role, memory, and skills — running independently or collaborating as a team.** Spin up agents from the terminal, run them as background daemons, and let them delegate tasks to each other. Every agent learns from experience and gets smarter over time.

<table>
<tr><td><b>Foreground + background modes</b></td><td>Interactive CLI or background HTTP daemon. Same agent, same memory, different channel.</td></tr>
<tr><td><b>Profile system</b></td><td>Each agent is a fully isolated profile — its own persona, model, keys, memory, skills, and workspace. Unlimited agents, each on its own port.</td></tr>
<tr><td><b>Multi-agent</b></td><td>Background agents register in a shared registry. Any agent can delegate tasks to any other via HTTP using the <code>agent_client</code> tool.</td></tr>
<tr><td><b>Built-in tools</b></td><td>web_search (Brave → DDG fallback), web_fetch, http, files, python_exec, node_exec, research, plus script reuse and multi-agent delegation. Add tools with one file in <code>tools/</code>.</td></tr>
<tr><td><b>Native tool use + MCP</b></td><td>Structured tool calling on capable models (Anthropic/OpenAI/paid OpenRouter), text-protocol fallback for the rest. Connect any MCP server over stdio — its tools join the loop as <code>mcp__server__tool</code>.</td></tr>
<tr><td><b>Hooks + permissions</b></td><td>Lifecycle hooks (pre/post tool use, stop) can block or modify any tool call. Per-tool allow/deny/ask rules and modes (default/auto/plan/bypass) in <code>persona.yaml</code>.</td></tr>
<tr><td><b>Self-improving</b></td><td>After complex tasks the agent writes YAML skill files from experience. Skills are hot-reloaded — no restart needed. Gets smarter over time, zero effort.</td></tr>
<tr><td><b>6 memory types</b></td><td>Working, Episodic, Semantic (sqlite-vec), Procedural (skills), Lessons Learned, User Profile — all SQLite, all local.</td></tr>
<tr><td><b>Cost control</b></td><td>Token and USD budgets per task. Warns at 80%, stops at 100%. Unset → safe default cap (500k tokens / $2); set <code>0</code> for explicit unlimited.</td></tr>
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
majestic           # start the default agent (interactive CLI)
```

The setup wizard asks for your LLM provider, API key, model (fetched live for OpenRouter; curated list for others), Brave Search key (optional), and agent name. Creates `profiles/default/` and writes keys to root `.env`.

---

## CLI Reference

| Command | Description |
|---------|-------------|
| `majestic setup` | Interactive first-time setup wizard |
| `majestic` | Run default profile — interactive CLI |
| `majestic <name>` | Run named profile — interactive CLI |
| `majestic new <name>` | Create a new profile |
| `majestic list` | List all profiles |
| `majestic config [name]` | Edit agent configuration interactively |
| `majestic model` | Change global LLM provider or model interactively |
| `majestic model <name>` | Override model for a specific profile (or clear override) |
| `majestic rm <name>` | Delete a profile (confirmation required) |
| `majestic run <name>` | Run as background HTTP daemon |
| `majestic ps` | List running background agents |
| `majestic stop <name>` | Stop a background agent |

**Slash commands** (available in the interactive CLI):

| Command | Description |
|---------|-------------|
| `/research [days]` | Fetch curated news → summary + live market snapshot |
| `/pains [days]` | Extract pain points (intensity, willingness-to-pay, domains) |
| `/ideas [days]` | Generate startup ideas from the accumulated pains corpus |
| `/products [days]` | TOP-10 sellable solo digital products + monetization audit |
| `/predict [days]` | Single-section, cross-sector forecasts grounded in real data |
| `/briefing [days]` | Daily intelligence briefing from the news corpus |
| `/news [days]` | Show stored news (no re-fetch) |
| `/ask <question>` | Answer against the research + pains corpus |
| `/goodmorning` | Full pipeline: research → pains → briefing → ideas → predict |
| `/skills` · `/tools` · `/agents` | List skills · tools · running agents |
| `/memory` · `/budget` | Memory stats · token & cost usage |
| `/help` · `/new` · `/quit` | Help · reset session · exit |

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
  # Unset → safe default cap (500k tokens / $2). 0 = explicit unlimited.
  max_tokens_per_task: 50000
  max_cost_per_task: 0.10
```

---

## LLM Providers

One model is used for all tasks — set during `majestic setup` or changed at any time with `majestic model`:

```bash
majestic model                # change global provider / model
majestic model sales_agent    # override model for one profile only
```

The wizard skips the API key prompt if you stay on the same provider. To revert a profile back to the global default, choose "Clear profile overrides".

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
| `research` | Query curated sources → ranked, summarized corpus |
| `list_scripts` / `run_script` | Reuse scripts promoted to `workspace/tools/` |
| `agent_client` | Delegate tasks to running background agents |

File attachments are auto-parsed (PDF / DOCX / CSV / TXT / MD → text → semantic memory) by the gateway — no explicit tool call needed.

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

Any agent can delegate to another via `agent_client`. If the target agent is not running, it is **started automatically** — no manual `majestic run` required. Registry lives in `data/registry.json`.

The default agent has two built-in tools for orchestration:

| Tool | Description |
|------|-------------|
| `list_agents` | List all profiles with roles and running status |
| `delegate_to_agent` | Delegate a task — auto-starts the agent if needed |

Example: ask the default agent *"do market research on X"* — it calls `list_agents`, picks the right profile, starts it, and delegates the task automatically.

**Background agent HTTP API:**

| Endpoint | Description |
|----------|-------------|
| `POST /task` | Submit a task → `{task_id}` |
| `GET /status` | Health check (agent name + port) |
| `WS /ws` | Live `token` / `step` / `done` / `error` events (results stream here) |
| `/api/*` | Desktop/API routes — profiles, memory, skills, workspace, budget, cron, workflows, products, predict |

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
Layer 7  CLI                 setup · new · list · config · rm · run · ps · stop
Layer 6  Channels + Server    CLI (foreground) · FastAPI server + /api (background)
Layer 5  Gateway              normalize · session · persona · file detection
Layer 4  Planner              classify · decompose · HITL · delegation
Layer 3  Agent Runtime        ReAct loop · native tool use · hooks · permissions · budget
Layer 2  Tools + MCP          web_search · web_fetch · http · files · exec · research · real MCP stdio
Layer 1  Memory + LLM         6 memory types · LLM Router (4 providers)
```

Package layout: `agent/` (runtime, gateway, planner, hooks, permissions) ·
`server/` (HTTP + api) · `intelligence/` (research/products/predict/…) ·
`evolution/` (self-improvement) · `orchestration/` (workflows + cron) ·
`tools/ · llm/ · memory/ · mcp/ · channels/ · storage/ · config/`.

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
