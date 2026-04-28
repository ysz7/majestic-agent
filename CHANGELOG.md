# Changelog

All notable changes to Majestic are documented here.
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

---

## [Unreleased]

## [0.12.1] - 2026-04-28
### Added
- `CHANGELOG.md` with full history in Keep a Changelog format
- Documentation links in README badge strip and landing page nav/footer/CTA

### Changed
- Removed triangle icon from documentation nav — text-only logo
- Footer "Docs" and "GitHub" links now resolve to real targets

---

## [0.12.0] - 2026-04-28
### Added
- `docs/docs.html` — full documentation SPA (14 pages, React + Babel standalone)
  - Getting Started: Introduction, Quick Start
  - Using Majestic: CLI Commands, Tools & Toolsets, Memory & Skills, Scheduling
  - Configuration: config.yaml reference, LLM Providers
  - Integrations: REST API, Gateways, MCP Servers
  - Customization: Specialization, Local Tools, Updating
- Per-page TOC with IntersectionObserver active-anchor tracking
- Prev / Next page navigation

---

## [0.11.3] - 2026-04-28
### Added
- `source: agent` field in auto-generated skill frontmatter
- `/agent-skills` REPL command — lists skills created automatically by the agent
- Landing page: square corners (border-radius 4px), reduced section spacing, softer headline fonts

### Changed
- `/skills` now shows only user-defined skills (not agent-auto-created ones)
- Agent-created skills excluded from tab-completion and direct `/<name>` invocation
- CLI prompt changed from `majestic ▶` to `▶`

---

## [0.11.2] - 2026-04-28
### Added
- `run_command` now requires user approval before executing any shell command
- `[y / N / always]` approval prompt — `always` permanently saves the command to `agent.allowed_commands`
- Non-interactive mode (gateway, cron) blocks commands by default unless `agent.allow_commands: true`
- `majestic doctor` warns when `agent.allow_commands: true` is set with a gateway enabled

---

## [0.11.1] - 2026-04-28
### Added
- `majestic update` command — git stash → pull --rebase → stash pop, auto-reinstalls deps if pyproject.toml changed
- `majestic/tools/local/` — gitignored directory for custom `@tool` Python files, auto-loaded on startup
- `.gitkeep` keeps the `local/` folder tracked in git while its content stays gitignored

---

## [0.11.0] - 2026-04-27
### Added
- Cron schedules support `parallel: true` and `subtasks: [...]` fields
- Parallel subtasks run in separate threads and are joined with a 120s timeout
- NL schedule parser (`nl_to_schedule`) recognises parallel intent and emits subtasks array
- `/schedule list` shows `[parallel]` tag on parallel schedules
- `majestic gateway start all` — single command starts Telegram + Discord + Email simultaneously (unconfigured platforms skipped)

---

## [0.10.0] - 2026-04-27
### Added
- Named toolsets: `research`, `coding`, `market`, `full` — switch with `/set toolset <name>`
- `/toolsets` REPL command and `majestic tools list` shell command
- `majestic tools` — interactive checkbox selector to enable/disable individual tools
- Memory dedup on `/exit` — LLM pass merges duplicate/contradicting memory entries (1 LLM call)
- Self-improving skills: every 3rd invocation, agent proposes improved skill body; user confirms before applying
- `queue_improvement_check` + `pop_pending_improvement` for background skill improvement

---

## [0.9.0] - 2026-04-27
### Added
- `rich`-based Markdown rendering for agent responses (syntax-highlighted code blocks, tables, bold)
- Tool call display with `╭─ 🔧 tool_name · arg ─╮` panels via rich
- Startup banner with version, provider, and model
- `/usage` and `/insights [days]` output via rich tables
- Multiline input: `Escape+Enter` inserts newline, `Enter` submits
- `/new` / `/reset` clears session history and starts a new `session_id`
- Bottom toolbar with token usage and cost (refreshes every 2s)
- Tab-completion for all slash commands via `prompt_toolkit`

---

