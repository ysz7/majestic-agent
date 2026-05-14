import os
import re
import sys
import threading
import time
from datetime import datetime, date
from pathlib import Path

# ── ANSI helpers ─────────────────────────────────────────────────────────────

_ANSI_ESC = re.compile(r'\033(?:\[[0-9;]*m|\]8;;[^\033]*\033\\)')

R   = "\033[0m"
B   = "\033[1m"
C   = "\033[38;2;217;87;103m"
G   = "\033[32m"
Y   = "\033[33m"
DIM = "\033[2m"
RED = "\033[31m"
CYN = "\033[36m"

# ── ASCII logo ────────────────────────────────────────────────────────────────

_LOGO_LINES = [
    "███╗   ███╗ █████╗      ██╗███████╗███████╗████████╗██╗ ██████╗ ",
    "████╗ ████║██╔══██╗     ██║██╔════╝██╔════╝╚══██╔══╝██║██╔════╝ ",
    "██╔████╔██║███████║     ██║█████╗  ███████╗   ██║   ██║██║      ",
    "██║╚██╔╝██║██╔══██║██   ██║██╔══╝  ╚════██║   ██║   ██║██║      ",
    "██║ ╚═╝ ██║██║  ██║╚█████╔╝███████╗███████║   ██║   ██║╚██████╗ ",
    "╚═╝     ╚═╝╚═╝  ╚═╝ ╚════╝ ╚══════╝╚══════╝   ╚═╝   ╚═╝ ╚═════╝",
]

# ── Spinner ───────────────────────────────────────────────────────────────────

class Spinner:
    """Animated terminal spinner shown while agent is thinking or acting."""

    _FRAMES = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"

    def __init__(self, text: str = "Thinking..."):
        self.text = text
        self._stop   = threading.Event()
        self._thread = threading.Thread(target=self._spin, daemon=True)
        self._real   = None

    def _spin(self) -> None:
        i = 0
        while not self._stop.is_set():
            frame = self._FRAMES[i % len(self._FRAMES)]
            self._real.write(f"\r\033[2K{CYN}{frame}{R} {self.text}")
            self._real.flush()
            i += 1
            time.sleep(0.08)

    def __enter__(self) -> "Spinner":
        import io
        self._real  = sys.__stdout__
        sys.stdout  = io.StringIO()
        self._thread.start()
        return self

    def __exit__(self, *_) -> None:
        self._stop.set()
        self._thread.join()
        sys.stdout = self._real
        self._real.write("\r\033[2K")
        self._real.flush()


# ── Helpers ───────────────────────────────────────────────────────────────────

def _vis(s: str) -> int:
    """Visual width — strips ANSI escape codes."""
    return len(_ANSI_ESC.sub('', s))


def _gather_startup(profile: str = "default") -> dict:
    """Collect all data for the startup panel. Never raises."""
    out: dict = {
        "profile":        profile,
        "agent_name":     "Assistant",
        "role":           "—",
        "model":          "—",
        "api_ok":         False,
        "port":           "—",
        "mode":           "foreground",
        "skills":         [],
        "skill_count":    0,
        "mem_count":      0,
        "lessons_count":  0,
        "running_agents": [],
        "has_brave":      False,
        "limits":         {"max_tokens": 0, "max_cost": 0},
        "recent":         [],
        "workdir":        str(Path.cwd()),
    }

    settings = None
    try:
        from majestic.config.settings import Settings
        settings = Settings(profile)

        out["agent_name"] = settings.agent_name
        out["role"]       = settings.agent_role
        out["model"]      = settings.get_model()
        lim = settings.limits
        out["limits"] = {
            "max_tokens": lim.get("max_tokens_per_task", 0),
            "max_cost":   lim.get("max_cost_per_task",   0),
        }
        out["port"] = str(settings.agent_port)
        out["api_ok"] = bool(
            settings._env_get("OPENROUTER_API_KEY")
            or settings._env_get("ANTHROPIC_API_KEY")
            or settings._env_get("OPENAI_API_KEY")
            or settings._env_get("OLLAMA_BASE_URL")
        )
        out["has_brave"] = bool(settings._env_get("BRAVE_SEARCH_API_KEY"))
    except Exception:
        pass

    if settings is not None:
        try:
            from majestic.memory.procedural import ProceduralMemory
            pm = ProceduralMemory(str(settings.skills_dir))
            all_skills = pm.get_all()
            out["skills"]      = all_skills
            out["skill_count"] = len(all_skills)
        except Exception:
            pass

        try:
            from majestic.memory.episodic import EpisodicMemory
            db_path = str(settings.data_dir / "episodic.db")
            em = EpisodicMemory(db_path)
            out["mem_count"] = em.count()
            recent = em.get_recent(limit=3)
            out["recent"] = [
                {"started_at": r.get("timestamp", ""), "goal": r.get("task", "")}
                for r in recent
            ]
            em.close()
        except Exception:
            pass

        try:
            import sqlite3 as _sqlite3
            lessons_db = settings.data_dir / "lessons.db"
            if lessons_db.exists():
                conn = _sqlite3.connect(str(lessons_db))
                row = conn.execute("SELECT COUNT(*) FROM lessons").fetchone()
                conn.close()
                out["lessons_count"] = row[0] if row else 0
        except Exception:
            pass

    try:
        import json
        reg = Path(__file__).resolve().parent.parent / "data" / "registry.json"
        if reg.exists():
            data = json.loads(reg.read_text())
            out["running_agents"] = [
                {"name": k, "port": v.get("port", "?"), "status": v.get("status", "?")}
                for k, v in data.items()
            ]
    except Exception:
        pass

    return out


