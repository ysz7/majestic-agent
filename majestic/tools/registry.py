"""Shared tool registration — builds the agent's built-in toolset and binds it
to a runtime.

Used by BOTH entrypoints so the foreground (CLI) and background (HTTP/desktop)
agents expose the identical toolset:

  - cli/foreground.py     (interactive)
  - __background__.py      (server / desktop chat / workflows)

Previously this lived only in foreground.py, so the background agent ran with
no tools at all (Phase K.1).
"""

from __future__ import annotations


def register_tools(runtime, settings, semantic=None):
    """Build the built-in toolset and assign it to ``runtime.tools``.

    Parameters
    ----------
    runtime:
        AgentRuntime to attach tools to. ``runtime._reflection`` is used when
        present to share the ScriptTracker; absent in minimal setups (safe).
    settings:
        Profile Settings (paths, API keys).
    semantic:
        Optional SemanticMemory — web_search results are indexed for RAG when
        provided.
    """
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

    # Reuse the tracker wired into the reflection engine so counts persist.
    script_tracker = None
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
        # Index results into semantic memory for future RAG retrieval.
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
