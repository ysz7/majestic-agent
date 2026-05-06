<div align="center">

<img src="docs/assets/majestic-cli-logo.png" alt="Majestic" width="480">

**Build Vertical AI Agents Without the Bloat.**

Lean agent infrastructure — local or cloud LLMs, persistent memory, tool execution, multi-agent network. One command to install, one config to specialize.

[![License: MIT](https://img.shields.io/badge/License-MIT-red.svg)](https://opensource.org/licenses/MIT)
[![Python](https://img.shields.io/badge/Python-3.11+-red.svg)](https://python.org)
[![Version](https://img.shields.io/badge/version-0.16.0-red.svg)](https://github.com/ysz7/majestic-agent)
[![Tests](https://img.shields.io/badge/tests-148%20passed-brightgreen.svg)](tests/)
[![Docs](https://img.shields.io/badge/docs-read-blue.svg)](https://ysz7.github.io/majestic-agent/docs)

</div>

---

## ♛ What is Majestic?

Majestic is a **lean AI agent core** designed to be specialized into vertical solutions. Take it, wire in your domain tools, set the role, ship.

```
  majestic ▶ Analyze support tickets from last week and summarize top issues

 ┌ read_file("tickets.csv")
 ├ Working... ⠹
 ├ run_python(analysis script)
 └ Done · 2 tool calls · $0.003 · 4.1s

  Top issues: billing (38%), login (24%), performance (21%)...
```

---

## Quick Install

```bash
curl -fsSL https://raw.githubusercontent.com/ysz7/majestic-agent/main/scripts/install.sh | bash
```

After install:

```bash
majestic setup    # interactive wizard — API keys, model, language
majestic          # launch agent REPL
```

Restart your terminal (or `source ~/.bashrc`) after install so `majestic` is on PATH.

---

## Installation Options

**Requirements:** Python 3.11+, Git, macOS / Linux

```bash
# One-liner (recommended)
curl -fsSL https://raw.githubusercontent.com/ysz7/majestic-agent/main/scripts/install.sh | bash

# Clone manually
git clone https://github.com/ysz7/majestic-agent
cd majestic-agent
./scripts/install.sh

# With systemd auto-start (Telegram gateway starts on boot)
./scripts/install.sh --service

# Manual venv setup
python3 -m venv .venv && source .venv/bin/activate
pip install -e .
majestic setup
```

### Docker

```bash
cp .env.example .env
# fill ANTHROPIC_API_KEY in .env
docker compose up -d
```

Data persists in `~/.majestic-agent/` on the host. Health check at `http://localhost:8080/health`.

---

## ✦ Features

| Feature | Details |
|---|---|
| **Lean Core** | ~20 focused tools — web, files, code execution, memory, scheduling |
| **Vertical-Ready** | Set `agent.role` + drop domain tools in `tools/` — registered automatically |
| **Persistent Memory** | Remembers context and skills across sessions |
| **Hybrid Search** | FTS5 + vector search across docs, history, and memory |
| **4 LLM Providers** | Anthropic, OpenAI, OpenRouter, Ollama — switch anytime |
| **Multi-Agent Network** | Named agents, delegation, auto-routing between specialized instances |
| **REST API** | `POST /chat`, `GET /health`, `GET /sessions` — connect any UI or script |
| **MCP Integration** | Any MCP server becomes agent tools instantly — no Python code |
| **Web Dashboard** | Browser UI — chat, memory editor, skill CRUD, file manager, settings |
| **Telegram Gateway** | Full bot integration — same agent, any device |
| **Script Library** | Agent creates reusable Python scripts, auto-discovered each session |
| **Docker Ready** | One command deploy with persistent volume and health endpoint |
| **Tested** | 148 unit tests across all critical paths, GitHub Actions CI |

---

## Commands

### Memory & skills

```
/memory                view persistent memory
/forget <topic>        remove memory entries mentioning a keyword
/skills                list saved skills
```

### Management

```
/model                 switch LLM provider or model
/history <query>       search past conversations with LLM summarization
/history last [N]      show last N sessions with one-line summaries
/usage [reset]         token usage and cost stats
/schedule list         list active cron schedules
/schedule add <text>   add schedule in plain language
/schedule remove <id>  remove a schedule
/remind <text>         add a natural-language reminder
/reminders             list active reminders
/stop                  interrupt current task
/exit                  save session memory and quit
```

---

## Multi-Agent Setup

Run multiple specialized agents and let them delegate to each other:

```bash
# Create named agents
majestic init finance_bot
majestic init support_agent

# Launch each in its own terminal
majestic finance_bot
majestic support_agent

# Manage all agents
majestic list    # all agents + status (● running / ○ stopped)
majestic ps      # running only
```

Each agent has isolated data: config, state.db, memory, skills — all under `~/.majestic-agent/<name>/`.

Agents can delegate tasks to each other:

```python
# Inside finance_bot, the agent can call:
delegate_task(task="summarize open tickets", to="support_agent")
```

Configure which agents an instance can route to:

```yaml
# ~/.majestic-agent/finance_bot/config.yaml
agent:
  name: finance_bot
  role: "Financial analyst — handles portfolio queries and investment research."
  delegates_to:
    - support_agent          # local named agent
    - http://10.0.0.2:8081   # remote agent URL
```

---

## Tools

```
tools/
├── web/        web_search · http_request · web_extract
├── files/      read_file · write_file · copy_file · workspace_*
├── system/     run_python · run_command
├── memory/     remember · db_search · history_search
├── scripts/    save_script · list_scripts · run_script
├── agent/      delegate_task · delegate_parallel
└── utils/      get_datetime · get_news
```

MCP tools are registered automatically from any configured MCP server:

```bash
majestic mcp add filesystem npx -y @modelcontextprotocol/server-filesystem /home/user
majestic mcp list   # shows mcp_filesystem_read_file, mcp_filesystem_write_file, ...
```

**Adding a custom tool:**

```python
# majestic/tools/myapp/action.py
from majestic.tools.registry import tool

@tool("my_tool", "Does something useful", {
    "type": "object",
    "properties": {"query": {"type": "string"}},
    "required": ["query"],
})
def my_tool(query: str) -> str:
    return result
# Agent picks it up automatically on next start
```

---

## Memory & Skills

**Memory** persists between sessions as plain Markdown files:

```
~/.majestic-agent/memory/
├── memory.md   # agent facts: context, knowledge, learned behaviors
└── user.md     # user profile: preferences, habits, background
```

**Skills** are reusable procedures stored as Markdown:

```
~/.majestic-agent/skills/
└── *.md        # each file is one skill, invoked as /skill-name
```

---

## Specialization

Fork for any domain without touching source code:

```yaml
# ~/.majestic-agent/config.yaml
agent:
  role: "You are a support specialist. Analyze tickets, identify patterns, draft responses."
```

Or from within the REPL:
```
/set role You are a DevOps specialist focused on infrastructure monitoring.
```

MCP servers in config — any MCP-compatible source becomes agent tools:
```yaml
mcp_servers:
  - name: github
    command: ["npx", "-y", "@modelcontextprotocol/server-github"]
    env:
      GITHUB_TOKEN: "${GITHUB_TOKEN}"
```

---

## LLM Providers

| Provider | Notes |
|---|---|
| **Anthropic** | `ANTHROPIC_API_KEY` — direct SDK, best tool use |
| **OpenAI** | `OPENAI_API_KEY` — GPT-4o, o3-mini |
| **OpenRouter** | `OPENROUTER_API_KEY` — route to any model (Claude, GPT, Gemini, Llama, free tier available) |
| **Ollama** | local models — no API key, set `llm.provider: ollama` |

```bash
majestic setup    # configure provider and model interactively
```

---

## Platforms

```
CLI (terminal)   ──┐
Telegram bot     ──┤── majestic (local / VPS) ──→ LLM ──→ tools
REST API         ──┤
Web Dashboard    ──┘
```

```bash
majestic gateway start telegram   # Telegram bot
majestic api start                # REST API on port 8080
majestic dashboard                # Web dashboard
./scripts/install.sh --service    # systemd auto-start
```

### REST API

```bash
majestic api start   # starts HTTP server on port 8080 (configurable via api.port)
```

```
POST /chat      {message, session_id?}  →  {answer, tools_used, cost_usd, elapsed_s}
POST /run       fire-and-forget background task  →  202 Accepted
GET  /health    {"status": "ok", "version": "..."}
GET  /sessions  list active sessions
```

Auth: set `api.key` in `config.yaml`, send as `X-API-Key` header.

---

## Data Layout

```
~/.majestic-agent/
├── state.db               # SQLite — sessions, messages, news, vectors, schedules
├── config.yaml            # settings: language, model, role
├── .env                   # API keys (never committed)
├── .registry.json         # named agent registry (ports, roles, status)
├── memory/
│   ├── memory.md          # agent memory
│   └── user.md            # user profile
├── skills/                # user-defined skills (*.md)
├── exports/               # generated reports and outputs
├── workspace/             # indexed uploaded files
└── <agent_name>/          # isolated named agent instances
    ├── config.yaml
    ├── state.db
    └── memory/
```

---

## Architecture

Max 300 lines per file, one responsibility per module:

```
majestic/
├── agent/        loop.py · prompt.py · delegate.py
├── api/          server.py  ← REST API (stdlib, no FastAPI dep)
├── db/           state.py · embedder.py · parser.py
├── llm/          base.py · anthropic.py · openai.py · openrouter.py · ollama.py
├── mcp/          client.py · bridge.py
├── memory/       store.py · session_summarizer.py
├── tools/        registry.py · web/ · files/ · system/ · scripts/ · history_search.py
├── skills/       loader.py
├── gateway/      base.py · telegram.py · health.py · formatter.py
├── cron/         scheduler.py · jobs.py
└── cli/          main.py · repl.py · repl_helpers.py · display.py · setup.py · agents.py
```

---

## Tests

```bash
pytest tests/ -v
# 148 passed in ~1.2s
```

---

## Documentation

Full reference documentation: **[https://ysz7.github.io/majestic-agent/docs](https://ysz7.github.io/majestic-agent/docs)**

Covers CLI commands, tools, memory, scheduling, configuration, LLM providers, REST API, gateways, MCP, multi-agent setup, and building vertical agents.

---

## License

MIT — do whatever you want.

---

<div align="center">

Made with ♛ by [ysz7](https://github.com/ysz7)

</div>
