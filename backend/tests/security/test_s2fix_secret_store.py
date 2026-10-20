"""S2-fix 第2项：领星密钥用 DPAPI 加密存储；老文件明文迁移成密文并清掉明文（方案 3.2 验收第 4 条：密钥文件里看不到明文）。

密钥值全是测试用假值，不用真实密钥。
"""
from __future__ import annotations

import json
import sys

import pytest

from fba_tool import secret_store
from fba_tool import lingxing_sync as ls

FAKE_KEY = "TEST-FAKE-KEY-0123456789abcdef"


def _fake_backend():
    xor = lambda b: bytes(x ^ 0x5A for x in b)[::-1]  # noqa: E731  可逆但不是明文
    return (xor, xor)


@pytest.fixture
def cfg(monkeypatch, tmp_path):
    path = tmp_path / "lingxing.json"
    monkeypatch.setattr(ls, "resolve_config_read", lambda name: path)
    monkeypatch.setattr(ls, "resolve_config_write", lambda name: path)
    old = secret_store._backend
    secret_store.set_backend(_fake_backend())
    yield path
    secret_store.set_backend(old)


def test_save_writes_only_ciphertext(cfg):
    ls.save_lingxing_settings(mcp_key=FAKE_KEY, mcp_url="https://example.invalid/mcp")
    text = cfg.read_text(encoding="utf-8")
    assert FAKE_KEY not in text and "mcp_key_enc" in text
    assert '"mcp_key"' not in text
    assert ls.load_lingxing_settings()["mcp_key"] == FAKE_KEY


def test_plaintext_migrated_on_first_read(cfg):
    cfg.write_text(json.dumps({"mcp_key": FAKE_KEY, "mcp_url": "https://example.invalid/mcp"}), encoding="utf-8")
    assert ls.load_lingxing_settings()["mcp_key"] == FAKE_KEY
    data = json.loads(cfg.read_text(encoding="utf-8"))
    assert "mcp_key" not in data and data["mcp_key_enc"].startswith(secret_store.PREFIX)
    assert FAKE_KEY not in cfg.read_text(encoding="utf-8")
    assert ls.load_lingxing_settings()["mcp_key"] == FAKE_KEY  # 迁移后照常读


def test_url_only_update_keeps_key(cfg):
    ls.save_lingxing_settings(mcp_key=FAKE_KEY)
    ls.save_lingxing_settings(mcp_url="https://example.invalid/2")
    s = ls.load_lingxing_settings()
    assert s["mcp_key"] == FAKE_KEY and s["mcp_url"] == "https://example.invalid/2"


def test_no_backend_refuses_plaintext(cfg):
    secret_store.set_backend(None)
    with pytest.raises(secret_store.SecretStoreError):
        ls.save_lingxing_settings(mcp_key=FAKE_KEY)
    assert not cfg.exists() or FAKE_KEY not in cfg.read_text(encoding="utf-8")


def test_corrupt_ciphertext_gives_empty_key(cfg):
    cfg.write_text(json.dumps({"mcp_key_enc": secret_store.PREFIX + "!!!"}), encoding="utf-8")
    secret_store.set_backend((lambda b: b, lambda b: (_ for _ in ()).throw(secret_store.SecretStoreError("x"))))
    assert ls.load_lingxing_settings()["mcp_key"] == ""


@pytest.mark.skipif(not sys.platform.startswith("win"), reason="DPAPI 只在 Windows 上有")
def test_real_dpapi_roundtrip():
    real = secret_store._dpapi()
    secret_store.set_backend(real)
    tok = secret_store.protect(FAKE_KEY)
    assert FAKE_KEY not in tok and secret_store.unprotect(tok) == FAKE_KEY
