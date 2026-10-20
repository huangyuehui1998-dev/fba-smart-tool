from __future__ import annotations

import os
import subprocess
import sys
import threading
import time
import traceback
import webbrowser
from pathlib import Path


def _app_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


def _bundled_root() -> Path:
    if getattr(sys, "frozen", False):
        return Path(getattr(sys, "_MEIPASS", _app_dir()))
    return Path(__file__).resolve().parent


def _ensure_streamlit_config(root: Path) -> None:
    import shutil

    dest_dir = root / ".streamlit"
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest_cfg = dest_dir / "config.toml"
    bundled_cfg = _bundled_root() / ".streamlit" / "config.toml"
    if not dest_cfg.exists() and bundled_cfg.exists():
        shutil.copy2(bundled_cfg, dest_cfg)


def _open_browser(url: str, delay: float = 2.0) -> None:
    time.sleep(delay)
    webbrowser.open(url)


def _pause_on_error() -> None:
    if getattr(sys, "frozen", False):
        input("\n按 Enter 键退出...")


def main() -> int:
    root = _app_dir()
    os.chdir(root)
    os.environ.setdefault("STREAMLIT_BROWSER_GATHER_USAGE_STATS", "false")
    os.environ.setdefault("STREAMLIT_SERVER_HEADLESS", "true")
    os.environ["STREAMLIT_GLOBAL_DEVELOPMENT_MODE"] = "false"

    try:
        from fba_tool.template_loader import ensure_portable_dirs

        ensure_portable_dirs()
    except Exception:
        pass

    _ensure_streamlit_config(root)

    app_path = root / "app.py"
    if not app_path.exists() and getattr(sys, "frozen", False):
        app_path = _bundled_root() / "app.py"

    if not app_path.exists():
        print(f"[错误] 未找到 app.py：{app_path}")
        _pause_on_error()
        return 1

    port = os.environ.get("FBA_PORT", "8501")
    url = f"http://localhost:{port}"

    threading.Thread(target=_open_browser, args=(url,), daemon=True).start()

    try:
        if getattr(sys, "frozen", False):
            from streamlit.web import cli as stcli

            sys.argv = [
                "streamlit",
                "run",
                str(app_path),
                f"--server.port={port}",
                "--server.headless=true",
                "--browser.gatherUsageStats=false",
                "--global.developmentMode=false",
            ]
            return stcli.main()

        python = sys.executable
        cmd = [
            python,
            "-m",
            "streamlit",
            "run",
            str(app_path),
            f"--server.port={port}",
            "--server.headless=true",
            "--browser.gatherUsageStats=false",
            "--global.developmentMode=false",
        ]
        return subprocess.call(cmd)
    except Exception as exc:
        print("[启动失败]", exc)
        traceback.print_exc()
        _pause_on_error()
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
