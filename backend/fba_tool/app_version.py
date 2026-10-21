"""产品版本号只在这里赋值。

Python 入口（run_app、finish_portable_dist、/api/health）从这里导入。
界面文案、spec 说明和便携版使用说明里的显示字符串由 test_v32_version.py 对照这个值。
FastAPI 的 version="1.2.0" 是 API 文档号，和产品版本无关。
"""
APP_VERSION = "V3.3"
