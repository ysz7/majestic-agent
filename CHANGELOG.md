# Changelog

All notable changes to Majestic are documented here.
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

---


## [0.19.1] - 2026-05-04
### Fixed
- Double user messages in chat on new sessions — user message now removed from stream state as soon as DB confirms it via `session_id` SSE event
- Tool result messages (raw search/news content) no longer shown in chat history — `get_session_messages` filters to `user` and `assistant` roles only
- Model selector showing stale model after switching active LLM config — settings query now invalidated alongside `llm-configs` on activation
- Search Mode field in Settings showing blank instead of current value

### Changed
- Ollama: tool list capped at 15 priority tools per request (MCP browser tools excluded) — improves reliability on smaller local models
- Ollama: context window now configurable via Settings → LLM → Context window slider (2 048 – 131 072 tokens in steps)
- Ollama: JSON objects written as plain text are rescued and matched to the correct tool call automatically
- System prompt cached 30 s in memory — reduces redundant file reads across consecutive tool-call iterations
- Monitoring refetch interval 15 s → 30 s

---

## [0.19.0] - 2026-05-04
### Added
- **Job registry** (`majestic/agent/jobs.py`) — all background work (reflection, signal collection, async scripts) runs through a unified `start_job` / `get_job` / `list_jobs` / `cancel_job` API
- `run_script_async` tool — run a saved script in the background; returns `job_id` immediately; delivers a Telegram/email notification on completion when `notify=true`
- `list_jobs` tool — formatted table of recent background jobs with type, status, duration, and result
- `cancel_job` tool — cancel a running background job by id
- Dashboard `/agent` page — unified view of autonomous activity: live job feed, cron schedules with enable/disable and manual-run controls, last reflections, top-10 script stats
- Cost awareness: `[Session budget]` block injected into system prompt shows cumulative tokens and cost for the current session
- `GET /api/jobs`, `POST /api/jobs/<id>/cancel`, `GET /api/jobs/stream` (SSE), `GET /api/reflections`, `GET /api/reflections/<id>`, `GET /api/script-stats` endpoints
- Config keys: `agent.async_notify` (default true), `agent.job_history` (default 200)

---

## [0.18.0] - 2026-05-04
### Added
- **Reflection layer** — after sessions with 3+ tool calls the agent runs a background self-review: what worked, what didn't, reusable patterns, memory suggestions. Results saved to `workspace/.reflections/`. Last 5 reflections injected as `[Recent learnings]` in the system prompt
- **Confidence tags** — every final answer includes `[confidence: high|medium|low]` based on whether the data came from live tools, recent memory, or training knowledge
- `plan_task` tool — agent creates an explicit step-by-step plan for multi-step tasks (required for tasks with 3+ steps)
- `update_step` tool — marks individual plan steps as `in_progress`, `done`, or `blocked`; plan state visible in CLI and dashboard chat
- Config keys: `agent.reflect` (default true), `agent.reflect_min_tools` (default 3), `agent.confidence_tags` (default true)

---

## [0.17.0] - 2026-05-04
### Added
- **Script self-healing** — when `run_script` returns a non-zero exit code the agent automatically analyses stderr, patches the script via `save_script`, and retries (up to 3 iterations). Controlled by `# auto_heal: true` frontmatter (default) and `agent.auto_heal` config key
- **Execution log + metrics** — every script run written to `workspace/scripts/.log.jsonl` with params, exit code, duration, and session id. `[Script library]` prompt block now shows usage counts and last-run date per script
- **Dependency management** — `# requires: <pkg>` frontmatter field; `run_script` checks availability and installs automatically when `agent.auto_install_deps: true` (default)
- **Script versioning** — previous version backed up to `workspace/scripts/.history/<name>_<ts>.py` on every save (last 10 kept); `revert_script` tool restores any version
- **Skill promotion** — scripts used >5 times with >80% success rate surface as promotion candidates in the system prompt; `promote_script_to_skill` tool converts them to a `.yaml` skill file in `~/.majestic-agent/skills/`
- `run_script_async` tool (background execution with job notification)
- Dashboard Scripts tab: History button shows version list; Revert action available per version
- `GET /api/scripts/<name>/history`, `POST /api/scripts/<name>/revert`, `GET /api/scripts/metrics` endpoints
- Config keys: `agent.auto_heal`, `agent.auto_install_deps`

---

## [0.16.0] - 2026-05-04
### Added
- `save_script`, `list_scripts`, `run_script` tools — agent can write reusable Python scripts to `workspace/scripts/` and call them in future sessions
- `agent.allow_scripts` config key (default enabled) — enable/disable script execution; toggle in Settings → Agent
- `[Script library]` block injected into system prompt listing all saved scripts with descriptions
- Scripts API endpoints: `GET /api/scripts`, `POST /api/scripts/run`, `DELETE /api/scripts/<name>`
- Scripts tab in Dashboard Files page with Run/Edit/Delete actions
- Judgment-based system prompt guideline: agent decides when to save scripts based on reusability, not mechanically

---