## [0.8.0] - 2026-04-27
### Added
- Built-in skills: `research.md`, `briefing.md`, `report.md`, `ideas.md` — installed to `~/.majestic-agent/skills/` on `majestic setup`
- Reports and briefings saved to `workspace/reports/`, `workspace/briefings/`, `workspace/ideas/`
- `workspace_list` and `workspace_search` cover all saved output automatically
- MiniMax provider (`majestic/llm/minimax.py`) — models `MiniMax-Text-01`, `abab6.5s-chat`
- Email gateway (`majestic/gateway/email_gw.py`) — IMAP polling + SMTP replies, `allowed_senders` whitelist
- Per-project context: `AGENTS.md` in the working directory is injected as a `[Project context]` system prompt block
- Voice memo transcription in Telegram via OpenAI Whisper API (`telegram.voice_transcription: true`)

### Changed
- Removed separate `exports/` directory — all generated content unified under `workspace/`
- Migration on startup moves existing `exports/` files into appropriate `workspace/` subdirectories

---

## [0.7.0] - 2026-04-26
### Added
- Discord gateway (`majestic/gateway/discord.py`) via `discord.py`
- Discord slash commands: `/ask`, `/briefing`, `/research`, `/remind`, `/schedule`
- `render_discord()` in `gateway/formatter.py` — plain Markdown (no HTML)
- `DISCORD_BOT_TOKEN` in `.env.example` and setup wizard

---

## [0.6.0] - 2026-04-26
### Added
- MCP (Model Context Protocol) integration — `majestic/mcp/client.py`, `bridge.py`
- Supports stdio and SSE MCP servers configured in `config.yaml`
- Auto-wraps MCP tools as native `@tool` entries with `mcp_{server}_{tool}` naming
- `majestic mcp list` — shows all configured servers and their tools
- `majestic mcp add <name> <cmd>` and `majestic mcp remove <name>`

---

## [0.5.0] - 2026-04-26
### Added
- `majestic/tools/history_search.py` — FTS5 search across messages, grouped by session with LLM summarization
- `/history <query>` REPL command — search past conversations
- `/history last [N]` — list last N sessions with one-line summaries
- Session summarization on `/exit` — 1-sentence summary stored in the `sessions` table

---

## [0.4.0] - 2026-04-26
### Added
- OpenAI provider (`majestic/llm/openai.py`) — OpenAI-compatible endpoint, supports GPT-4o, o1, o3-mini
- OpenRouter provider (`majestic/llm/openrouter.py`) — routes to any model with cost fallback
- Automatic Anthropic-to-OpenAI tool schema translation
- `OPENAI_API_KEY`, `OPENROUTER_API_KEY` added to `.env.example`
- Both providers available in `majestic setup` and `/model` selector

---

## [0.3.0] - 2026-04-26
### Added
- REST API server (`majestic/api/server.py`) — stdlib only, no FastAPI dependency
- `POST /chat` — single-turn with `{answer, tools_used, cost_usd, elapsed_s}`
- `POST /run` — fire-and-forget task (202 response)
- `GET /health` — status + version
- `GET /sessions` — list recent sessions
- Optional `api.key` config for `X-API-Key` header auth
- `majestic api start` shell command

---

## [0.2.0] - 2026-04-26
### Added
- `agent.role` config key — extra system prompt block injected into every request
- `agent.tools_enabled` whitelist and `agent.tools_disabled` blacklist
- `/set` REPL command for live config editing without restart
- `majestic setup` wizard exposes role and tool filters

---

## [0.1.0] - 2026-04-25
### Added
- Core agent loop (`majestic/agent/loop.py`) — LLM + tool calls, up to 10 iterations
- SQLite state DB with FTS5 full-text search and sqlite-vec vector chunks
- Persistent memory (`~/.majestic-agent/memory/`) loaded on startup, saved on exit
- Telegram gateway with `allowed_user_ids` whitelist
- Anthropic provider with native tool use
- Ollama provider for local models
- RAG interface — `index_file()`, `ask()`, FTS5 + vector hybrid search
- Built-in tools: web search (DuckDuckGo / Tavily), market data (CoinGecko, forex, Alpha Vantage), file I/O, shell execution
- Research pipeline: HN, Reddit, GitHub, arXiv, Mastodon, Dev.to, Google Trends, NewsAPI
- Cron scheduler with natural-language parsing
- `majestic setup` interactive wizard
- Docker Compose deploy with persistent volume
- Full test suite (110 tests)
