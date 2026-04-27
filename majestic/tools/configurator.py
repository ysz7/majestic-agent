"""
Interactive tool configurator — `majestic tools`.

Shows a numbered checklist of all tools. User toggles by number,
applies a toolset by name, then saves to agent.tools_disabled.
"""
from __future__ import annotations


def run_configurator() -> None:
    """Launch interactive tool checklist in the terminal."""
    # Need tools to be registered first
    import majestic.tools  # noqa: F401
    from majestic.tools.registry import _registry
    from majestic.tools.toolsets import list_toolsets, get_active_tools, apply_toolset
    from majestic import config as cfg
    from majestic.cli.display import R, B, C, G, Y, DIM

    all_tools = sorted(_registry.keys())
    if not all_tools:
        print("  No tools registered.")
        return

    active = set(get_active_tools())
    toolsets = list_toolsets()

    def _print_list() -> None:
        print(f"\n  {B}Tool Configuration{R}  {DIM}(toggle by number, 'ts <name>' for toolset, Enter to save, q to quit){R}\n")
        for i, name in enumerate(all_tools, 1):
            mark = f"{G}✓{R}" if name in active else f"{DIM}✗{R}"
            desc = (_registry[name].description or "")[:55]
            print(f"  {mark} {DIM}{i:>2}.{R} {name:<28} {DIM}{desc}{R}")
        print(f"\n  {DIM}Toolsets: {', '.join(toolsets.keys())}{R}")
        print(f"  {DIM}Active: {len(active)}/{len(all_tools)} tools{R}\n")

    _print_list()

    while True:
        try:
            raw = input(f"  {C}tools ▶ {R}").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break

        if not raw or raw.lower() == "q":
            break

        if raw.lower().startswith("ts "):
            ts_name = raw[3:].strip()
            if apply_toolset(ts_name):
                active = set(get_active_tools())
                print(f"  {G}✓ Toolset '{ts_name}' applied.{R}")
                _print_list()
            else:
                print(f"  {Y}Unknown toolset: {ts_name}. Available: {', '.join(toolsets.keys())}{R}")
            continue

        # Parse space-separated numbers to toggle
        changed = False
        for token in raw.split():
            try:
                idx = int(token) - 1
                if 0 <= idx < len(all_tools):
                    name = all_tools[idx]
                    if name in active:
                        active.discard(name)
                    else:
                        active.add(name)
                    changed = True
            except ValueError:
                pass

        if changed:
            _print_list()

    # Save — compute disabled list
    try:
        import majestic.tools  # noqa: F401
        from majestic.tools.registry import _registry as reg
        all_names = set(reg.keys())
        disabled  = sorted(all_names - active)
        cfg.set_value("agent.tools_disabled", disabled)
        cfg.set_value("agent.tools_enabled", [])
        print(f"\n  {G}✓ Saved. {len(active)} tools active, {len(disabled)} disabled.{R}\n")
    except Exception as e:
        print(f"  {Y}Could not save: {e}{R}\n")


def print_toolsets() -> None:
    """Print all available toolsets and their tools."""
    from majestic.tools.toolsets import list_toolsets, current_toolset
    from majestic.cli.display import R, B, C, G, DIM

    toolsets = list_toolsets()
    active_ts = current_toolset()

    print()
    for name, tools in toolsets.items():
        marker = f" {G}← active{R}" if name == active_ts else ""
        label  = tools if tools else ["(all tools)"]
        print(f"  {C}{name}{R}{marker}")
        print(f"  {DIM}{', '.join(label)}{R}")
        print()
