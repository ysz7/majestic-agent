import asyncio
import time


def run(profile_name: str = "default", tui: bool = False):
    """Run agent in foreground mode — plain CLI by default, TUI with --tui."""
    if tui:
        try:
            from majestic.cli.tui.app import MajesticApp
        except ImportError:
            import majestic.display as display
            display.warn("textual not installed — falling back to plain mode.")
            display.info("Install with: pip install textual")
            asyncio.run(_run_plain(profile_name))
            return
        app = MajesticApp(profile_name)
        app.run()
    else:
        asyncio.run(_run_plain(profile_name))


async def _run_plain(profile_name: str):
    from majestic.config.settings import Settings
    from majestic.memory.working import WorkingMemory
    from majestic.memory.semantic import SemanticMemory
    from majestic.memory.episodic import EpisodicMemory
    from majestic.core.gateway import Gateway
    from majestic.channels.cli import CLIChannel
    from majestic.core.runtime import AgentRuntime
    from majestic.llm.router import LLMRouter
    from majestic.system.startup import StartupManager
    from majestic import display
    import uuid

    settings = Settings(profile_name)
    settings.validate()

    session_id = str(uuid.uuid4())[:8]
    working_memory = WorkingMemory()
    channel = CLIChannel(session_id=session_id)
    llm_router = LLMRouter(settings)

    # Memory systems wired into gateway for per-request RAG
    _semantic = SemanticMemory(str(settings.data_dir / "semantic.db"))
    _episodic = EpisodicMemory(str(settings.data_dir / "episodic.db"))

    startup = StartupManager(settings)
    incomplete = await startup.run()

    if incomplete:
        display.warn(f"{len(incomplete)} incomplete task(s) found — will resume on next run.")

    display.print_startup(profile_name, "foreground")

    # Register profile skills as slash-command completions
    try:
        from majestic.memory.procedural import ProceduralMemory
        pm = ProceduralMemory(str(settings.skills_dir))
        channel.set_skill_completions([s.get("name", "") for s in pm.get_all()])
    except Exception:
        pass

    gateway = Gateway(settings, working_memory, channel,
                      episodic_memory=_episodic,
                      semantic_memory=_semantic)

    runtime = _build_runtime(settings, working_memory, llm_router)
    runtime = _register_tools(runtime, settings, semantic=_semantic)

    _last_stats: dict | None = None

    while True:
        try:
            raw = await channel.receive()
        except (EOFError, KeyboardInterrupt):
            print("\nGoodbye!")
            break

        text = raw.get("text", "").strip()
        if not text:
            continue
        if text.lower() in ("/exit", "/quit", "exit", "quit"):
            display.ok("Goodbye!")
            break

        if text.startswith("/"):
            slash_result = await _handle_slash_plain(
                text, profile_name, working_memory, runtime, settings,
                semantic=_semantic, channel=channel, gateway=gateway,
            )
            if slash_result is True:
                continue
            elif isinstance(slash_result, str):
                text = slash_result  # skill expanded to task

        # Show previous task stats right below the user's input line
        if _last_stats:
            display.inline_stats(**_last_stats)

        working_memory.add_message("user", text)
        print()

        # Per-request enriched system prompt: persona + episodic history + semantic RAG
        system_prompt = gateway._build_enriched_system_prompt(text)

        t0 = time.monotonic()
        try:
            result = await runtime.run(
                task=text,
                system_prompt=system_prompt,
            )
        except Exception as exc:
            result = f"Error: {exc}"
        elapsed = time.monotonic() - t0

        _last_stats = {
            "tokens":  getattr(runtime, "_tokens_used", 0),
            "cost":    getattr(runtime, "_cost_used", 0.0),
            "elapsed": elapsed,
        }

        await channel.send(f"\n{result}\n")
        working_memory.add_message("assistant", result)


