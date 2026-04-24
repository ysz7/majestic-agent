"""
Markdown rendering utilities.
- render_cli()       : markdown → ANSI for terminal output
- render_telegram()  : markdown → Telegram HTML
"""
import re


# ── CLI / ANSI ────────────────────────────────────────────────────────────────

_R    = "\033[0m"
_B    = "\033[1m"
_DIM  = "\033[2m"
_C    = "\033[38;2;217;87;103m"   # accent #d95767
_G    = "\033[32m"                 # green
_Y    = "\033[33m"                 # yellow
_CY   = "\033[36m"                 # cyan
_BG   = "\033[48;2;30;30;30m"     # dark bg for code


def render_cli(text: str) -> str:
    """Convert markdown to ANSI-colored terminal output."""
    lines = text.splitlines()
    out = []
    in_code_block = False

    for line in lines:
        # ── Code block fence ──────────────────────────────────────────────────
        if line.strip().startswith("```"):
            in_code_block = not in_code_block
            if in_code_block:
                lang = line.strip()[3:].strip()
                out.append(f"{_DIM}{'─' * 50}{_R}")
                if lang:
                    out.append(f"{_DIM}  {lang}{_R}")
            else:
                out.append(f"{_DIM}{'─' * 50}{_R}")
            continue

        if in_code_block:
            out.append(f"  {_CY}{line}{_R}")
            continue

        # ── Headers ───────────────────────────────────────────────────────────
        if re.match(r'^# ', line):
            content = line[2:].strip()
            bar = "═" * (len(content) + 4)
            out.append(f"\n{_C}{_B}  {bar}{_R}")
            out.append(f"{_C}{_B}  ◆ {content}{_R}")
            out.append(f"{_C}{_B}  {bar}{_R}")
            continue

        if re.match(r'^## ', line):
            content = line[3:].strip()
            out.append(f"\n{_B}{_Y}▸ {content}{_R}")
            out.append(f"{_DIM}{'─' * 40}{_R}")
            continue

        if re.match(r'^### ', line):
            content = line[4:].strip()
            out.append(f"\n{_B}  › {content}{_R}")
            continue

        # ── Horizontal rule ───────────────────────────────────────────────────
        if re.match(r'^---+$', line.strip()):
            out.append(f"{_DIM}{'─' * 60}{_R}")
            continue

        # ── Bullet points ─────────────────────────────────────────────────────
        m = re.match(r'^(\s*)([-*])\s+(.+)$', line)
        if m:
            indent = len(m.group(1))
            bullet = "•" if indent == 0 else "◦"
            content = m.group(3)
            content = _apply_inline(content)
            out.append(f"  {'  ' * (indent // 2)}{_G}{bullet}{_R} {content}")
            continue

        # ── Numbered list ─────────────────────────────────────────────────────
        m = re.match(r'^(\s*)(\d+)\.\s+(.+)$', line)
        if m:
            indent = len(m.group(1))
            num = m.group(2)
            content = m.group(3)
            content = _apply_inline(content)
            out.append(f"  {'  ' * (indent // 2)}{_B}{num}.{_R} {content}")
            continue

        # ── Blockquote ────────────────────────────────────────────────────────
        if line.startswith("> "):
            content = _apply_inline(line[2:])
            out.append(f"  {_DIM}│{_R} {_DIM}{content}{_R}")
            continue

        # ── Regular line ──────────────────────────────────────────────────────
        out.append(_apply_inline(line))

    return "\n".join(out)


def _apply_inline(text: str) -> str:
    """Apply inline markdown formatting (bold, italic, code)."""
    # Bold **text**
    text = re.sub(r'\*\*(.+?)\*\*', lambda m: f"{_B}{m.group(1)}{_R}", text)
    # Italic *text* or _text_
    text = re.sub(r'(?<!\*)\*([^*\n]+?)\*(?!\*)', lambda m: f"{_DIM}{m.group(1)}{_R}", text)
    text = re.sub(r'_([^_\n]+?)_', lambda m: f"{_DIM}{m.group(1)}{_R}", text)
    # Inline code `text`
    text = re.sub(r'`([^`]+)`', lambda m: f"{_C}{m.group(1)}{_R}", text)
    return text


# ── Telegram HTML ─────────────────────────────────────────────────────────────

def _esc(text: str) -> str:
    """Escape HTML special characters."""
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def render_telegram(text: str) -> str:
    """Convert markdown to Telegram HTML (parse_mode='HTML')."""
    lines = text.splitlines()
    out = []
    in_code_block = False
    code_buf = []

    for line in lines:
        # ── Code block fence ──────────────────────────────────────────────────
        if line.strip().startswith("```"):
            if not in_code_block:
                in_code_block = True
                code_buf = []
            else:
                in_code_block = False
                code_content = _esc("\n".join(code_buf))
                out.append(f"<pre>{code_content}</pre>")
            continue

        if in_code_block:
            code_buf.append(line)
            continue

        # ── Headers ───────────────────────────────────────────────────────────
        m = re.match(r'^#{1,3} (.+)$', line)
        if m:
            content = _esc(m.group(1))
            out.append(f"\n<b>◆ {content}</b>")
            continue

        # ── Horizontal rule ───────────────────────────────────────────────────
        if re.match(r'^---+$', line.strip()):
            out.append("")
            continue

        # ── Bullet points ─────────────────────────────────────────────────────
        m = re.match(r'^(\s*)([-*])\s+(.+)$', line)
        if m:
            indent = len(m.group(1))
            bullet = "•" if indent == 0 else "◦"
            content = _apply_inline_tg(m.group(3))
            out.append(f"{'  ' * (indent // 2)}{bullet} {content}")
            continue

        # ── Numbered list ─────────────────────────────────────────────────────
        m = re.match(r'^(\s*)(\d+)\.\s+(.+)$', line)
        if m:
            indent = len(m.group(1))
            num = m.group(2)
            content = _apply_inline_tg(m.group(3))
            out.append(f"{'  ' * (indent // 2)}<b>{num}.</b> {content}")
            continue

        # ── Blockquote ────────────────────────────────────────────────────────
        if line.startswith("> "):
            content = _apply_inline_tg(line[2:])
            out.append(f"<i>│ {content}</i>")
            continue

        # ── Regular line ──────────────────────────────────────────────────────
        out.append(_apply_inline_tg(line))

    return "\n".join(out)


def _apply_inline_tg(text: str) -> str:
    """Apply inline markdown to Telegram HTML."""
    text = _esc(text)
    # Bold **text**
    text = re.sub(r'\*\*(.+?)\*\*', lambda m: f"<b>{m.group(1)}</b>", text)
    # Italic *text* or _text_
    text = re.sub(r'(?<!\*)\*([^*\n]+?)\*(?!\*)', lambda m: f"<i>{m.group(1)}</i>", text)
    text = re.sub(r'_([^_\n]+?)_', lambda m: f"<i>{m.group(1)}</i>", text)
    # Inline code `text`
    text = re.sub(r'`([^`\n]+)`', lambda m: f"<code>{m.group(1)}</code>", text)
    return text
