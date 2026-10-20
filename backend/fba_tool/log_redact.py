"""日志里的密钥、令牌和手机号写成 ***。"""
from __future__ import annotations

import logging
import re

_BEARER = re.compile(r"(?i)(Authorization:\s*Bearer\s+)\S+")
_JSON_SECRET = re.compile(
    r'("(?:access_token|refresh_token|api_key|token|secret|password)"\s*:\s*")[^"]*(")',
    re.IGNORECASE,
)
_ASSIGNED_SECRET = re.compile(r"(?i)\b[\w-]*(?:key|token|secret)\b\s*[:=]\s*\S+")
_SK = re.compile(r"sk-[A-Za-z0-9]{16,}")
_PHONE = re.compile(r"(?:\+?86[- ]?)?1[3-9]\d[- ]?\d{4}[- ]?\d{4}")


def redact_text(text: str) -> str:
    """按固定顺序脱敏。报关单号 JUS 和运单号 LCL 是业务号，不改。"""
    out = _BEARER.sub(r"\1***", str(text))
    out = _JSON_SECRET.sub(r"\1***\2", out)
    out = _ASSIGNED_SECRET.sub("***", out)
    out = _SK.sub("***", out)
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