# ── Main startup panel ────────────────────────────────────────────────────────

def print_startup(profile: str = "default", mode: str = "foreground") -> None:
    """Two-column startup panel with logo."""

    d = _gather_startup(profile)
    d["mode"] = mode

    # Logo
    print()
    for line in _LOGO_LINES:
        print(f"  {C}{B}{line}{R}")

    today = date.today().strftime("%Y.%m.%d")
    print()
    print(f"  {C}Majestic v0.1.0  ·  {today}{R}  {DIM}github.com/ysz7/majestic-agent{R}")
    print(f"  {DIM}{'─' * 72}{R}")
    print()

    LW, RW = 32, 58

    # ── Left column ───────────────────────────────────────────────────────

    api_dot   = f"{G}●{R}" if d["api_ok"]    else f"{RED}●{R}"
    brave_dot = f"{G}●{R}" if d["has_brave"] else f"{Y}●{R}"

    tok_lim  = str(d["limits"]["max_tokens"]) if d["limits"]["max_tokens"] else "unlimited"
    cost_lim = f"${d['limits']['max_cost']}"  if d["limits"]["max_cost"]   else "unlimited"

    wd = d["workdir"]
    if len(wd) > 22:
        wd = "…" + wd[-21:]

    left: list[str] = [
        f"{C} *   *   *   *   *{R}",
        f"{C} |\\ /|\\ /|\\ /|\\ /|{R}",
        f"{C} | X | X | X | X |{R}",
        f"{C} |/ \\|/ \\|/ \\|/ \\|{R}",
        f"{C} ‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾{R}",
        f"{C}  M A J E S T I C{R}",
        "",
        f"{DIM}profile  · {R}{C}{d['profile']}{R}",
        f"{DIM}agent    · {R}{B}{d['agent_name']}{R}",
        f"{DIM}role     · {R}{DIM}{(d['role'][:20] + '…') if len(d['role']) > 21 else d['role']}{R}",
        f"{DIM}mode     · {R}{'background' if mode == 'background' else 'foreground'}",
        f"{DIM}port     · {R}{d['port']}  {DIM}(bg only){R}",
        f"{DIM}api      · {R}{api_dot} ok" if d["api_ok"] else f"{DIM}api      · {R}{api_dot} missing key",
        f"{DIM}search   · {R}{brave_dot} {'Brave' if d['has_brave'] else 'DuckDuckGo (free)'}",
        f"{DIM}workdir  · {R}{DIM}{wd}{R}",
        "",
        f"{C}── LIMITS ──────────────────{R}",
        f"{DIM}tokens   · {R}{tok_lim}",
        f"{DIM}cost     · {R}{cost_lim}",
        "",
        f"{C}── RECENT TASKS ────────────{R}",
    ]

    if d["recent"]:
        for task in d["recent"]:
            try:
                delta = datetime.now() - datetime.fromisoformat(task["started_at"])
                rel   = "today" if delta.days == 0 else ("yesterday" if delta.days == 1 else f"{delta.days}d ago")
                label = (task.get("goal") or "")[:18]
                left.append(f"{DIM}·{R} {DIM}{rel:<10}{R}{label}")
            except Exception:
                left.append(f"{DIM}· {task}{R}")
    else:
        left.append(f"{DIM}no tasks yet{R}")

    # ── Right column ──────────────────────────────────────────────────────

    def _sec(title: str) -> str:
        dashes = "─" * max(0, RW - len(title) - 1)
        return f"{C}{title}{R} {DIM}{dashes}{R}"

    skills      = d["skills"]
    skill_cnt   = d["skill_count"]
    mem_cnt     = d["mem_count"]
    lessons_cnt = d["lessons_count"]
    agents      = d["running_agents"]

    right: list[str] = [
        _sec("MODEL"),
        f"{DIM}model    · {R}{(d['model'] or '—')[:RW - 12]}",
        "",
        _sec("TOOLS"),
        f"{DIM}web      · {R}web_search  web_fetch",
        f"{DIM}net      · {R}http",
        f"{DIM}fs       · {R}files  file_parser",
        f"{DIM}exec     · {R}python_exec  node_exec",
        f"{DIM}agents   · {R}agent_client",
        f"{DIM}ext      · {R}MCP servers (registry.yaml)",
        "",
        _sec("SKILLS"),
    ]

    if skills:
        for sk in skills[:4]:
            n    = (sk.get("name", "?"))[:16]
            desc = (sk.get("description", ""))[:RW - 19]
            right.append(f"{DIM}/{n:<16}{R} {desc}")
        if skill_cnt > 4:
            right.append(f"{DIM}+ {skill_cnt - 4} more{R}")
    else:
        right.append(f"{DIM}none yet — add YAML files to skills/{R}")

    right += [
        "",
        _sec("MEMORY"),
        f"{DIM}episodic · {R}{G if mem_cnt else DIM}{mem_cnt} task{'s' if mem_cnt != 1 else ''}{R}",
        f"{DIM}lessons  · {R}{G if lessons_cnt else DIM}{lessons_cnt} lesson{'s' if lessons_cnt != 1 else ''}{R}",
        f"{DIM}semantic · {R}{DIM}sqlite-vec{R}",
        "",
        _sec("RUNNING AGENTS"),
    ]

    if agents:
        for ag in agents[:4]:
            name   = ag["name"][:12]
            port   = ag["port"]
            status = ag["status"]
            dot    = G if status == "running" else Y
            right.append(f"  {dot}●{R} {name:<14} {DIM}:{port}{R}")
    else:
        right.append(f"{DIM}none — use: majestic run <profile>{R}")

    # ── Render two-column box ─────────────────────────────────────────────

    height    = max(len(left), len(right))
    left_rows  = left  + [""] * (height - len(left))
    right_rows = right + [""] * (height - len(right))

    print(f"  ┌{'─' * (LW + 2)}┐  ┌{'─' * (RW + 2)}┐")
    for lc, rc in zip(left_rows, right_rows):
        lp = " " * max(0, LW - _vis(lc))
        rp = " " * max(0, RW - _vis(rc))
        print(f"  │ {lc}{lp} │  │ {rc}{rp} │")
    print(f"  └{'─' * (LW + 2)}┘  └{'─' * (RW + 2)}┘")

    print()
    print(
        f"  {DIM}8 tools · {skill_cnt} skill{'s' if skill_cnt != 1 else ''} · "
        f"{mem_cnt} memor{'ies' if mem_cnt != 1 else 'y'} · "
        f"{lessons_cnt} lesson{'s' if lessons_cnt != 1 else ''}{R}"
    )
    print()
    print(f"  {C}Welcome, {d['agent_name']}!{R}  Type your message or {B}/help{R} for commands.")
    print(f"  {DIM}· /help · /skills · /agents · /memory · /budget · /quit{R}")
    print()
    print()


