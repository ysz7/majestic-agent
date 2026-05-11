def run(name: str):
    """Delete a profile after confirmation."""
    import shutil
    from pathlib import Path
    from majestic import display

    profile_dir = Path(f"profiles/{name}")
    if not profile_dir.exists():
        display.err(f"Profile '{name}' not found.")
        return

    confirmed = display.confirm_delete(name)
    if not confirmed:
        display.info("Cancelled.")
        return

    shutil.rmtree(profile_dir)
    display.ok(f"Profile '{name}' deleted.")
