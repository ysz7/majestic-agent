<div align="center">

```
███╗   ███╗ █████╗      ██╗███████╗███████╗████████╗██╗ ██████╗ 
████╗ ████║██╔══██╗     ██║██╔════╝██╔════╝╚══██╔══╝██║██╔════╝ 
██╔████╔██║███████║     ██║█████╗  ███████╗   ██║   ██║██║      
██║╚██╔╝██║██╔══██║██   ██║██╔══╝  ╚════██║   ██║   ██║██║      
██║ ╚═╝ ██║██║  ██║╚█████╔╝███████╗███████║   ██║   ██║╚██████╗ 
╚═╝     ╚═╝╚═╝  ╚═╝ ╚════╝ ╚══════╝╚══════╝   ╚═╝   ╚═╝ ╚═════╝
```

**The agent that gets it done.**

Not a chatbot. Not a command menu. A universal agent that runs on your laptop or server — and executes any task across every platform.

[![License: MIT](https://img.shields.io/badge/License-MIT-red.svg)](https://opensource.org/licenses/MIT)
[![Python](https://img.shields.io/badge/Python-3.11+-red.svg)](https://python.org)
[![Version](https://img.shields.io/badge/version-0.1.0-red.svg)](https://github.com/ysz/majestic-agent)

</div>

---

## ♛ What is Majestic?

Majestic is a **universal agent-executor** built for people who want results, not menus. Give it any task in plain language — it picks the right tools and gets it done. Research, market analysis, file work, automations — all from one agent, on any platform.

```
$ majestic
majestic ~/projects ❯ Research crypto market and send me a briefing on Telegram

  ◆ Starting session · claude-sonnet-4
  ├ web_search     · 8 sources · 247 signals collected
  ├ market_data    · BTC $67,420 ↑2.4% · ETH $3,890 ↑1.8%
  ├ db_search      · 912 items indexed · 14 relevant
  └ briefing       · generating analysis · 1,240 tokens

✓ Briefing sent to Telegram · @you · $0.003
```

---

## ✦ Features

| Feature | Description |
|---|---|
| **Universal Execution** | Give any task in plain language — agent picks the right tools |
| **Persistent Memory** | Remembers preferences, sessions, and skills across conversations |
| **Universal Search** | Hybrid FTS5 + vector search across all your data — news, reports, docs, history |
| **Modular Toolsets** | Drop a file in `tools/` — agent picks it up automatically |
| **Smart Automations** | Natural language scheduling delivered to any platform |
| **One-File Backup** | All data in `~/.majestic/state.db` — one command backup |

---

## ⚡ Quick Start

```bash
# Install
curl -fsSL https://raw.githubusercontent.com/ysz/majestic-agent/main/install.sh | bash

# Setup (interactive wizard)
majestic setup

# Run
majestic
```

That's it. The wizard configures your LLM provider, API keys, and platforms.

---

## 📦 Installation

**Requirements:** Python 3.11+, macOS / Linux

```bash
# Option 1 — install script (recommended)
curl -fsSL https://raw.githubusercontent.com/ysz/majestic-agent/main/install.sh | bash

# Option 2 — from source
git clone https://github.com/ysz/majestic-agent
cd majestic-agent
pip install -e .
majestic setup
```

---

## 🖥️ Runs Anywhere

Majestic runs on your **laptop** or a **remote server** — you connect from any device.

```
MacBook → CLI        ──┐
Phone   → Telegram   ──┤
Team    → Slack      ──┤── majestic (VPS) → LLM
Desktop → Discord    ──┤
Cron    → schedule   ──┘
```

**Supported platforms:** Telegram · Discord · Slack · WhatsApp · Signal · CLI

---

## 🛠️ Toolsets

Tools are grouped by domain. The agent selects automatically. Add your own — drop a file in `tools/`, it's instantly available.

```
tools/
├── web/            web_search, web_extract
├── research/       news, briefing, report, predict, flows, ideas
├── market/         crypto, stocks, forex
├── files/          read_file, write_file, index
├── system/         terminal
└── db_search.py    universal search across all data (core)
```

### Adding a custom tool

```python
# tools/myapp/action.py
from majestic.tools import registry

@registry.tool
def my_tool(query: str) -> str:
    """Describe what this tool does."""
    ...
    return result
# Agent picks it up automatically on next start
```

---

## 🧠 Memory & Skills

**Memory** — agent remembers between sessions:
- `~/.majestic/memory/memory.md` — agent facts and knowledge
- `~/.majestic/memory/user.md` — your profile and preferences

**Skills** — reusable procedures the agent creates from experience:
- `~/.majestic/skills/*.md` — each skill is a markdown file
- Agent proposes saving a skill after complex tasks
- Skills improve with repeated use

```bash
/memory          # view memory
/forget <topic>  # remove a memory
/skills          # list skills
```

---

## 🔍 Universal Search

Unlike most agents, Majestic searches **across all your data** — not just uploaded documents.

```
db_search("query")
    ├── messages_fts    → conversation history  (FTS5 / BM25)
    ├── news_fts        → collected news         (FTS5 / BM25)
    ├── reports_fts     → generated reports      (FTS5 / BM25)
    ├── market_history  → market data            (SQL)
    └── vectors         → documents              (sqlite-vec)
                                  ↓
                        RRF fusion → ranked results
```

No ChromaDB. No separate processes. Everything in `~/.majestic/state.db`.

---

## 💾 Storage

All data lives in one directory — easy to backup, easy to move:

```
~/.majestic/
├── state.db        # SQLite — sessions, messages, market, vectors, schedules
├── memory/
│   ├── memory.md   # agent memory
│   └── user.md     # user profile
├── skills/
│   └── *.md        # skills
├── exports/        # briefings, reports
├── .env            # API keys and tokens
└── config.yaml     # settings
```

**Backup:**
```bash
tar -czf majestic-backup.tar.gz ~/.majestic/
```

---

## ⌨️ Commands

**Agent management:**
```
/model       switch model
/memory      view memory
/forget      remove a memory entry
/skills      list skills
/stop        interrupt execution
/schedule    manage scheduled tasks
/background  run task in background
/usage       token and cost stats
```

**Research shortcuts (from Parallax):**
```
/research    collect signals from all sources
/briefing    full briefing: signals + market + direction
/news [N]    latest N news by score
/market      crypto + stocks + forex
/predict     predictions with probabilities
/flows       where capital is moving
/ideas       business ideas from trends
/report      deep report on a topic
/reports     list saved reports
```

---

## 🗓️ Automations

Natural language scheduling:

```
/schedule add "every Monday at 9am, send me a market briefing on Telegram"
/schedule add "daily at 7am, research AI news and brief me"
/schedule list
/schedule remove <id>
```

---

## 🤖 LLM Providers

| Provider | Usage |
|---|---|
| **Anthropic** | Direct (recommended) |
| **OpenRouter** | 200+ models via one API |

Switch model anytime:
```bash
majestic model
# or
/model
```

---

## 🏗️ Architecture

Clean modular structure — max 300 lines per file, one responsibility per file:

```
majestic/
├── agent/          loop.py · prompt.py · compressor.py · delegate.py
├── db/             state.py · migrations.py
├── memory/         store.py · nudge.py
├── llm/            base.py · anthropic.py · openrouter.py
├── tools/          registry.py · web/ · research/ · market/ · files/ · system/
├── skills/         loader.py · creator.py
├── gateway/        base.py · runner.py · telegram.py · discord.py · slack.py ...
├── cron/           scheduler.py · jobs.py
└── cli/            main.py · setup.py · commands.py · display.py
```

---

## 📄 License

MIT — do whatever you want.

---

<div align="center">

**[Website](https://majestic-agent.dev) · [Docs](https://majestic-agent.dev/docs) · [Discord](https://discord.gg/majestic)**

Made with ♛ by [ysz](https://github.com/ysz)

</div>
