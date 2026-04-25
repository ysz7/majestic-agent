<div align="center">


**The agent that gets it done.**

Not a chatbot. Not a command menu. A universal agent-executor — runs on your laptop or VPS, executes any task in plain language, across every platform.

[![License: MIT](https://img.shields.io/badge/License-MIT-red.svg)](https://opensource.org/licenses/MIT)
[![Python](https://img.shields.io/badge/Python-3.11+-red.svg)](https://python.org)
[![Version](https://img.shields.io/badge/version-0.1.0-red.svg)](https://github.com/ysz/majestic-agent)
[![Tests](https://img.shields.io/badge/tests-54%20passed-brightgreen.svg)](tests/)

</div>

---

## ♛ What is Majestic?

Majestic is a **universal agent-executor**. Give it a task in plain language — it picks the right tools and executes. Research, market data, file work, automations — all from one agent, on any platform.

```
$ majestic

  ╔══════════════╗  ╔══════════════════════════════════════════╗
  ║  *  *  *  *  ║  ║  Available Tools                         ║
  ║ /| /| /| /|  ║  ║  web:       web_search, web_extract      ║
  ║/ \/ \/ \/ \  ║  ║  research:  news, briefing, report       ║
  ║──────────────║  ║  market:    crypto, stocks, forex         ║
  ║  MAJESTIC    ║  ║  files:     read_file, write_file, index  ║
  ║              ║  ║  system:    terminal                      ║
  ║  model    ·  ║  ║  core:      db_search                     ║
  ║  claude-s-4  ║  ╠══════════════════════════════════════════╣
  ║  memory   ·  ║  ║  Memory Snapshot                         ║
  ║  on · 12 f   ║  ║  user:   prefers crypto focus            ║
  ╚══════════════╝  ║  agent:  12 facts · updated today        ║
                    ╚══════════════════════════════════════════╝

  6 toolsets · 0 skills · 12 memories · /help for commands
  ♛ claude-sonnet-4  │  0 tok  │  $0.0000  │  Tab for commands

▶
```

---

## ⚡ Quick Start

```bash
git clone https://github.com/ysz/majestic-agent
cd majestic-agent
./scripts/install.sh   # creates .venv, installs deps, registers PATH

majestic setup         # interactive wizard — API keys, model, platform
majestic               # launch agent
```

Restart your terminal after install (or `source ~/.bashrc`) so `majestic` is available everywhere.

---

## 📦 Installation

**Requirements:** Python 3.11+, macOS / Linux

```bash
# Recommended — sets up venv, registers PATH, optional systemd service
./scripts/install.sh

# With systemd auto-start (gateway starts on boot)
./scripts/install.sh --service

# Or manually
python3 -m venv .venv && source .venv/bin/activate
pip install -e .
majestic setup
```

### Docker

```bash
cp .env.example .env
# fill in ANTHROPIC_API_KEY and TELEGRAM_BOT_TOKEN in .env

docker compose up -d
```

Data persists in `~/.majestic-agent/` on the host (mapped as a volume). Health check available at `http://localhost:8080/health`.

---

## ✦ Features

| | Feature | Details |
|---|---|---|
| ♛ | **Universal Execution** | Any task in plain language — agent picks the right tools |
| 🧠 | **Persistent Memory** | Remembers preferences, context, and skills across sessions |
| 🔍 | **Hybrid Search** | FTS5 + vector search across all data: news, docs, history, reports |
| 🔧 | **Modular Tools** | Drop a file in `tools/` — registered automatically on next start |
| 🗓️ | **Automations** | Natural language scheduling delivered to any platform |
| 📡 | **Multi-Platform** | Telegram bot + CLI — same agent, any interface |
| 🐳 | **Docker Ready** | One command deploy with persistent volume and health endpoint |
| ✅ | **Tested** | 54 unit tests across all critical paths, GitHub Actions CI |

---

## 🖥️ Platforms

```
CLI (terminal)   ──┐
Telegram bot     ──┤── majestic (local / VPS)  ──→  LLM  ──→  tools
Cron / schedule  ──┘
```

**CLI** — interactive REPL with prompt_toolkit: tab-completion for all commands, token/cost status bar, history.

**Telegram** — same agent as CLI. Start with `majestic gateway start` or enable the systemd service.

---

## 🛠️ Toolsets

Tools are grouped by domain. The agent selects automatically based on the task.

```
tools/
├── web/         web_search · web_extract
├── research/    news · briefing · report · predict · flows · ideas
├── files/       read_file · write_file · index (pdf, docx, csv, md)
├── system/      terminal
└── db_search.py unified search across all indexed data  ← core tool
```

**Adding a custom tool:**

```python
# tools/myapp/action.py
from majestic.tools.registry import tool

@tool("my_tool", "Does something useful", {
    "type": "object",
    "properties": {"query": {"type": "string"}},
    "required": ["query"],
})
def my_tool(query: str) -> str:
    ...
    return result
# Agent picks it up automatically on next start — nothing else to change
```

---

## 🧠 Memory & Skills

**Memory** persists between sessions as plain Markdown files:

```
~/.majestic-agent/memory/
├── memory.md   # agent facts: context, knowledge, learned behaviors
└── user.md     # user profile: preferences, habits, background
```

```
/memory          # view current memory
/forget crypto   # remove all entries mentioning "crypto"
```

**Skills** are reusable procedures stored as Markdown:

```
~/.majestic-agent/skills/
└── *.md         # each file is one skill, invoked as /skill-name
```

```
/skills          # list available skills
/my-skill        # invoke by name, tab-complete in the REPL
```

---

## 🔍 Universal Search

```
db_search("query")
    ├── messages_fts    → conversation history   (FTS5 · BM25)
    ├── news_fts        → collected intel         (FTS5 · BM25)
    ├── vector_chunks   → indexed documents       (sqlite-vec · cosine)
    └── market_history  → market snapshots        (SQL · time range)
                                  ↓
                        RRF fusion → ranked results
```

No ChromaDB. No extra processes. Everything in `~/.majestic-agent/state.db`.

---

## 💾 Data Layout

One directory, one backup:

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

```bash
tar -czf majestic-backup.tar.gz ~/.majestic-agent/
```

---

## ⌨️ Commands

<table>
<tr>
<td valign="top">

**Agent**
```
/research        collect intel from all sources
/briefing [N]    market + tech briefing (default 14d)
/market          crypto · stocks · forex snapshot
/news [N]        latest N news items
/report <topic>  deep report on a topic
/ideas           business ideas from signals
```

</td>
<td valign="top">

**Management**
```
/memory          view persistent memory
/forget <topic>  remove memory entries
/skills          list saved skills
/model           switch LLM provider/model
/usage [reset]   token + cost stats
/schedule ...    manage cron schedules
/remind <text>   add a reminder
/rss ...         manage RSS feeds
/reports ...     view / delete saved reports
/stop            interrupt current task
/exit            save session memory and quit
```

</td>
</tr>
</table>

---

## 🗓️ Automations

Schedule any task in plain language:

```
/schedule add "every Monday at 9am, send me a market briefing on Telegram"
/schedule add "daily at 7am, research AI news and brief me"
/schedule list
/schedule remove 2
```

The scheduler ticks in the background, delivers to Telegram or CLI. Expressions are parsed by the LLM and stored as cron.

---

## 🤖 LLM Providers

| Provider | Config |
|---|---|
| **Anthropic** | `ANTHROPIC_API_KEY` — direct SDK, best tool use |
| **Ollama** | local models — no API key, set `llm.provider: ollama` |

```bash
majestic model     # interactive model selector
/model             # same, from within the REPL
```

---

## 🏗️ Architecture

Max 300 lines per file, one responsibility per module:

```
majestic/
├── agent/        loop.py · prompt.py · delegate.py · runner.py
├── db/           state.py · migrations.py · embedder.py · parser.py
├── llm/          base.py · anthropic.py · ollama.py · openrouter.py
├── memory/       store.py · nudge.py
├── tools/        registry.py · web/ · research/ · files/ · system/
├── skills/       loader.py
├── gateway/      base.py · telegram.py · health.py · formatter.py
├── cron/         scheduler.py · jobs.py
└── cli/          main.py · repl.py · repl_helpers.py · display.py · setup.py

tests/
├── conftest.py
├── test_db.py     · test_memory.py  · test_llm.py
├── test_tools.py  · test_cron.py   · test_agent.py
```

---

## ✅ Tests

```bash
pytest tests/ -v
# 54 passed in 0.56s
```

All critical paths are covered without real LLM calls or network access:

| File | Coverage |
|---|---|
| `test_db.py` | Sessions, messages, FTS5 search, news, vector chunks |
| `test_memory.py` | Load, append, dedup, forget, show |
| `test_llm.py` | ToolCall, Usage, MockProvider, streaming |
| `test_tools.py` | Register, execute, schema format, error handling |
| `test_cron.py` | CRUD, get_due, mark_ran, nl_to_schedule mock |
| `test_agent.py` | Single turn, history, tool calls, stop signal, iteration cap |

CI runs on every push via GitHub Actions.

---

## 📄 License

MIT — do whatever you want.

---

<div align="center">

Made with ♛ by [ysz](https://github.com/ysz)

</div>
