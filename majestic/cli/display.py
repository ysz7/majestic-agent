import os
import re
import sys
import threading
import time
from datetime import datetime, date
from pathlib import Path

_ANSI_ESC = re.compile(r'\033(?:\[[0-9;]*m|\]8;;[^\033]*\033\\)')

R   = "\033[0m"
B   = "\033[1m"
C   = "\033[38;2;217;87;103m"
G   = "\033[32m"
Y   = "\033[33m"
DIM = "\033[2m"
RED = "\033[31m"

_LOGO_LINES = [
    "███╗   ███╗ █████╗      ██╗███████╗███████╗████████╗██╗ ██████╗ ",
    "████╗ ████║██╔══██╗     ██║██╔════╝██╔════╝╚══██╔══╝██║██╔════╝ ",
    "██╔████╔██║███████║     ██║█████╗  ███████╗   ██║   ██║██║      ",
    "██║╚██╔╝██║██╔══██║██   ██║██╔══╝  ╚════██║   ██║   ██║██║      ",
    "██║ ╚═╝ ██║██║  ██║╚█████╔╝███████╗███████║   ██║   ██║╚██████╗ ",
    "╚═╝     ╚═╝╚═╝  ╚═╝ ╚════╝ ╚══════╝╚══════╝   ╚═╝   ╚═╝ ╚═════╝",
]


class Spinner:
    """Animated terminal spinner. Swallows stdout from inner code."""
    _FRAMES = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"

    def __init__(self, text: str = "Thinking..."):
        self.text    = text
        self._stop   = threading.Event()
        self._thread = threading.Thread(target=self._spin, daemon=True)
        self._real: object = None

    def _spin(self) -> None:
        i = 0
        while not self._stop.is_set():
            frame = self._FRAMES[i % len(self._FRAMES)]
            self._real.write(f"\r\033[2K\033[36m{frame}\033[0m {self.text}")  # type: ignore[attr-defined]
            self._real.flush()  # type: ignore[attr-defined]
            i += 1
            time.sleep(0.08)

    def __enter__(self) -> "Spinner":
        import io
        self._real = sys.__stdout__
        sys.stdout = io.StringIO()
        self._thread.start()
        return self

    def __exit__(self, *_) -> None:
        self._stop.set()
        self._thread.join()
        sys.stdout = self._real  # type: ignore[assignment]
        self._real.write("\r\033[2K")  # type: ignore[attr-defined]
        self._real.flush()  # type: ignore[attr-defined]


def _vis(s: str) -> int:
    """Visual (printable) width of a string — strips ANSI escape codes."""
    return len(_ANSI_ESC.sub('', s))


def _gather_startup() -> dict:
    """Collect all data for the startup panel. Never raises."""
    out: dict = {
        'model': '—', 'provider': 'anthropic', 'api_ok': False,
        'mem_count': 0, 'user_first': '', 'skills': [], 'recent': [],
        'workdir': str(Path.cwd()),
    }
    try:
        from majestic import config as cfg
        out['model']    = (cfg.get('llm.model')    or '—')
        out['provider'] = (cfg.get('llm.provider') or 'anthropic')
        key_map = {
            'anthropic':  'ANTHROPIC_API_KEY',
            'openai':     'OPENAI_API_KEY',
            'openrouter': 'OPENROUTER_API_KEY',
        }
        key_var = key_map.get(out['provider'], '')
        out['api_ok'] = bool(os.environ.get(key_var)) if key_var else True
    except Exception:
        pass
    try:
        from majestic.memory.store import load_user, load_memory
        u = load_user()
        m = load_memory()
        out['mem_count'] = sum(1 for p in (u + '\n\n' + m).split('\n\n') if p.strip())
        out['user_first'] = next(
            (l.strip() for l in u.splitlines() if l.strip() and not l.startswith('#')), ''
        )[:48]
    except Exception:
        pass
    try:
        from majestic.skills.loader import list_skills
        out['skills'] = list_skills() or []
    except Exception:
        pass
    try:
        from majestic.db.state import StateDB
        rows = StateDB()._conn.execute(
            "SELECT source, started_at FROM sessions ORDER BY started_at DESC LIMIT 3"
        ).fetchall()
        out['recent'] = [(r['source'], r['started_at']) for r in rows]
    except Exception:
        pass
    return out



