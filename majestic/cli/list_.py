def run():
    """List all available profiles."""
    from pathlib import Path
    from majestic import display

    profiles_dir = Path("profiles")
    if not profiles_dir.exists():
        display.warn("No profiles found. Run 'majestic setup' first.")
        return

    profiles = sorted(d.name for d in profiles_dir.iterdir() if d.is_dir())
    if not profiles:
        display.warn("No profiles found. Run 'majestic setup' first.")
        return

    display.print_profiles_list(profiles)
