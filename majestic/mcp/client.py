import yaml, subprocess, asyncio
from pathlib import Path

class MCPClient:
    def __init__(self, registry_path: str = "majestic/mcp/registry.yaml"):
        self.registry_path = Path(registry_path)
        self._servers: dict = {}
        self._tools: dict = {}

    def load_registry(self) -> dict:
        with open(self.registry_path) as f:
            return yaml.safe_load(f)

    def install_server(self, name: str, server_config: dict):
        """Install MCP server package if not already installed."""
        runtime = server_config.get("runtime", "python")
        package = server_config.get("package")
        if runtime == "python":
            subprocess.run(["pip", "install", package], capture_output=True)
        elif runtime == "node":
            subprocess.run(["npm", "install", "-g", package], capture_output=True)

    def get_available_servers(self) -> list[dict]:
        """Return list of configured MCP servers."""
        try:
            registry = self.load_registry()
            return [{"name": k, **v} for k, v in registry.get("servers", {}).items()]
        except Exception:
            return []

    async def call_tool(self, server: str, tool: str, args: dict) -> str:
        """Call a tool on an MCP server (stub — real MCP protocol would use stdio/HTTP)."""
        return f"MCP tool call: {server}/{tool} with {args}"
