#!/usr/bin/env python3
"""
CLI — local interface for Parallax AI
Run: python cli.py
"""
import sys
import os
import re
import shutil
import threading
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent))

from dotenv import load_dotenv
load_dotenv()

# ── Pre-load core modules (so deprecation warnings appear at startup, not mid-query) ──
import warnings
warnings.filterwarnings("ignore", category=UserWarning, module="langchain_core")

from core.rag_engine import ask, index_file, stats, INBOX_DIR, DONE_DIR, EXPORT_DIR, splitter, vectorstore, unload_llm
from core.reminders import extract_reminder_intent, add_reminder, list_reminders, format_reminder, parse_date, start_watcher
from core.formatter import render_cli

# ── prompt_toolkit setup ───────────────────────────────────────────────────────
from prompt_toolkit import PromptSession
from prompt_toolkit.completion import Completer, Completion
from prompt_toolkit.history import InMemoryHistory
from prompt_toolkit.formatted_text import ANSI
from prompt_toolkit.styles import Style

# Commands with descriptions shown in autocomplete
COMMANDS: dict[str, str] = {
    "/research":       "collect HN + Reddit + GitHub + auto-summary",
    "/news":           "last N news items (default: /news 10)",
    "/market":         "fetch market snapshot → saved to DB",
    "/briefing":       "world briefing + segment map + predictions (default 14d, e.g. /briefing 7)",
    "/predict":        "cross-niche predictions with probabilities (default 14d, e.g. /predict 30)",
    "/flows":          "money flows — sectors where money is moving NOW (default 14d, e.g. /flows 7)",
    "/ideas":          "5 hot niches to enter right now",
    "/report":         "generate deep report on a topic",
    "/reports":        "list saved reports",
    "/reports view":   "view report by number",
    "/reports pdf":    "export report to PDF by number",
    "/reports del":    "delete report by number",
    "/tokens":         "Anthropic token usage and cost",
    "/tokens reset":   "reset token counter",
    "/logs":           "recent error log",
    "/set":            "show current settings",
    "/set lang":       "set response language (e.g. /set lang EN)",
    "/set currency":   "set prices currency (e.g. /set currency USD)",
    "/set mod":        "set search scope: all | docs | intel (e.g. /set mod intel)",
    "/remind":         "add reminder (natural language date)",
    "/reminders":      "list active reminders",
    "/rss":            "manage RSS feeds (/rss list | add <url> | remove <N>)",
    "/stats":          "knowledge base statistics",
    "/help":           "show help",
    "/exit":           "quit",
}


import shutil as _shutil

class CommandCompleter(Completer):
    def get_completions(self, document, complete_event):
        text = document.text_before_cursor
        if not text.startswith("/"):
            return
        term_width = _shutil.get_terminal_size((120, 20)).columns
        cmd_col    = 22
        desc_width = max(term_width - cmd_col - 6, 20)
        matches = [(cmd, desc) for cmd, desc in COMMANDS.items() if cmd.startswith(text)]
        for cmd, desc in matches:
            row = f"  {cmd:<{cmd_col}}  {desc[:desc_width]}"
            yield Completion(cmd, start_position=-len(text), display=row)


_pt_style = Style.from_dict({
    # noinherit breaks inheritance chain so prompt_toolkit defaults don't win
    "completion-menu":                         "noinherit bg:default",
    "completion-menu.completion":              "noinherit bg:default fg:#606060",
    "completion-menu.completion.current":      "noinherit bg:default fg:#d95767 bold",
    "completion-menu.meta.completion":         "noinherit bg:default fg:default",
    "completion-menu.meta.completion.current": "noinherit bg:default fg:default",
    "scrollbar":                               "noinherit bg:default fg:default",
    "scrollbar.background":                    "noinherit bg:default",
    "scrollbar.button":                        "noinherit bg:default fg:default",
    "scrollbar.arrow":                         "noinherit bg:default fg:default",
})

_session = None

def _get_session():
    global _session
    if _session is None:
        if not sys.stdin.isatty():
            _session = False
            return None
        try:
            _session = PromptSession(
                history=InMemoryHistory(),
                completer=CommandCompleter(),
                complete_while_typing=True,
                style=_pt_style,
                mouse_support=False,
            )
        except Exception:
            try:
                # Fallback for xterm-256color terminals on Windows (VS Code, Windows Terminal)
                from prompt_toolkit.output.vt100 import Vt100_Output
                from prompt_toolkit.input.vt100 import Vt100Input
                import warnings
                with warnings.catch_warnings():
                    warnings.simplefilter("ignore")
                    out = Vt100_Output.from_pty(sys.__stdout__, term="xterm-256color")
                    inp = Vt100Input(sys.stdin)
                _session = PromptSession(
                    history=InMemoryHistory(),
                    completer=CommandCompleter(),
                    complete_while_typing=True,
                    style=_pt_style,
                    mouse_support=False,
                    output=out,
                    input=inp,
                )
            except Exception:
                _session = False  # plain input() fallback
    return _session if _session else None

# ── Shared execution gate (prevents concurrent runs of heavy commands) ─────────

