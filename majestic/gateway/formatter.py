"""Markdown rendering — ANSI for CLI, HTML for Telegram, Markdown for Discord."""
import re

_R   = "\033[0m"
_B   = "\033[1m"
_DIM = "\033[2m"
_C   = "\033[38;2;217;87;103m"
_G   = "\033[32m"
_Y   = "\033[33m"
_CY  = "\033[36m"


def render_cli(text: str) -> str:
    """Convert Markdown to ANSI-colored terminal output."""
    lines = text.splitlines()
    out: list[str] = []
    in_code = False
    for line in lines:
        if line.strip().startswith("```"):
            in_code = not in_code
            out.append(f"{_DIM}{'─' * 50}{_R}")
            if in_code:
                lang = line.strip()[3:].strip()
                if lang:
                    out.append(f"{_DIM}  {lang}{_R}")
            continue
        if in_code:
            out.append(f"  {_CY}{line}{_R}")
            continue
        if re.match(r'^# ', line):
            c = line[2:].strip()
            bar = "═" * (len(c) + 4)
            out += [f"\n{_C}{_B}  {bar}{_R}", f"{_C}{_B}  ◆ {c}{_R}", f"{_C}{_B}  {bar}{_R}"]
            continue
        if re.match(r'^## ', line):
            c = line[3:].strip()
            out += [f"\n{_B}{_Y}▸ {c}{_R}", f"{_DIM}{'─' * 40}{_R}"]
            continue
        if re.match(r'^### ', line):
            out.append(f"\n{_B}  › {line[4:].strip()}{_R}")
            continue
        if re.match(r'^---+$', line.strip()):
            out.append(f"{_DIM}{'─' * 60}{_R}")
            continue
        m = re.match(r'^(\s*)([-*])\s+(.+)$', line)
        if m:
            indent = len(m.group(1))
            bullet = "•" if indent == 0 else "◦"
            out.append(f"  {'  ' * (indent // 2)}{_G}{bullet}{_R} {_inline(m.group(3))}")
            continue
        m = re.match(r'^(\s*)(\d+)\.\s+(.+)$', line)
        if m:
            indent = len(m.group(1))
            out.append(f"  {'  ' * (indent // 2)}{_B}{m.group(2)}.{_R} {_inline(m.group(3))}")
            continue
        if line.startswith("> "):
            out.append(f"  {_DIM}│{_R} {_DIM}{_inline(line[2:])}{_R}")
            continue
        out.append(_inline(line))
    return "\n".join(out)


def _inline(text: str) -> str:
    text = re.sub(r'\*\*(.+?)\*\*', lambda m: f"{_B}{m.group(1)}{_R}", text)
    text = re.sub(r'(?<!\*)\*([^*\n]+?)\*(?!\*)', lambda m: f"{_DIM}{m.group(1)}{_R}", text)
    text = re.sub(r'_([^_\n]+?)_', lambda m: f"{_DIM}{m.group(1)}{_R}", text)
    text = re.sub(r'`([^`]+)`', lambda m: f"{_C}{m.group(1)}{_R}", text)
    return text


def _esc(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def render_telegram(text: str) -> str:
    """Convert Markdown to Telegram HTML (parse_mode='HTML')."""
    lines = text.splitlines()
    out: list[str] = []
    in_code = False
    code_buf: list[str] = []
    for line in lines:
        if line.strip().startswith("```"):
            if not in_code:
                in_code = True
                code_buf = []
            else:
                in_code = False
                out.append(f"<pre>{_esc(chr(10).join(code_buf))}</pre>")
            continue
        if in_code:
            code_buf.append(line)
            continue
        m = re.match(r'^#{1,3} (.+)$', line)
        if m:
            out.append(f"\n<b>◆ {_esc(m.group(1))}</b>")
            continue
        if re.match(r'^---+$', line.strip()):
            out.append("")
            continue
        m = re.match(r'^(\s*)([-*])\s+(.+)$', line)
        if m:
            indent = len(m.group(1))
            bullet = "•" if indent == 0 else "◦"
            out.append(f"{'  ' * (indent // 2)}{bullet} {_inline_tg(m.group(3))}")
            continue
        m = re.match(r'^(\s*)(\d+)\.\s+(.+)$', line)
        if m:
            indent = len(m.group(1))
            out.append(f"{'  ' * (indent // 2)}<b>{m.group(2)}.</b> {_inline_tg(m.group(3))}")
            continue
        if line.startswith("> "):
            out.append(f"<i>│ {_inline_tg(line[2:])}</i>")
            continue
        out.append(_inline_tg(line))
    return "\n".join(out)


def _inline_tg(text: str) -> str:
    text = _esc(text)
    text = re.sub(r'\*\*(.+?)\*\*', lambda m: f"<b>{m.group(1)}</b>", text)
    text = re.sub(r'(?<!\*)\*([^*\n]+?)\*(?!\*)', lambda m: f"<i>{m.group(1)}</i>", text)
    text = re.sub(r'_([^_\n]+?)_', lambda m: f"<i>{m.group(1)}</i>", text)
    text = re.sub(r'`([^`\n]+)`', lambda m: f"<code>{m.group(1)}</code>", text)
    return text


def render_discord(text: str) -> str:
    """Convert Markdown for Discord — clean up headings and separators, keep native Discord markdown."""
    lines = text.splitlines()
    out: list[str] = []
    for line in lines:
        # headings → bold with prefix
        m = re.match(r'^# (.+)$', line)
        if m:
            out.append(f"\n**◆ {m.group(1)}**")
            continue
        m = re.match(r'^#{2,3} (.+)$', line)
        if m:
            out.append(f"\n**▸ {m.group(1)}**")
            continue
        # horizontal rules → blank line
        if re.match(r'^---+$', line.strip()):
            out.append("")
            continue
        out.append(line)
    result = "\n".join(out)
    # collapse 3+ consecutive blank lines to 2
    result = re.sub(r'\n{3,}', '\n\n', result)
    return result.strip()


def chunk_discord(text: str, limit: int = 1900) -> list[str]:
    """Split text into chunks that fit Discord's 2000-char message limit."""
    if len(text) <= limit:
        return [text]
    chunks: list[str] = []
    while text:
        if len(text) <= limit:
            chunks.append(text)
            break
        split = text.rfind("\n", 0, limit)
        if split == -1:
            split = limit
        chunks.append(text[:split])
        text = text[split:].lstrip("\n")
    return chunks
