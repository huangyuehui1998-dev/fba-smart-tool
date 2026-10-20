#!/usr/bin/env python3
"""
FBA Smart Tool 一键启动器（单机版）。产品版本见 fba_tool.app_version.APP_VERSION。

双击或在命令行运行本脚本：
  1. 初始化 app_data/ 业务数据目录
  2. 寻找可用端口并启动 FastAPI（含前端静态页）
  3. 服务就绪后自动打开浏览器
"""
from __future__ import annotations

import os
import socket
import sys
import threading
import time
import urllib.error
import urllib.request
import webbrowser
from pathlib import Path

def _setup_console_utf8() -> None:
    """统一控制台为 UTF-8，确保任意区域设置的电脑都不出现中文乱码。

    - Windows：将控制台输入/输出代码页切到 65001（UTF-8）
    - 所有平台：把 stdout/stderr 重配为 utf-8，遇到不可编码字符用替代符而非崩溃
    """
    if sys.platform == "win32":
        try:
            import ctypes

            kernel32 = ctypes.windll.kernel32
            kernel32.SetConsoleOutputCP(65001)
            kernel32.SetConsoleCP(65001)
        except Exception:
            pass
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]
        except Exception:
            pass


_setup_console_utf8()

if getattr(sys, "frozen", False):
    print("FBA Smart Tool 正在启动，请稍候…", flush=True)


def _resolve_paths() -> tuple[Path, Path]:
    if getattr(sys, "frozen", False):
        meipass = Path(getattr(sys, "_MEIPASS", Path(sys.executable).resolve().parent))
        exe_root = Path(sys.executable).resolve().parent
        return exe_root, meipass
    root = Path(__file__).resolve().parent
    return root, root / "backend"


PROJECT_ROOT, BACKEND_DIR = _resolve_paths()

if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

os.chdir(BACKEND_DIR)

DEFAULT_PORT = 8002
PREFERRED_PORTS = [DEFAULT_PORT, *range(8003, 8012), *range(18002, 18020)]
HOST = "127.0.0.1"
HEALTH_TIMEOUT_SEC = 120
SINGLE_INSTANCE_MUTEX = "Global\\FBA_Smart_Tool_V1"
_INSTANCE_MUTEX_HANDLE = None


def _data_dir() -> Path:
    """S8 D9：和后端 app_paths.app_data_dir() 同一规则——FBA_APP_DATA_DIR 优先，否则 <程序目录>/app_data。"""
    override = os.environ.get("FBA_APP_DATA_DIR", "").strip()
    return Path(override) if override else PROJECT_ROOT / "app_data"


def _no_browser() -> bool:
    """S8 D9：FBA_NO_BROWSER=1（或 true/yes）时不自动打开浏览器（测试 / 远程启动用）。"""
    return os.environ.get("FBA_NO_BROWSER", "").strip().lower() in ("1", "true", "yes", "on")


def _open_url(url: str) -> None:
    if _no_browser():
        print(f"[提示] 已设置 FBA_NO_BROWSER，不自动打开浏览器；请手动访问 {url}")
        return
    webbrowser.open(url)


def _port_file() -> Path:
    return _data_dir() / ".server_port"


def _read_saved_port() -> int | None:
    path = _port_file()
    if not path.is_file():
        return None
    try:
        port = int(path.read_text(encoding="utf-8").strip())
        return port if 1 < port < 65536 else None
    except Exception:
        return None


def _write_saved_port(port: int) -> None:
    path = _port_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(str(port), encoding="utf-8")


def _clear_saved_port() -> None:
    path = _port_file()
    if path.is_file():
        try:
            path.unlink()
        except Exception:
            pass


def _health_ok(port: int) -> bool:
    url = f"http://{HOST}:{port}/api/health"
    try:
        with urllib.request.urlopen(url, timeout=1.5) as resp:
            return resp.status == 200
    except (urllib.error.URLError, TimeoutError, OSError, ValueError):
        return False