## [0.15.2] - 2026-05-04
### Added
- Settings → Email tab in dashboard: IMAP/SMTP form, allowed senders editor, "Test connection" button, Start/Stop gateway controls
- Gmail setup guide with auto-fill defaults collapsible block
- `GET /api/email/status`, `POST /api/email/test`, `POST /api/email/start`, `POST /api/email/stop` endpoints

---

## [0.15.1] - 2026-05-04
### Added
- MCP bundle presets: `majestic mcp install browser|github|postgres` — one command adds Playwright, GitHub, or PostgreSQL MCP server to config
- Settings → MCP tab shows all configured servers with enable/disable toggles and tool counts
- `GET /api/mcp/status` endpoint returns active servers and their tool inventory

---

## [0.15.0] - 2026-05-04
### Added
- `run_python` tool — execute Python code in subprocess, stdout/stderr returned; working dir is `WORKSPACE_DIR`
- `http_request` tool — GET/POST any external REST API, auto-formats JSON responses
- `get_datetime` tool — accurate current date/time in any timezone and format
- `remember` tool — explicitly save a fact or preference to persistent memory mid-session
- `send_email` tool — send email via configured SMTP; Markdown body converted to HTML
- `copy_file` tool — copy files within the workspace

---

## [0.14.3] - 2026-05-04
### Added
- `file_artifact` SSE event emitted after each `write_file` tool call
- File artifact badges rendered under assistant messages — icon, filename, download button
- FileViewer component: HTML (sandboxed iframe), Markdown (ReactMarkdown), code (syntax highlight), CSV (table), images, and download fallback
- `write_file` now enforces workspace-relative paths for all absolute paths

---

## [0.14.2] - 2026-05-04
### Added
- Silent Adaptive Layer (`majestic/profile/`) — collects session signals (language, tools used, query length) at zero cost
- `user_profile.yaml` updated every N sessions via single background LLM call
- `[User profile]` block injected into system prompt — agent adapts tone and style automatically
- Config: `profile.enabled`, `profile.update_every`

---

## [0.14.1] - 2026-05-04
### Added
- Chat page redesigned to three-panel layout: Sessions | Agent Graph | Chat
- Agent Graph (SVG-based): Majestic node with status ring, tool call nodes appearing in real time via SSE
- Tool nodes show name, arg preview, and status (running spinner, done ✓, error ✗)
- `AgentGraph` widget subscribes to `tool_call` / `done` SSE events — no new backend endpoints

---

## [0.14.0] - 2026-05-04
### Added
- Dashboard `/files` page (renamed from `/workspace`): breadcrumb navigation, file grid, inline viewer/editor
- File viewer renders text/code, Markdown preview, images, CSV tables; binary files download-only
- Upload file, create folder, delete with confirmation
- Path-traversal protection — root locked to `~/.majestic-agent/workspace/`
- `GET /api/workspace/list`, `GET /api/workspace/file`, `POST /api/workspace/file`, `POST /api/workspace/upload`, `DELETE /api/workspace/file`, `POST /api/workspace/mkdir`

---

## [0.13.4] - 2026-05-04
### Added
- LLM Keys Manager in Settings → LLM: multiple named provider configurations, one-click activation
- Active config applies immediately to all gateways without restart
- Keys stored in `.env` as `LLM_KEY_<NAME>`; `GET /api/llm/configs`, `POST /api/llm/configs`, `POST /api/llm/configs/<name>/activate`, `DELETE /api/llm/configs/<name>`

---

## [0.13.3] - 2026-05-04
### Added
- Dashboard `/tables` page: create/view/edit user SQLite tables with DataTable CRUD
- Agent auto-receives user table schema in `[User tables]` system prompt block
- Dashboard `/monitoring` page: token/cost chart, active schedules, reminders list
- Delete schedule from monitoring UI
- `GET /api/tables`, `POST /api/tables`, rows CRUD, `GET /api/monitoring`, `DELETE /api/schedules/:id`

---

## [0.13.2] - 2026-05-04
### Added
- Dashboard `/settings` page: all `config.yaml` keys editable in form, live system prompt preview
- Dashboard `/memory` page: agent memory editor, user profile editor, skill list with Create/Edit/Delete
- `GET/POST /api/settings`, `GET/POST /api/memory`, skills CRUD endpoints

---

## [0.13.1] - 2026-05-04
### Added
- Dashboard `/chat` page: session sidebar, SSE-streamed chat, tool call cards, New Chat button
- `GET /stream` SSE endpoint streaming `text`, `tool_call`, and `done` events
- `GET /api/sessions`, `GET /api/sessions/:id`, `DELETE /api/sessions/:id`

---

## [0.13.0] - 2026-05-04
### Added
- `majestic dashboard` command — builds React frontend and serves it via the existing API server
- `--dev` flag starts Vite dev server + API in parallel with HMR
- Onboarding wizard at `/onboarding`: LLM provider, basic settings, Telegram (optional)
- `GET /api/setup/status`, `POST /api/setup` endpoints
- Dashboard auth: `dashboard.password` config key; without password only localhost accepted
- Zustand global store + TanStack Query for server state throughout dashboard
- Node.js 20+ requirement; `majestic doctor` and `majestic dashboard` prompt to install if missing

---

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
