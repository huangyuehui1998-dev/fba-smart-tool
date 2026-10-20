# 已归档：旧 Streamlit 版入口（S7，v8 §3.8）

这里是 V1.x 的 Streamlit 界面和它的打包脚本，**不再维护、不再打包**，只留作参考。
现在的程序是 FastAPI 后端 + React 前端：开发用 `一键启动.bat` 或 `python run_app.py`，打包用 `packaging/FBA_Smart_Tool.spec`。

| 文件 | 原位置 | 说明 |
|---|---|---|
| app.py、launcher.py | backend/ | Streamlit 主程序与启动器 |
| fba_tool/settings_ui.py、session_ui.py、product_catalog_ui.py、perf_cache.py | backend/fba_tool/ | 只被 app.py 使用的 Streamlit 页面/缓存 |
| FBAWizard*.spec、build_v1.6/1.8.bat、build_portable_windows.bat | backend/ | 旧版 PyInstaller 打包 |
| run_unix.sh、run_windows.bat | backend/ | 旧版启动脚本（调 launcher.py） |

归档后 requirements 不再含 streamlit；如果确实要跑旧版：另建虚拟环境 `pip install streamlit`，把这些文件放回原位置再运行。
