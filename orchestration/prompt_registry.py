"""orchestration/prompt_registry.py — versioned prompt management."""
from __future__ import annotations

import json
import logging
from pathlib import Path

from contracts.schemas import PromptTemplate

logger = logging.getLogger(__name__)


class PromptRegistry:
    """In-memory prompt store. Production: backed by DynamoDB / S3."""

    def __init__(self) -> None:
        self._store: dict[str, PromptTemplate] = {}

    def register(self, template: PromptTemplate) -> None:
        key = f"{template.name}:{template.version}"
        self._store[key] = template
        logger.info("Registered prompt %s", key)

    def get(self, name: str, version: str = "latest") -> PromptTemplate | None:
        if version == "latest":
            matching = [(k, v) for k, v in self._store.items() if k.startswith(f"{name}:")]
            if not matching:
                return None
            return sorted(matching, key=lambda x: x[0])[-1][1]
        return self._store.get(f"{name}:{version}")

    def list_versions(self, name: str) -> list[str]:
        return [k.split(":")[1] for k in self._store if k.startswith(f"{name}:")]

    def load_from_dir(self, directory: str | Path) -> int:
        directory = Path(directory)
        count = 0
        for f in directory.glob("*.json"):
            try:
                data = json.loads(f.read_text())
                self.register(PromptTemplate(**data))
                count += 1
            except Exception as exc:
                logger.warning("Failed to load prompt %s: %s", f, exc)
        return count
