"""R12-13：CORS 白名单、日志脱敏 11 个样本、DeepSeek Key 不回传。"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from fba_tool.log_redact import redact_text


SAMPLES = [
    "Authorization: Bearer abc.def.ghi1234",
    '"access_token": "abcd1234efgh"',
    "token=abcdef123456",
    "DEEPSEEK_KEY=sk-1234567890abcdef",
    "sk-1234567890abcdef1234",
    "+8613812345678",
    "138-1234-5678",
    "138 1234 5678",
    "api_key=sk-abcdef123456",
    "x-api-key: zzzz9999yyyy",
    "phone 13812345678",
]

SECRETS = [
    "abc.def.ghi1234",
    "abcd1234efgh",
    "abcdef123456",
    "sk-1234567890abcdef",
    "sk-1234567890abcdef1234",
    "+8613812345678",
    "138-1234-5678",
    "138 1234 5678",
    "sk-abcdef123456",
    "zzzz9999yyyy",
    "13812345678",
]


@pytest.mark.parametrize("sample,secret", list(zip(SAMPLES, SECRETS)))
def test_redact_covers_every_sample(sample, secret):
    out = redact_text(sample)
    assert "***" in out
    assert secret not in out


def test_customs_and_waybill_numbers_stay():
    text = "报关单号 JUS20261020001 运单号 LCL260101001 token=abcdef123456"
    out = redact_text(text)
    assert "JUS20261020001" in out
    assert "LCL260101001" in out
    assert "abcdef123456" not in out


def test_cors_rejects_unlisted_origin():
    from main import app

    client = TestClient(app)
    response = client.get("/api/health", headers={"Origin": "http://localhost:9999"})
    headers = {key.lower(): value for key, value in response.headers.items()}
    assert "access-control-allow-origin" not in headers
    assert "access-control-allow-credentials" not in headers


def test_deepseek_put_is_422_off_windows_and_get_hides_the_key():
    from main import app

    client = TestClient(app)
    secret = "sk-1234567890abcdef1234"
    put = client.put("/api/settings/deepseek-key", json={"key": secret})
    assert put.status_code == 422
    assert secret not in put.text
    got = client.get("/api/settings/deepseek-key")
    assert got.status_code == 200
    assert got.json() == {"status": "未设置"}
    assert secret not in got.text


def test_cors_regex_constant_is_gone():
    from pathlib import Path

    needle = "CORS_ALLOW_" + "ORIGIN_REGEX"
    root = Path(__file__).resolve().parents[2]
    hits = []
    for path in root.rglob("*"):
        if not path.is_file() or path.suffix not in {".py", ".md", ".json", ".ts", ".tsx"}:
            continue
        if "node_modules" in path.parts or ".venv" in path.parts:
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        if needle in text:
            hits.append(str(path))
    assert hits == []
