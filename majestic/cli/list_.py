def run():
    """List all available profiles."""
    from pathlib import Path
    profiles_dir = Path("profiles")
    if not profiles_dir.exists():
        print("No profiles found. Run 'majestic setup' first.")
        return
    profiles = [d.name for d in profiles_dir.iterdir() if d.is_dir()]
    if not profiles:
        print("No profiles found. Run 'majestic setup' first.")
        return
    print("\nAvailable profiles:")
    for p in sorted(profiles):
        env = (profiles_dir / p / ".env").exists()
        persona = (profiles_dir / p / "persona.yaml").exists()
        status = "✓" if env and persona else "⚠ incomplete"
        print(f"  {status}  {p}")
    print()
