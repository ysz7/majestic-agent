def run(name: str):
    """Delete a profile after confirmation."""
    import shutil
    from pathlib import Path

    profile_dir = Path(f"profiles/{name}")
    if not profile_dir.exists():
        print(f"Profile '{name}' not found.")
        return

    confirm = input(f"Delete profile '{name}'? This cannot be undone. (yes/no): ").strip().lower()
    if confirm != "yes":
        print("Cancelled.")
        return

    shutil.rmtree(profile_dir)
    print(f"✓ Profile '{name}' deleted.")