def print_startup() -> None:
    """Two-column startup panel."""
    d = _gather_startup()

    # ── Logo ─────────────────────────────────────────────────────────────────
    print()
    for line in _LOGO_LINES:
        print(f"  {C}{B}{line}{R}")

    today = date.today().strftime("%Y.%m.%d")
    print()
    print(f"  {C}Majestic Agent v0.1.0 ({today}){R}  {DIM}·  github.com/ysz7/majestic-agent{R}")
    print(f"  {DIM}{'─' * 68}{R}")
    print()

    # ── Column widths ────────────────────────────────────────────────────────
    LW, RW = 30, 56

    # ── Left column ──────────────────────────────────────────────────────────
    model    = (d['model'] or '—')[:19]
    provider = d['provider']
    api_dot  = f"{G}●{R}" if d['api_ok'] else f"{RED}●{R}"
    mc       = d['mem_count']
    mem_col  = G if mc else DIM
    mem_str  = f"{'on' if mc else 'off'} · {mc} fact{'s' if mc != 1 else ''}"
    wd       = d['workdir']
    if len(wd) > 19:
        wd = '…' + wd[-18:]

    left: list[str] = [
        f"{C}  *   *   *   *   *{R}",
        f"{C}  |\\ /|\\ /|\\ /|\\ /|{R}",
        f"{C}  | X | X | X | X |{R}",
        f"{C}  |/ \\|/ \\|/ \\|/ \\|{R}",
        f"{C}  ‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾{R}",
        f"{C}   M A J E S T I C{R}",
        "",
        f"{DIM}model    · {R}{model}",
        f"{DIM}provider · {R}{api_dot} {provider}",
        f"{DIM}memory   · {R}{mem_col}{mem_str}{R}",
        f"{DIM}workdir  · {R}{DIM}{wd}{R}",
        f"{DIM}session  · {R}{DIM}new{R}",
        "",
        f"{C}── RECENT ACTIVITY ──{R}",
    ]
    if d['recent']:
        for src, ts in d['recent']:
            try:
                delta = datetime.now() - datetime.fromisoformat(ts)
                if delta.days == 0:    rel = "today"
                elif delta.days == 1:  rel = "yesterday"
                else:                  rel = f"{delta.days}d ago"
                left.append(f"{DIM}·{R} {DIM}{rel:<10}{R}{src}")
            except Exception:
                left.append(f"{DIM}· {src}{R}")
    else:
        left.append(f"{DIM}no activity yet{R}")

    # ── Right column ─────────────────────────────────────────────────────────
    def _sec(title: str) -> str:
        dashes = '─' * max(0, RW - len(title) - 1)
        return f"{C}{title}{R} {DIM}{dashes}{R}"

    skills    = d['skills']
    skill_cnt = len(skills)
    uf        = d['user_first']

    right: list[str] = [
        _sec("AVAILABLE TOOLS"),
        f"{DIM}web:        {R}web_search, web_extract",
        f"{DIM}research:   {R}news, briefing, report, predict",
        f"{DIM}market:     {R}crypto, stocks, forex, flows",
        f"{DIM}files:      {R}read_file, write_file, index",
        f"{DIM}system:     {R}terminal",
        f"{DIM}core:       {R}{C}db_search{R}",
        "",
        _sec("AVAILABLE SKILLS"),
    ]
    if skills:
        for sk in skills[:3]:
            n    = (sk.get('name') or '?')[:14]
            desc = (sk.get('description') or '')[:RW - 17]
            right.append(f"{DIM}/{n:<14}{R}  {desc}")
        if skill_cnt > 3:
            right.append(f"{DIM}+ {skill_cnt - 3} more{R}")
    else:
        right.append(f"{DIM}none yet — add to ~/.majestic-agent/skills/{R}")
    right += ["", _sec("MEMORY SNAPSHOT")]
    right.append(f"{DIM}user:  {R}{uf if uf else DIM + '(empty)' + R}")
    right.append(f"{DIM}agent: {R}{mc} fact{'s' if mc != 1 else ''}")

    # ── Render two-column box ─────────────────────────────────────────────────
    height     = max(len(left), len(right))
    left_rows  = left  + [''] * (height - len(left))
    right_rows = right + [''] * (height - len(right))

    print(f" ┌{'─' * (LW + 2)}┐  ┌{'─' * (RW + 2)}┐")
    for lc, rc in zip(left_rows, right_rows):
        lp = ' ' * max(0, LW - _vis(lc))
        rp = ' ' * max(0, RW - _vis(rc))
        print(f" │ {lc}{lp} │  │ {rc}{rp} │")
    print(f" └{'─' * (LW + 2)}┘  └{'─' * (RW + 2)}┘")

    print()
    print(f"  {DIM}6 toolsets · {skill_cnt} skill{'s' if skill_cnt != 1 else ''} · {mc} memor{'ies' if mc != 1 else 'y'}  ·  /help for commands{R}")
    print()
    print(f"  {C}Welcome to Majestic!{R} Type your message or {B}/help{R} for commands.")
    print(f"  {DIM}· /research for fresh intel  ·  /briefing for daily summary{R}")
    print()
    print()


def ok(msg: str) -> None:
    print(f"  {G}✓{R} {msg}")


def warn(msg: str) -> None:
    print(f"  {Y}⚠{R}  {msg}")


def err(msg: str) -> None:
    print(f"  {RED}✗{R} {msg}")


def info(msg: str) -> None:
    print(f"  {DIM}{msg}{R}")


def ask(prompt: str, default: str = "") -> str:
    hint = f" [{default}]" if default else ""
    try:
        val = input(f"  {B}{prompt}{hint}:{R} ").strip()
    except (EOFError, KeyboardInterrupt):
        print()
        raise SystemExit(0)
    return val or default


def choose(prompt: str, options: list[str], default: int = 0) -> int:
    print(f"\n  {B}{prompt}{R}")
    for i, opt in enumerate(options, 1):
        marker = f"{C}▶{R}" if i - 1 == default else " "
        print(f"  {marker} {i}. {opt}")
    raw = ask("Select", str(default + 1))
    try:
        idx = int(raw) - 1
        return idx if 0 <= idx < len(options) else default
    except ValueError:
        return default
