import asyncio
from pathlib import Path
from .modules_manager import ModulesManager


class NodeExecutor:
    TIMEOUT = 30

    def __init__(self, workspace_dir: str, script_tracker=None):
        self.workspace = Path(workspace_dir)
        self.modules = ModulesManager(workspace_dir)
        self.tracker = script_tracker  # ScriptTracker | None

    async def run(self, code: str, install_packages: list[str] = None) -> str:
        """
        Write code to temp file, run with Node.js, return stdout+stderr.
        Timeout: 30 seconds. Records execution in ScriptTracker.
        """
        if install_packages:
            self.modules.npm_install(install_packages)

        temp_dir = self.workspace / "workspace" / "temp"
        temp_dir.mkdir(parents=True, exist_ok=True)
        script_path = temp_dir / "temp_script.js"
        script_path.write_text(code)

        success = False
        output = ""
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
            success = proc.returncode == 0
            return output[:5000]
        except asyncio.TimeoutError:
            proc.kill()
            output = "Error: script timed out after 30 seconds"
            return output
        except FileNotFoundError:
            output = "Error: Node.js not found. Please install Node.js."
            return output
        finally:
            if self.tracker:
                self.tracker.record(
                    lang="node",
                    code=code,
                    success=success,
                    output=output,
                )

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