class _SyncGate:
    """Run fn once at a time; concurrent callers wait and share the result."""

    def __init__(self, name: str):
        self.name    = name
        self._lock   = threading.Lock()
        self._busy   = False
        self._event  = threading.Event()
        self._event.set()   # starts as "free"
        self._result = None
        self._error: Exception | None = None

    def run(self, fn, *args):
        """Returns (result, is_fresh)."""
        with self._lock:
            if not self._busy:
                self._busy  = True
                self._error = None
                self._event.clear()
                am_runner = True
            else:
                am_runner = False

        if am_runner:
            try:
                self._result = fn(*args)
            except Exception as e:
                self._error  = e
                self._result = None
            finally:
                with self._lock:
                    self._busy = False
                self._event.set()
            if self._error:
                raise self._error
            return self._result, True
        else:
            self._event.wait()
            if self._error:
                raise self._error
            return self._result, False


_sync_gates: dict[str, _SyncGate] = {
    "research":    _SyncGate("research"),
    "briefing":    _SyncGate("briefing"),
    "ideas":       _SyncGate("ideas"),
    "market":      _SyncGate("market"),
    "predictions": _SyncGate("predictions"),
}


# ── Spinner ────────────────────────────────────────────────────────────────────
import time

class Spinner:
    """Animated spinner for long-running operations. Suppresses stdout noise."""
    FRAMES = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"

    def __init__(self, text: str):
        self.text = text
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._spin, daemon=True)
        self._real_stdout = None

    def _spin(self):
        i = 0
        while not self._stop.is_set():
            frame = self.FRAMES[i % len(self.FRAMES)]
            self._real_stdout.write(f"\r\033[2K\033[36m{frame}\033[0m {self.text}")
            self._real_stdout.flush()
            i += 1
            time.sleep(0.08)

    def __enter__(self):
        import io
        self._real_stdout = sys.__stdout__  # always use the true stdout
        sys.stdout = io.StringIO()          # swallow prints from core modules
        self._thread.start()
        return self

    def __exit__(self, *_):
        self._stop.set()
        self._thread.join()
        sys.stdout = self._real_stdout
        self._real_stdout.write("\r\033[2K")
        self._real_stdout.flush()


# ── Colors ─────────────────────────────────────────────────────────────────────
R   = "\033[0m"
B   = "\033[1m"
C   = "\033[38;2;217;87;103m"  # #d95767
G   = "\033[32m"
Y   = "\033[33m"
DIM = "\033[2m"
RED = "\033[31m"

_LINK = "\033]8;;https://github.com/ysz7\033\\by ysz\033]8;;\033\\"
BANNER = f"""{C}{B}
  ██████╗  █████╗ ██████╗  █████╗ ██╗     ██╗      █████╗ ██╗  ██╗
  ██╔══██╗██╔══██╗██╔══██╗██╔══██╗██║     ██║     ██╔══██╗╚██╗██╔╝
  ██████╔╝███████║██████╔╝███████║██║     ██║     ███████║ ╚███╔╝
  ██╔═══╝ ██╔══██║██╔══██╗██╔══██║██║     ██║     ██╔══██║ ██╔██╗
  ██║     ██║  ██║██║  ██╗██║  ██║███████╗███████╗██║  ██║██╔╝ ██╗
  ╚═╝     ╚═╝  ╚═╝╚═╝  ╚═╝╚═╝  ╚═╝╚══════╝╚══════╝╚═╝  ╚═╝╚═╝  ╚═╝
{R}{DIM}                                AI Research & Intelligence Agent  {_LINK}{R}
"""


def _print_status() -> None:
    """Print system status line below the banner."""
    import subprocess

    # ── LLM provider / model ──────────────────────────────────────────────
    provider = os.getenv("LLM_PROVIDER", "ollama").lower()
    if provider == "anthropic":
        model = os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-20250514")
    else:
        model = os.getenv("OLLAMA_MODEL", "gemma3")

    # ── Ollama status ─────────────────────────────────────────────────────
    if provider == "ollama":
        try:
            result = subprocess.run(
                ["ollama", "list"], capture_output=True, text=True, timeout=2
            )
            ollama_ok = result.returncode == 0
        except Exception:
            ollama_ok = False
        ollama_dot = f"\033[32m●\033[0m" if ollama_ok else f"\033[31m●\033[0m"
        ollama_status = f"{ollama_dot}{DIM} ollama{R}"
    else:
        ollama_status = f"\033[32m●\033[0m{DIM} anthropic{R}"

    # ── ChromaDB doc count ────────────────────────────────────────────────
    try:
        from core.rag_engine import vectorstore
        doc_count = vectorstore._collection.count()
        db_dot = f"\033[32m●\033[0m"
    except Exception:
        doc_count = 0
        db_dot = f"\033[31m●\033[0m"
    db_status = f"{db_dot}{DIM} chromadb{R}"

    # ── Model label ───────────────────────────────────────────────────────
    model_label = f"{DIM}{provider} / {model}{R}"

    print(f"  {ollama_status}   {db_status}   {DIM}docs: {doc_count}{R}   {model_label}\n")

