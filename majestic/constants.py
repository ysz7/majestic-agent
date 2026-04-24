import os
from pathlib import Path

MAJESTIC_HOME = Path(os.environ.get("MAJESTIC_HOME", "~/.majestic-agent")).expanduser()

CONFIG_FILE   = MAJESTIC_HOME / "config.yaml"
ENV_FILE      = MAJESTIC_HOME / ".env"
STATE_DB      = MAJESTIC_HOME / "state.db"
MEMORY_DIR    = MAJESTIC_HOME / "memory"
SKILLS_DIR    = MAJESTIC_HOME / "skills"
EXPORTS_DIR   = MAJESTIC_HOME / "exports"
WORKSPACE_DIR = MAJESTIC_HOME / "workspace"
