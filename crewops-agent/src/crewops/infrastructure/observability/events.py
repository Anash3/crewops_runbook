"""Write one self-contained JSON object per run event."""

import json
from pathlib import Path
from typing import Any


class JsonlEventSink:
    def __init__(self, path: Path) -> None:
        self.path = str(path)

    def write(self, event: dict[str, Any]) -> None:
        encoded = json.dumps(event, ensure_ascii=False, default=str)
        try:
            path = Path(self.path)
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("a", encoding="utf-8") as event_file:
                event_file.write(encoded + "\n")
        except OSError as exc:
            print(f"RUN EVENT LOG ERROR: {exc}", flush=True)
        print("RUN_EVENT: " + encoded, flush=True)
