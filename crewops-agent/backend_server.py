"""Start the runbook backend HTTP API."""

import uvicorn

from crewops.api.server import app, container


if __name__ == "__main__":
    uvicorn.run(app, host=container.settings.backend_host, port=container.settings.backend_port)
