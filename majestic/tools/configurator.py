"""Interactive tool configurator — `majestic tools`."""
from __future__ import annotations


def run_configurator() -> None:
    """Launch interactive tool checklist in the terminal."""
    import majestic.tools  # noqa: F401
    from majestic.tools.registry import _registry
    from majestic import config as cfg
    from majestic.cli.display import R, B, C, G, Y, DIM

    all_tools = sorted(_registry.keys())
    if not all_tools:
        print("  No tools registered.")
        return

    disabled = set(cfg.get("agent.tools_disabled", []) or [])
    active = {t for t in all_tools if t not in disabled}

    def _print_list() -> None:
        print(f"\n  {B}Tool Configuration{R}  {DIM}(toggle by number, Enter to save, q to quit){R}\n")
        for i, name in enumerate(all_tools, 1):
            mark = f"{G}✓{R}" if name in active else f"{DIM}✗{R}"
            desc = (_registry[name].description or "")[:55]
            print(f"  {mark} {DIM}{i:>2}.{R} {name:<28} {DIM}{desc}{R}")
        print(f"\n  {DIM}Active: {len(active)}/{len(all_tools)} tools{R}\n")

    _print_list()

    while True:
        try:
            raw = input(f"  {C}tools ▶ {R}").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break

        if not raw or raw.lower() == "q":
            break

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

    try:
        import majestic.tools  # noqa: F401
        from majestic.tools.registry import _registry as reg
        all_names = set(reg.keys())
        disabled_list = sorted(all_names - active)
        cfg.set_value("agent.tools_disabled", disabled_list)
        cfg.set_value("agent.tools_enabled", [])
        print(f"\n  {G}✓ Saved. {len(active)} tools active, {len(disabled_list)} disabled.{R}\n")
    except Exception as e:
        print(f"  {Y}Could not save: {e}{R}\n")
