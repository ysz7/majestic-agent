"""Tests for Discord gateway — formatter, chunking, platform config check."""
import pytest


# ── render_discord ────────────────────────────────────────────────────────────

def test_render_discord_h1():
    from majestic.gateway.formatter import render_discord
    result = render_discord("# Title")
    assert "**◆ Title**" in result
    assert "#" not in result.replace("**◆ Title**", "")


def test_render_discord_h2():
    from majestic.gateway.formatter import render_discord
    result = render_discord("## Section")
    assert "**▸ Section**" in result


def test_render_discord_h3():
    from majestic.gateway.formatter import render_discord
    result = render_discord("### Sub")
    assert "**▸ Sub**" in result


def test_render_discord_hr_removed():
    from majestic.gateway.formatter import render_discord
    result = render_discord("before\n---\nafter")
    assert "---" not in result
    assert "before" in result
    assert "after" in result


def test_render_discord_preserves_bold():
    from majestic.gateway.formatter import render_discord
    result = render_discord("**bold text**")
    assert "**bold text**" in result


def test_render_discord_preserves_code_block():
    from majestic.gateway.formatter import render_discord
    result = render_discord("```python\nprint('hello')\n```")
    assert "```" in result
    assert "print" in result


def test_render_discord_collapses_blank_lines():
    from majestic.gateway.formatter import render_discord
    result = render_discord("a\n\n\n\n\nb")
    assert "\n\n\n" not in result


def test_render_discord_plain_text_unchanged():
    from majestic.gateway.formatter import render_discord
    result = render_discord("just plain text here")
    assert result == "just plain text here"


# ── chunk_discord ─────────────────────────────────────────────────────────────

def test_chunk_discord_short():
    from majestic.gateway.formatter import chunk_discord
    chunks = chunk_discord("short message", limit=1900)
    assert chunks == ["short message"]


def test_chunk_discord_splits_on_newline():
    from majestic.gateway.formatter import chunk_discord
    text = "line1\nline2\nline3"
    chunks = chunk_discord(text, limit=10)
    assert len(chunks) > 1
    for chunk in chunks:
        assert len(chunk) <= 10


def test_chunk_discord_exact_limit():
    from majestic.gateway.formatter import chunk_discord
    text = "a" * 1900
    chunks = chunk_discord(text, limit=1900)
    assert chunks == [text]


def test_chunk_discord_long_no_newlines():
    from majestic.gateway.formatter import chunk_discord
    text = "x" * 3000
    chunks = chunk_discord(text, limit=1900)
    assert len(chunks) == 2
    for chunk in chunks:
        assert len(chunk) <= 1900


def test_chunk_discord_reassembles():
    from majestic.gateway.formatter import chunk_discord
    text = "\n".join(f"Line {i}: some content here" for i in range(100))
    chunks = chunk_discord(text, limit=500)
    reassembled = "\n".join(chunks)
    for i in range(100):
        assert f"Line {i}:" in reassembled


# ── DiscordPlatform ───────────────────────────────────────────────────────────

def test_discord_platform_name():
    from majestic.gateway.discord import DiscordPlatform
    p = DiscordPlatform()
    assert p.name == "discord"


def test_discord_platform_not_configured_without_token(monkeypatch):
    monkeypatch.delenv("DISCORD_BOT_TOKEN", raising=False)
    from majestic.gateway.discord import DiscordPlatform
    p = DiscordPlatform()
    assert not p.is_configured()


def test_discord_platform_configured_with_token(monkeypatch):
    monkeypatch.setenv("DISCORD_BOT_TOKEN", "test-token-123")
    from majestic.gateway.discord import DiscordPlatform
    p = DiscordPlatform()
    assert p.is_configured()


def test_discord_platform_implements_interface():
    import inspect
    from majestic.gateway.base import Platform
    from majestic.gateway.discord import DiscordPlatform
    assert issubclass(DiscordPlatform, Platform)
    assert inspect.iscoroutinefunction(DiscordPlatform.start)
    assert inspect.iscoroutinefunction(DiscordPlatform.stop)
