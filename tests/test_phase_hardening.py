"""Regression tests for the G/I/J/K subsystems (Phase L.2).

Covers what previously had zero coverage: hooks, permissions, runtime budget
caps + native-vs-text tool path, workflow runner, MCP stdio client, the
products/predict/corpus intelligence services, and the shared tool registry.

No API keys or network — a mock LLM and a fake stdio MCP server are used.
Async tests follow the repo pattern: sync `def test_*` calling `asyncio.run`.
"""

from __future__ import annotations

import asyncio
import sys

from majestic.config.settings import Settings
from majestic.memory.working import WorkingMemory
from majestic.agent.runtime import AgentRuntime


# ── helpers ──────────────────────────────────────────────────────────────────

class FakeSettings:
    """Minimal settings stand-in for hook/permission/budget tests."""
    def __init__(self, *, limits=None, hooks=None, permissions=None):
        self._limits = limits or {}
        self.hooks = hooks or []
        self.permissions = permissions or {}
    @property
    def limits(self):
        return self._limits


class ToolThenFinalLLM:
    """Emits a native tool call on the first turn, a final answer after."""
    context_limit = 128_000
    def __init__(self, native=True, tool="web_search", args=None):
        self.native = native
        self.tool = tool
        self.args = args or {"query": "x"}
        self.calls = []
    def supports_native_tools(self, step_type="reason"):
        return self.native
    async def chat(self, messages, step_type="reason", **kw):
        self.calls.append(kw)
        if len(self.calls) == 1 and self.native:
            return {
                "content": "TOOL_CALL", "input_tokens": 1, "output_tokens": 1, "cost": 0.0,
                "native_tool_call": {"id": "1", "name": self.tool, "input": self.args},
            }
        return {"content": "FINAL_ANSWER: done", "input_tokens": 1, "output_tokens": 1, "cost": 0.0}


# ── L.1 budget caps ──────────────────────────────────────────────────────────

def test_budget_unset_uses_default_cap():
    rt = AgentRuntime(FakeSettings(), WorkingMemory(), llm_router=None)
    rt._tokens_used = AgentRuntime.DEFAULT_MAX_TOKENS_PER_TASK + 1
    from majestic.agent.runtime import BudgetExceeded
    try:
        rt._check_budget()
        assert False, "expected default cap to trigger"
    except BudgetExceeded:
        pass


def test_budget_explicit_zero_is_unlimited():
    rt = AgentRuntime(FakeSettings(limits={"max_tokens_per_task": 0, "max_cost_per_task": 0}),
                      WorkingMemory(), llm_router=None)
    rt._tokens_used = 10_000_000
    rt._cost_used = 999.0
    rt._check_budget()  # must not raise


def test_budget_explicit_tight_cap():
    rt = AgentRuntime(FakeSettings(limits={"max_cost_per_task": 0.10}),
                      WorkingMemory(), llm_router=None)
    rt._cost_used = 0.25
    from majestic.agent.runtime import BudgetExceeded
    try:
        rt._check_budget()
        assert False
    except BudgetExceeded:
        pass


# ── K.5 permissions ──────────────────────────────────────────────────────────

def test_permission_precedence_and_globs():
    from majestic.agent.permissions import PermissionPolicy as P
    pol = P(mode="default", allow=["web_search"], ask=["python_exec", "http_*"], deny=["delegate_to_agent"])
    assert pol.decide("delegate_to_agent") == "deny"
    assert pol.decide("python_exec") == "ask"
    assert pol.decide("http_get") == "ask"
    assert pol.decide("web_search") == "allow"
    assert pol.decide("anything_else") == "allow"


def test_permission_modes():
    from majestic.agent.permissions import PermissionPolicy as P
    assert P(mode="bypass", deny=["x"]).decide("x") == "allow"
    assert P(mode="plan").decide("web_search") == "deny"
    assert P(mode="auto", ask=["python_exec"]).decide("python_exec") == "allow"
    assert P(mode="auto", deny=["x"]).decide("x") == "deny"
    class S:  # bad mode falls back to default
        permissions = {"mode": "weird", "deny": ["a"]}
    assert P.from_settings(S()).mode == "default"


# ── K.4 hooks ────────────────────────────────────────────────────────────────