async def _handle_slash_plain(text: str, profile_name: str, working_memory, runtime, settings=None, semantic=None, channel=None, gateway=None):
    """Handle a slash command in plain CLI.

    Returns:
        True  — handled, skip to next message.
        str   — skill expanded to a task string; caller runs it through runtime.
        False — not a known command, pass original text to agent.
    """
    try:
        from rich.console import Console
        console = Console()
    except ImportError:
        console = None

    def out(markup: str) -> None:
        if console:
            console.print(markup)
        else:
            print(markup)

    cmd = text.strip().lower().split()[0]

    if cmd == "/help":
        from majestic.cli.tui.commands import SLASH_COMMANDS
        out("[bold]Available commands:[/bold]")
        for c, desc in SLASH_COMMANDS.items():
            out(f"  [cyan]{c:<10}[/cyan]  [dim]{desc}[/dim]")
        return True

    if cmd == "/skills":
        try:
            from majestic.display import _gather_startup
            d = _gather_startup(profile_name)
            skills = d.get("skills", [])
            if not skills:
                out("[dim]No skills loaded yet. Add YAML files to profiles/<name>/skills/[/dim]")
            else:
                out("[bold]Loaded skills:[/bold]")
                for sk in skills:
                    name = sk.get("name", "?")
                    raw  = sk.get("description", "")
                    desc = (raw[:57] + "…") if len(raw) > 60 else raw
                    out(f"  [cyan]/{name:<18}[/cyan] [dim]{desc}[/dim]")
        except Exception as e:
            out(f"[red]Error: {e}[/red]")
        return True

    if cmd == "/tools":
        tools = list(getattr(runtime, "tools", {}).keys())
        if not tools:
            out("[dim]No tools registered.[/dim]")
        else:
            out("[bold]Available tools:[/bold]")
            for t in tools:
                out(f"  [cyan]{t}[/cyan]")
        return True

    if cmd == "/research":
        from majestic import display as _display
        out("[dim]Connecting to curated sources…[/dim]")
        _display.tree_reset()

        def _on_source(name: str, count: int, success: bool) -> None:
            if success:
                _display.tree_step(name, f"{count} article{'s' if count != 1 else ''}")
            else:
                _display.tree_step(name, "no response", status="warn")

        try:
            from majestic.tools.research import fetch_all
            from majestic.tools.research.db import ResearchDB
            articles, ok_sources, failed = await fetch_all(on_source=_on_source)
        except Exception as e:
            out(f"[red]Fetch error: {e}[/red]")
            return True

        # Store to profile DB — only new (unseen) articles go to the agent
        new_articles: list[dict] = articles
        if settings is not None:
            try:
                db = ResearchDB(str(settings.data_dir / "research.db"))
                new_articles, skipped = db.insert_articles(articles)
                stats = db.stats()
                db.close()
                _display.tree_step(
                    "saved",
                    f"{len(new_articles)} new · {skipped} cached · {stats['total']} total",
                )
            except Exception as e:
                out(f"[yellow]DB warning: {e}[/yellow]")

            # Index new articles into semantic memory so future queries can find them
            if semantic is not None and new_articles:
                try:
                    for a in new_articles:
                        chunk = f"{a['title']}. {a.get('summary', '')}"
                        semantic.index(
                            source=a.get("url") or a.get("source", "research"),
                            content=chunk,
                        )
                except Exception:
                    pass

        _display.tree_close("sending to agent…")

        if not articles:
            out("[dim]No articles fetched. Check your internet connection.[/dim]")
            return True

        if not new_articles:
            out("[dim]No new articles since last /research. Use /briefing to analyze stored news.[/dim]")
            return True

        # Build prompt — only newly fetched articles (not cached ones)
        lines = [
            f"Here are {len(new_articles)} NEW articles just fetched from {len(ok_sources)} sources "
            f"(previously seen articles were excluded):\n"
        ]
        for a in new_articles[:40]:
            lines.append(f"[{a.get('category','?').upper()}] {a.get('source','?')} · {a.get('date','')}:")
            lines.append(f"  {a.get('title','')}")
            if a.get("summary"):
                lines.append(f"  {a.get('summary','')[:180]}")
            lines.append("")
        lines.append(
            "\nWrite a concise briefing of these NEW articles only. "
            "Structure it as: 1) Top stories right now, 2) Tech & AI, "
            "3) Business & Finance, 4) Science & World. "
            "Be specific, mention real names and numbers. Under 400 words."
        )
        return "\n".join(lines)

    if cmd == "/briefing":
        from majestic import display as _display
        words = text.strip().split()
        days = 30
        if len(words) > 1:
            try:
                days = int(words[1])
            except ValueError:
                pass

        if settings is None:
            out("[red]No settings — briefing requires a profile.[/red]")
            return True

        try:
            from majestic.tools.research.db import ResearchDB
            db = ResearchDB(str(settings.data_dir / "research.db"))
            articles = db.get_articles(days=days)
            stats = db.stats()
            db.close()
        except Exception as e:
            out(f"[red]DB error: {e}[/red]")
            return True

        if not articles:
            out(f"[dim]No articles in database for the last {days} days. Run /research first.[/dim]")
            return True

        from collections import defaultdict

        # ── 1. Sort newest-first within each article (iso dates sort lexicographically)
        articles.sort(key=lambda a: a.get("date", ""), reverse=True)

        # ── 2. Deduplicate near-identical titles (keep first/newest occurrence)
        def _title_key(title: str) -> str:
            import re as _re
            words_t = _re.sub(r"[^a-z0-9 ]", "", title.lower()).split()
            return " ".join(words_t[:8])  # first 8 normalized words as fingerprint

        seen_keys: set[str] = set()
        deduped: list[dict] = []
        for a in articles:
            key = _title_key(a.get("title", ""))
            if key and key not in seen_keys:
                seen_keys.add(key)
                deduped.append(a)
        articles = deduped

        # ── 3. Group by category
        by_cat: dict[str, list] = defaultdict(list)
        for a in articles:
            by_cat[a.get("category", "general")].append(a)

        _display.tree_reset()
        _display.tree_step("Research DB", f"{stats['total']} total · last {days}d: {len(articles)} articles (deduped)")
        for cat, items in by_cat.items():
            _display.tree_step(cat.title(), f"{len(items)} articles")

        # ── 4. Build corpus, capping at ~60K chars to stay within token budget
        _MAX_CORPUS_CHARS = 60_000
        corpus_lines: list[str] = []
        corpus_chars = 0
        capped = False

        for cat, items in by_cat.items():
            corpus_lines.append(f"=== {cat.upper()} ({len(items)} articles) ===")
            corpus_chars += len(corpus_lines[-1])
            for a in items[:30]:
                entry = f"· [{a.get('date','')}] {a.get('source','')}: {a.get('title','')}"
                corpus_lines.append(entry)
                corpus_chars += len(entry)
                if a.get("summary"):
                    summary_line = f"  {a.get('summary','')[:300]}"
                    corpus_lines.append(summary_line)
                    corpus_chars += len(summary_line)
                if corpus_chars >= _MAX_CORPUS_CHARS:
                    corpus_lines.append("  [corpus truncated — token budget limit]")
                    capped = True
                    break
            corpus_lines.append("")
            if capped:
                break

        article_count_note = f"{len(articles)} articles" + (" (truncated for token budget)" if capped else "")
        lines = [f"INTELLIGENCE CORPUS — {article_count_note}, last {days} days\n"]
        lines.extend(corpus_lines)

        instructions = (
            f"Produce the 4-section intelligence briefing below. "
            f"Rules: (1) use ONLY facts from the corpus above; (2) cite source + date for every claim; "
            f"(3) actors/themes appearing in multiple categories are strongest signals — prioritize them.\n\n"

            f"## SECTION 1 — WORLD PICTURE\n\n"
            f"Write a macro synthesis — NOT a list of headlines. Identify 3–4 underlying structural forces "
            f"that explain MOST of what you see across ALL categories together. Connect geopolitics, technology, "
            f"economy, and society into one coherent narrative. What is quietly shifting that most people "
            f"aren't noticing? Ground every claim in specific evidence from the corpus.\n\n"

            f"---\n\n"

            f"## SECTION 2 — MONEY FLOWS\n\n"
            f"Map where capital is moving. For each significant flow use this format:\n\n"
            f"**ENTERING [sector/asset class]**\n"
            f"- Actor: [exact name from articles] — what they are doing\n"
            f"- Evidence: (source, date)\n"
            f"- Scale: dollar amounts or size signals if mentioned in articles\n\n"
            f"**LEAVING [sector/asset class]**\n"
            f"- Actor: [exact name from articles] — why they are exiting\n"
            f"- Evidence: (source, date)\n\n"
            f"Then give market signals:\n\n"
            f"**BUY** [asset/sector] — evidence: (source)\n"
            f"**HOLD** [asset] — rationale from corpus\n"
            f"**SELL / AVOID** [asset] — risk signal from corpus\n\n"
            f"Cover equities, crypto, commodities, bonds — only where articles give a signal. "
            f"Do not include assets with no corpus evidence.\n\n"

            f"---\n\n"

            f"## SECTION 3 — PREDICTIONS & PROBABILITIES\n\n"
            f"Cross-correlate independent signals pointing the same direction. "
            f"Calibration: 1 signal = 30–50%, 2 independent = 50–65%, 3 = 65–80%, 4+ = 80–88% max.\n\n"
            f"For each prediction:\n\n"
            f"**[EVENT STATEMENT]** — **XX%**\n"
            f"- Horizon: near-term (1–4 wks) / medium (1–3 mo) / long-term (6–12 mo)\n"
            f"- Signals: list each supporting article (source, date)\n"
            f"- Winners / Losers if this happens\n"
            f"- Invalidation: what single event would kill this prediction\n\n"
            f"Generate 5–7 predictions ranked highest to lowest probability. "
            f"Only include predictions directly traceable to articles above.\n\n"

            f"---\n\n"

            f"## SECTION 4 — TOP 3 HIGH-CONVICTION IDEAS\n\n"
            f"Find ideas at the intersection of 2+ trends in different categories — "
            f"timing arbitrage opportunities created by specific news events. For each:\n\n"
            f"**#N — [IDEA NAME]** — [one-sentence concept]\n\n"
            f"- **News trigger**: specific event(s) opening this window right now (source, date)\n"
            f"- **Why this timing is unique**: what changes in 3–6 months that closes the window\n"
            f"- **Market signal**: what the corpus tells us about size and demand\n"
            f"- **Key risk**: main threat — cite any warning signal from corpus\n"
            f"- **Kill check**: what must be true in 30 days or this is dead on arrival\n"
            f"- **Success probability**: XX% — reasoning chain from corpus signals\n\n"
            f"Rank #1 highest → #3 lowest probability.\n\n"
            f"---\n\n"
            f"End with one sentence: the single most underappreciated insight in this corpus."
        )
        lines.append(instructions)
        prompt = "\n".join(lines)

        # ── 5. Direct LLM call — no ReAct loop, no tool injection (all data is in the corpus)
        import time as _time
        from datetime import date as _date
        _t0 = _time.monotonic()

        _system = (
            "You are a world-class intelligence analyst. "
            "Your response MUST begin with the exact text '## SECTION 1 — WORLD PICTURE' "
            "as your very first characters — nothing before it. "
            "No preamble. No meta-commentary. No reasoning narration. No 'Let me', 'We need', 'First I will'. "
            "Use ONLY facts from the corpus. Cite (source, date) for every claim."
        )
        _messages = [
            {"role": "system", "content": _system},
            {"role": "user",   "content": prompt},
        ]

        try:
            with _display.TreePending("analyzing…"):
                _response = await runtime.llm.chat(_messages, step_type="reason")
            _display.tree_close()
            result = _response.get("content", "")
            _in  = _response.get("input_tokens", 0)
            _out = _response.get("output_tokens", 0)
            runtime._tokens_used = _in + _out
            # Cost: use router value or estimate from tokens
            _cost = _response.get("cost") or 0.0
            if not _cost and (_in or _out):
                try:
                    from majestic.llm.base import BaseLLM
                    _cost = BaseLLM._estimate_cost(_in, _out)
                except Exception:
                    pass
            runtime._cost_used = _cost
        except Exception as exc:
            _display.tree_close("error")
            result = f"Error: {exc}"
            _cost = 0.0
        _elapsed = _time.monotonic() - _t0

        # ── 6. Strip any preamble — keep from first "## SECTION" header
        import re as _re
        _section_match = _re.search(r'##\s*SECTION\s*1', result, _re.IGNORECASE)
        if _section_match:
            result = result[_section_match.start():]

        # ── 7. Save briefing to workspace/briefings/YYYY-MM-DD.md
        try:
            briefings_dir = settings.workspace_dir / "briefings"
            briefings_dir.mkdir(parents=True, exist_ok=True)
            fname = briefings_dir / f"{_date.today().isoformat()}.md"
            fname.write_text(result, encoding="utf-8")
            _display.tree_reset()
            _display.tree_step("saved", f"{fname.name}")
            _display.tree_close()
        except Exception:
            pass

        # Display result and stats
        if channel is not None:
            await channel.send(f"\n{result}\n")
        else:
            out(result)

        from majestic import display as _d
        _d.inline_stats(
            tokens=getattr(runtime, "_tokens_used", 0),
            cost=getattr(runtime, "_cost_used", 0.0),
            elapsed=_elapsed,
        )
        return True

    if cmd == "/news":
        words = text.strip().split()
        days = 7
        if len(words) > 1:
            try:
                days = int(words[1])
            except ValueError:
                pass

        if settings is None:
            out("[dim]News requires a profile with a research DB. Run /research first.[/dim]")
            return True

        try:
            from majestic.tools.research.db import ResearchDB
            db = ResearchDB(str(settings.data_dir / "research.db"))
            articles = db.get_articles(days=days)
            db.close()
        except Exception as e:
            out(f"[red]DB error: {e}[/red]")
            return True

        if not articles:
            out(f"[dim]No articles for the last {days} days. Run /research first.[/dim]")
            return True

        from collections import defaultdict
        by_cat: dict[str, list] = defaultdict(list)
        for a in articles:
            by_cat[a.get("category", "general")].append(a)

        out(f"\n[bold]NEWS[/bold]  [dim]· last {days} days · {len(articles)} articles[/dim]\n")
        for cat in sorted(by_cat):
            items = by_cat[cat]
            dashes = "─" * max(0, 48 - len(cat))
            out(f"  [bold cyan]{cat.upper()}[/bold cyan]  [dim]{dashes}[/dim]")
            for a in items[:25]:
                date   = a.get("date", "")
                title  = (a.get("title", "")[:68] + "…") if len(a.get("title","")) > 68 else a.get("title","")
                source = a.get("source", "")
                url    = a.get("url", "")
                url_d  = url.replace("https://","").replace("http://","")
                url_d  = (url_d[:66] + "…") if len(url_d) > 66 else url_d
                out(f"  [dim]{date}[/dim]  {title}  [dim]· {source}[/dim]")
                if url_d:
                    out(f"  [dim]          {url_d}[/dim]")
            if len(items) > 25:
                out(f"  [dim]          … and {len(items) - 25} more[/dim]")
            out("")
        return True

    if cmd == "/agents":
        try:
            import json
            from pathlib import Path
            reg = Path(__file__).resolve().parent.parent.parent / "data" / "registry.json"
            if not reg.exists():
                out("[dim]No background agents running. Start one with: majestic run <profile>[/dim]")
            else:
                data = json.loads(reg.read_text())
                if not data:
                    out("[dim]No background agents running. Start one with: majestic run <profile>[/dim]")
                else:
                    out("[bold]Running agents:[/bold]")
                    for name, info in data.items():
                        port = info.get("port", "?")
                        status = info.get("status", "?")
                        dot = "[green]●[/green]" if status == "running" else "[yellow]●[/yellow]"
                        out(f"  {dot} [bold]{name}[/bold]  [dim]:{port}  {status}[/dim]")
        except Exception as e:
            out(f"[red]Error: {e}[/red]")
        return True

    if cmd == "/memory":
        try:
            from majestic.display import _gather_startup
            d = _gather_startup(profile_name)
            mem = d.get("mem_count", 0)
            les = d.get("lessons_count", 0)
            out(
                f"[bold]Memory:[/bold]\n"
                f"  [dim]episodic · [/dim]{mem} tasks\n"
                f"  [dim]lessons  · [/dim]{les}\n"
                f"  [dim]semantic · [/dim]sqlite-vec"
            )
        except Exception as e:
            out(f"[red]Error: {e}[/red]")
        return True

    if cmd == "/budget":
        tokens = getattr(runtime, "_tokens_used", 0)
        cost = getattr(runtime, "_cost_used", 0.0)
        out(
            f"[bold]Budget:[/bold]\n"
            f"  [dim]tokens · [/dim]{tokens:,}\n"
            f"  [dim]cost   · [/dim]${cost:.4f}"
        )
        return True

    if cmd == "/new":
        working_memory.clear()
        out("[dim]Session cleared.[/dim]")
        return True

    # Skill invocation: /skill_name [optional user input]
    if settings is not None:
        try:
            from majestic.memory.procedural import ProceduralMemory
            pm = ProceduralMemory(str(settings.skills_dir))
            skill_map = {s.get("name", ""): s for s in pm.get_all()}
            cmd_name = cmd.lstrip("/")
            if cmd_name in skill_map:
                skill = skill_map[cmd_name]
                words = text.strip().split(None, 1)
                user_input = words[1].strip() if len(words) > 1 else ""
                lines = [skill.get("description", skill["name"])]
                steps = skill.get("steps", [])
                if steps:
                    lines.append("\nFollow these steps:")
                    lines.extend(f"  - {s}" for s in steps)
                if user_input:
                    lines.append(f"\nUser input: {user_input}")
                print()
                out(f"  [dim]Running skill:[/dim] [bold]{cmd_name}[/bold]")
                return "\n".join(lines)
        except Exception:
            pass

    return False


