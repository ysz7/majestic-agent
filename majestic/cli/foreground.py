import asyncio
import sys
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

    settings = Settings(profile_name)
    settings.validate()

    session_id = "main"

    # Persistent working memory when enabled in persona.yaml
    _wm_db = str(settings.data_dir / "working.db") if settings.working_persistent else None
    working_memory = WorkingMemory(db_path=_wm_db, session_id=session_id)

    channel = CLIChannel(session_id=session_id)
    llm_router = LLMRouter(settings)

    from majestic.memory.user_profile import UserProfile
    from majestic.memory.procedural import ProceduralMemory

    # Memory systems wired into gateway for per-request RAG
    _semantic = SemanticMemory(str(settings.data_dir / "semantic.db"))
    _episodic = EpisodicMemory(str(settings.data_dir / "episodic.db"))
    _user_profile = UserProfile(str(settings.data_dir / "user_profile.db"))

    startup = StartupManager(settings)
    incomplete = await startup.run()

    if incomplete:
        display.warn(f"{len(incomplete)} incomplete task(s) found — will resume on next run.")

    display.print_startup(profile_name, "foreground")

    # Register profile skills as slash-command completions
    _pm = None
    try:
        _shared = str(settings.shared_skills_dir)
        _pm = ProceduralMemory(str(settings.skills_dir), shared_dir=_shared)
        channel.set_skill_completions([s.get("name", "") for s in _pm.get_all()])
    except Exception:
        pass

    gateway = Gateway(settings, working_memory, channel,
                      episodic_memory=_episodic,
                      semantic_memory=_semantic,
                      user_profile=_user_profile)

    def _stream_cb(token: str) -> None:
        sys.stdout.write(token)
        sys.stdout.flush()

    _stream_callback = _stream_cb if settings.streaming else None
    runtime = _build_runtime(
        settings, working_memory, llm_router,
        stream_callback=_stream_callback,
        semantic=_semantic,
        user_profile=_user_profile,
        procedural_memory=_pm,
    )
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


def _build_news_corpus(
    articles: list[dict],
    max_chars: int = 50_000,
    include_summaries: bool = True,
) -> tuple[list[str], bool]:
    """Deduplicate, group by category, build a token-budget-aware corpus. Returns (lines, capped)."""
    import re as _re
    from collections import defaultdict as _dd

    articles = sorted(articles, key=lambda a: a.get("date", ""), reverse=True)

    seen: set[str] = set()
    deduped: list[dict] = []
    for a in articles:
        k = " ".join(_re.sub(r"[^a-z0-9 ]", "", a.get("title", "").lower()).split()[:8])
        if k and k not in seen:
            seen.add(k)
            deduped.append(a)

    by_cat: dict = _dd(list)
    for a in deduped:
        by_cat[a.get("category", "general")].append(a)

    lines: list[str] = []
    chars = 0
    capped = False
    for cat, items in by_cat.items():
        header = f"=== {cat.upper()} ({len(items)} articles) ==="
        lines.append(header)
        chars += len(header)
        for a in items[:30]:
            entry = f"· [{a.get('date','')}] {a.get('source','')}: {a.get('title','')}"
            lines.append(entry)
            chars += len(entry)
            if include_summaries and a.get("summary"):
                s = f"  {a.get('summary','')[:300]}"
                lines.append(s)
                chars += len(s)
            if chars >= max_chars:
                capped = True
                break
        lines.append("")
        if capped:
            break
    return lines, capped