# ── Utility print functions ───────────────────────────────────────────────────

def ok(msg: str) -> None:
    print(f"  {G}✓{R} {msg}")

def warn(msg: str) -> None:
    print(f"  {Y}⚠{R} {msg}")

def err(msg: str) -> None:
    print(f"  {RED}✗{R} {msg}")

def info(msg: str) -> None:
    print(f"  {DIM}{msg}{R}")

def budget_warn(pct: int, kind: str, used: str, limit: str) -> None:
    """Shown when token or cost budget hits 80%+."""
    print(f"  {Y}⚠{R} {B}{pct}%{R} of {kind} budget used  {DIM}({used} / {limit}){R}")

def budget_exceeded(kind: str, used: str, limit: str) -> None:
    """Shown when budget is fully exhausted."""
    print(f"  {RED}✗{R} {kind} limit reached  {DIM}({used} / {limit}){R}  Task stopped.")

def agent_delegating(to: str, task_preview: str) -> None:
    """Shown when current agent delegates to another."""
    preview = task_preview[:48] + "…" if len(task_preview) > 48 else task_preview
    print(f"  {CYN}→{R} Delegating to {B}{to}{R}  {DIM}{preview}{R}")

def agent_result(from_agent: str) -> None:
    """Shown when delegated result comes back."""
    print(f"  {G}←{R} Result from {B}{from_agent}{R}")