def _find_running_port() -> int | None:
    saved = _read_saved_port()
    if saved and _health_ok(saved):
        return saved
    for port in PREFERRED_PORTS:
        if _health_ok(port):
            return port
    return None


def _try_single_instance_redirect() -> bool:
    """若已有实例在跑，打开浏览器并退出。返回 True 表示应直接结束。"""
    global _INSTANCE_MUTEX_HANDLE

    if sys.platform != "win32":
        running = _find_running_port()
        if running:
            url = f"http://{HOST}:{running}/"
            _open_url(url)
            print(f"程序已在运行：{url}")
            return True
        return False

    import ctypes

    kernel32 = ctypes.windll.kernel32
    _INSTANCE_MUTEX_HANDLE = kernel32.CreateMutexW(None, False, SINGLE_INSTANCE_MUTEX)
    already_exists = kernel32.GetLastError() == 183
    if not already_exists:
        return False

    running = _find_running_port()
    if running:
        url = f"http://{HOST}:{running}/"
        _open_url(url)
        print(f"程序已在运行：{url}")
    else:
        print("程序已在运行，请查看先前打开的黑色窗口中的服务地址。")
    return True


def _bind_listen_socket(port: int) -> socket.socket:
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind((HOST, port))
    sock.listen(2048)
    return sock


def _open_browser_when_ready(port: int) -> None:
    url = f"http://{HOST}:{port}/"
    deadline = time.time() + HEALTH_TIMEOUT_SEC
    while time.time() < deadline:
        if _health_ok(port):
            try:
                _open_url(url)
            except Exception as exc:
                print(f"[提示] 无法自动打开浏览器：{exc}\n请手动访问 {url}")
            return
        time.sleep(0.4)
    print(f"[提示] 服务启动较慢，请手动访问 {url}")


def _run_server_with_port_retry(app) -> None:
    from uvicorn import Config, Server

    last_err: Exception | None = None
    for port in PREFERRED_PORTS:
        try:
            sock = _bind_listen_socket(port)
        except OSError as exc:
            last_err = exc
            continue

        _write_saved_port(port)
        url = f"http://{HOST}:{port}/"
        print("=" * 56)
        from fba_tool.app_version import APP_VERSION

        print(f"  FBA Smart Tool {APP_VERSION} — 一键启动")
        print(f"  数据目录: {_data_dir()}")
        print(f"  服务地址: {url}")
        print("  关闭本窗口即停止服务")
        print("=" * 56)
        threading.Thread(target=_open_browser_when_ready, args=(port,), daemon=True).start()
        try:
            config = Config(app, host=HOST, port=port, log_level="info")
            Server(config).run(sockets=[sock])
            return
        except OSError as exc:
            last_err = exc
            winerr = getattr(exc, "winerror", None)
            errno = getattr(exc, "errno", None)
            if winerr == 10048 or errno in (98, 10048):
                print(f"[提示] 端口 {port} 已被占用，尝试下一个…")
                continue
            raise
        finally:
            try:
                sock.close()
            except Exception:
                pass

    if last_err:
        raise RuntimeError(
            "所有候选端口均被占用，请关闭其他 FBA Smart Tool 窗口或占用 8002–8011 的程序后重试。"
        ) from last_err
    raise RuntimeError("未找到可用端口，请关闭占用 8002–8011 的程序后重试。")


def main() -> None:
    if _try_single_instance_redirect():
        return

    from fba_tool.template_loader import ensure_portable_dirs

    ensure_portable_dirs()

    import uvicorn  # noqa: F401
    from main import app

    try:
        _run_server_with_port_retry(app)
    finally:
        _clear_saved_port()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n已退出。")
    except Exception as exc:
        print(f"\n启动失败：{exc}", file=sys.stderr)
        input("按 Enter 键关闭…")
        raise SystemExit(1) from exc


if False:  # pragma: no cover — PyInstaller 静态分析
    import main  # noqa: F401
    import settings  # noqa: F401
    import static_ui  # noqa: F401
