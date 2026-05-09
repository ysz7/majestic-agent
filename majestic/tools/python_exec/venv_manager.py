import subprocess
import sys
from pathlib import Path


class VenvManager:
    def __init__(self, workspace_dir: str):
        self.venv_path = Path(workspace_dir) / ".venv"

    def ensure_venv(self):
        """Create .venv if it doesn't exist."""
        if not self.venv_path.exists():
            subprocess.run(
                [sys.executable, "-m", "venv", str(self.venv_path)],
                check=True,
            )

    def pip_install(self, packages: list[str]):
        """Install packages into .venv."""
        pip = self.venv_path / "bin" / "pip"
        if not pip.exists():
            pip = self.venv_path / "Scripts" / "pip.exe"
        subprocess.run(
            [str(pip), "install"] + packages,
            check=True,
            capture_output=True,
        )

    def get_python(self) -> str:
        """Return path to python executable in .venv."""
        python = self.venv_path / "bin" / "python"
        if not python.exists():
            python = self.venv_path / "Scripts" / "python.exe"
        return str(python)