def test_hook_deny_modify_and_isolation():
    from majestic.agent import hooks as H

    async def main():
        bus = H.HookBus()
        bus.on(H.PRE_TOOL_USE, lambda ev, ctx: H.HookDecision("deny", reason="no")
               if ctx["tool"] == "python_exec" else None)
        d = await bus.fire(H.PRE_TOOL_USE, {"tool": "python_exec", "args": {}})
        assert d.denied and d.reason == "no"
        assert not (await bus.fire(H.PRE_TOOL_USE, {"tool": "web_search", "args": {}})).denied

        bus2 = H.HookBus()
        bus2.on(H.PRE_TOOL_USE, lambda ev, ctx: H.HookDecision("modify", args={"q": "clean"}))
        d2 = await bus2.fire(H.PRE_TOOL_USE, {"tool": "x", "args": {"q": "dirty"}})
        assert d2.action == "modify" and d2.args["q"] == "clean"

        bus3 = H.HookBus()
        def boom(ev, ctx): raise RuntimeError("boom")
        bus3.on(H.PRE_TOOL_USE, boom)
        assert (await bus3.fire(H.PRE_TOOL_USE, {"tool": "x", "args": {}})).action == "allow"

    asyncio.run(main())


def test_runtime_pre_tool_hook_blocks_execution():
    from majestic.agent import hooks as H

    async def main():
        ran = {"n": 0}
        async def web_search(query, max_results=5):
            ran["n"] += 1
            return "res"
        bus = H.HookBus()
        bus.on(H.PRE_TOOL_USE, lambda ev, ctx: H.HookDecision("deny", reason="blocked"))
        rt = AgentRuntime(Settings("default"), WorkingMemory(),
                          llm_router=ToolThenFinalLLM(), hook_bus=bus)
        rt.tools = {"web_search": web_search}
        await rt.run("go", task_id="deny")
        assert ran["n"] == 0  # tool blocked by hook

    asyncio.run(main())


# ── K.2 native vs text tool path ─────────────────────────────────────────────

def test_native_tool_path_passes_schemas_and_executes():
    async def main():
        seen = {"n": 0}
        async def web_search(query, max_results=5):
            seen["n"] += 1
            return "res"
        llm = ToolThenFinalLLM(native=True)
        rt = AgentRuntime(Settings("default"), WorkingMemory(), llm_router=llm)
        rt.tools = {"web_search": web_search}
        out = await rt.run("go", task_id="nat")
        assert "done" in out and seen["n"] == 1
        assert llm.calls[0].get("tools"), "tools must be passed on capable model"

    asyncio.run(main())


def test_text_path_does_not_pass_tools():
    async def main():
        async def web_search(query, max_results=5):
            return "res"
        llm = ToolThenFinalLLM(native=False)
        rt = AgentRuntime(Settings("default"), WorkingMemory(), llm_router=llm)
        rt.tools = {"web_search": web_search}
        await rt.run("hi", task_id="txt")
        assert not llm.calls[0].get("tools")

    asyncio.run(main())


# ── K.1 tool registry ────────────────────────────────────────────────────────

def test_register_tools_wires_full_toolset():
    from majestic.tools.registry import register_tools
    rt = AgentRuntime(Settings("default"), WorkingMemory(), llm_router=None)
    register_tools(rt, Settings("default"), semantic=None)
    for t in ("web_search", "python_exec", "node_exec", "research", "file_read",
              "http_get", "delegate_to_agent"):
        assert t in rt.tools


# ── orchestration: workflow runner ───────────────────────────────────────────

def test_workflow_topology_and_substitution():
    from majestic.orchestration.workflow_runner import (
        _topological_order, _build_action_task, _substitute,
    )
    nodes = [
        {"id": "o1", "type": "outputNode", "data": {"subtype": "notify"}},
        {"id": "t1", "type": "triggerNode", "data": {"subtype": "manual"}},
        {"id": "a1", "type": "actionNode", "data": {"subtype": "research", "query": "AI {date}"}},
    ]
    edges = [{"source": "t1", "target": "a1"}, {"source": "a1", "target": "o1"}]
    assert [n["id"] for n in _topological_order(nodes, edges)] == ["t1", "a1", "o1"]
    task = _build_action_task(nodes[2], "PREV", "default")
    assert "AI" in task and "{date}" not in task
    assert _substitute("{prev_output}", "X", "a") == "X"


# ── MCP stdio client ─────────────────────────────────────────────────────────

_FAKE_MCP = '''
import sys, json
def send(o): sys.stdout.write(json.dumps(o)+"\\n"); sys.stdout.flush()
for line in sys.stdin:
    line=line.strip()
    if not line: continue
    m=json.loads(line); i=m.get("id"); meth=m.get("method")
    if meth=="initialize": send({"jsonrpc":"2.0","id":i,"result":{"protocolVersion":"2024-11-05","capabilities":{}}})
    elif meth=="tools/list": send({"jsonrpc":"2.0","id":i,"result":{"tools":[{"name":"echo","description":"e","inputSchema":{"type":"object","properties":{"text":{"type":"string"}}}}]}})
    elif meth=="tools/call": send({"jsonrpc":"2.0","id":i,"result":{"content":[{"type":"text","text":"echo: "+m["params"]["arguments"].get("text","")}]}})
    elif meth and meth.startswith("notifications/"): pass
    else: send({"jsonrpc":"2.0","id":i,"result":{}})
'''


