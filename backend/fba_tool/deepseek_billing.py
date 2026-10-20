"""DeepSeek Token 用量累计与 RMB 预估（百万 token 单价）。"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List

# 单位：元 / 百万 tokens
PRICING_RMB_PER_M: Dict[str, Dict[str, float]] = {
    "deepseek-v4-flash": {"input": 1.0, "output": 2.0},
    "deepseek-v4-pro": {"input": 3.0, "output": 6.0},
}

_DEFAULT_PRICING = PRICING_RMB_PER_M["deepseek-v4-flash"]


@dataclass
class UsageEntry:
    model: str
    prompt_tokens: int
    completion_tokens: int


@dataclass
class DeepseekUsageAccumulator:
    entries: List[UsageEntry] = field(default_factory=list)

    def add(self, model: str, prompt_tokens: int, completion_tokens: int) -> None:
        prompt_tokens = max(0, int(prompt_tokens or 0))
        completion_tokens = max(0, int(completion_tokens or 0))
        if prompt_tokens == 0 and completion_tokens == 0:
            return
        self.entries.append(
            UsageEntry(
                model=model,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
            )
        )

    @property
    def total_tokens(self) -> int:
        return sum(e.prompt_tokens + e.completion_tokens for e in self.entries)

    def estimated_cost_rmb(self) -> float:
        cost = 0.0
        for entry in self.entries:
            prices = PRICING_RMB_PER_M.get(entry.model, _DEFAULT_PRICING)
            cost += (entry.prompt_tokens / 1_000_000) * prices["input"]
            cost += (entry.completion_tokens / 1_000_000) * prices["output"]
        return round(cost, 4)
