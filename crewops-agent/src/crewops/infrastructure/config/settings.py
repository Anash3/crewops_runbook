"""Load defaults, environment configuration, then environment overrides."""

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parents[4]


@dataclass(frozen=True)
class Settings:
    project_root: Path
    backend_host: str
    backend_port: int
    backend_api_key: str | None
    mcp_host: str
    mcp_port: int
    crewops_mcp_url: str
    mcp_api_key: str | None
    approval_api_key: str | None
    event_log_path: Path
    runbook_path: Path


def _config(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    loaded = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(loaded, dict):
        raise ValueError(f"Configuration {path} must be a YAML object")
    return loaded


def _merge(base: dict[str, Any], overlay: dict[str, Any]) -> dict[str, Any]:
    merged = dict(base)
    for key, value in overlay.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def load_settings(project_root: Path = PROJECT_ROOT) -> Settings:
    load_dotenv(project_root / ".env")
    environment = os.getenv("CREWOPS_ENV", "development")
    defaults = _config(project_root / "configs" / "base.yaml")
    configured = _merge(defaults, _config(project_root / "configs" / f"{environment}.yaml"))
    mcp = configured.get("mcp", {})
    backend = configured.get("backend", {})
    host = os.getenv("MCP_HOST", mcp.get("host", "127.0.0.1"))
    port = int(os.getenv("MCP_PORT", mcp.get("port", 8000)))
    return Settings(
        project_root=project_root,
        backend_host=os.getenv("BACKEND_HOST", backend.get("host", "127.0.0.1")),
        backend_port=int(os.getenv("BACKEND_PORT", backend.get("port", 8001))),
        backend_api_key=os.getenv("BACKEND_API_KEY") or None,
        mcp_host=host,
        mcp_port=port,
        crewops_mcp_url=os.getenv("CREWOPS_MCP_URL", f"http://{host}:{port}/mcp"),
        mcp_api_key=os.getenv("MCP_API_KEY") or None,
        approval_api_key=os.getenv("RUNBOOK_APPROVAL_API_KEY") or None,
        event_log_path=Path(
            os.getenv("RUNBOOK_EVENT_LOG_PATH", str(project_root / "runbook_events.jsonl"))
        ),
        runbook_path=project_root / "runbooks" / "crew_duty_risk_resolution.yaml",
    )
