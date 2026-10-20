"""产品版本号（界面顶栏、/api/health、打包 zip 名都用这个口径）。

FastAPI 的 version="1.2.0" 是 API 文档号，和产品版本无关。发布改版本时同时改：
frontend/src/components/app-header.tsx、scripts/finish_portable_dist.py 的 RELEASE_VERSION、
packaging/使用说明.txt、run_app.py、packaging/FBA_Smart_Tool.spec（backend/test_v32_version.py 会核对）。
"""
APP_VERSION = "V3.2"
