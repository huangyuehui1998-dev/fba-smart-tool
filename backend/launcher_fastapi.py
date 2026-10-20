import multiprocessing
import uvicorn
import os
import sys
import webbrowser
import threading
import time
from pathlib import Path

def _open_browser(url: str, delay: float = 2.0) -> None:
    time.sleep(delay)
    webbrowser.open(url)

if __name__ == '__main__':
    # PyInstaller multi-processing requirement
    multiprocessing.freeze_support()
    
    # Ensure app path is in sys.path
    if getattr(sys, 'frozen', False):
        app_dir = sys._MEIPASS
    else:
        app_dir = os.path.dirname(os.path.abspath(__file__))
    
    if app_dir not in sys.path:
        sys.path.insert(0, app_dir)

    # Change working directory so relative paths (like templates/) work as expected
    if getattr(sys, 'frozen', False):
        os.chdir(os.path.dirname(sys.executable))
    else:
        os.chdir(app_dir)

    try:
        from fba_tool.template_loader import ensure_portable_dirs
        ensure_portable_dirs()
    except Exception as e:
        print(f"Warning: ensure_portable_dirs failed: {e}")
        pass
        
    import socket
    def get_free_port(start_port=8002, max_port=8100):
        for p in range(start_port, max_port):
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                try:
                    s.bind(('127.0.0.1', p))
                    return p
                except OSError:
                    continue
        return start_port

    base_port = int(os.environ.get("FBA_PORT", "8002"))
    port = get_free_port(base_port)
    url = f"http://localhost:{port}"
    
    print(f"=============================================")
    print(f"FBA Smart Tool (FastAPI) Starting on port {port}")
    print(f"Browser will open automatically at {url}")
    print(f"=============================================")
    
    threading.Thread(target=_open_browser, args=(url,), daemon=True).start()
    
    # Import app AFTER sys.path adjustment
    from main import app
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="info")