def test_mcp_stdio_handshake_list_call(tmp_path):
    from majestic.mcp.client import MCPServer
    script = tmp_path / "fake_mcp.py"
    script.write_text(_FAKE_MCP, encoding="utf-8")

    async def main():
        s = MCPServer("fake", [sys.executable, str(script)])
        await s.connect()
        assert [t["name"] for t in s.tools] == ["echo"]
        out = await s.call_tool("echo", {"text": "hi"})
        assert out == "echo: hi"
        await s.close()

    asyncio.run(main())


def test_mcp_derive_command():
    from majestic.mcp.client import _derive_command
    assert _derive_command({"runtime": "node", "package": "pkg"})[:2] == ["npx", "-y"]
    assert _derive_command({"runtime": "python", "package": "mcp-server-git"})[0] == "mcp-server-git"
    assert _derive_command({"command": ["x"], "args": ["--y"]}) == ["x", "--y"]


# ── intelligence services ────────────────────────────────────────────────────

def test_products_json_salvage_and_score():
    from majestic.intelligence.products import _extract_json_array, _score
    trunc = '[{"name":"A","one_liner":"x"}, {"name":"B"}, {"name":"C","one_lin'
    assert [o["name"] for o in _extract_json_array(trunc)] == ["A", "B"]
    fenced = 'pre ```json\n[{"name":"Z"}]\n``` post'
    assert [o["name"] for o in _extract_json_array(fenced)] == ["Z"]
    s = _score({"score_breakdown": {"demand": 90, "trend": 80, "competition_gap": 70,
                                    "solo_feasibility": 60, "margin_speed": 50}})
    assert s == 74


def test_predict_cooccurrence_and_trend():
    from majestic.intelligence.predict import _anchor_hits, _apply_trend
    anchors = ["Crypto (BTC/ETH)", "AI / Tech", "Macro + geopolitics", "Stock markets"]
    arts = [{"title": "Bitcoin ETF", "summary": "btc and nasdaq rally"}]
    counts, pairs = _anchor_hits(arts, anchors)
    assert counts["Crypto (BTC/ETH)"] >= 1 and counts["Stock markets"] >= 1
    items = [{"niche": "Crypto (BTC/ETH)", "anchor": True, "direction": "up", "probability": 71}]
    _apply_trend(items, {"Crypto (BTC/ETH)": {"direction": "up", "probability": 64}})
    assert "64% up -> 71% up" in items[0]["trend"]


def test_corpus_dedup_single_renderer():
    from majestic.tools.research.corpus import build_corpus
    from majestic.intelligence.corpus import build_news_corpus
    arts = [{"title": "Alpha", "date": "2026-06-01", "category": "tech", "source": "X"},
            {"title": "Alpha", "date": "2026-06-02", "category": "tech", "source": "Y"},
            {"title": "Beta", "date": "2026-06-03", "category": "macro", "source": "Z"}]
    lines, _ = build_news_corpus(arts, max_chars=50_000)
    text = "\n".join(lines)
    assert text.count("Alpha") == 1 and "TECH" in text and "MACRO" in text
    # delegate produces identical output to build_corpus at equivalent budget
    l2, _ = build_corpus(arts, token_budget=12_500)
    assert lines == l2


def test_generate_ideas_and_briefing_services():
    from majestic.intelligence import generate_ideas, generate_briefing

    class FakeLLM:
        context_limit = 128_000
        async def chat(self, messages, step_type="reason", **kw):
            return {"content": "## SECTION 1\n**#1 -- Alpha**", "input_tokens": 5,
                    "output_tokens": 7, "cost": 0.0}

    async def main():
        pains = [{"pain_text": "p", "intensity": "HIGH", "willingness_to_pay": True,
                  "domain": "fin", "source": "r"}]
        arts = [{"title": "N", "date": "2026-06-01", "category": "tech", "summary": "s"}]
        oi = await generate_ideas(llm=FakeLLM(), pains=pains, articles=arts,
                                  briefing="ctx", past_ideas=[], days=30, lang="en")
        assert oi["markdown"].startswith("## SECTION 1") and oi["tokens"] == 12
        ob = await generate_briefing(llm=FakeLLM(), articles=arts, prices_block="P",
                                     days=30, lang="en")
        assert ob["markdown"].startswith("## SECTION 1") and "capped" in ob

    asyncio.run(main())