HELP = f"""
{B}Commands:{R}
  {G}/research{R}          — collect HN + Reddit + GitHub + auto-summary
  {G}/news [N]{R}          — last N news items (default 10)
  {G}/market{R}            — fetch market snapshot (saved to DB)
  {G}/briefing [N]{R}      — world briefing + segment map + predictions (default 14 days)
  {G}/predict [N]{R}       — cross-niche predictions with probabilities (default 14 days)
  {G}/flows [N]{R}         — money flows: sectors where money is confirmed moving (default 14 days)
  {G}/ideas{R}             — 5 hot niches to enter right now
  {G}/report <topic>{R}    — generate deep report on a topic
  {G}/reports{R}           — list saved reports
  {G}/reports view <N>{R}  — view report by number
  {G}/reports pdf <N>{R}   — export report to PDF
  {G}/reports del <N>{R}   — delete report by number
  {G}/tokens{R}            — Anthropic token usage and cost
  {G}/tokens reset{R}      — reset token counter
  {G}/logs{R}              — recent error log
  {G}/set lang <code>{R}       — set response language (EN, ES, DE, ...)
  {G}/set currency <code>{R}   — set prices currency (USD, EUR, GBP, ...)
  {G}/set mod <scope>{R}       — set search scope: all | docs | intel
  {G}/remind <text>{R}     — add reminder (natural language date)
  {G}/reminders{R}         — list active reminders
  {G}/rss list{R}          — list configured RSS feeds
  {G}/rss add <url>{R}    — add an RSS feed by URL
  {G}/rss remove <N>{R}   — remove RSS feed by number
  {G}/stats{R}             — knowledge base statistics
  {G}/help{R}              — this help
  {G}/exit{R}              — quit

{B}Input:{R}
  Type any question    — RAG search across knowledge base
  Drag & drop a file   — indexes it automatically
  Paste a file path    — same as drag & drop
  Shift+Enter          — new line without sending (multiline input)

{B}Supported file formats:{R} .pdf  .docx  .csv  .txt  .md
"""

# ── Supported file formats ─────────────────────────────────────────────────────
SUPPORTED_EXTS = {".pdf", ".docx", ".csv", ".txt", ".md"}

# ── File path detection ────────────────────────────────────────────────────────
# Matches: plain paths, quoted paths, paths with ~ or drive letters
_PATH_RE = re.compile(
    r'^"?([A-Za-z]:[\\\/][^"*?<>|]+|~[^\s"]*|\/[^\s"]+)"?$'
)


def _looks_like_path(text: str) -> bool:
    """Return True if the entire input looks like one or more file paths."""
    parts = _split_paths(text.strip())
    return len(parts) > 0


def _split_paths(text: str) -> list[Path]:
    """
    Extract valid file paths from text.
    Handles: single path, multiple space-separated paths, quoted paths.
    """
    # Try splitting on whitespace respecting quotes
    tokens = re.findall(r'"[^"]*"|\'[^\']*\'|\S+', text)
    paths = []
    for token in tokens:
        token = token.strip('"\'')
        token = token.replace("\\", "/")
        p = Path(token).expanduser()
        if p.exists() and p.is_file() and p.suffix.lower() in SUPPORTED_EXTS:
            paths.append(p)
    return paths


# ── Progress indicator ─────────────────────────────────────────────────────────

