import subprocess
from pathlib import Path


class ModulesManager:
    def __init__(self, workspace_dir: str):
        self.modules_path = Path(workspace_dir) / "node_modules"
        self.workspace = Path(workspace_dir)

    def ensure_init(self):
        """Ensure package.json exists so npm install works."""
        package_json = self.workspace / "package.json"
        if not package_json.exists():
            package_json.write_text(
                '{"name":"workspace","version":"1.0.0","private":true}'
            )

    def npm_install(self, packages: list[str]):
        """Install npm packages into the workspace."""
        self.ensure_init()
        subprocess.run(
            ["npm", "install"] + packages,
            cwd=str(self.workspace),
            check=True,
            capture_output=True,
        )
