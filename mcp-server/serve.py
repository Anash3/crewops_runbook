"""Start the standalone CrewOps FastMCP server."""

import uvicorn

from crewops_mcp.server import app, load_settings


if __name__ == "__main__":
    settings = load_settings()
    uvicorn.run(app, host=settings.mcp_host, port=settings.mcp_port)
