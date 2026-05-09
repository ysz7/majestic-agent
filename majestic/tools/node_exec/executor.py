import asyncio
from pathlib import Path
from .modules_manager import ModulesManager


class NodeExecutor:
    TIMEOUT = 30

    def __init__(self, workspace_dir: str):
        self.workspace = Path(workspace_dir)
        self.modules = ModulesManager(workspace_dir)

    async def run(self, code: str, install_packages: list[str] = None) -> str:
        """
        Write code to temp file, run with Node.js, return stdout+stderr.
        Timeout: 30 seconds.
        """
        if install_packages:
            self.modules.npm_install(install_packages)

        script_path = self.workspace / "workspace" / "tools" / "temp_script.js"
        script_path.parent.mkdir(parents=True, exist_ok=True)
        script_path.write_text(code)

        try:
            proc = await asyncio.create_subprocess_exec(
                "node",
                str(script_path),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=str(self.workspace),
            )
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(), timeout=self.TIMEOUT
            )
            output = stdout.decode() + (
                ("\nSTDERR:\n" + stderr.decode()) if stderr else ""
            )
            return output[:5000]
        except asyncio.TimeoutError:
            proc.kill()
            return "Error: script timed out after 30 seconds"
        except FileNotFoundError:
            return "Error: Node.js not found. Please install Node.js."

    def tool_schema(self) -> dict:
        return {
            "name": "node_exec",
            "description": "Write and execute a Node.js script. Returns stdout output.",
            "parameters": {
                "type": "object",
                "properties": {
                    "code": {
                        "type": "string",
                        "description": "JavaScript code to execute",
                    },
                    "install_packages": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "npm packages to install before running",
                    },
                },
                "required": ["code"],
            },
        }
