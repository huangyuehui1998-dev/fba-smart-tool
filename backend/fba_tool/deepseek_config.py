from __future__ import annotations

import os

DEFAULT_DEEPSEEK_MODEL = "deepseek-v4-flash"
DEFAULT_DEEPSEEK_TEMPERATURE = 0.1
ALLOWED_DEEPSEEK_MODELS = frozenset({"deepseek-v4-flash", "deepseek-v4-pro"})


def resolve_deepseek_options(
    model: str | None = None,
    temperature: float | None = None,
) -> tuple[str, float]:
    resolved_model = (model or os.environ.get("DEEPSEEK_MODEL") or DEFAULT_DEEPSEEK_MODEL).strip()
    if resolved_model not in ALLOWED_DEEPSEEK_MODELS:
        resolved_model = DEFAULT_DEEPSEEK_MODEL

    if temperature is None:
        env_temp = os.environ.get("DEEPSEEK_TEMPERATURE", "")
        try:
            temperature = float(env_temp) if env_temp.strip() else DEFAULT_DEEPSEEK_TEMPERATURE
        except ValueError:
            temperature = DEFAULT_DEEPSEEK_TEMPERATURE

    resolved_temp = max(0.0, min(2.0, float(temperature)))
    return resolved_model, resolved_temp
