"""Step 4 校验进度收集（供流式 API 推送）。"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Callable, Iterator, List, Tuple

ProgressFn = Callable[[str, int], None]


@dataclass
class ValidationProgress:
    """收集校验过程中的进度事件，供生成器分批 yield。"""

    events: List[Tuple[str, int]] = field(default_factory=list)

    def report(self, message: str, percent: int) -> None:
        self.events.append((message, max(0, min(100, int(percent)))))

    def drain(self) -> List[Tuple[str, int]]:
        out = list(self.events)
        self.events.clear()
        return out

    def callback(self) -> ProgressFn:
        return self.report


def ndjson_progress(message: str, percent: int) -> str:
    return json.dumps(
        {"event": "progress", "message": message, "percent": percent},
        ensure_ascii=False,
    ) + "\n"


def ndjson_result(data: Any) -> str:
    return json.dumps({"event": "result", "data": data}, ensure_ascii=False) + "\n"


def yield_progress_events(progress: ValidationProgress) -> Iterator[str]:
    for message, percent in progress.drain():
        yield ndjson_progress(message, percent)
