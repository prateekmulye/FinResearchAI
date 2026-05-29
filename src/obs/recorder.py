# src/obs/recorder.py
from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class RunRecorder:
    """Collects per-node events for a single graph run and flushes them to JSONL."""

    runs_dir: str = "runs"
    run_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    events: list[dict] = field(default_factory=list)

    def record(self, node: str, kind: str, data: dict[str, Any]) -> None:
        self.events.append(
            {"run_id": self.run_id, "node": node, "kind": kind, "data": data}
        )

    def flush(self) -> Path:
        out_dir = Path(self.runs_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        path = out_dir / f"{self.run_id}.jsonl"
        with path.open("w", encoding="utf-8") as f:
            for event in self.events:
                f.write(json.dumps(event, default=str) + "\n")
        return path
