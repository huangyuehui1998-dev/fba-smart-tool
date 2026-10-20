"""日志里的密钥、令牌和手机号写成 ***。"""
from __future__ import annotations

import logging
import re

_SECRET = re.compile(
    r"(?i)(api[_-]?key|mcp[_-]?key|access[_-]?token|refresh[_-]?token|secret|password|authorization)"
    r"(\s*[:=]\s*|\s+)([A-Za-z0-9._~+/=-]{4,})"
)
_BEARER = re.compile(r"(?i)(Bearer\s+)[A-Za-z0-9._~+/=-]{8,}")
_PHONE = re.compile(r"\b1[3-9]\d{9}\b")


def redact_text(text: str) -> str:
    out = _SECRET.sub(lambda m: f"{m.group(1)}{m.group(2)}***", str(text))
    out = _BEARER.sub(r"\1***", out)
    return _PHONE.sub("***", out)


class RedactFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.msg, str):
            record.msg = redact_text(record.msg)
        if isinstance(record.args, dict):
            record.args = {key: redact_text(value) if isinstance(value, str) else value for key, value in record.args.items()}
        elif isinstance(record.args, tuple):
            record.args = tuple(redact_text(value) if isinstance(value, str) else value for value in record.args)
        return True


def install_redacting_logs() -> None:
    filt = RedactFilter()
    root = logging.getLogger()
    if not any(isinstance(item, RedactFilter) for item in root.filters):
        root.addFilter(filt)
    for handler in root.handlers:
        if not any(isinstance(item, RedactFilter) for item in handler.filters):
            handler.addFilter(filt)
    logging.getLogger("fba_tool").addFilter(filt)
