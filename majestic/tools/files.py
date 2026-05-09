from pathlib import Path


class FilesTool:
    def __init__(self, workspace_dir: str):
        self.workspace = Path(workspace_dir)

    def _resolve(self, path: str) -> Path:
        """Resolve path relative to workspace, ensuring it stays within."""
        resolved = (self.workspace / path).resolve()
        workspace_resolved = self.workspace.resolve()
        if not str(resolved).startswith(str(workspace_resolved)):
            raise ValueError(f"Path '{path}' escapes workspace directory")
        return resolved

    def read(self, path: str) -> str:
        """Read file from workspace. Path is relative to workspace."""
        full_path = self._resolve(path)
        return full_path.read_text(encoding="utf-8", errors="replace")

    def write(self, path: str, content: str) -> str:
        """Write file to workspace. Creates dirs as needed. Returns 'OK'."""
        full_path = self._resolve(path)
        full_path.parent.mkdir(parents=True, exist_ok=True)
        full_path.write_text(content, encoding="utf-8")
        return "OK"

    def list(self, subdir: str = "") -> list[str]:
        """List files in workspace or subdirectory."""
        base = self._resolve(subdir) if subdir else self.workspace.resolve()
        if not base.exists():
            return []
        return [
            str(p.relative_to(self.workspace.resolve()))
            for p in sorted(base.rglob("*"))
            if p.is_file()
        ]

    def delete(self, path: str) -> str:
        """Delete a file from workspace."""
        full_path = self._resolve(path)
        if not full_path.exists():
            return f"Error: file '{path}' not found"
        full_path.unlink()
        return "OK"

    def tool_schemas(self) -> list[dict]:
        """Return JSON schemas for read/write/list/delete."""
        return [
            {
                "name": "file_read",
                "description": "Read a file from the agent workspace. Path is relative to workspace root.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "path": {"type": "string", "description": "Relative path to file within workspace"},
                    },
                    "required": ["path"],
                },
            },
            {
                "name": "file_write",
                "description": "Write content to a file in the agent workspace. Creates parent directories as needed.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "path": {"type": "string", "description": "Relative path to file within workspace"},
                        "content": {"type": "string", "description": "Content to write to the file"},
                    },
                    "required": ["path", "content"],
                },
            },
            {
                "name": "file_list",
                "description": "List all files in the workspace or a subdirectory.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "subdir": {
                            "type": "string",
                            "description": "Optional subdirectory to list (relative to workspace). Defaults to workspace root.",
                            "default": "",
                        },
                    },
                    "required": [],
                },
            },
            {
                "name": "file_delete",
                "description": "Delete a file from the agent workspace.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "path": {"type": "string", "description": "Relative path to file within workspace"},
                    },
                    "required": ["path"],
                },
            },
        ]
