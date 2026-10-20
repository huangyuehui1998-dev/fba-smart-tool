"""S2-7: 访问日志里屏蔽 ?token=。"""
import logging

from security import TokenMaskFilter, install_token_log_filter


def _rec(msg, args=()):
    return logging.LogRecord("uvicorn.access", logging.INFO, __file__, 1, msg, args, None)


def test_mask_in_args():
    r = _rec('%s - "%s %s HTTP/%s" %d', ("127.0.0.1:1", "GET", "/api/x?token=abc123&a=1", "1.1", 200))
    assert TokenMaskFilter().filter(r) is True
    out = r.getMessage()
    assert "abc123" not in out and "token=***" in out and "a=1" in out


def test_mask_in_plain_msg_and_case():
    r = _rec("GET /login?TOKEN=Secret-X_1 ok")
    TokenMaskFilter().filter(r)
    assert "Secret-X_1" not in r.getMessage()


def test_no_token_untouched():
    r = _rec("GET /api/health?tokens_count=3")
    TokenMaskFilter().filter(r)
    assert r.getMessage() == "GET /api/health?tokens_count=3"


def test_installed_on_uvicorn_access_idempotent():
    install_token_log_filter()
    install_token_log_filter()
    lg = logging.getLogger("uvicorn.access")
    assert sum(isinstance(f, TokenMaskFilter) for f in lg.filters) == 1