def _load_recent_briefing(settings, max_days: int = 3) -> str | None:
    """Return the most recent saved briefing within max_days, or None."""
    from datetime import date as _d, timedelta as _td
    try:
        bd = settings.workspace_dir / "briefings"
        if not bd.exists():
            return None
        today = _d.today()
        for delta in range(max_days + 1):
            f = bd / f"{(today - _td(days=delta)).isoformat()}.md"
            if f.exists():
                content = f.read_text(encoding="utf-8")
                if content.strip():
                    return content
    except Exception:
        pass
    return None


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
        _lang = getattr(settings, "agent_language", "") or "en"
        _lang_note = (
            f" Respond in {_lang}. Article titles may stay in original language."
            if _lang and _lang.lower() not in ("en", "english") else ""
        )
        lines.append(
            f"\nWrite a concise briefing of these NEW articles only.{_lang_note} "
            "Structure it as: 1) Top stories right now, 2) Tech & AI, "
            "3) Business & Finance, 4) Science & World. "
            "Be specific, mention real names and numbers. Under 400 words."
        )
        return "\n".join(lines)

    if cmd == "/pains":
        from majestic import display as _display
        from majestic.tools.pains.db import PainsDB
        words = text.strip().split()
        _pains_days: int | None = None
        if len(words) > 1:
            try:
                _pains_days = int(words[1])
            except ValueError:
                pass

        # DB-read mode: return stored pain points for the last N days (no network fetch)
        if _pains_days is not None:
            if settings is None:
                out("[dim]No profile loaded — cannot read from pains DB.[/dim]")
                return True
            try:
                _pdb_r = PainsDB(str(settings.data_dir / "pains.db"))
                _stored_pains = _pdb_r.get_pains(days=_pains_days)
                _pdb_r.close()
            except Exception as e:
                out(f"[red]DB error: {e}[/red]")
                return True
            if not _stored_pains:
                out(f"[dim]No pain points in DB for the last {_pains_days} days. Run /pains (no args) to scan sources.[/dim]")
                return True
            from collections import defaultdict as _ddict2
            _by_dom: dict = _ddict2(list)
            for _p in _stored_pains:
                _by_dom[_p.get("domain", "other")].append(_p)
            _lines = [f"\n## Pain Radar — {len(_stored_pains)} stored · last {_pains_days}d\n"]
            for _dom, _items in sorted(_by_dom.items(), key=lambda x: -len(x[1])):
                _lines.append(f"### {_dom.upper()} ({len(_items)})")
                for _p in _items[:6]:
                    _src = f"[{_p.get('source', '')}] " if _p.get("source") else ""
                    _lines.append(f"- {_src}{_p.get('pain_text', '')}")
                _lines.append("")
            _result_pains = "\n".join(_lines)
            if channel is not None:
                await channel.send(_result_pains)
            else:
                out(_result_pains)
            return True

        # Fresh-fetch mode: scan sources, extract, store, display new pains
        out("[dim]Scanning pain-signal sources…[/dim]")
        _display.tree_reset()

        def _on_pain_source(name: str, count: int, success: bool) -> None:
            if success:
                _display.tree_step(name, f"{count} post{'s' if count != 1 else ''}")
            else:
                _display.tree_step(name, "no response", status="warn")

        try:
            from majestic.tools.pains import fetch_all as _pains_fetch_all, extract_pains as _extract_pains
            posts, ok_sources, failed = await _pains_fetch_all(on_source=_on_pain_source)
        except Exception as e:
            out(f"[red]Fetch error: {e}[/red]")
            return True

        if not posts:
            out("[dim]No posts fetched. Check your internet connection.[/dim]")
            return True

        # Store to DB — only new (unseen) posts go to LLM extraction
        new_posts: list[dict] = posts
        _pdb = None
        if settings is not None:
            try:
                _pdb = PainsDB(str(settings.data_dir / "pains.db"))
                new_posts, skipped = _pdb.insert_posts(posts)
                _display.tree_step(
                    "saved",
                    f"{len(new_posts)} new · {skipped} cached",
                )
            except Exception as e:
                out(f"[yellow]DB warning: {e}[/yellow]")

        if not new_posts:
            out("[dim]No new posts since last /pains. Run /briefing to see pain analysis.[/dim]")
            if _pdb:
                _pdb.close()
            return True

        # Batch LLM extraction — one call for all new posts
        _pains_lang = getattr(settings, "agent_language", "en") or "en"
        pains: list[dict] = []
        try:
            with _display.TreePending(f"extracting pains from {min(len(new_posts), 60)} posts…"):
                pains = await _extract_pains(new_posts, runtime.llm, lang=_pains_lang)
        except Exception as e:
            out(f"[yellow]Extraction warning: {e}[/yellow]")

        if _pdb and pains:
            try:
                n = _pdb.insert_pains(pains)
                stats = _pdb.stats()
                _display.tree_step(
                    "pains",
                    f"{n} extracted · {stats['total_pains']} total in DB",
                )
            except Exception as e:
                out(f"[yellow]Pain save warning: {e}[/yellow]")

        if _pdb:
            _pdb.close()

        _display.tree_close()

        if not pains:
            out("[dim]No pain points extracted from new posts.[/dim]")
            return True

        # Immediate summary grouped by domain
        from collections import defaultdict as _ddict
        by_domain: dict = _ddict(list)
        for p in pains:
            by_domain[p.get("domain", "other")].append(p)

        summary_lines = [f"\n## Pain Radar — {len(pains)} pain points · {len(ok_sources)} sources\n"]
        for domain, items in sorted(by_domain.items(), key=lambda x: -len(x[1])):
            summary_lines.append(f"### {domain.upper()} ({len(items)})")
            for p in items[:6]:
                src_tag = f"[{p.get('source', '')}] " if p.get("source") else ""
                summary_lines.append(f"- {src_tag}{p.get('pain_text', '')}")
            summary_lines.append("")

        result_text = "\n".join(summary_lines)
        if channel is not None:
            await channel.send(result_text)
        else:
            out(result_text)
        return True

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

        # ── 2–4. Deduplicate, group by category, build token-bounded corpus
        corpus_lines, capped = _build_news_corpus(articles, max_chars=60_000, include_summaries=True)

        _display.tree_reset()
        _display.tree_step("Research DB", f"{stats['total']} total · last {days}d: {len(articles)} articles")

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

        _lang = getattr(settings, "agent_language", "") or "en"
        _is_non_en = _lang and _lang.lower() not in ("en", "english")
        _lang_rule = (
            f"LANGUAGE: Write the ENTIRE response in {_lang}, including all section headings and labels. "
            "Source/article titles may remain in their original language. "
        ) if _is_non_en else ""
        _system = (
            f"{_lang_rule}"
            "You are a world-class intelligence analyst. "
            "Your response MUST begin with a '##' section header — nothing before it. "
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

        # ── 6. Strip any preamble — keep from first '##' heading
        import re as _re
        _section_match = _re.search(r'^##', result, _re.MULTILINE)
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

    if cmd == "/ideas":
        from majestic import display as _display
        words = text.strip().split()
        days = 30
        if len(words) > 1:
            try:
                days = int(words[1])
            except ValueError:
                pass

        if settings is None:
            out("[red]No settings — /ideas requires a profile.[/red]")
            return True

        # LAYER 2: Pain signals (required)
        try:
            from majestic.tools.pains.db import PainsDB as _PainsDB2
            _idb = _PainsDB2(str(settings.data_dir / "pains.db"))
            _ideas_pains = _idb.get_pains(days=days)
            _idb.close()
        except Exception as e:
            out(f"[red]Pains DB error: {e}[/red]")
            return True

        if not _ideas_pains:
            out(f"[dim]No pain points for the last {days} days. Run /pains first.[/dim]")
            return True

        # LAYER 3: Market signals — news with full summaries (optional)
        _ideas_articles: list[dict] = []
        try:
            from majestic.tools.research.db import ResearchDB as _RDB2
            _rdb2 = _RDB2(str(settings.data_dir / "research.db"))
            _ideas_articles = _rdb2.get_articles(days=days)
            _rdb2.close()
        except Exception:
            pass

        # LAYER 1: Macro briefing (optional, enriches with world context)
        _ideas_briefing = _load_recent_briefing(settings, max_days=3)

        # Split articles: product launches vs market news
        _launches   = [a for a in _ideas_articles if a.get("category") == "launches"]
        _mkt_news   = [a for a in _ideas_articles if a.get("category") != "launches"]

        _display.tree_reset()
        if _ideas_briefing:
            _display.tree_step("Briefing", "macro context loaded")
        else:
            _display.tree_step("Briefing", "not found — run /briefing for richer analysis", status="warn")
        _display.tree_step("Pains DB", f"{len(_ideas_pains)} pain points · last {days}d")
        if _mkt_news:
            _display.tree_step("Research DB", f"{len(_mkt_news)} articles")
        if _launches:
            _display.tree_step("ProductHunt", f"{len(_launches)} launches")
        else:
            _display.tree_step("ProductHunt", "no launches — run /research to fetch", status="warn")

        # ── Build 4-layer corpus ──────────────────────────────────────────────
        _corpus_lines: list[str] = [f"INTELLIGENCE CORPUS — last {days} days\n"]

        # LAYER 1: Macro briefing capped at 8K chars
        if _ideas_briefing:
            _b_cap = _ideas_briefing[:8_000]
            if len(_ideas_briefing) > 8_000:
                _b_cap += "\n[... truncated ...]"
            _corpus_lines.append("=== MACRO INTELLIGENCE (from /briefing) ===\n")
            _corpus_lines.append(_b_cap)
            _corpus_lines.append("")

        # LAYER 2: Pain signals grouped by domain
        from collections import defaultdict as _ddict3
        _ip_by_domain: dict = _ddict3(list)
        for _ip in _ideas_pains:
            _ip_by_domain[_ip.get("domain", "other")].append(_ip)

        _corpus_lines.append(f"=== DEMAND & PAIN SIGNALS ({len(_ideas_pains)} pain points) ===\n")
        for _dom, _pitems in sorted(_ip_by_domain.items(), key=lambda x: -len(x[1])):
            _corpus_lines.append(f"[{_dom.upper()} — {len(_pitems)} mentions]")
            for _pi in _pitems[:20]:
                _corpus_lines.append(f"· [{_pi.get('source', '')}] {_pi.get('pain_text', '')}")
            _corpus_lines.append("")

        # LAYER 3: Market & news signals with full summaries, capped at 25K chars
        if _mkt_news:
            _news_lines, _ = _build_news_corpus(_mkt_news, max_chars=25_000, include_summaries=True)
            _corpus_lines.append(f"=== MARKET & NEWS SIGNALS ({len(_mkt_news)} articles) ===\n")
            _corpus_lines.extend(_news_lines)

        # LAYER 4: ProductHunt launches — what's being built RIGHT NOW
        if _launches:
            _corpus_lines.append(
                f"=== MARKET LAUNCHES — {len(_launches)} products trending on ProductHunt ===\n"
                "Use this to assess competition: are pain points already being solved? What gap remains?\n"
            )
            for _l in _launches[:30]:
                _corpus_lines.append(f"· [{_l.get('date','')}] {_l.get('title','')}")
                if _l.get("summary"):
                    _corpus_lines.append(f"  {_l.get('summary','')[:200]}")
            _corpus_lines.append("")

        _lang = getattr(settings, "agent_language", "") or "en"
        _is_non_en_i = _lang and _lang.lower() not in ("en", "english")
        _lang_rule_i = (
            f"LANGUAGE: Write the ENTIRE response in {_lang}, including all section headings and labels. "
            "Source/article titles may remain in their original language. "
        ) if _is_non_en_i else ""

        _ideas_instructions = (
            "TASK: Identify 7 realistic business opportunities by synthesizing ALL FOUR corpus layers: "
            "macro structural shifts (LAYER 1), expressed user pains (LAYER 2), "
            "market capital flows (LAYER 3), and what's already being built on ProductHunt (LAYER 4).\n"
            "RULE: Every idea must connect at least 2 layers. "
            "Check MARKET LAUNCHES — if a gap is already filled, find the remaining niche or drop the idea.\n\n"

            "## SECTION 1 — BOTTLENECK MAP\n\n"
            "Identify 5–7 structural gaps from the corpus where demand exists but supply hasn't caught up.\n"
            "Check MARKET LAUNCHES for each: already built / partial / open field.\n\n"
            "**→ [GAP NAME]** — [one sentence: what's missing and why it matters now]\n"
            "- Evidence: (source) + competition status on ProductHunt\n\n"
            "---\n\n"

            "## SECTION 2 — 7 IDEAS\n\n"
            "Rank #1 highest conviction → #7 lowest.\n\n"
            "NAMING RULE: give a short creative product name (not a description of the niche). "
            "Think Stripe, Notion, Figma — not 'AI-Powered Invoice Tool'.\n\n"

            "**#N — [Product Name]** *([who it's for])*\n\n"
            "**Суть**: [2–3 предложения на нормальном языке — что это и зачем. "
            "Объясни как другу, без технических аббревиатур и корпоративного языка. "
            "Читатель должен сразу понять идею.]\n\n"
            "**Как работает**: [конкретный сценарий от первого лица — пользователь открывает, видит, делает, получает. "
            "Один реальный пример использования. Без слов 'платформа', 'SaaS', 'AI-агент'.]\n\n"
            "**Почему сейчас**: [что именно изменилось недавно, что открыло это окно — cite corpus]\n"
            "**Для кого**: [точная персона: роль, контекст, размер компании]\n"
            "**Деньги**: [как монетизируется, конкретные цифры]\n"
            "**Конкуренция**: [что уже есть на PH/рынке → какая конкретно дыра остаётся]\n"
            "**Kill check**: [что должно быть правдой через 30 дней или идея мертва]\n"
            "**Убеждённость**: XX%\n\n"
            "No filler. If fewer than 7 strong gaps exist — say so."
        )

        _ideas_system = (
            f"{_lang_rule_i}"
            "You are a world-class product strategist and venture analyst. "
            "Your response MUST begin with a '##' section header — nothing before it. "
            "No preamble. No meta-commentary."
        )
        _ideas_prompt = "\n".join(_corpus_lines) + "\n\n" + _ideas_instructions
        _ideas_messages = [
            {"role": "system", "content": _ideas_system},
            {"role": "user",   "content": _ideas_prompt},
        ]

        import time as _time2
        from datetime import date as _date2
        _t0_i = _time2.monotonic()

        try:
            with _display.TreePending("generating ideas…"):
                _ideas_resp = await runtime.llm.chat(_ideas_messages, step_type="reason")
            _display.tree_close()
            _ideas_result = _ideas_resp.get("content", "")
            _in_i  = _ideas_resp.get("input_tokens", 0)
            _out_i = _ideas_resp.get("output_tokens", 0)
            runtime._tokens_used = _in_i + _out_i
            _cost_i = _ideas_resp.get("cost") or 0.0
            if not _cost_i and (_in_i or _out_i):
                try:
                    from majestic.llm.base import BaseLLM as _BLLM
                    _cost_i = _BLLM._estimate_cost(_in_i, _out_i)
                except Exception:
                    pass
            runtime._cost_used = _cost_i
        except Exception as exc:
            _display.tree_close("error")
            _ideas_result = f"Error: {exc}"
            _cost_i = 0.0
        _elapsed_i = _time2.monotonic() - _t0_i

        # Strip preamble — keep from first '##' heading
        import re as _re2
        _im = _re2.search(r'^##', _ideas_result, _re2.MULTILINE)
        if _im:
            _ideas_result = _ideas_result[_im.start():]

        # Save to workspace/ideas/YYYY-MM-DD.md
        try:
            _ideas_dir = settings.workspace_dir / "ideas"
            _ideas_dir.mkdir(parents=True, exist_ok=True)
            _ifname = _ideas_dir / f"{_date2.today().isoformat()}.md"
            _ifname.write_text(_ideas_result, encoding="utf-8")
            _display.tree_reset()
            _display.tree_step("saved", f"{_ifname.name}")
            _display.tree_close()
        except Exception:
            pass

        if channel is not None:
            await channel.send(f"\n{_ideas_result}\n")
        else:
            out(_ideas_result)

        from majestic import display as _d2
        _d2.inline_stats(
            tokens=getattr(runtime, "_tokens_used", 0),
            cost=getattr(runtime, "_cost_used", 0.0),
            elapsed=_elapsed_i,
        )
        return True

    if cmd == "/predict":
        from majestic import display as _display
        words = text.strip().split()
        days = 30
        if len(words) > 1:
            try:
                days = int(words[1])
            except ValueError:
                pass

        if settings is None:
            out("[red]No settings — /predict requires a profile.[/red]")
            return True

        # Load research articles
        _pred_articles: list[dict] = []
        try:
            from majestic.tools.research.db import ResearchDB as _RDB3
            _rdb3 = _RDB3(str(settings.data_dir / "research.db"))
            _pred_articles = _rdb3.get_articles(days=days)
            _rdb3.close()
        except Exception:
            pass

        # Load pain points
        _pred_pains: list[dict] = []
        try:
            from majestic.tools.pains.db import PainsDB as _PDB3
            _pdb3 = _PDB3(str(settings.data_dir / "pains.db"))
            _pred_pains = _pdb3.get_pains(days=days)
            _pdb3.close()
        except Exception:
            pass

        if not _pred_articles and not _pred_pains:
            out(f"[dim]No data for the last {days} days. Run /research and /pains first.[/dim]")
            return True

        # Load recent briefing as macro layer (optional)
        _pred_briefing = _load_recent_briefing(settings, max_days=3)

        _display.tree_reset()
        if _pred_briefing:
            _display.tree_step("Briefing", "macro context loaded")
        if _pred_articles:
            _display.tree_step("Research DB", f"{len(_pred_articles)} articles")
        if _pred_pains:
            _display.tree_step("Pains DB", f"{len(_pred_pains)} pain points")

        # ── Build combined corpus ─────────────────────────────────────────────
        from collections import defaultdict as _ddict4

        _pred_lines: list[str] = [f"INTELLIGENCE CORPUS — last {days} days\n"]

        # LAYER 1: Macro briefing capped at 8K chars
        if _pred_briefing:
            _b_cap = _pred_briefing[:8_000]
            if len(_pred_briefing) > 8_000:
                _b_cap += "\n[... truncated ...]"
            _pred_lines.append("=== MACRO SYNTHESIS (from /briefing) ===\n")
            _pred_lines.append(_b_cap)
            _pred_lines.append("")

        # LAYER 2: News & market signals with full summaries, capped at 45K chars
        if _pred_articles:
            _news_lines, _ = _build_news_corpus(_pred_articles, max_chars=45_000, include_summaries=True)
            _pred_lines.append(f"=== NEWS & MARKET SIGNALS ({len(_pred_articles)} articles) ===\n")
            _pred_lines.extend(_news_lines)

        # LAYER 3: Pain signals capped at 15K chars
        if _pred_pains:
            _by_dom4: dict = _ddict4(list)
            for _pp in _pred_pains:
                _by_dom4[_pp.get("domain", "other")].append(_pp)

            _pred_lines.append(f"=== DEMAND & PAIN SIGNALS ({len(_pred_pains)} pain points) ===\n")
            _pc = 0
            for _dom4, _domitems in sorted(_by_dom4.items(), key=lambda x: -len(x[1])):
                _pred_lines.append(f"[{_dom4.upper()} — {len(_domitems)} mentions]")
                for _pi4 in _domitems[:15]:
                    _pe = f"· [{_pi4.get('source','')}] {_pi4.get('pain_text','')}"
                    _pred_lines.append(_pe)
                    _pc += len(_pe)
                    if _pc >= 15_000:
                        break
                _pred_lines.append("")
                if _pc >= 15_000:
                    break

        _pred_instructions = (
            "CRITICAL SYNTHESIS RULE: Every prediction in SECTIONS 2–4 MUST be grounded in "
            "signals from at least 2 DIFFERENT corpus sections (e.g. a NEWS signal + a PAIN signal, "
            "or two independent news categories). Single-source observations belong ONLY in SECTION 5.\n\n"
            "Rules: (1) use ONLY facts from the corpus; (2) build causal chains, not lists of citations; "
            "(3) calibrate probabilities against reference classes — explain the base rate; "
            "(4) when the corpus contains financial signals, add a FINANCIAL MARKETS block inside SECTIONS 2–4: "
            "equities (specific tickers or sectors mentioned in corpus), crypto (BTC, ETH, major alts), "
            "commodities, forex — ONLY where the corpus provides direct evidence. "
            "Format: **[BUY/HOLD/SELL/AVOID] [asset]** — XX% — causal chain from corpus.\n\n"

            "## SECTION 1 — SIGNAL MAP\n\n"
            "Before predicting, scan the ENTIRE corpus and map 8–12 directional forces — "
            "things actively pushing in a specific direction. Group signals pointing the same way.\n\n"
            "**→ [DIRECTION/THEME]** (N signals)\n"
            "- [Signal]: what's happening — (source, date or pain source)\n"
            "- [Signal]: ...\n\n"
            "This map is the foundation for all predictions below. "
            "Themes with 3+ independent signals = highest conviction.\n\n"
            "---\n\n"

            "## SECTION 2 — SHORT-TERM (1–4 weeks)\n\n"
            "Events already in motion, likely to resolve within a month. "
            "Each prediction MUST connect 2+ signals from SECTION 1 via a causal chain.\n\n"
            "**[PREDICTION STATEMENT]** — **XX%**\n"
            "- Causal chain: [Signal A (source)] → [mechanism] → [Signal B (source)] → [outcome]\n"
            "- Base rate: reference class grounding this probability\n"
            "- Counter-signals: what in the corpus argues against\n"
            "- Invalidation: one event that kills this prediction\n"
            "- Winners / Losers\n\n"
            "3–5 predictions, ranked highest → lowest. Omit if fewer than 2 signals support it.\n\n"
            "---\n\n"

            "## SECTION 3 — MEDIUM-TERM (1–3 months)\n\n"
            "Trends forming now, directional but not yet resolved. "
            "Prioritize themes where NEWS and PAIN signals both point the same way — "
            "that cross-validation significantly raises confidence. Same format. 3–5 predictions.\n\n"
            "---\n\n"

            "## SECTION 4 — LONG-TERM (6–12 months)\n\n"
            "Structural shifts: focus on themes where signals from multiple corpus sections "
            "have been building consistently. These carry the highest cross-validation. "
            "Same format. 2–4 predictions.\n\n"
            "---\n\n"

            "## SECTION 5 — TAIL RISKS\n\n"
            "2–3 events under 20% probability but catastrophic impact. "
            "Single-signal observations and weak hints belong here.\n"
            "**[RISK EVENT]** — **XX%**\n"
            "- Weak signal: (source)\n"
            "- Impact if it materialises\n"
            "- Early warning to watch in next 30 days\n\n"
            "---\n\n"
            "End: the single highest-confidence prediction and the exact signal combination that drives it."
        )

        _lang = getattr(settings, "agent_language", "") or "en"
        _is_non_en_p = _lang and _lang.lower() not in ("en", "english")
        _lang_rule_p = (
            f"LANGUAGE: Write the ENTIRE response in {_lang}, including all section headings and labels. "
            "Source/article titles may remain in their original language. "
        ) if _is_non_en_p else ""
        _pred_system = (
            f"{_lang_rule_p}"
            "You are a professional intelligence analyst trained in Superforecasting methodology. "
            "Your task is SYNTHESIS — find patterns that emerge from MULTIPLE independent signals, "
            "not summaries of individual items. Build causal chains across signal types. "
            "Your response MUST begin with a '##' section header — nothing before it. "
            "No preamble. No meta-commentary. Calibrated probabilities only."
        )
        _pred_prompt = "\n".join(_pred_lines) + "\n" + _pred_instructions
        _pred_messages = [
            {"role": "system", "content": _pred_system},
            {"role": "user",   "content": _pred_prompt},
        ]

        import time as _time3
        from datetime import date as _date3
        _t0_p = _time3.monotonic()

        try:
            with _display.TreePending("analyzing signals…"):
                _pred_resp = await runtime.llm.chat(_pred_messages, step_type="reason")
            _display.tree_close()
            _pred_result = _pred_resp.get("content", "")
            _in_p  = _pred_resp.get("input_tokens", 0)
            _out_p = _pred_resp.get("output_tokens", 0)
            runtime._tokens_used = _in_p + _out_p
            _cost_p = _pred_resp.get("cost") or 0.0
            if not _cost_p and (_in_p or _out_p):
                try:
                    from majestic.llm.base import BaseLLM as _BLLM2
                    _cost_p = _BLLM2._estimate_cost(_in_p, _out_p)
                except Exception:
                    pass
            runtime._cost_used = _cost_p
        except Exception as exc:
            _display.tree_close("error")
            _pred_result = f"Error: {exc}"
            _cost_p = 0.0
        _elapsed_p = _time3.monotonic() - _t0_p

        # Strip preamble — keep from first '##' heading
        import re as _re4
        _pm = _re4.search(r'^##', _pred_result, _re4.MULTILINE)
        if _pm:
            _pred_result = _pred_result[_pm.start():]

        # Save to workspace/predictions/YYYY-MM-DD.md
        try:
            _pred_dir = settings.workspace_dir / "predictions"
            _pred_dir.mkdir(parents=True, exist_ok=True)
            _pfname = _pred_dir / f"{_date3.today().isoformat()}.md"
            _pfname.write_text(_pred_result, encoding="utf-8")
            _display.tree_reset()
            _display.tree_step("saved", f"{_pfname.name}")
            _display.tree_close()
        except Exception:
            pass

        if channel is not None:
            await channel.send(f"\n{_pred_result}\n")
        else:
            out(_pred_result)

        from majestic import display as _d3
        _d3.inline_stats(
            tokens=getattr(runtime, "_tokens_used", 0),
            cost=getattr(runtime, "_cost_used", 0.0),
            elapsed=_elapsed_p,
        )
        return True

    if cmd == "/ask":
        import re as _re_ask
        from majestic import display as _display

        question = text.strip()[len("/ask"):].strip()
        if not question:
            out("[dim]Usage: /ask <question>  e.g.: /ask how will falling oil prices affect Bitcoin?[/dim]")
            return True

        if settings is None:
            out("[red]No settings — /ask requires a profile.[/red]")
            return True

        _display.tree_reset()

        # ── Layer 1: Recent briefing (macro context) ─────────────────────────
        _ask_briefing = _load_recent_briefing(settings, max_days=3)
        if _ask_briefing:
            _display.tree_step("Briefing", "macro context loaded")

        # ── Layer 2: Recent prediction ────────────────────────────────────────
        _ask_prediction: str | None = None
        try:
            from datetime import date as _date_ask, timedelta as _td_ask
            _pd = settings.workspace_dir / "predictions"
            if _pd.exists():
                _today_a = _date_ask.today()
                for _delta in range(4):
                    _f = _pd / f"{(_today_a - _td_ask(days=_delta)).isoformat()}.md"
                    if _f.exists():
                        _c = _f.read_text(encoding="utf-8").strip()
                        if _c:
                            _ask_prediction = _c
                            break
        except Exception:
            pass
        if _ask_prediction:
            _display.tree_step("Predictions", "context loaded")

        # ── Keyword extraction (shared across layers 3–4) ─────────────────────
        _kw = [w.lower() for w in _re_ask.sub(r"[^\w\s]", " ", question).split() if len(w) > 3]

        # ── Layer 3: Semantic search ──────────────────────────────────────────
        _sem_results: list[dict] = []
        if semantic is not None:
            try:
                _safe_q = " ".join(_re_ask.sub(r"[^\w\s]", " ", question).split()[:10])
                if _safe_q.strip():
                    _sem_results = semantic.search(_safe_q, limit=25)
                _display.tree_step("Semantic", f"{len(_sem_results)} relevant chunks")
            except Exception:
                pass

        # ── Layer 4: Keyword-matched articles ────────────────────────────────
        _ask_articles: list[dict] = []
        try:
            from majestic.tools.research.db import ResearchDB as _RDB_ask
            _rdb_ask = _RDB_ask(str(settings.data_dir / "research.db"))
            _all_art = _rdb_ask.get_articles(days=60)
            _rdb_ask.close()
            if _kw:
                for _a in _all_art:
                    _txt = f"{_a.get('title','')} {_a.get('summary','')}".lower()
                    if any(k in _txt for k in _kw):
                        _ask_articles.append(_a)
            if _ask_articles:
                _display.tree_step("Research DB", f"{len(_ask_articles)} matching articles")
        except Exception:
            pass

        # ── Layer 5: Keyword-matched pain signals ─────────────────────────────
        _ask_pains: list[dict] = []
        try:
            from majestic.tools.pains.db import PainsDB as _PDB_ask
            _pdb_ask = _PDB_ask(str(settings.data_dir / "pains.db"))
            _all_pains = _pdb_ask.get_pains(days=60)
            _pdb_ask.close()
            if _kw:
                for _p in _all_pains:
                    if any(k in _p.get("pain_text", "").lower() for k in _kw):
                        _ask_pains.append(_p)
            if _ask_pains:
                _display.tree_step("Pains DB", f"{len(_ask_pains)} matching signals")
        except Exception:
            pass

        if not any([_ask_briefing, _ask_prediction, _sem_results, _ask_articles, _ask_pains]):
            out("[dim]No context found. Run /research, /pains, /briefing, /predict first.[/dim]")
            return True

        # ── Build focused corpus ──────────────────────────────────────────────
        _ask_corpus: list[str] = [f"ANALYSIS CORPUS — question: {question}\n"]

        if _ask_briefing:
            _ask_corpus.append("=== MACRO INTELLIGENCE (recent /briefing) ===\n")
            _ask_corpus.append(_ask_briefing[:5_000])
            if len(_ask_briefing) > 5_000:
                _ask_corpus.append("\n[... truncated ...]")
            _ask_corpus.append("")

        if _ask_prediction:
            _ask_corpus.append("=== PREDICTIONS (recent /predict) ===\n")
            _ask_corpus.append(_ask_prediction[:5_000])
            if len(_ask_prediction) > 5_000:
                _ask_corpus.append("\n[... truncated ...]")
            _ask_corpus.append("")

        if _sem_results:
            _ask_corpus.append(f"=== SEMANTIC HITS ({len(_sem_results)}) ===\n")
            for _sr in _sem_results:
                _ask_corpus.append(f"[{_sr.get('source','')}]: {_sr.get('content','')[:300]}")
            _ask_corpus.append("")

        if _ask_articles:
            _ask_corpus.append(f"=== MATCHING ARTICLES ({len(_ask_articles)}) ===\n")
            for _aa in _ask_articles[:30]:
                _ask_corpus.append(
                    f"· [{_aa.get('date','')}] {_aa.get('source','')}: {_aa.get('title','')}"
                )
                if _aa.get("summary"):
                    _ask_corpus.append(f"  {_aa.get('summary','')[:200]}")
            _ask_corpus.append("")

        if _ask_pains:
            _ask_corpus.append(f"=== MATCHING PAIN SIGNALS ({len(_ask_pains)}) ===\n")
            for _ap in _ask_pains[:15]:
                _ask_corpus.append(f"· [{_ap.get('source','')}] {_ap.get('pain_text','')}")
            _ask_corpus.append("")

        _lang = getattr(settings, "agent_language", "") or "en"
        _is_non_en_a = _lang and _lang.lower() not in ("en", "english")
        _lang_rule_a = (
            f"LANGUAGE: Write the ENTIRE response in {_lang}, including section headings. "
            "Source/article titles may remain in their original language. "
        ) if _is_non_en_a else ""

        _ask_instructions = (
            f"QUESTION: {question}\n\n"
            "Answer using ONLY the corpus above. Format exactly:\n\n"
            "## Direct Answer\n"
            "[1–2 sentences. State the conclusion directly.]\n\n"
            "## Evidence Chain\n"
            "[Each signal: what it shows → mechanism → consequence. Cite (source, date). "
            "Show HOW signals connect to answer the question.]\n\n"
            "## Confidence\n"
            "[XX% — how many independent signals? Are they convergent or contradictory?]\n\n"
            "## Counter-signals\n"
            "[What in the corpus argues against? If none — state why.]\n\n"
            "## Watch For\n"
            "[2–3 specific events in next 30 days that confirm or deny this.]\n\n"
            "RULE: use ONLY corpus facts. Cite every claim. "
            "If corpus has insufficient data, say so explicitly — do not fill gaps with assumptions."
        )

        _ask_system = (
            f"{_lang_rule_a}"
            "You are a professional intelligence analyst. "
            "Your response MUST begin with a '##' heading — nothing before it. "
            "No preamble. No meta-commentary. Answer the specific question using only corpus evidence."
        )
        _ask_prompt = "\n".join(_ask_corpus) + "\n\n" + _ask_instructions
        _ask_messages = [
            {"role": "system", "content": _ask_system},
            {"role": "user",   "content": _ask_prompt},
        ]

        import time as _time_ask
        _t0_ask = _time_ask.monotonic()

        try:
            with _display.TreePending("analyzing…"):
                _ask_resp = await runtime.llm.chat(_ask_messages, step_type="reason")
            _display.tree_close()
            _ask_result = _ask_resp.get("content", "")
            _in_a  = _ask_resp.get("input_tokens", 0)
            _out_a = _ask_resp.get("output_tokens", 0)
            runtime._tokens_used = _in_a + _out_a
            _cost_a = _ask_resp.get("cost") or 0.0
            if not _cost_a and (_in_a or _out_a):
                try:
                    from majestic.llm.base import BaseLLM as _BLLM_a
                    _cost_a = _BLLM_a._estimate_cost(_in_a, _out_a)
                except Exception:
                    pass
            runtime._cost_used = _cost_a
        except Exception as exc:
            _display.tree_close("error")
            _ask_result = f"Error: {exc}"
            _cost_a = 0.0
        _elapsed_ask = _time_ask.monotonic() - _t0_ask

        # Strip preamble
        _am = _re_ask.search(r"^##", _ask_result, _re_ask.MULTILINE)
        if _am:
            _ask_result = _ask_result[_am.start():]

        if channel is not None:
            await channel.send(f"\n{_ask_result}\n")
        else:
            out(_ask_result)

        from majestic import display as _d_ask
        _d_ask.inline_stats(
            tokens=getattr(runtime, "_tokens_used", 0),
            cost=getattr(runtime, "_cost_used", 0.0),
            elapsed=_elapsed_ask,
        )
        return True

    if cmd == "/goodmorning":
        from majestic import display as _display
        words = text.strip().split()
        days = 30
        if len(words) > 1:
            try:
                days = int(words[1])
            except ValueError:
                pass

        out(f"\n[bold]Good Morning[/bold] [dim]— full intelligence pipeline · last {days}d[/dim]\n")

        # Step 1 — collect news
        out("[dim]━━ 1/5  /research — fetching news…[/dim]\n")
        _gm_research = await _handle_slash_plain(
            "/research", profile_name, working_memory, runtime, settings, semantic, channel, gateway
        )
        if isinstance(_gm_research, str):
            # New articles fetched — data is in DB; briefing will do the deep analysis
            out("[dim]  News data collected. /briefing will analyze below.[/dim]\n")

        # Step 2 — collect pain signals
        out("[dim]━━ 2/5  /pains — scanning community signals…[/dim]\n")
        await _handle_slash_plain(
            "/pains", profile_name, working_memory, runtime, settings, semantic, channel, gateway
        )

        # Step 3 — intelligence briefing
        out(f"\n[dim]━━ 3/5  /briefing {days} — analyzing all news…[/dim]\n")
        await _handle_slash_plain(
            f"/briefing {days}", profile_name, working_memory, runtime, settings, semantic, channel, gateway
        )

        # Step 4 — predictions
        out(f"\n[dim]━━ 4/5  /predict {days} — generating predictions…[/dim]\n")
        await _handle_slash_plain(
            f"/predict {days}", profile_name, working_memory, runtime, settings, semantic, channel, gateway
        )

        # Step 5 — ideas
        out(f"\n[dim]━━ 5/5  /ideas {days} — generating ideas…[/dim]\n")
        await _handle_slash_plain(
            f"/ideas {days}", profile_name, working_memory, runtime, settings, semantic, channel, gateway
        )

        out("\n[green]✓[/green] [dim]Pipeline complete.[/dim]")
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
            _shared_dir = str(settings.shared_skills_dir)
            pm = ProceduralMemory(str(settings.skills_dir), shared_dir=_shared_dir)
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
                    expanded = pm.expand_steps(steps)
                    lines.extend(f"  - {s}" for s in expanded)
                if user_input:
                    lines.append(f"\nUser input: {user_input}")
                print()
                out(f"  [dim]Running skill:[/dim] [bold]{cmd_name}[/bold]")
                return "\n".join(lines)
        except Exception:
            pass

    return False


def _build_runtime(
    settings,
    working_memory,
    llm_router,
    stream_callback=None,
    semantic=None,
    user_profile=None,
    procedural_memory=None,
) -> "AgentRuntime":
    """Instantiate AgentRuntime with the full self-evolution stack wired up."""
    from majestic.core.runtime import AgentRuntime
    from majestic.core.context_manager import ContextManager
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
        procedural_memory=procedural_memory,
    )

    consolidator = None
    if semantic is not None and user_profile is not None:
        from majestic.memory.consolidator import MemoryConsolidator
        consolidator = MemoryConsolidator(
            episodic=episodic_memory,
            semantic=semantic,
            user_profile=user_profile,
            llm_router=llm_router,
        )

    reflection_engine = ReflectionEngine(
        llm_router=llm_router,
        lessons_store=lessons_store,
        episodic_memory=episodic_memory,
        self_evolution=evolution,
        consolidator=consolidator,
    )
    planner = Planner(settings, llm_router, lessons_store)
    context_manager = ContextManager(llm_router=llm_router)

    return AgentRuntime(
        settings=settings,
        working_memory=working_memory,
        llm_router=llm_router,
        checkpoint_store=checkpoint_store,
        reflection_engine=reflection_engine,
        planner=planner,
        context_manager=context_manager,
        hitl_enabled=False,
        stream_callback=stream_callback,
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
