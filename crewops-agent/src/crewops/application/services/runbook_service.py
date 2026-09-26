"""Load and validate a human-authored runbook."""

from pathlib import Path

import yaml
from pydantic import ValidationError

from crewops.core.domain.runbook import Runbook


class RunbookService:
    def load(self, path: Path) -> Runbook:
        try:
            raw = yaml.safe_load(path.read_text(encoding="utf-8"))
            return Runbook.model_validate(raw)
        except (OSError, yaml.YAMLError, ValidationError, TypeError) as exc:
            raise ValueError(f"Could not load valid runbook {path.name}: {exc}") from exc