def reflection_start() -> None:
    print(f"  {DIM}· reflecting on task...{R}")

def lesson_saved(lesson: str) -> None:
    preview = lesson[:56] + "…" if len(lesson) > 56 else lesson
    print(f"  {G}✓{R} {DIM}lesson saved:{R} {preview}")

def task_report(steps: int, tokens: int, cost: float, elapsed: float) -> None:
    """Summary shown after every task completes."""
    print()
    print(f"  {DIM}{'─' * 56}{R}")
    print(
        f"  {DIM}steps {steps}  ·  tokens {tokens:,}  ·  "
        f"cost ${cost:.4f}  ·  {elapsed:.1f}s{R}"
    )
    print(f"  {DIM}{'─' * 56}{R}")
    print()

def ask(prompt: str, default: str = "") -> str:
    hint = f" [{default}]" if default else ""
    try:
        val = input(f"  {B}{prompt}{hint}:{R} ").strip()
    except (EOFError, KeyboardInterrupt):
        print()
        raise SystemExit(0)
    return val or default

def choose(prompt: str, options: list[str], default: int = 0) -> int:
    """Arrow-key selection via questionary when available; numbered list fallback."""
    try:
        import questionary
        default_choice = options[default] if 0 <= default < len(options) else options[0]
        result = questionary.select(prompt, choices=options, default=default_choice).ask()
        if result is None:
            raise SystemExit(0)
        return options.index(result)
    except ImportError:
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

def confirm_delete(profile_name: str) -> bool:
    """Used by majestic rm — requires typing the profile name."""
    print()
    warn(f"This will permanently delete profile {B}{profile_name}{R}")
    print(f"  {DIM}including all data, memory, workspace files and skills.{R}")
    print()
    typed = ask(f"Type the profile name to confirm")
    return typed == profile_name

def print_agents_table(agents: list[dict]) -> None:
    """Used by majestic ps."""
    if not agents:
        info("No agents running. Use: majestic run <profile>")
        return
    print()
    print(f"  {B}{'NAME':<20} {'PORT':<8} {'PID':<8} {'STATUS':<10} STARTED{R}")
    print(f"  {DIM}{'─' * 60}{R}")
    for ag in agents:
        dot    = f"{G}●{R}" if ag.get("status") == "running" else f"{Y}●{R}"
        name   = ag.get("name", "?")[:18]
        port   = str(ag.get("port", "?"))
        pid    = str(ag.get("pid",  "?"))
        status = ag.get("status", "?")
        try:
            delta   = datetime.now() - datetime.fromisoformat(ag.get("started_at", ""))
            started = "today" if delta.days == 0 else f"{delta.days}d ago"
        except Exception:
            started = "—"
        print(f"  {dot} {name:<20} {port:<8} {pid:<8} {status:<10} {DIM}{started}{R}")
    print()

def print_profiles_list(profiles: list[str], active: str = "") -> None:
    """Used by majestic list."""
    print()
    print(f"  {B}Available profiles:{R}")
    print()
    for p in profiles:
        marker = f"{C}▶{R}" if p == active else " "
        tag    = f"  {DIM}(active){R}" if p == active else ""
        print(f"  {marker} {p}{tag}")
    print()
    print(f"  {DIM}Run a profile: majestic <profile>{R}")
    print(f"  {DIM}Background:    majestic run <profile>{R}")
    print()