def _build_runtime(settings, working_memory, llm_router) -> "AgentRuntime":
    """Instantiate AgentRuntime with the full self-evolution stack wired up."""
    from majestic.core.runtime import AgentRuntime
    from majestic.memory.lessons import LessonsStore
    from majestic.memory.episodic import EpisodicMemory
    from majestic.memory.checkpoints import CheckpointStore
    from majestic.core.script_tracker import ScriptTracker
    from majestic.core.skill_writer import SkillWriter
    from majestic.core.self_evolution import SelfEvolution
    from majestic.core.reflection import ReflectionEngine
    from majestic.core.planner import Planner

    data_dir   = settings.data_dir
    skills_dir = settings.skills_dir
    workspace  = settings.workspace_dir

    lessons_store   = LessonsStore(str(data_dir / "lessons.db"))
    episodic_memory = EpisodicMemory(str(data_dir / "episodic.db"))
    checkpoint_store = CheckpointStore(str(data_dir / "checkpoints.db"))
    script_tracker  = ScriptTracker(str(data_dir / "script_tracker.db"))

    skill_writer = SkillWriter(llm_router, str(skills_dir))
    evolution    = SelfEvolution(
        llm_router=llm_router,
        skill_writer=skill_writer,
        script_tracker=script_tracker,
        lessons_store=lessons_store,
        workspace_dir=str(workspace),
    )
    reflection_engine = ReflectionEngine(
        llm_router=llm_router,
        lessons_store=lessons_store,
        episodic_memory=episodic_memory,
        self_evolution=evolution,
    )
    planner = Planner(settings, llm_router, lessons_store)

    return AgentRuntime(
        settings=settings,
        working_memory=working_memory,
        llm_router=llm_router,
        checkpoint_store=checkpoint_store,
        reflection_engine=reflection_engine,
        planner=planner,
        hitl_enabled=False,
    )