def _index_with_progress(path: Path) -> int:
    """Index a file with a live chunk counter. Returns chunk count."""
    from core.rag_engine import load_file

    docs = load_file(path)
    if not docs:
        return 0

    chunks = splitter.split_documents(docs)
    total = len(chunks)
    bar_width = 20

    def _bar(done: int) -> str:
        filled = int(bar_width * done / max(total, 1))
        return "█" * filled + "░" * (bar_width - filled)

    # Add in batches and update progress
    batch = max(1, total // 20)
    added = 0
    for i in range(0, total, batch):
        slice_ = chunks[i : i + batch]
        vectorstore.add_documents(slice_)
        added += len(slice_)
        pct = _bar(added)
        print(f"\r  ⏳ {path.name}... {pct} {added}/{total} chunks", end="", flush=True)

    print()  # newline after progress bar

    # Move to processed/
    dest = DONE_DIR / path.name
    if dest.exists():
        dest = DONE_DIR / f"{path.stem}_{int(datetime.now().timestamp())}{path.suffix}"
    shutil.move(str(path), str(dest))

    return total


def _handle_files(paths: list[Path]):
    """Show preview, confirm, then index."""
    if not paths:
        return

    if len(paths) == 1:
        p = paths[0]
        size_kb = p.stat().st_size / 1024
        size_str = f"{size_kb:.1f} KB" if size_kb < 1024 else f"{size_kb/1024:.1f} MB"
        print(f"\n  📄 {p.name} ({size_str}) — index? [Enter / n] ", end="", flush=True)
        confirm = input().strip().lower()
        if confirm == "n":
            print(f"  {DIM}Skipped.{R}\n")
            return
        n = _index_with_progress(p)
        if n:
            print(f"  {G}✅ {p.name} — {n} chunks added{R}\n")
        else:
            print(f"  {Y}⚠️  {p.name} — could not index (unsupported or empty){R}\n")
    else:
        print(f"\n  📄 Found {len(paths)} files:")
        for p in paths:
            size_kb = p.stat().st_size / 1024
            size_str = f"{size_kb:.1f} KB" if size_kb < 1024 else f"{size_kb/1024:.1f} MB"
            print(f"     • {p.name} ({size_str})")
        print(f"  Index all? [Enter / n] ", end="", flush=True)
        confirm = input().strip().lower()
        if confirm == "n":
            print(f"  {DIM}Skipped.{R}\n")
            return
        for p in paths:
            n = _index_with_progress(p)
            if n:
                print(f"  {G}✅ {p.name} — {n} chunks{R}")
            else:
                print(f"  {Y}⚠️  {p.name} — skipped{R}")
        print()


# ── Input via prompt_toolkit ───────────────────────────────────────────────────

def _read_input(prompt: str) -> str:
    session = _get_session()
    try:
        if session:
            return session.prompt(ANSI(prompt)).strip()
        else:
            return input(prompt).strip()
    except (EOFError, KeyboardInterrupt):
        return "/exit"


# ── Command handlers ───────────────────────────────────────────────────────────

def cmd_research():
    from core.intel import collect_and_index

    gate = _sync_gates["research"]
    if gate._busy:
        print(f"\n  {Y}⏳ Research already running — waiting for result...{R}")

    sp = Spinner("Starting...")
    with sp:
        def _progress(name, current, total):
            sp.text = f"[{current}/{total}] {name}..."

        def _run():
            return collect_and_index(on_progress=_progress)

        result, is_fresh = gate.run(_run)

    total_new = result['total_new']
    by_src = result.get("by_source", {})

    print(f"\n  {B}Research complete{R}")
    print(f"  New: {G}{total_new}{R}  |  Skipped: {DIM}{result['total_seen']} duplicates{R}\n")

    SOURCE_LABELS = {
        "hackernews":      f"{Y}HN{R}",
        "reddit":          f"{C}RD{R}",
        "github_trending": f"{G}GH{R}",
        "producthunt":     f"\033[35mPH{R}",
        "mastodon":        f"\033[34mMD{R}",
        "devto":           f"{G}DV{R}",
        "google_trends":   f"{Y}GT{R}",
        "newsapi":         f"{B}NW{R}",
        "arxiv":           f"\033[36mAX{R}",
    }
    for src, count in by_src.items():
        label = SOURCE_LABELS.get(src, src)
        print(f"  [{label}] {count} new")

    new_items = result.get("new_items", [])
    if new_items:
        from core.trends import quick_summary_from_new
        with Spinner("Generating summary..."):
            summary = quick_summary_from_new(new_items)
        print(f"\n{render_cli(summary)}\n")
    else:
        print(f"\n{DIM}No new items to summarize.{R}\n")

    # Always refresh market data after research so briefings have fresh prices
    try:
        from core.market_pulse import collect_market_pulse, format_pulse
        with Spinner("Fetching market snapshot..."):
            market_data = collect_market_pulse()
        print(f"\n{format_pulse(market_data)}\n")
    except Exception as _e:
        print(f"  {Y}⚠️  Market data unavailable: {_e}{R}\n")


def cmd_stats():
    from core.rag_engine import delete_file
    s = stats()
    print(f"\n{B}📊 Knowledge base:{R}")
    print(f"  Chunks  : {G}{s['chunks']}{R}")

    # Split intel sources from real indexed files
    intel_files = [f for f in s["file_list"] if f.startswith("intel:")]
    real_files  = [f for f in s["file_list"] if not f.startswith("intel:")]

    if intel_files:
        print(f"\n{DIM}  Intel sources ({len(intel_files)}):{R}")
        for src in sorted(intel_files):
            print(f"    • {DIM}{src}{R}")

    if real_files:
        print(f"\n{B}  Indexed files ({len(real_files)}):{R}")
        for i, f in enumerate(real_files, 1):
            print(f"    {DIM}{i:>2}.{R} {f}")
        print(f"\n  {DIM}Delete by number (or Enter to skip):{R} ", end="", flush=True)
        choice = input().strip()
        if choice.isdigit():
            idx = int(choice) - 1
            if 0 <= idx < len(real_files):
                target = real_files[idx]
                n = delete_file(target)
                # Also remove physical file from processed/ if it exists
                phys = DONE_DIR / target
                if phys.exists():
                    phys.unlink()
                    print(f"\n  {G}✅ Deleted: {target} ({n} chunks removed, file deleted){R}\n")
                else:
                    print(f"\n  {G}✅ Deleted: {target} ({n} chunks removed){R}\n")
            else:
                print(f"\n  {Y}Invalid number.{R}\n")
        else:
            print()
    else:
        print(f"\n  {DIM}No indexed files yet.{R}")

    # Backup status
    from core.backup import backup_status
    bk = backup_status()
    print(f"\n{B}💾 Backups:{R}")
    last = bk["last_backup"]
    if last == "never":
        print(f"  Last backup : {Y}never{R}")
    else:
        from datetime import datetime
        try:
            dt = datetime.fromisoformat(last)
            last_fmt = dt.strftime("%Y-%m-%d %H:%M")
        except Exception:
            last_fmt = last
        print(f"  Last backup : {G}{last_fmt}{R}  {DIM}({bk['size_mb']} MB){R}")
    print(f"  Stored      : {bk['total_backups']} / 7")
    print(f"  Next backup : {DIM}{bk['next_backup']}{R}")
    print()


def cmd_ideas():
    from core.agent import generate_ideas
    with Spinner("Generating 5 business ideas..."):
        ideas = generate_ideas(force=True)  # always fresh, ignore cache
    # Save to exports as a report
    out = EXPORT_DIR / f"ideas_{datetime.now().strftime('%Y%m%d_%H%M%S')}.md"
    out.write_text(f"# Ideas — {datetime.now().strftime('%Y-%m-%d %H:%M')}\n\n{ideas}", encoding="utf-8")
    print(f"\n{render_cli(ideas)}\n")
    print(f"{DIM}💾 Saved: {out.name}{R}\n")


def cmd_market():
    from core.market_pulse import collect_market_pulse, format_pulse
    with Spinner("Fetching market data..."):
        data = collect_market_pulse()
    print(f"\n{format_pulse(data)}\n")


def _parse_score(item) -> int:
    v = item.get("score") or item.get("stars") or 0
    try:
        return int(str(v).replace(",", "").split()[0])
    except Exception:
        return 0


def cmd_news(limit: int = 10):
    from core.intel import load_feed
    from core.ccw import ccw_label
    items = load_feed(limit=limit * 3)  # fetch more, then sort by CCW
    if not items:
        print(f"\n  {DIM}No news yet. Run /research first.{R}\n")
        return

    # Sort by CCW desc, then by engagement — take top N
    items = sorted(
        items,
        key=lambda x: (x.get("ccw", 0), _parse_score(x)),
        reverse=True,
    )[:limit]

    SOURCE_ICONS = {
        "hackernews":      f"{Y}HN{R}",
        "reddit":          f"{C}RD{R}",
        "github_trending": f"{G}GH{R}",
        "producthunt":     f"\033[35mPH{R}",
        "mastodon":        f"\033[34mMD{R}",
        "devto":           f"{G}DV{R}",
        "google_trends":   f"{Y}GT{R}",
        "rss":             f"\033[36mRS{R}",
    }

    print(f"\n{B}Latest {len(items)} news (sorted by CCW, #1 = top):{R}\n")
    # Display lowest-ranked first so highest CCW (#1) appears closest to the prompt
    for i, item in reversed(list(enumerate(items, 1))):
        src   = item.get("source", "")
        icon  = SOURCE_ICONS.get(src, src[:2].upper())
        title = item.get("title", "")
        url   = item.get("url", "")
        score = item.get("score") or item.get("stars") or ""
        score_str = f" {DIM}[{score}]{R}" if score else ""
        ccw = item.get("ccw", 0)
        ccw_str = f" {C}{ccw_label(ccw)}{R}" if ccw >= 5 else ""
        print(f"  {DIM}{i:>2}.{R} [{icon}] {B}{title}{R}{score_str}{ccw_str}")
        if item.get("ccw_reason"):
            print(f"       {DIM}↳ {item['ccw_reason']}{R}")
        if url:
            print(f"       {DIM}{url}{R}")
    print()


def cmd_briefing(days: int = 14):
    from core.trends import generate_briefing
    with Spinner(f"Generating briefing (last {days} days)..."):
        briefing = generate_briefing(days=days)
    print(f"\n{render_cli(briefing)}\n")


def cmd_predict(days: int = 14):
    from core.trends import generate_predictions
    with Spinner(f"Generating predictions (last {days} days)..."):
        result = generate_predictions(days=days)
    print(f"\n{render_cli(result)}\n")


def cmd_flows(days: int = 14):
    from core.trends import generate_money_flows
    with Spinner(f"Analyzing money flows (last {days} days)..."):
        result = generate_money_flows(days=days)
    print(f"\n{render_cli(result)}\n")


def cmd_remind(text: str):
    if not text.strip():
        print(f"  {Y}Usage: /remind <text with date>{R}")
        print(f"  {DIM}Example: /remind tomorrow at 10:00 call Ivan{R}\n")
        return
    intent = extract_reminder_intent(text)
    if not intent:
        dt = parse_date(text)
        if dt:
            title = re.sub(
                r"(завтра|сегодня|послезавтра|через .+?|в \d{1,2}[:.]\d{2}|"
                r"tomorrow|today|in \d+ \w+|on \w+|\d{1,2}[:.]\d{2})",
                "", text, flags=re.IGNORECASE
            ).strip(" —-–:,")
            intent = {"title": title or text, "dt": dt}
        else:
            print(f"  {Y}Could not parse date from: «{text}»{R}")
            print(f"  {DIM}Try: /remind tomorrow at 10:00 call Ivan{R}\n")
            return
    r = add_reminder(intent["title"], intent["dt"])
    print(f"\n  {G}✅ Reminder added:{R} {format_reminder(r)}\n")


def cmd_reminders():
    items = list_reminders()
    if not items:
        print(f"\n  {DIM}No active reminders.{R}\n")
        return
    print(f"\n{B}Active reminders ({len(items)}):{R}")
    for r in items:
        print(f"  {format_reminder(r)}")
    print()


def cmd_reports(arg: str = ""):
    """List or delete saved reports."""
    files = sorted(EXPORT_DIR.glob("*.md"), key=lambda f: f.stat().st_mtime, reverse=True)
    if not files:
        print(f"\n  {DIM}No reports yet.{R}\n")
        return

    parts = arg.strip().split()

    # /reports del <N>
    if parts and parts[0] == "del":
        if len(parts) < 2 or not parts[1].isdigit():
            print(f"  {Y}Usage: /reports del <number>{R}\n")
            return
        idx = int(parts[1]) - 1
        if idx < 0 or idx >= len(files):
            print(f"  {Y}Invalid number. Use /reports to see the list.{R}\n")
            return
        target = files[idx]
        target.unlink()
        print(f"\n  {G}✅ Deleted: {target.name}{R}\n")
        return

    # /reports view <N>
    if parts and parts[0] == "view":
        if len(parts) < 2 or not parts[1].isdigit():
            print(f"  {Y}Usage: /reports view <number>{R}\n")
            return
        idx = int(parts[1]) - 1
        if idx < 0 or idx >= len(files):
            print(f"  {Y}Invalid number. Use /reports to see the list.{R}\n")
            return
        f = files[idx]
        content = f.read_text(encoding="utf-8")
        print(f"\n{DIM}{'─' * 60}{R}")
        print(f"{B}{f.name}{R}")
        print(f"{DIM}{'─' * 60}{R}\n")
        print(render_cli(content))
        print(f"\n{DIM}{'─' * 60}{R}\n")
        return

    # /reports pdf <N>
    if parts and parts[0] == "pdf":
        if len(parts) < 2 or not parts[1].isdigit():
            print(f"  {Y}Usage: /reports pdf <number>{R}\n")
            return
        idx = int(parts[1]) - 1
        if idx < 0 or idx >= len(files):
            print(f"  {Y}Invalid number. Use /reports to see the list.{R}\n")
            return
        f = files[idx]
        try:
            from core.exporter import export_md_to_pdf
            with Spinner(f"Exporting {f.name} to PDF..."):
                pdf_path = export_md_to_pdf(f)
            print(f"\n  {G}✅ PDF saved: {pdf_path}{R}\n")
        except RuntimeError as e:
            print(f"\n  {Y}⚠️  {e}{R}\n")
        return

    # List — display oldest first so newest appears at bottom (no scrolling needed)
    print(f"\n{B}Saved reports ({len(files)}):{R}\n")
    for i, f in reversed(list(enumerate(files, 1))):
        size_kb = f.stat().st_size / 1024
        mtime = datetime.fromtimestamp(f.stat().st_mtime).strftime("%Y-%m-%d %H:%M")
        print(f"  {DIM}{i:>2}.{R} {B}{f.name}{R}")
        print(f"       {DIM}{mtime}  {size_kb:.1f} KB{R}")
    print(f"\n  {DIM}To view: /reports view <number>  |  To delete: /reports del <number>{R}\n")


_NO_DATA_MARKERS = (
    "no relevant information", "не найдено", "no data", "нет данных", "not found in",
    "ограниченная информация", "limited information", "не содержит", "отсутствует",
    "не представлена", "только косвенно", "недостаточно", "нет прямой",
    "контекст не содержит", "предоставленный контекст", "в контексте отсутствует",
)


def _web_fallback(question: str, result: dict) -> dict:
    """If RAG result is low-quality, search the web and return web-based answer."""
    if not _rag_has_no_data(result["answer"], result.get("sources", [])):
        return result
    from core.web_search import search_and_answer
    WEB = "\033[38;2;90;180;255m"
    with Spinner(f"{WEB}🌐 Searching the web...{R}"):
        web_result = search_and_answer(question)
    if not web_result:
        return result
    return web_result


def _rag_has_no_data(answer: str, sources: list) -> bool:
    """True if RAG answer is low-quality: vague text markers OR only intel feed sources."""
    a = answer.lower()
    if any(m in a for m in _NO_DATA_MARKERS):
        return True
    # All sources are intel feed items (no real indexed documents)
    if sources and all(str(s).startswith("intel:") for s in sources):
        return True
    return False


def cmd_report(topic: str):
    if not topic.strip():
        print(f"  {Y}Usage: /report <topic>{R}\n")
        return
    from core.config import get_mod
    from core.web_search import search
    scope = get_mod()
    scope_label = {"all": "all sources", "docs": "local documents", "intel": "research intel"}
    question = (
        f"Create a detailed structured report on the topic: «{topic}». "
        "Include all relevant data from the documents. "
        "Divide into sections with headings."
    )
    with Spinner(f"Generating report on: {topic} [{scope_label.get(scope, scope)}]..."):
        result = ask(question, scope=scope)

    # If RAG found nothing useful — enrich with web search
    web_sources = []
    if _rag_has_no_data(result["answer"], result.get("sources", [])):
        with Spinner(f"\033[38;2;90;180;255m🌐 No local data — searching the web for: {topic[:50]}\033[0m"):
            web_results = search(topic, max_results=6)
        if web_results:
            from core.rag_engine import llm
            from core.config import get_lang
            from langchain_core.messages import HumanMessage
            lang = get_lang()
            web_ctx = "\n\n---\n\n".join(
                f"[{r['title']}]\n{r['content']}\nSource: {r['url']}" for r in web_results
            )
            web_prompt = (
                f"Create a detailed structured report on: «{topic}».\n"
                f"Use ONLY the web search results below. Respond in {lang}. "
                f"Use ## headings, bullet points, bold key facts.\n\n"
                f"{web_ctx[:6000]}\n\nReport:"
            )
            with Spinner(f"\033[38;2;90;180;255m🌐 Building report from {len(web_results)} web results...\033[0m"):
                response = llm.invoke([HumanMessage(content=web_prompt)])
                from core.token_tracker import track_response
                track_response(response, "report.web")
            result = {"answer": response.content, "sources": []}
            web_sources = [r["url"] for r in web_results if r.get("url")]

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    slug = topic[:40].replace(" ", "_").replace("/", "-")
    out = EXPORT_DIR / f"report_{slug}_{ts}.md"
    content = f"# Report: {topic}\n_Created: {datetime.now().strftime('%Y-%m-%d %H:%M')}_\n\n"
    content += result["answer"]
    all_sources = list(result.get("sources", [])) + web_sources
    if all_sources:
        content += f"\n\n---\n**Sources:** {', '.join(all_sources)}"
    out.write_text(content, encoding="utf-8")
    print(f"\n{G}✅ Report saved: {out}{R}\n")
    preview = result["answer"]
    rendered = render_cli(preview[:800]) + f"\n{DIM}...{R}" if len(preview) > 800 else render_cli(preview)
    print(rendered)
    print()


def cmd_search(query: str):
    from core.web_search import search_and_answer
    if not query.strip():
        print(f"  {Y}Usage: /search <query>{R}\n")
        return
    WEB = "\033[38;2;90;180;255m"
    with Spinner(f"{WEB}🌐 Searching web: {query[:50]}...{R}"):
        result = search_and_answer(query)
    if not result:
        print(f"  {Y}No results found.{R}\n")
        return
    print(f"\n{WEB}{B}🌐 Web search:{R}")
    print(render_cli(result["answer"]))
    if result.get("sources"):
        print(f"\n{DIM}🔗 Sources:{R}")
        for url in result["sources"]:
            print(f"  {DIM}{url}{R}")
    print()


def cmd_tokens(arg: str = ""):
    from core.token_tracker import format_stats, reset as token_reset
    if arg.strip().lower() == "reset":
        print(f"\n  {Y}Reset token counter? All history will be cleared. [y/N]: {R}", end="", flush=True)
        confirm = input().strip().lower()
        if confirm == "y":
            token_reset()
            print(f"  {G}✅ Token counter reset.{R}\n")
        else:
            print(f"  {DIM}Cancelled.{R}\n")
        return
    print(f"\n{render_cli(format_stats())}\n")


def cmd_logs():
    from core.error_logger import format_errors
    print(f"\n{render_cli(format_errors())}\n")


def cmd_set(args: str):
    from core.config import set_lang, get_lang, set_currency, get_currency, set_mod, get_mod
    parts = args.strip().split()
    if len(parts) < 2:
        mod = get_mod()
        mod_desc = {"all": "all sources (docs + intel)", "docs": "local documents only", "intel": "research intel only"}
        print(f"\n  {B}Current settings:{R}")
        print(f"    lang     : {G}{get_lang()}{R}")
        print(f"    currency : {G}{get_currency()}{R}")
        print(f"    mod      : {G}{mod}{R}  {DIM}({mod_desc.get(mod, mod)}){R}")
        print(f"\n  {DIM}Usage: /set lang <code>      (e.g. EN, RU, ES)")
        print(f"         /set currency <code>  (e.g. USD, EUR, GBP)")
        print(f"         /set mod <scope>      (all | docs | intel){R}\n")
        return
    key = parts[0].lower()
    value = parts[1]
    if key == "lang":
        set_lang(value.upper())
        print(f"\n  {G}✅ Language set to {get_lang()}{R}\n")
    elif key == "currency":
        set_currency(value.upper())
        print(f"\n  {G}✅ Currency set to {get_currency()}{R}\n")
    elif key == "mod":
        try:
            set_mod(value.lower())
            mod = get_mod()
            mod_desc = {"all": "all sources (docs + intel)", "docs": "local documents only", "intel": "research intel only"}
            print(f"\n  {G}✅ Search mode set to {B}{mod}{G} — {mod_desc.get(mod, mod)}{R}\n")
        except ValueError as e:
            print(f"  {Y}{e}{R}\n")
    else:
        print(f"  {Y}Unknown setting: {key}. Available: lang, currency, mod{R}\n")


def cmd_rss(args: str):
    from core.rss import list_feeds, add_feed, remove_feed
    parts = args.strip().split(None, 1)
    sub = parts[0].lower() if parts else "list"

    if sub == "list" or not parts:
        feeds = list_feeds()
        if not feeds:
            print(f"\n  {DIM}No RSS feeds configured. Use /rss add <url>{R}\n")
            return
        print(f"\n{B}RSS feeds ({len(feeds)}):{R}\n")
        for i, f in enumerate(feeds, 1):
            print(f"  {DIM}{i:>2}.{R} {B}{f['name']}{R}")
            print(f"       {DIM}{f['url']}{R}")
            print(f"       {DIM}Added: {f['added']}{R}")
        print(f"\n  {DIM}Remove: /rss remove <number>{R}\n")

    elif sub == "add":
        url = parts[1].strip() if len(parts) > 1 else ""
        if not url:
            print(f"  {Y}Usage: /rss add <url>{R}\n")
            return
        result = None
        error  = None
        with Spinner("Validating feed..."):
            try:
                result = add_feed(url)
            except Exception as e:
                error = e
        if result:
            print(f"\n  {G}✅ Added: {result['name']}{R}\n  {DIM}{result['url']}{R}\n")
        else:
            print(f"\n  {Y}⚠️  {error}{R}\n")

    elif sub == "remove":
        n_str = parts[1].strip() if len(parts) > 1 else ""
        if not n_str.isdigit():
            print(f"  {Y}Usage: /rss remove <number>{R}\n")
            return
        try:
            removed = remove_feed(int(n_str))
            print(f"\n  {G}✅ Removed: {removed['name']}{R}\n")
        except Exception as e:
            print(f"\n  {Y}⚠️  {e}{R}\n")

    else:
        print(f"  {Y}Usage: /rss list | /rss add <url> | /rss remove <N>{R}\n")


def _print_answer(result: dict):
    from core.config import get_mod
    mod = get_mod()
    mod_icon = {"all": "⬡", "docs": "📄", "intel": "🔍"}.get(mod, "●")
    print(f"\n{DIM}{'─' * 64}{R}")
    print(render_cli(result["answer"]))
    print(f"{DIM}{'─' * 64}{R}")
    # Sources: show doc files always; show intel sources only in intel/all mode
    sources = result.get("sources", [])
    doc_sources   = [s for s in sources if not s.startswith("intel:")]
    intel_sources = [s for s in sources if s.startswith("intel:")]
    footer_parts = []
    if doc_sources:
        footer_parts.append(f"📄 {', '.join(doc_sources)}")
    if intel_sources and mod in ("all", "intel"):
        labels = [s.replace("intel:", "") for s in intel_sources]
        footer_parts.append(f"🔍 {', '.join(labels)}")
    if footer_parts:
        print(f"{DIM}  {mod_icon} {' │ '.join(footer_parts)}{R}")
    print()


# ── Reminder watcher (background) ─────────────────────────────────────────────

def _start_reminder_watcher():
    def _on_due(r):
        dt_str = r.get("dt", "")
        try:
            dt_str = datetime.fromisoformat(dt_str).strftime("%H:%M")
        except Exception:
            pass
        out = sys.__stdout__
        out.write(f"\n{Y}⏰ REMINDER [{dt_str}]: {r['title']}{R}\n")
        out.write(f"{C}▶ {R}")
        out.flush()

    start_watcher(on_due=_on_due)


# ── Auto-research scheduler ───────────────────────────────────────────────────

def _start_auto_research():
    interval_min = int(os.getenv("AUTO_RESEARCH_INTERVAL", "0"))
    if interval_min <= 0:
        return

    def _loop():
        import io as _io
        while True:
            time.sleep(interval_min * 60)
            from core.intel import collect_and_index
            from core.trends import quick_summary_from_new

            gate = _sync_gates["research"]
            # Suppress [Intel] prints from background thread
            _old, sys.stdout = sys.stdout, _io.StringIO()
            try:
                result, is_fresh = gate.run(collect_and_index)
            finally:
                sys.stdout = _old

            if not is_fresh:
                continue  # manual /research ran simultaneously — skip duplicate output

            new_items = result.get("new_items", [])
            if new_items:
                _old2, sys.stdout = sys.stdout, _io.StringIO()
                try:
                    summary = quick_summary_from_new(new_items)
                finally:
                    sys.stdout = _old2
                out = sys.__stdout__
                out.write(f"\n{Y}[Auto-research] {result['total_new']} new items{R}\n")
                out.write(render_cli(summary) + "\n")
                out.write(f"{C}▶ {R}")
                out.flush()

    t = threading.Thread(target=_loop, daemon=True)
    t.start()


# ── Main loop ──────────────────────────────────────────────────────────────────

def main():
    print(BANNER)
    _print_status()

    _start_reminder_watcher()
    _start_auto_research()

    # Backup check — runs once on start (backs up if >24h since last backup)
    from core.backup import check_and_backup
    import threading
    threading.Thread(target=check_and_backup, daemon=True, name="backup-check").start()

    # Conversation history for multi-turn context (in-memory, current session only)
    _history: list[tuple[str, str]] = []

    while True:
        user = _read_input(f"{C}▶ {R}")

        if not user:
            continue

        # ── Exit ──────────────────────────────────────────────────────────────
        if user.lower() in ("/exit", "/quit", "exit", "quit"):
            unload_llm()
            print(f"{DIM}Bye!{R}")
            break

        # ── Help ──────────────────────────────────────────────────────────────
        elif user == "/help":
            print(HELP)

        # ── Commands ──────────────────────────────────────────────────────────
        elif user == "/research":
            cmd_research()

        elif user.startswith("/news"):
            arg = user[5:].strip()
            limit = int(arg) if arg.isdigit() else 10
            cmd_news(limit)

        elif user == "/stats":
            cmd_stats()

        elif user == "/ideas":
            cmd_ideas()

        elif user == "/market":
            cmd_market()

        elif user.startswith("/briefing"):
            arg = user[9:].strip()
            try:
                days = int(arg) if arg else 14
            except ValueError:
                days = 14
            cmd_briefing(days=days)

        elif user.startswith("/predict"):
            arg = user[8:].strip()
            try:
                days = int(arg) if arg else 14
            except ValueError:
                days = 14
            cmd_predict(days=days)

        elif user.startswith("/flows"):
            arg = user[6:].strip()
            try:
                days = int(arg) if arg else 14
            except ValueError:
                days = 14
            cmd_flows(days=days)

        elif user.startswith("/remind "):
            cmd_remind(user[8:])

        elif user == "/remind":
            cmd_remind("")

        elif user == "/reminders":
            cmd_reminders()

        elif user.startswith("/report "):
            cmd_report(user[8:])

        elif user == "/report":
            cmd_report("")

        elif user.startswith("/reports"):
            cmd_reports(user[8:].strip())

        elif user.startswith("/tokens"):
            cmd_tokens(user[7:].strip())

        elif user == "/logs":
            cmd_logs()

        elif user.lower().startswith("/set"):
            cmd_set(user[4:])

        elif user.lower().startswith("/rss"):
            cmd_rss(user[4:].strip())

        elif user.startswith("/"):
            print(f"  {Y}Unknown command. Type /help{R}\n")

        # ── File path / drag & drop ───────────────────────────────────────────
        elif _looks_like_path(user):
            paths = _split_paths(user)
            if paths:
                _handle_files(paths)
            else:
                # Path exists but unsupported format
                p = Path(user.strip('"').replace("\\", "/")).expanduser()
                if p.exists():
                    print(f"  {Y}Unsupported format: {p.suffix}. Supported: {', '.join(SUPPORTED_EXTS)}{R}\n")
                else:
                    # Treat as a regular question
                    with Spinner("Thinking..."):
                        result = ask(user, history=_history)
                    result = _web_fallback(user, result)
                    _print_answer(result)
                    _history.append((user, result["answer"]))
                    if len(_history) > 10:
                        _history = _history[-10:]

        # ── RAG question ──────────────────────────────────────────────────────
        else:
            with Spinner("Thinking..."):
                result = ask(user, history=_history)
            result = _web_fallback(user, result)
            _print_answer(result)
            # Update conversation memory (keep last 10 turns)
            _history.append((user, result["answer"]))
            if len(_history) > 10:
                _history = _history[-10:]


if __name__ == "__main__":
    main()
