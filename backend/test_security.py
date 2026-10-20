"""S1d：默认只监听本机 + 可选访问口令。"""
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import security


def _app(monkeypatch, token=None):
    if token is None:
        monkeypatch.delenv("FBA_ACCESS_TOKEN", raising=False)
    else:
        monkeypatch.setenv("FBA_ACCESS_TOKEN", token)
    app = FastAPI()
    security.install_access_control(app)

    @app.get("/api/health")
    def health():
        return {"ok": True}

    @app.get("/api/data")
    def data():
        return {"d": 1}

    @app.post("/api/data")
    def post():
        return {"p": 1}

    @app.get("/")
    def index():
        return {"index": 1}

    return TestClient(app)


def test_default_host_is_loopback(monkeypatch):
    monkeypatch.delenv("FBA_HOST", raising=False)
    assert security.bind_host() == "127.0.0.1"


def test_main_does_not_bind_all_interfaces():
    src = open("main.py", encoding="utf-8").read()
    assert "0.0.0.0" not in src


@pytest.mark.parametrize("host", ["127.0.0.1", "localhost", "::1"])
def test_loopback_without_token_ok(host):
    security.check_bind_safety(host, None)


@pytest.mark.parametrize("host", ["0.0.0.0", "192.168.1.5", "::"])
def test_remote_without_token_refused(host):
    with pytest.raises(RuntimeError):
        security.check_bind_safety(host, None)
    with pytest.raises(RuntimeError):
        security.check_bind_safety(host, "  ")


def test_remote_with_token_ok():
    security.check_bind_safety("0.0.0.0", "secret123")


def test_no_token_everything_open(monkeypatch):
    c = _app(monkeypatch)
    assert c.get("/api/data").status_code == 200
    assert c.post("/api/data").status_code == 200


def test_token_blocks_api_without_credentials(monkeypatch):
    c = _app(monkeypatch, "secret123")
    assert c.get("/api/data").status_code == 401
    assert c.post("/api/data").status_code == 401
    r = c.post("/api/data", headers={"X-Access-Token": "wrong"})
    assert r.status_code == 401
    assert "message" in r.json()["detail"]


def test_token_exempt_paths(monkeypatch):
    c = _app(monkeypatch, "secret123")
    assert c.get("/api/health").status_code == 200
    assert c.get("/").status_code == 200


def test_token_header_works(monkeypatch):
    c = _app(monkeypatch, "secret123")
    h = {"X-Access-Token": "secret123"}
    assert c.get("/api/data", headers=h).status_code == 200
    assert c.post("/api/data", headers=h).status_code == 200


def test_login_sets_cookie(monkeypatch):
    c = _app(monkeypatch, "secret123")
    r = c.post("/api/auth/login", json={"token": "bad"})
    assert r.status_code == 401
    r = c.post("/api/auth/login", json={"token": "secret123"})
    assert r.status_code == 200
    assert security.COOKIE_NAME in r.cookies or security.COOKIE_NAME in c.cookies
    assert c.post("/api/data").status_code == 200


def test_login_get_redirects(monkeypatch):
    c = _app(monkeypatch, "secret123")
    r = c.get("/api/auth/login", params={"token": "secret123"}, follow_redirects=False)
    assert r.status_code in (302, 303, 307)
    assert c.get("/api/data").status_code == 200


def test_login_form_post_redirects_and_sets_cookie(monkeypatch):
    c = _app(monkeypatch, "secret123")
    r = c.post("/api/auth/login", data={"token": "secret123"}, follow_redirects=False)
    assert r.status_code == 303
    assert c.get("/api/data").status_code == 200


def test_login_form_post_wrong_token(monkeypatch):
    c = _app(monkeypatch, "secret123")
    r = c.post("/api/auth/login", data={"token": "bad"}, follow_redirects=False)
    assert r.status_code == 401


def test_login_page_without_token_shows_post_form(monkeypatch):
    c = _app(monkeypatch, "secret123")
    r = c.get("/api/auth/login")
    assert r.status_code == 200
    assert 'method="post"' in r.text and 'type="password"' in r.text
    assert "secret123" not in r.text


def test_security_doc_warns_url_token_logged():
    import security as s
    assert "日志" in s.__doc__ and "POST" in s.__doc__
