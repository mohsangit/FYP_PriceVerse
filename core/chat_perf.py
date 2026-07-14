"""Timing and performance helpers for the chatbot pipeline."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class PipelineTiming:
    intent_ms: float = 0.0
    db_ms: float = 0.0
    payload_ms: float = 0.0
    llm_ms: float = 0.0
    total_ms: float = 0.0
    source: str = ""
    cached: bool = False
    phone_count: int = 0

    def as_dict(self) -> dict[str, Any]:
        return {
            "intent_ms": round(self.intent_ms, 1),
            "db_ms": round(self.db_ms, 1),
            "payload_ms": round(self.payload_ms, 1),
            "llm_ms": round(self.llm_ms, 1),
            "total_ms": round(self.total_ms, 1),
            "source": self.source,
            "cached": self.cached,
            "phone_count": self.phone_count,
        }


class StageTimer:
    """Context manager that records elapsed milliseconds into PipelineTiming."""

    def __init__(self, timing: PipelineTiming, attr: str):
        self.timing = timing
        self.attr = attr
        self._start = 0.0

    def __enter__(self):
        self._start = time.perf_counter()
        return self

    def __exit__(self, *args):
        elapsed = (time.perf_counter() - self._start) * 1000
        setattr(self.timing, self.attr, getattr(self.timing, self.attr) + elapsed)


def log_timing(timing: PipelineTiming, intent_kind: str = "") -> None:
    logger.info(
        "chat pipeline intent=%s phones=%d cached=%s source=%s "
        "intent=%.0fms db=%.0fms payload=%.0fms llm=%.0fms total=%.0fms",
        intent_kind,
        timing.phone_count,
        timing.cached,
        timing.source or "-",
        timing.intent_ms,
        timing.db_ms,
        timing.payload_ms,
        timing.llm_ms,
        timing.total_ms,
    )