def _register_tools(runtime, settings, semantic=None):
    workspace = settings.workspace_dir
    brave_key = settings.brave_search_api_key

    from majestic.tools.web_search.search import search as web_search_fn
    from majestic.tools.web_fetch import fetch as web_fetch_fn
    from majestic.tools.http import get as http_get, post as http_post
    from majestic.tools.files import FilesTool
    from majestic.tools.python_exec.executor import PythonExecutor
    from majestic.tools.node_exec.executor import NodeExecutor
    from majestic.tools.agent_client import AgentClient
    from majestic.tools.research import research as research_fn
    from majestic.core.script_tracker import ScriptTracker
    from pathlib import Path

    # Reuse the tracker wired into the reflection engine so counts persist
    script_tracker: ScriptTracker | None = None
    try:
        script_tracker = runtime._reflection.evolution.tracker
    except AttributeError:
        pass

    files     = FilesTool(workspace)
    py_exec   = PythonExecutor(str(settings.profile_dir), script_tracker=script_tracker)
    node_exec = NodeExecutor(str(settings.profile_dir),   script_tracker=script_tracker)
    agent_client = AgentClient()

    tools_dir = settings.tools_dir  # auto-creates workspace/tools/

    async def web_search_tool(query: str, max_results: int = 5):
        """Search the web for information."""
        results = await web_search_fn(query, max_results, brave_api_key=brave_key)
        # Index results into semantic memory for future RAG retrieval
        if semantic is not None and isinstance(results, list):
            for r in results:
                try:
                    chunk = " ".join(filter(None, [
                        r.get("title", ""), r.get("snippet", ""), r.get("description", ""),
                    ]))
                    if chunk:
                        semantic.index(source=r.get("url", query), content=chunk)
                except Exception:
                    pass
        return results

    async def list_scripts() -> list[str]:
        """List reusable scripts in workspace/tools/. Always call before writing new code."""
        scripts = [p.name for p in sorted(tools_dir.iterdir()) if p.suffix in (".py", ".js")]
        return scripts if scripts else ["(no scripts yet)"]

    async def run_script(filename: str) -> str:
        """Run a saved script from workspace/tools/ by filename. Use list_scripts first."""
        script = tools_dir / filename
        if not script.exists():
            return f"Error: '{filename}' not found. Available: {[p.name for p in tools_dir.iterdir() if p.suffix in ('.py', '.js')]}"
        code = script.read_text(encoding="utf-8")
        if filename.endswith(".js"):
            return await node_exec.run(code)
        return await py_exec.run(code)

    async def delegate_to_agent(agent_name: str, task: str):
        """Delegate a task to a background agent (fire-and-forget — no result returned here)."""
        await agent_client.ensure_running(agent_name)
        resp = await agent_client.delegate(agent_name, task)
        return (
            f"Task accepted by agent '{agent_name}' (task_id={resp.get('task_id', '?')}). "
            "Processing in background — no result returned. Synthesize your answer now."
        )

    runtime.tools = {
        "web_search":        web_search_tool,
        "web_fetch":         web_fetch_fn,
        "http_get":          http_get,
        "http_post":         http_post,
        "file_read":         files.read,
        "file_write":        files.write,
        "file_list":         files.list,
        "python_exec":       py_exec.run,
        "node_exec":         node_exec.run,
        "list_scripts":      list_scripts,
        "run_script":        run_script,
        "research":          research_fn,
        "list_agents":       agent_client.list_profiles_with_roles,
        "delegate_to_agent": delegate_to_agent,
    }

    return runtime
