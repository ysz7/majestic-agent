<div align="center">

<img src="docs/assets/majestic-cli-logo.png" alt="Majestic" width="480">

**The agent that gets it done.**

Not a chatbot. Not a command menu. A universal agent-executor — runs on your laptop or VPS, executes any task in plain language, across every platform.

[![License: MIT](https://img.shields.io/badge/License-MIT-red.svg)](https://opensource.org/licenses/MIT)
[![Python](https://img.shields.io/badge/Python-3.11+-red.svg)](https://python.org)
[![Version](https://img.shields.io/badge/version-0.1.0-red.svg)](https://github.com/ysz7/majestic-agent)
[![Tests](https://img.shields.io/badge/tests-54%20passed-brightgreen.svg)](tests/)

</div>

---

## ♛ What is Majestic?

Majestic is a **universal agent-executor**. Give it a task in plain language — it picks the right tools and executes. Research, market data, file work, automations — all from one agent, on any platform.

```
  majestic ▶ Research BTC market and send briefing to Telegram

 ┌ web_search
 ├ Working... ⠹
 ├ get_market_data
 ├ Working... ⠸
 ├ get_briefing
 └ Done · 3 tool calls · $0.004 · 8.2s

  BTC is trading at $67,420 (+2.4%)...
```

---

## Quick Install

```bash
curl -fsSL https://raw.githubusercontent.com/ysz7/majestic-agent/main/scripts/install.sh | bash
```

After install:

```bash
majestic setup    # interactive wizard — API keys, model, language
majestic          # launch agent
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
# fill ANTHROPIC_API_KEY and TELEGRAM_BOT_TOKEN in .env
docker compose up -d
```

Data persists in `~/.majestic-agent/` on the host. Health check at `http://localhost:8080/health`.

---

## ✦ Features

| | Feature | Details |
|---|---|
| **Universal Execution** | Any task in plain language — agent picks the right tools |
| **Persistent Memory** | Remembers preferences, context, and skills across sessions |
| **Hybrid Search** | FTS5 + vector search across all data: news, docs, history, reports |
| **Modular Tools** | Drop a file in `tools/` — registered automatically on next start |
| **Automations** | Natural language scheduling delivered to any platform |
| **Multi-Platform** | Telegram bot + CLI — same agent, any interface |
| **Docker Ready** | One command deploy with persistent volume and health endpoint |
| **Tested** | 54 unit tests across all critical paths, GitHub Actions CI |

---

## Commands

### Agent tools

```
/research              collect intel from all sources (HN, Reddit, GitHub, arXiv...)
/briefing [days]       market + tech briefing (default 14 days)
/market                crypto · stocks · forex snapshot
/news [N]              latest N news items sorted by relevance
/report <topic>        deep report on any topic
/ideas                 business ideas generated from recent signals
```

### Memory & skills

```
/memory                view persistent memory
/forget <topic>        remove memory entries mentioning a keyword
/skills                list saved skills
```

### Management

```
/model                 switch LLM provider or model
/usage [reset]         token usage and cost stats
/schedule list         list active cron schedules
/schedule add <text>   add schedule in plain language
/schedule remove <id>  remove a schedule
/remind <text>         add a natural-language reminder
/reminders             list active reminders
/rss list              list RSS feeds
/rss add <url>         add RSS feed
/rss remove <id>       remove RSS feed
/reports               list saved reports
/reports view <N>      view a report
/reports del <N>       delete a report
/stop                  interrupt current task
/exit                  save session memory and quit
```

---

## Toolsets

Tools are grouped by domain. The agent selects automatically based on the task.

```
tools/
├── web/         web_search · web_extract
├── research/    news · briefing · report · predict · flows · ideas
├── files/       read_file · write_file · index (pdf, docx, csv, md)
├── system/      terminal
└── db_search    unified search across all indexed data  ← core
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

## Automations

Schedule any task in plain language:

```
/schedule add "every Monday at 9am, send me a market briefing on Telegram"
/schedule add "daily at 7am, research AI news and brief me"
/schedule list
/schedule remove 2
```

The scheduler runs in the background and delivers to Telegram or CLI.

---

## LLM Providers

| Provider | Notes |
|---|---|
| **Anthropic** | `ANTHROPIC_API_KEY` — direct SDK, best tool use |
| **Ollama** | local models — no API key, set `llm.provider: ollama` |

```bash
majestic model    # interactive model selector
/model            # same, from within the REPL
```

---

## Platforms

```
CLI (terminal)   ──┐
Telegram bot     ──┤── majestic (local / VPS) ──→ LLM ──→ tools
Cron / schedule  ──┘
```

Start the Telegram gateway:

```bash
majestic gateway start
# or as a systemd service:
./scripts/install.sh --service
```

---

## Data Layout

```
~/.majestic-agent/
├── state.db               # SQLite — sessions, messages, news, vectors, schedules
├── config.yaml            # settings: language, model, search_mode
├── .env                   # API keys (never committed)
├── memory/
│   ├── memory.md          # agent memory
│   └── user.md            # user profile
├── skills/                # user-defined skills (*.md)
├── exports/               # generated briefings, reports, ideas
├── workspace/             # indexed uploaded files
└── backups/               # daily auto-backups (.zip)
```

Backup everything:
```bash
tar -czf majestic-backup.tar.gz ~/.majestic-agent/
```

---

## Architecture

Max 300 lines per file, one responsibility per module:

```
majestic/
├── agent/        loop.py · prompt.py · delegate.py · runner.py
├── db/           state.py · embedder.py · parser.py
├── llm/          base.py · anthropic.py · ollama.py · openrouter.py
├── memory/       store.py · nudge.py
├── tools/        registry.py · web/ · research/ · files/ · system/
├── skills/       loader.py
├── gateway/      base.py · telegram.py · health.py · formatter.py
├── cron/         scheduler.py · jobs.py
└── cli/          main.py · repl.py · repl_helpers.py · display.py · setup.py
```

---

## Tests

```bash
pytest tests/ -v
# 54 passed in ~0.6s
```

| File | What's tested |
|---|---|
| `test_db.py` | Sessions, messages, FTS5 search, news, vector chunks |
| `test_memory.py` | Load, append, dedup, forget, show |
| `test_llm.py` | ToolCall, Usage, MockProvider |
| `test_tools.py` | Register, execute, schema, error handling |
| `test_cron.py` | CRUD, get_due, mark_ran, nl_to_schedule |
| `test_agent.py` | Single turn, history, tool calls, stop signal, iteration cap |

---

## License

MIT — do whatever you want.

---

<div align="center">

Made with ♛ by [ysz7](https://github.com/ysz7)

</div>
